from copy import deepcopy
from types import SimpleNamespace as N

import pytest
from test_red_player_field_goals import setup

from pokemon_red_completion import red_player_field_goals as f
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification


def fixture(monkeypatch):
    rt, actions, route, story, lesson, calls = setup(monkeypatch)

    def observer(reader, *, capability_projector):
        assert capability_projector is f.cut_capabilities
        return N(observe=lambda: N())

    monkeypatch.setattr(f, "Gen1TraversalObserver", observer)
    raw = rt.reader.read()
    raw.party_hp = (4,)
    lesson["objective_catalog"] = list(lesson["completed_objectives"])
    lesson["party"][0]["moves"] = [[33, 10]]
    rt.reader.read = lambda: N(**vars(raw))

    def capture(_):
        return N(raw=rt.reader.read()), deepcopy(lesson)

    monkeypatch.setattr(f, "capture_player_lesson_snapshot", capture)
    rt.adapter = N(observe=lambda: capture(None)[0])
    rt.emulator.save_state_bytes = lambda: repr(
        (vars(raw), lesson, actions.actions_executed)
    ).encode()
    monkeypatch.setattr(f, "_raw_party_fully_restored", lambda obs: obs.party_hp == (20,))
    state = N(fail=False, incomplete=False, unavailable=False)

    def heal():
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        if not state.incomplete:
            raw.party_hp = (20,)
        return GoalExecutionReport(1, 10, dict(whole_party_restore=True))

    def verify(report):
        return (
            GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if state.fail
            else GoalVerification.succeeded()
        )

    monkeypatch.setattr(
        f,
        "RedCenterRestoreGoalProvider",
        lambda *a, **k: N(
            offer=lambda _: N(binding=None if state.unavailable else N(execute=heal, verify=verify))
        ),
    )
    return rt, actions, route, story, lesson, calls, raw, state


@pytest.mark.parametrize("fault", [None, "cash", "xp", "health_lost"])
def test_native_travel_healing_needs_no_redundant_nurse_but_preserves_guards(monkeypatch, fault):
    rt, actions, route, story, lesson, calls, raw, state = fixture(monkeypatch)
    original = type(route).__call__

    def travel(self, *args):
        original(self, *args)
        raw.party_hp = (20,)

    monkeypatch.setattr(type(route), "__call__", travel)
    state.unavailable = True
    binding = f.routed_restoration_binding(rt, actions, home_map=41, route=route)
    report = binding.execute()
    assert report.actions_executed == 1
    assert report.evidence["restoration"]["nurse_interaction"] is False
    if fault == "cash":
        raw.player_money -= 1
    if fault == "xp":
        lesson["party"][0]["experience"] += 1
    if fault == "health_lost":
        raw.party_hp = (4,)
    assert binding.verify(report).status is (
        GoalDecisionOutcome.SUCCEEDED if fault is None else GoalDecisionOutcome.FAILED
    )
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "cash",
        "item",
        "xp",
        "species",
        "move",
        "objective",
        "catalog",
        "incomplete",
        "nurse_verification",
        "unavailable",
        "stale",
        "destination",
    ],
)
def test_routed_healing_is_observed_single_use_and_preserves_progress(monkeypatch, fault):
    rt, actions, route, story, lesson, calls, raw, state = fixture(monkeypatch)
    binding = f.routed_restoration_binding(rt, actions, home_map=41, route=route)
    assert binding is not None and not calls
    if fault == "stale":
        raw.player_y += 1
        with pytest.raises(ValueError, match="stale"):
            binding.execute()
        assert not calls
        return
    if fault == "unavailable":
        state.unavailable = True
        with pytest.raises(RuntimeError, match="unavailable"):
            binding.execute()
        assert len(calls) == 1
        return
    if fault == "destination":
        monkeypatch.setattr(
            type(route), "__call__", lambda *a: actions.execute(MacroAction(MacroActionKind.WAIT))
        )
        with pytest.raises(RuntimeError, match="destination"):
            binding.execute()
        assert raw.map_id == 1
        return
    state.incomplete = fault == "incomplete"
    state.fail = fault == "nurse_verification"
    report = binding.execute()
    assert report.actions_executed == 2 and report.frames_executed == 20
    assert report.evidence["model_queries"] == 0
    if fault == "cash":
        raw.player_money -= 1
    if fault == "item":
        raw.bag_items = ((1, 1),)
    if fault == "xp":
        lesson["party"][0]["experience"] += 1
    if fault == "species":
        lesson["party"][0]["species_id"] = 1
    if fault == "move":
        lesson["party"][0]["moves"][0][0] = 1
    if fault == "objective":
        lesson["completed_objectives"].append("extra")
    if fault == "catalog":
        lesson["objective_catalog"].append("extra")
    assert binding.verify(report).status is (
        GoalDecisionOutcome.SUCCEEDED if fault is None else GoalDecisionOutcome.FAILED
    )
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


@pytest.mark.parametrize(
    "fault",
    [
        "healthy",
        "defeated",
        "battle",
        "dialogue",
        "unready",
        "cash_unknown",
        "bag_unknown",
        "opening_rival",
    ],
)
def test_unsafe_or_unnecessary_routed_healing_is_not_offered(monkeypatch, fault):
    rt, actions, route, story, _, calls, raw, _ = fixture(monkeypatch)
    if fault == "healthy":
        raw.party_hp = (20,)
    if fault == "defeated":
        raw.party_hp = (0,)
    if fault == "battle":
        raw.battle_state = 1
    if fault == "dialogue":
        rt.reader.read_bottom_dialogue_box_visible = lambda: True
    if fault == "unready":
        rt.reader.read_input_readiness = lambda: N(ready=False)
    if fault == "cash_unknown":
        raw.player_money = None
    if fault == "bag_unknown":
        raw.bag_items = None
    if fault == "opening_rival":
        raw.map_id = f.MapId.OAKS_LAB
        story.battled_rival = False
    assert f.routed_restoration_binding(rt, actions, home_map=41, route=route) is None
    assert not calls


@pytest.mark.parametrize(
    "fault", [None, "unobserved", "quest", "mixed", "empty", "lost", "catalog"]
)
def test_healing_accepts_only_native_arrival_progress(monkeypatch, fault):
    rt, actions, route, _, lesson, _, raw, _ = fixture(monkeypatch)
    lesson["objective_catalog"].append("arrival")
    facts = frozenset({"location:town"})
    required = {
        "quest": frozenset({"story:quest"}),
        "mixed": facts | {"story:quest"},
        "empty": frozenset(),
    }.get(fault, facts)
    rt.adapter.graph = N(objective=lambda _: N(completion_facts=required))
    monkeypatch.setattr(
        f,
        "semantic_facts",
        lambda _: frozenset() if fault == "unobserved" else facts | {"story:quest"},
    )
    binding = f.routed_restoration_binding(rt, actions, home_map=41, route=route)
    report = binding.execute()
    lesson["completed_objectives"].append("arrival")
    if fault == "lost":
        lesson["completed_objectives"].remove("choose_starter")
    if fault == "catalog":
        lesson["objective_catalog"].append("other")
    assert binding.verify(report).status is (
        GoalDecisionOutcome.SUCCEEDED if fault is None else GoalDecisionOutcome.FAILED
    )
