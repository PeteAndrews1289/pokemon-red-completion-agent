from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.observation import CurrentMapObject, ItemId, RawGameState
from pokemon_red_completion.red_one_off_capture import OneOffCaptureBudget, OneOffCaptureRequest
from pokemon_red_completion.red_static_capture import RedStaticCaptureTarget
from pokemon_red_completion.red_static_capture_runtime import execute_static_capture

TARGET = RedStaticCaptureTarget(145, 75, 50, 83, 9, 9, (9, 4), 1129)
REQUEST = OneOffCaptureRequest(75, 50, ItemId.GREAT_BALL)


class World:
    def __init__(self, fault=None):
        self.raw = RawGameState(
            True,
            83,
            4,
            10,
            1,
            0,
            player_money=100,
            party_hp=(100,),
            party_pp=((10, 0, 0, 0),),
            party_species_ids=(28,),
            bag_items=((3, 20),),
            event_flags=bytes(320),
        )
        self.dex = NS(owned_species=frozenset({9}), seen_species=frozenset({9}))
        self.objects = (CurrentMapObject(9, 9, (9, 4), 0, 0),)
        self.calls = []
        self.fault = fault
        self.boxes = NS(current_box_index=0, boxes=(NS(species_ids=()),))

    def read(self):
        return self.raw

    def read_pokedex_state(self):
        return self.dex

    def read_all_box_states(self):
        return self.boxes

    def read_current_map_objects(self):
        return self.objects

    def read_pc_items(self):
        return ()

    def read_input_readiness(self):
        return NS(ready=True)

    def read_bottom_dialogue_box_visible(self):
        return False

    def read_player_facing(self):
        return "up"

    def read_wild_capture_identity(self):
        return NS(original_species_id=75)

    def pulse(self, *args, **kwargs):
        self.calls.append(args[1])
        if len(self.calls) == 1:
            self.raw = replace(self.raw, battle_state=1, enemy_hp=150, enemy_level=50)
            self.dex.seen_species |= {145}
            if self.fault == "owned":
                self.dex.owned_species |= {145}
            if self.fault == "seen":
                self.dex.seen_species |= {150}
            if self.fault == "pp":
                self.raw = replace(self.raw, party_pp=((9, 0, 0, 0),))
            if self.fault == "hp":
                self.raw = replace(self.raw, party_hp=(99,))
            if self.fault == "trainer":
                self.raw = replace(self.raw, battle_state=2)
        elif self.raw.battle_state == 0 and self.fault != "event":
            flags = bytearray(self.raw.event_flags)
            flags[1129 // 8] |= 1 << (1129 % 8)
            self.raw = replace(self.raw, event_flags=bytes(flags))
            self.objects = () if self.fault != "object" else self.objects
            if self.fault == "settle_money":
                self.raw = replace(self.raw, player_money=0)


def setup(monkeypatch, fault=None):
    import pokemon_red_completion.red_static_capture_runtime as module
    import pokemon_red_completion.surge as surge

    w = World(fault)
    # Each observation is a fresh immutable snapshot, not an aliased live object.
    w.read_pokedex_state = lambda: NS(**vars(w.dex))
    monkeypatch.setattr(module, "red_static_capture_targets", lambda _: (TARGET,))
    monkeypatch.setattr(module, "advance_battle_to_policy_boundary", lambda *_a, **_k: None)
    monkeypatch.setattr(surge, "_pulse", w.pulse)

    def capture(*args, budget, **kwargs):
        budget.throws_committed += 1
        w.raw = replace(
            w.raw,
            battle_state=0,
            bag_items=((3, 19),),
            party_species_ids=(28, 75),
            party_hp=(100, 150),
            party_pp=((10, 0, 0, 0), (15, 25, 0, 0)),
        )
        w.dex.owned_species |= {145}
        return True

    monkeypatch.setattr(module, "run_one_off_capture", capture)
    return w


def run(w, budget=None, target=TARGET, **kwargs):
    return execute_static_capture(
        w,
        w,
        w,
        target,
        REQUEST,
        rom=b"rom",
        budget=budget or OneOffCaptureBudget(REQUEST, 20, 20),
        **kwargs,
    )


def test_native_seen_bit_and_consumed_object_settlement(monkeypatch):
    w = setup(monkeypatch)
    result = run(w)
    assert result.captured and result.consumed_event and result.source_removed
    assert result.throws_committed == 1 and len(w.calls) == 2


def test_explicit_one_time_weakening_can_reduce_target_hp(monkeypatch):
    w = setup(monkeypatch)

    def prepare():
        w.raw = replace(w.raw, enemy_hp=80)

    assert run(w, prepare_encounter=prepare).captured


@pytest.mark.parametrize(
    "fault", ["ko", "heal", "map", "money", "bag", "target", "owned", "prethrow"]
)
def test_initial_preparation_drift_stops_before_ball(monkeypatch, fault):
    w = setup(monkeypatch)
    budget = OneOffCaptureBudget(REQUEST, 20, 20)

    def prepare():
        updates = {
            "ko": dict(enemy_hp=0),
            "heal": dict(enemy_hp=151),
            "map": dict(map_id=41),
            "money": dict(player_money=0),
            "bag": dict(bag_items=((3, 19),)),
        }.get(fault, {})
        w.raw = replace(w.raw, **updates)
        if fault == "target":
            w.read_wild_capture_identity = lambda: NS(original_species_id=74)
        if fault == "owned":
            w.dex.owned_species |= {145}
        if fault == "prethrow":
            budget.throws_committed = 1

    with pytest.raises(RuntimeError, match="initial preparation"):
        run(w, budget, prepare_encounter=prepare)
    assert len(w.calls) == 1


@pytest.mark.parametrize("fault", ["owned", "seen", "pp", "hp", "trainer"])
def test_introduction_rejects_unrelated_drift(monkeypatch, fault):
    w = setup(monkeypatch, fault)
    with pytest.raises(RuntimeError):
        run(w)
    assert len(w.calls) == 1


@pytest.mark.parametrize("fault", ["event", "object", "settle_money"])
def test_capture_alone_not_source_lifecycle_proof(monkeypatch, fault):
    w = setup(monkeypatch, fault)
    with pytest.raises(RuntimeError):
        run(w)
    assert len(w.calls) <= 49


@pytest.mark.parametrize("fault", ["spent", "ball_count", "cartridge"])
def test_bad_allocation_or_target_zero_inputs(monkeypatch, fault):
    w = setup(monkeypatch)
    budget = OneOffCaptureBudget(REQUEST, 20, 20, 1 if fault == "spent" else 0)
    if fault == "ball_count":
        budget.initial_ball_count = 21
    target = replace(TARGET, at=(8, 4)) if fault == "cartridge" else TARGET
    with pytest.raises(ValueError):
        run(w, budget, target)
    assert not w.calls
