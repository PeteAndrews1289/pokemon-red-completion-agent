from types import SimpleNamespace as N

import pytest
from test_red_player_story_battle import setup as battle_setup

from pokemon_red_completion import red_player_bill as b
from pokemon_red_completion.goal_manager import GoalDecisionOutcome


def flags(*events):
    value = bytearray(256)
    for event in events:
        value[int(event) // 8] |= 1 << (int(event) % 8)
    return bytes(value)


def fixture(monkeypatch, name, *, fault=None):
    rt, actions, route, raw, lesson, _, _, _, _ = battle_setup(monkeypatch)
    raw.map_id, raw.player_y, raw.player_x = 88, 7, 2
    prior = []
    if name in {"separator", "ticket"}:
        prior.append(b.EventFlag.BILL_SAID_USE_CELL_SEPARATOR)
    if name == "ticket":
        prior.extend(
            (b.EventFlag.USED_CELL_SEPARATOR_ON_BILL, b.EventFlag.MET_BILL, b.EventFlag.MET_BILL_2)
        )
    raw.event_flags = flags(*prior)
    if fault == "full":
        raw.bag_items = tuple((i, 1) for i in range(1, 21))
    target = N(sprite_index=1 if name == "request" else 2, picture_id=5, at=(4, 4))
    rt.reader.read_current_map_objects = lambda: (target,)
    objective = N(id="help_bill", completion_facts=frozenset({"item:ss_ticket"}))
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    rt.adapter.graph.objective = lambda _: objective
    rt.observer.latch_verified_facts = lambda _: lesson["completed_objectives"].append("help_bill")
    from copy import copy

    initial = copy(raw)
    reads = [0]

    def snapshot(_):
        reads[0] += 1
        return N(raw=initial if reads[0] == 1 else raw, game_state=object()), {
            "completed_objectives": list(lesson["completed_objectives"])
        }

    monkeypatch.setattr(b, "capture_player_lesson_snapshot", snapshot)
    monkeypatch.setattr(b, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(b, "_field_ready", lambda _: True)
    monkeypatch.setattr(b, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: object()))
    monkeypatch.setattr(b, "Gen1TrainerSightProjector", lambda *a, **k: object())
    monkeypatch.setattr(
        b, "map_object_events", lambda *a: (N(object_index=target.sprite_index, sprite_id=5),)
    )
    monkeypatch.setattr(b, "face_pc_boundary", lambda *a: None)
    def plan(*a, **k):
        if name == "separator":
            # Hidden-event coordinates describe the PC, not a walkable player tile.
            assert k["goal_at"] == (5, 1)
        return N(terminal_at=k["goal_at"], cost=12)

    monkeypatch.setattr(
        type(route),
        "route_world",
        property(
            lambda _: N(plan_feasible_to_map=plan)
        ),
    )
    inputs = []

    def act(action):
        inputs.append(action)
        actions.actions_executed += 1
        if fault == "event":
            return
        done = {
            "request": b.EventFlag.BILL_SAID_USE_CELL_SEPARATOR,
            "separator": b.EventFlag.MET_BILL_2,
            "ticket": b.EventFlag.GOT_SS_TICKET,
        }[name]
        raw.event_flags = flags(*prior, done)
        if name == "separator":
            raw.event_flags = flags(
                *prior, done, b.EventFlag.USED_CELL_SEPARATOR_ON_BILL, b.EventFlag.MET_BILL
            )
        if name == "ticket" and fault != "item":
            raw.bag_items = (*initial.bag_items, (int(b.ItemId.SS_TICKET), 1))
        if fault == "cash":
            raw.player_money -= 1

    actions.execute = act
    binding = b.bill_interaction_binding(rt, actions, route=route)
    return rt, binding, inputs, lesson


@pytest.mark.parametrize("name", ["request", "separator", "ticket"])
def test_each_bill_phase_is_bounded_and_only_ticket_completes_objective(monkeypatch, name):
    rt, binding, inputs, lesson = fixture(monkeypatch, name)
    assert not inputs
    report = binding.execute()
    assert report.evidence["objective_completed"] is (name == "ticket")
    assert ("help_bill" in lesson["completed_objectives"]) is (name == "ticket")
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


@pytest.mark.parametrize("fault", ["event", "item", "cash"])
def test_bill_rejects_missing_proof_or_unexpected_resources(monkeypatch, fault):
    _, binding, _, lesson = fixture(monkeypatch, "ticket", fault=fault)
    with pytest.raises(RuntimeError, match="not verified"):
        binding.execute()
    assert "help_bill" not in lesson["completed_objectives"]


def test_full_bag_does_not_offer_ticket(monkeypatch):
    _, binding, inputs, _ = fixture(monkeypatch, "ticket", fault="full")
    assert binding is None and not inputs


def test_bill_stale_binding_never_acts(monkeypatch):
    rt, binding, inputs, _ = fixture(monkeypatch, "request")
    rt.emulator.save_state_bytes = lambda: b"changed"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert not inputs
