"""Cold checkpoint recovery must not turn into general dialogue authority."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_gen1_route_runtime import FakeReader, raw

from pokemon_red_completion import red_player_forced_motion as s
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import EventFlag, MapId


def setup(monkeypatch, fault=None):
    flags = bytearray(320)
    event = int(EventFlag.IN_PURIFIED_ZONE)
    flags[event // 8] |= 1 << (event % 8)
    initial = replace(raw(), map_id=MapId.POKEMON_TOWER_5F, player_y=9, player_x=10,
        party_hp=(100,), party_max_hp=(100,), party_species_ids=(28,),
        party_levels=(38,), party_status=(0,), party_moves=((33, 0, 0, 0),),
        party_pp=((106, 0, 0, 0),), event_flags=bytes(flags), player_money=9605)
    fake = FakeReader(initial, ready=False, dialogue_visible=True, moving_direction=4)
    fake.read_all_box_states = fake.read_pokedex_state = fake.read_pc_items = lambda: ()
    em = N(frame_count=0, pressed_buttons=(), payload=b"exact-earned-tail")
    em.save_state_bytes = lambda: em.payload
    rt, actions, calls = N(reader=fake, emulator=em), N(actions_executed=0), []
    custody = ["individual", 12345, (), (), ()]
    monkeypatch.setattr(s, "_field_ready", lambda _: fake.ready and not fake.dialogue_visible)
    monkeypatch.setattr(s, "capture_player_lesson_snapshot", lambda _: (None, {"goals": ()}))
    monkeypatch.setattr(s, "_purified_message_custody", lambda _: deepcopy(custody))

    def execute(action):
        assert action.kind in {MacroActionKind.CANCEL, MacroActionKind.WAIT}
        calls.append(action.kind)
        actions.actions_executed += 1
        em.frame_count += 24
        em.payload = b"native-dismissal"
        if action.kind is MacroActionKind.CANCEL and fault != "stuck":
            fake.ready, fake.dialogue_visible, fake.moving_direction = True, False, 0
            change = {
                "cash": dict(player_money=9604), "bag": dict(bag_items=((1, 1),)),
                "hp": dict(party_hp=(99,)), "pp": dict(party_pp=((105, 0, 0, 0),)),
                "event": dict(event_flags=bytes(320)), "move": dict(party_moves=((1, 0, 0, 0),)),
                "level": dict(party_levels=(39,)), "stats": dict(party_stats=((1, 2, 3, 4),)),
                "relocation": dict(player_y=8), "battle": dict(battle_state=2),
            }.get(fault, {})
            fake.raw = replace(fake.raw, **change)
            if fault in {"identity", "xp", "boxes", "dex", "pc"}:
                custody[{"identity": 0, "xp": 1, "boxes": 2, "dex": 3, "pc": 4}[fault]] = "changed"
    actions.execute = execute
    return rt, actions, calls, fake, em


def test_already_healed_message_uses_existing_bounded_support_then_returns_control(monkeypatch):
    rt, actions, calls, fake, em = setup(monkeypatch)
    original = fake.raw
    binding = s.interrupted_motion_binding(rt, actions, rom=b"unused")
    assert not calls and binding.binding_ref.startswith("pokemon.red:retained-motion:")
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    report = binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert calls == [MacroActionKind.CANCEL, MacroActionKind.WAIT]
    assert fake.raw == original and report.actions_executed == 2 and report.frames_executed == 48
    assert report.evidence["individual_xp_box_dex_custody_verified"]
    assert report.evidence["model_queries"] == report.evidence["directional_inputs"] == 0
    assert not report.evidence["healing_performed_by_handler"]
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()
    em.payload = b"later"
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("fault", ["map", "cell", "event", "missing_event", "hp",
    "status", "pp", "moves", "count", "trainer", "battle", "held", "ready", "no_text"])
def test_quote_rejects_unproven_boundary_without_controller_input(monkeypatch, fault):
    rt, actions, calls, fake, em = setup(monkeypatch)
    change = {"map": dict(map_id=MapId.ROUTE_1), "cell": dict(player_y=7),
        "event": dict(event_flags=bytes(320)), "missing_event": dict(event_flags=None),
        "hp": dict(party_hp=(99,)), "status": dict(party_status=(8,)),
        "pp": dict(party_pp=((105, 0, 0, 0),)), "moves": dict(party_moves=()),
        "count": dict(party_count=2), "battle": dict(battle_state=1)}.get(fault, {})
    fake.raw = replace(fake.raw, **change)
    fake.trainer_engagement = fault == "trainer"
    if fault == "held":
        em.pressed_buttons = ("a",)
    if fault == "ready":
        fake.ready, fake.dialogue_visible = True, False
    if fault == "no_text":
        fake.dialogue_visible = False
    assert s.interrupted_motion_binding(rt, actions, rom=b"unused") is None
    assert not calls and not em.frame_count


@pytest.mark.parametrize("fault", ["cash", "bag", "hp", "pp", "event", "move", "level",
    "stats", "relocation", "battle", "identity", "xp", "boxes", "dex", "pc", "stuck"])
def test_settlement_preserves_full_state_custody_and_finite_input_bound(monkeypatch, fault):
    rt, actions, calls, _, _ = setup(monkeypatch, fault)
    binding = s.interrupted_motion_binding(rt, actions, rom=b"unused")
    with pytest.raises(RuntimeError):
        binding.execute()
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    assert len(calls) <= 65


def test_stale_healed_message_sends_no_input(monkeypatch):
    rt, actions, calls, _, em = setup(monkeypatch)
    binding = s.interrupted_motion_binding(rt, actions, rom=b"unused")
    em.payload = b"changed"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert not calls
