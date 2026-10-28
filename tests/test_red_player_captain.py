from copy import copy
from types import SimpleNamespace as N

import pytest
from test_red_player_bill import flags
from test_red_player_story_battle import setup

from pokemon_red_completion import red_player_captain as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome


def fixture(monkeypatch, fault=None):
    rt, actions, route, raw, lesson, *_ = setup(monkeypatch)
    raw.map_id, raw.party_status, raw.event_flags = 101, (0,), flags()
    if fault == "full":
        raw.bag_items = tuple((i, 1) for i in range(1, 21))
    initial = copy(raw)
    target = N(sprite_index=1, picture_id=46, at=(2, 4))
    rt.reader.read_current_map_objects = lambda: (target,)
    rt.reader.read_ss_anne_rival_script = lambda: 0 if fault == "rival" else 4
    rt.adapter.graph.available_objectives = lambda _: (N(id="obtain_cut"),)
    rt.adapter.graph.objective = lambda _: N(completion_facts={"item:hm01"})
    rt.observer.latch_verified_facts = lambda _: lesson["completed_objectives"].append("obtain_cut")
    reads = [0]

    def snapshot(_):
        reads[0] += 1
        return N(raw=initial if reads[0] == 1 else raw, game_state=object()), {
            "completed_objectives": list(lesson["completed_objectives"])
        }

    monkeypatch.setattr(s, "capture_player_lesson_snapshot", snapshot)
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: object()))
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **k: object())
    monkeypatch.setattr(
        s,
        "map_object_events",
        lambda *a: (N(object_index=1, sprite_id=46, movement=255, y=2, x=4),),
    )
    monkeypatch.setattr(s, "face_pc_boundary", lambda *a: None)
    inputs = []

    def act(action):
        inputs.append(action)
        actions.actions_executed += 1
        if fault != "events":
            raw.event_flags = flags(s.EventFlag.RUBBED_CAPTAINS_BACK, s.EventFlag.GOT_HM01)
        if fault != "item":
            raw.bag_items = (*initial.bag_items, (int(s.ItemId.HM01_CUT), 1))
        if fault == "cash":
            raw.player_money -= 1
        if fault == "battle":
            raw.battle_state = 2

    actions.execute = act
    binding = s.captain_interaction_binding(rt, actions, route=route)
    return rt, binding, inputs, lesson


def test_captain_requires_native_reward_and_rejects_reuse(monkeypatch):
    rt, binding, inputs, lesson = fixture(monkeypatch)
    assert not inputs
    report = binding.execute()
    assert report.evidence["objective_completed"] and "obtain_cut" in lesson["completed_objectives"]
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


@pytest.mark.parametrize("fault", ["events", "item", "cash", "battle"])
def test_captain_does_not_credit_false_or_unowned_reward(monkeypatch, fault):
    _, binding, _, lesson = fixture(monkeypatch, fault)
    with pytest.raises((RuntimeError, ValueError)):
        binding.execute()
    assert "obtain_cut" not in lesson["completed_objectives"]


@pytest.mark.parametrize("fault", ["full", "rival"])
def test_captain_prerequisites_are_checked_without_input(monkeypatch, fault):
    _, binding, inputs, _ = fixture(monkeypatch, fault)
    assert binding is None and not inputs


def test_stale_captain_refuses_without_input(monkeypatch):
    rt, binding, inputs, _ = fixture(monkeypatch)
    rt.emulator.save_state_bytes = lambda: b"changed"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert not inputs
