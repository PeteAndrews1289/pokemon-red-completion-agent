from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_story_battle import actor

from pokemon_red_completion import red_silph_continuation as phase
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_story_battle import (
    FrozenStoryBattleController,
    StoryTrainerContract,
)


@pytest.mark.parametrize("blocked", [False, True])
def test_boss_approach_replans_and_requires_arrival(monkeypatch, blocked):
    from dataclasses import dataclass

    from pokemon_red_completion.red_training_ground_route import RedVermilionGroundTransition

    calls = []
    raw = NS(party_pp=((10, 0, 0, 0),), party_moves=((33, 0, 0, 0),))

    @dataclass
    class Transition:
        destination_map: int = 0
        destination_at: tuple = ()
        full_event_offsets: bool = False
        observe_terrain: bool = False

        def __call__(self, *args):
            assert self.destination_map == 235 and self.destination_at == (14, 7)
            assert self.full_event_offsets and self.observe_terrain
            calls.append("replan")
            if blocked:
                raise ValueError("no observed route")

    monkeypatch.setattr(RedVermilionGroundTransition, "from_rom", lambda rom: Transition())
    monkeypatch.setattr(phase.route, "_require", lambda *a: calls.append("arrival"))
    for name in ("_move", "_interact", "_confirm_many", "_require_event", "_await_trainer_battle"):
        monkeypatch.setattr(phase.route, name, lambda *a, name=name: calls.append(name))
    args = ("giovanni", NS(), NS(read=lambda: raw), NS(), phase.route.DEFAULT_SILPH_TIMING, b"rom")
    if blocked:
        with pytest.raises(ValueError, match="no observed route"):
            phase._approach(*args)
        assert calls == ["replan"]
    else:
        phase._approach(*args)
        assert calls[:2] == ["replan", "arrival"]
        assert calls.index("_require_event") < calls.index("_await_trainer_battle")


@pytest.mark.parametrize("starter,number", [(177, 7), (153, 8), (176, 9)])
def test_rival_contract_uses_persistent_starter_and_cartridge_quote(monkeypatch, starter, number):
    monkeypatch.setattr(phase, "verify_rom_bytes", lambda _: None)
    seen = []

    def quote(rom, opponent, n):
        seen.append((opponent, n))
        return NS(expected_victory_money=3960)

    monkeypatch.setattr(phase, "trainer_party_quote", quote)
    contract = phase.silph_continuation_contract(
        b"rom", NS(event_flags=bytes(256)), "rival", rival_starter=starter
    )
    assert contract.trainer_identity == (242, 42, number)
    assert contract.defeated_event == 0x740 and contract.victory_money == 3960
    assert seen == [(242, number)]


@pytest.mark.parametrize("starter", [None, 0, True, 999])
def test_unknown_rival_selector_refuses(monkeypatch, starter):
    monkeypatch.setattr(phase, "verify_rom_bytes", lambda _: None)
    with pytest.raises(ValueError):
        phase.silph_continuation_contract(
            b"rom", NS(event_flags=bytes(256)), "rival", rival_starter=starter
        )


@pytest.mark.parametrize("identity", [(229, 2), (229, 1), (230, 2), None])
def test_giovanni_requires_exact_cartridge_object(monkeypatch, identity):
    monkeypatch.setattr(phase, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        phase,
        "map_object_events",
        lambda *a: (
            ()
            if identity is None
            else (NS(object_index=3, trainer_class=identity[0], trainer_set=identity[1]),)
        ),
    )
    monkeypatch.setattr(phase, "trainer_party_quote", lambda *a: NS(expected_victory_money=4059))

    def call():
        return phase.silph_continuation_contract(b"rom", NS(event_flags=bytes(256)), "giovanni")

    if identity == (229, 2):
        assert call().trainer_identity == (229, 29, 2)
    else:
        with pytest.raises(ValueError):
            call()


