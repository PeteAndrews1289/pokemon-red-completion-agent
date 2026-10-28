"""Narrow safe-route orchestration, not native qualification or learning."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from test_post_battle_strategy import menu
from test_red_live_option_menu import _binding, _model, _situation

import pokemon_red_completion.red_autonomous_player as runner
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.executor import GoalExecutionBudgetExhausted
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet, GoalExecutionReport
from pokemon_red_completion.living_dex_option_value import upgrade_option_value_model_for_readiness
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.player_readiness import PlayerReadiness
from pokemon_red_completion.red_integrated_play import safe_route_setback
from pokemon_red_completion.red_live_option_menu import (
    RedLiveOptionChoice,
    RedLiveOptionSelectionMode,
    build_red_live_option_set,
)
from pokemon_red_completion.resource_economy_observation import EconomySnapshot
from pokemon_red_completion.route_executor import (
    RouteExecutionError,
    RouteExecutionFailureReason,
    RouteExecutionFailureReport,
    TraversalSnapshot,
)
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError


def facts(n=0):
    return dict(actions=n, completed_actions=n, frames=10*n, cash=539,
                owned_species=["pokemon:national:009"], specimen_counts={"one": 1},
                completed_objectives=["first"], battle_state=0, buttons_released=True,
                input_ready=True, coins=20, bag_items=[[1, 1], [3, 1]],
                party_guard_verified=True,
                player_lesson=dict(schema="pokemon.red.player-lesson-snapshot.v1",
                                   party=[dict(specimen_ref="original-one", hp=232,
                                       species_id=177, level=82, experience=550000,
                                       status="none", moves=[])]),
                route_boundary=dict(map_id=165, at=[16, 20], ready=True,
                                    interruption=None, mode="land"))


def route_error():
    error = RouteExecutionError("route replanning found no candidate",
        reason=RouteExecutionFailureReason.PLANNER_NO_ROUTE)
    error.__cause__ = RoutePlanningError("no staged route")
    error.attach_failure(RouteExecutionFailureReport(
        initial_plan=RoutePlan(MacroPath((165,), ()), (16, 20), "land", (), None,
                               (16, 20), "land"),
        reason=error.reason, last_observation=TraversalSnapshot(
            165, (16, 20), True, mode="land"),
        executed_steps=(), interruptions=(), replans=(), movement_requests=1,
        wait_actions=0))
    return error


def blocked_walk_error():
    plan = RoutePlan(MacroPath((165,), ()), (16, 20), "land", (),
        LocalPath(((16, 20), (16, 21)),
                  (LocalEdge((16, 21), action="right", required_mode="land", result_mode="land"),),
                  ("land", "land")), (16, 21), "land")
    error = RouteExecutionError("walk acknowledgement exhausted",
        reason=RouteExecutionFailureReason.STEP_ACKNOWLEDGEMENT_EXHAUSTED)
    error.attach_failure(replace(route_error().failure, initial_plan=plan,
        reason=error.reason, movement_requests=8))
    return error


def accepted(*, before=None, after=None, error=None, kind=GoalKind.ACQUIRE_SPECIES,
             report=None, verification=None):
    return safe_route_setback(_binding(kind, binding_ref="test-route", calls=[]),
        before or runner.AutonomousSnapshot(b"0", facts(), True),
        after or runner.AutonomousSnapshot(b"1", facts(1), True),
        report, verification, error if error is not None else route_error())


def test_exact_settled_route_failure_has_failed_cost_not_a_success_report():
    receipt = accepted()
    assert receipt["reason"] == "planner_no_route"
    assert receipt["cost"] == dict(actions=1, completed_actions=1, frames=10, cash_spent=0)
    assert receipt["route_terminal"] == facts()["route_boundary"]


@pytest.mark.parametrize("kind", [GoalKind.ACQUIRE_SPECIES, GoalKind.RESUPPLY])
def test_settled_blocked_walk_keeps_the_exact_failed_step(kind):
    receipt = accepted(error=blocked_walk_error(), kind=kind)
    assert receipt["reason"] == "step_acknowledgement_exhausted"
    assert receipt["failed_walk"] == dict(source_map=165, source_at=[16, 20],
        expected_map=165, expected_at=[16, 21], action="right")


@pytest.mark.parametrize("fault", ["cause", "no_step", "replanned", "water", "warp",
                                  "field_move", "wrong_source", "moving", "budget",
                                  "malformed_step", "zero_requests"])
def test_blocked_walk_rejects_unknown_transition_or_partial_traces(fault):
    error = blocked_walk_error()
    failure = error.failure
    if fault == "cause":
        error.__cause__ = RuntimeError("unknown")
    elif fault == "budget":
        error.reason = RouteExecutionFailureReason.INTERRUPTION_BUDGET_EXHAUSTED
    elif fault == "no_step":
        error.failure = replace(failure, initial_plan=route_error().failure.initial_plan)
    elif fault == "replanned":
        error.failure = replace(failure, replans=(object(),))
    elif fault == "malformed_step":
        error.failure = replace(failure, executed_steps=(object(),))
    elif fault == "zero_requests":
        error.failure = replace(failure, movement_requests=0)
    elif fault in {"wrong_source", "moving"}:
        error.failure = replace(failure, last_observation=replace(failure.last_observation,
            **({"at": (16, 21)} if fault == "wrong_source" else {"ready": False})))
    else:
        edge = failure.initial_plan.terminal_approach.edges[0]
        changed = {
            "water": dict(required_mode="water", result_mode="water"),
            "warp": dict(kind="warp"),
            "field_move": dict(action_kind=MacroActionKind.FIELD_MOVE),
        }[fault]
        path = replace(failure.initial_plan.terminal_approach, edges=(replace(edge, **changed),),
                       **({"modes": ("water", "water")} if fault == "water" else {}))
        error.failure = replace(failure, initial_plan=replace(failure.initial_plan,
            terminal_approach=path,
            **({"start_mode": "water", "terminal_mode": "water"} if fault == "water" else {})))
    assert accepted(error=error, kind=GoalKind.RESUPPLY) is None


@pytest.mark.parametrize("key,value", [
    ("party_guard_verified", False), ("party_guard_verified", 1),
    ("cash", 538), ("cash", 540), ("cash", True),
    ("coins", 21), ("coins", None), ("bag_items", [[1, 1]]),
    ("bag_items", None), ("bag_items", [[1, True]]),
    ("owned_species", []), ("specimen_counts", {}), ("completed_objectives", []),
    ("player_lesson", {}), ("battle_state", 1), ("buttons_released", False),
    ("input_ready", False), ("completed_actions", 0), ("actions", -1),
    ("frames", 0), ("route_boundary", None),
    ("route_boundary", {**facts()["route_boundary"], "at": [16, 21]}),
    ("route_boundary", {**facts()["route_boundary"], "map_id": 165.0}),
    ("route_boundary", {**facts()["route_boundary"], "at": [16.0, 20]}),
    ("route_boundary", {**facts()["route_boundary"], "ready": 1}),
])
def test_missing_changed_or_partial_terminal_never_resumes(key, value):
    assert accepted(after=runner.AutonomousSnapshot(b"1", {**facts(1), key: value}, True)) is None


@pytest.mark.parametrize("side", ["before", "after"])
def test_unsafe_boundary_rejected_on_either_side(side):
    assert accepted(**{side: runner.AutonomousSnapshot(b"1", facts(1), False)}) is None


@pytest.mark.parametrize("fault", ["missing", "reason", "cause", "nested_budget", "last",
                                  "moving", "battle", "wrong_mode", "negative_trace"])
def test_failure_trace_is_required_and_unknown_causes_stay_fatal(fault):
    error = route_error()
    if fault == "missing":
        error.failure = None
    elif fault == "reason":
        error.reason = RouteExecutionFailureReason.INTERRUPTION_BUDGET_EXHAUSTED
    elif fault == "cause":
        error.__cause__ = RuntimeError("unknown input failure")
    elif fault == "nested_budget":
        error.__cause__.__cause__ = RuntimeError("input allowance exhausted")
    else:
        last = error.failure.last_observation
        error.failure = replace(error.failure, **{
            "last": dict(last_observation=None),
            "moving": dict(last_observation=replace(last, ready=False)),
            "battle": dict(last_observation=replace(last, interruption="wild_battle")),
            "wrong_mode": dict(last_observation=replace(last, mode="unknown")),
            "negative_trace": dict(movement_requests=-1),
        }[fault])
    assert accepted(error=error) is None


@pytest.mark.parametrize("kind", [GoalKind.RESTORE_TEAM, GoalKind.RESUPPLY,
                                  GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM])
def test_other_goal_kinds_cannot_use_route_exception_continuation(kind):
    assert accepted(kind=kind) is None


def test_party_identity_health_or_pp_changes_are_not_this_narrow_route_case():
    for value in (dict(specimen_ref="replacement", hp=232),
                  dict(specimen_ref="original-one", hp=100)):
        after = deepcopy(facts(1))
        after["player_lesson"]["party"] = [value]
        assert accepted(after=runner.AutonomousSnapshot(b"1", after, True)) is None
    assert accepted(report=GoalExecutionReport(1, 10, {})) is None
    assert accepted(verification=object()) is None


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("failure_kind", ["planner", "blocked_walk"])
@pytest.mark.parametrize("fault", [None, "partial", "resource", "budget", "unsettled", "wall"])
def test_default_stops_but_opt_in_keeps_failed_receipt_and_queries_changed_state(
    tmp_path, monkeypatch, enabled, fault, failure_kind
):
    state, observed, selections = {"n": 0}, [], []
    readiness = PlayerReadiness.from_context(menu().context, menu().remaining_budget)

    def snapshot():
        value = facts(state["n"])
        if state["n"] == 1:
            if fault == "partial":
                value["completed_actions"] = 0
            elif fault == "resource":
                value["bag_items"] = [[1, 1]]
            elif fault == "unsettled":
                value["input_ready"] = False
        return runner.AutonomousSnapshot(str(state["n"]).encode(), value, True)

    def observe(ordinal):
        observed.append(state["n"])

        def execute():
            state["n"] += 1
            if ordinal == 0:
                if fault == "budget":
                    raise GoalExecutionBudgetExhausted("actual input allowance exhausted")
                raise route_error() if failure_kind == "planner" else blocked_walk_error()
            return GoalExecutionReport(1, 10, {})

        bindings = tuple(replace(_binding(kind, binding_ref=kind.value, calls=[]), execute=execute)
                         for kind in (GoalKind.ACQUIRE_SPECIES, GoalKind.RESUPPLY))
        return build_red_live_option_set(supplements=(),
            situation=_situation(resources=0.1, safety=0.1),
            binding_set=GoalBindingSet(tuple(b.opportunity for b in bindings), bindings),
            model_feature_version=5, ordering_seed_sha256="a" * 64, readiness=readiness,
            economy_snapshot=EconomySnapshot(539, ()), target_cash=0)

    def select(model, options, *, seed, **kwargs):
        selections.append(state["n"])
        wanted = GoalKind.ACQUIRE_SPECIES if state["n"] == 0 else GoalKind.RESUPPLY
        i = next(i for i, b in enumerate(options.bindings) if b.kind is wanted)
        return RedLiveOptionChoice(options, i, RedLiveOptionSelectionMode.MODEL_EXPLORATION,
                                  (0., 0.), (.5, .5), seed, model.model_sha256)

    monkeypatch.setattr(runner, "select_red_live_option", select)
    if fault == "wall":
        monkeypatch.setattr(runner, "monotonic", lambda: 100 if state["n"] else 0)
    result = runner.run_autonomous_options(
        model=upgrade_option_value_model_for_readiness(_model()), output=tmp_path / "run",
        snapshot=snapshot, observe=observe, seed=31, maximum_decisions=2,
        continuous_player=True, continue_safe_route_failures=enabled, maximum_cash_spent=None,
        maximum_seconds=20 if fault == "wall" else 1800,
        provenance=dict(source=dict(partition="development")))
    resumed = enabled and fault is None
    certified = enabled and fault in {None, "wall"}
    expected_stop = "decision_budget" if resumed else (
        "wall_time_budget" if certified and fault == "wall" else "execution_failed")
    assert result["stop_reason"] == expected_stop
    assert observed == selections == ([0, 1] if resumed else [0])
    assert result["successful_decisions"] == int(resumed)
    assert result["teacher_actions"] == 0
    assert result["outcomes"][0]["verification"] is None
    assert result["outcomes"][0]["measured_cost"] is None
    assert result["outcomes"][0]["error_type"] == (
        "GoalExecutionBudgetExhausted" if fault == "budget" else "RouteExecutionError")
    if fault != "budget":
        assert result["outcomes"][0]["error_chain"][0]["reason_code"] == (
            "planner_no_route" if failure_kind == "planner" else "step_acknowledgement_exhausted")
    if enabled:
        assert result["recoverable_route_setbacks"] == int(certified)
        if certified:
            assert result["outcomes"][0]["recoverable_route_setback"]["cost"]["actions"] == 1
            assert result["outcomes"][0]["measured_cost"] is None
            assert result["outcomes"][0]["verification"] is None
            assert result["search_memory"]["entries"]
            assert sum(row["actions"] for row in result["search_memory"]["entries"].values()) == 1
    saved = json.loads((tmp_path / "run/step-000/outcome.json").read_text())
    assert saved == result["outcomes"][0]


@pytest.mark.parametrize("enabled,continuous,partition", [
    (1, True, "development"), (True, False, "development"),
    (True, True, "train"), (True, True, "evaluation"),
])
def test_invalid_scope_rejects_before_any_state_or_menu_read(
    tmp_path, enabled, continuous, partition
):
    with pytest.raises(ValueError, match="safe route continuation"):
        runner.run_autonomous_options(model=_model(), output=tmp_path / "run",
            snapshot=lambda: pytest.fail("no observation authorized"),
            observe=lambda _: pytest.fail("no menu authorized"), seed=1,
            continuous_player=continuous, continue_safe_route_failures=enabled,
            provenance=dict(source=dict(partition=partition)))
    assert not (tmp_path / "run").exists()