@pytest.mark.parametrize(
    "fault", [None, "lost", "unresolved", "scope", "prerequisite", "cash", "bag"]
)
def test_continuation_preserves_scope_resources_and_loss(monkeypatch, tmp_path, fault):
    events = bytearray(256)
    events[0x784 // 8] |= 1 << (0x784 % 8)
    raw = RawGameState(
        True,
        235,
        12,
        3,
        2,
        0,
        party_hp=(30, 40),
        party_pp=((25, 0, 0, 0),) * 2,
        party_moves=((44, 0, 0, 0),) * 2,
        party_species_ids=(28, 64),
        player_money=1000,
        bag_items=((48, 1),),
        event_flags=bytes(events),
    )
    state = [raw]
    calls = []
    reader = NS(
        read=lambda: state[0],
        read_input_readiness=lambda: NS(ready=True),
        read_bottom_dialogue_box_visible=lambda: False,
        read_pokedex_state=lambda: NS(owned_species={1}),
    )
    emulator = NS(pressed_buttons=frozenset())
    c = StoryTrainerContract("liberate_silph", "boss", 235, (229, 29, 2), 0x78F, 4059)
    controller = FrozenStoryBattleController(actor(tmp_path), (c,))
    monkeypatch.setattr(phase, "silph_continuation_contract", lambda *a, **k: c)

    def approach(*a):
        calls.append("route")
        state[0] = replace(
            state[0],
            battle_state=2,
            player_money=0 if fault == "cash" else 1000,
            bag_items=() if fault == "bag" else raw.bag_items,
        )

    monkeypatch.setattr(phase, "_approach", approach)

    def run(*a, **k):
        calls.append("model")
        state[0] = replace(state[0], battle_state=0)
        return NS(
            outcome=fault if fault in {"lost", "unresolved"} else "won",
            field_ready=fault != "unresolved",
            final_state=state[0],
            public_dict=lambda: {},
        )

    controller.run = run
    if fault == "scope":
        controller.contracts = (replace(c, victory_money=1),)
    if fault == "prerequisite":
        state[0] = replace(raw, event_flags=bytes(256))

    def execute():
        return phase.run_learned_silph_continuation(
            emulator,
            reader,
            NS(execute=lambda _: None),
            rom=b"rom",
            phase="giovanni",
            controller=controller,
            record=lambda *a: None,
        )

    if fault in {"scope", "prerequisite", "cash", "bag"}:
        with pytest.raises((ValueError, RuntimeError)):
            execute()
        assert "model" not in calls
    else:
        assert execute()["status"] == (fault or "complete")
        assert calls == ["route", "model"]


@pytest.mark.parametrize(
    "fault", [None, "missing_stock", "low_cash", "unhealed", "wrong_item_delta"]
)
def test_recovered_rival_item_support_is_explicit_and_exact(monkeypatch, tmp_path, fault):
    events = bytearray(256)
    events[0x709 // 8] |= 1 << (0x709 % 8)
    raw = RawGameState(
        True,
        182,
        3,
        3,
        1,
        0,
        party_hp=(100,),
        party_pp=((25, 0, 0, 0),),
        party_moves=((44, 0, 0, 0),),
        party_species_ids=(28,),
        player_money=3812,
        bag_items=((48, 1), (46, 2), (int(phase.ItemId.X_SPECIAL), 1)),
        event_flags=bytes(events),
    )
    if fault == "missing_stock":
        raw = replace(raw, bag_items=((48, 1),))
    if fault == "low_cash":
        raw = replace(raw, player_money=1906)
    state = [raw]
    calls = []
    records = []
    reader = NS(
        read=lambda: state[0],
        read_rival_starter=lambda: 153,
        read_input_readiness=lambda: NS(ready=True),
        read_bottom_dialogue_box_visible=lambda: False,
        read_pokedex_state=lambda: NS(owned_species={9}),
        read_active_trainer_identity=lambda: (242, 42, 8),
    )
    c = StoryTrainerContract("liberate_silph", "rival", 212, (242, 42, 8), 0x740, 4455)
    controller = FrozenStoryBattleController(actor(tmp_path), (c,))
    monkeypatch.setattr(phase, "silph_continuation_contract", lambda *a, **k: c)
    monkeypatch.setattr(phase, "_raw_party_fully_restored", lambda _: fault != "unhealed")

    def approach(which, *a):
        assert which == "rival-center"
        calls.append("route")
        state[0] = replace(state[0], map_id=212, battle_state=2)

    monkeypatch.setattr(phase, "_approach", approach)
    monkeypatch.setattr(phase, "advance_battle_to_policy_boundary", lambda *a, **k: None)

    def special(*a):
        calls.append("special")
        state[0] = replace(state[0], bag_items=((48, 1), (46, 2)), party_hp=(95,))

    def accuracy(*a):
        calls.append("accuracy")
        state[0] = replace(
            state[0], bag_items=((48, 1), (46, 2 if fault == "wrong_item_delta" else 1))
        )

    monkeypatch.setattr(phase.route, "_battle_x_special", special)
    monkeypatch.setattr(phase, "_battle_x_accuracy", accuracy)

    def run(*a, **k):
        calls.append("model")
        return NS(outcome="lost", field_ready=True, public_dict=lambda: {})

    controller.run = run

    def execute():
        return phase.run_learned_silph_continuation(
            NS(pressed_buttons=frozenset()),
            reader,
            NS(execute=lambda _: None),
            rom=b"rom",
            phase="rival",
            controller=controller,
            record=lambda *a: records.append(a),
            rival_from_center=True,
            opening_item_support=True,
        )

    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            execute()
        assert "model" not in calls
    else:
        assert execute()["status"] == "lost"
        assert calls == ["route", "special", "accuracy", "model"]
        assert records[1][0] == "opening-item-support"
