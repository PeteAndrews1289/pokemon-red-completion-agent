from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import (
    ExecutedRouteStep,
    RouteExecutionReport,
    TraversalSnapshot,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route
from pokemon_red_completion.strategic_navigation import (
    DestinationAvailability,
    DestinationUnavailableReason,
    NavigationFailureReason,
    NavigationOutcomeStatus,
    StrategicNavigationError,
    StrategicNavigationTag,
)
from pokemon_red_completion.strategic_navigation_binding import (
    BoundStrategicNavigationDecision,
    DestinationRouteBinding,
    bind_strategic_navigation_decision,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH,
    parse_strategic_navigation_registry,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _plans() -> tuple[RoutePlan, RoutePlan]:
    graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), action="right"),),
            (0, 1): (LocalEdge((0, 2), action="right"),),
            (0, 2): (),
        }
    )
    macro = MacroGraph({1: ()})
    return (
        plan_route(macro, {1: graph}, 1, (0, 0), 1, goal_at=(0, 1)),
        plan_route(macro, {1: graph}, 1, (0, 0), 1, goal_at=(0, 2)),
    )


def _bindings() -> tuple[DestinationRouteBinding, ...]:
    short, long = _plans()
    return (
        DestinationRouteBinding.available(
            "pokemon.test:destination:safe",
            (StrategicNavigationTag.HEALING, StrategicNavigationTag.SAFE_HUB),
            short,
        ),
        DestinationRouteBinding.available(
            "pokemon.test:destination:progress",
            (StrategicNavigationTag.CHALLENGE, StrategicNavigationTag.STORY_PROGRESS),
            long,
        ),
        DestinationRouteBinding.unavailable(
            "pokemon.test:destination:reward",
            (StrategicNavigationTag.OPTIONAL_REWARD,),
            DestinationUnavailableReason.MISSING_CAPABILITY,
        ),
    )


def _bound(
    bindings: tuple[DestinationRouteBinding, ...] | None = None,
    *,
    selected_destination_ref: str = "pokemon.test:destination:safe",
) -> BoundStrategicNavigationDecision:
    return bind_strategic_navigation_decision(
        episode_id="episode-001",
        decision_index=0,
        root_lineage_id="root-001",
        partition="unassigned",
        actor="deterministic_teacher",
        policy_id="strategic-teacher-v1",
        semantic_need_tags=(
            StrategicNavigationTag.HEALING,
            StrategicNavigationTag.RECOVERY,
        ),
        origin_semantic_tags=(StrategicNavigationTag.OVERWORLD,),
        origin_region_ref="pokemon.test:region:origin",
        bindings=bindings or _bindings(),
        selected_destination_ref=selected_destination_ref,
    )


def _report(plan: RoutePlan) -> RouteExecutionReport:
    return RouteExecutionReport(
        initial_plan=plan,
        terminal=TraversalSnapshot(
            map_id=plan.terminal_map,
            at=plan.terminal_at,
            ready=True,
            mode=plan.terminal_mode,
        ),
        executed_steps=tuple(
            ExecutedRouteStep(step, movement_requests=1, interruption_count=0)
            for step in plan.steps
        ),
        interruptions=(),
        replans=(),
        movement_requests=len(plan.steps),
        wait_actions=0,
    )


def test_binding_retains_all_candidates_but_exposes_only_selected_plan() -> None:
    bound = _bound()

    assert bound.selected_plan == _plans()[0]
    assert bound.decision.selected_index == 0
    assert tuple(item.availability for item in bound.decision.candidates) == (
        DestinationAvailability.AVAILABLE,
        DestinationAvailability.AVAILABLE,
        DestinationAvailability.UNAVAILABLE,
    )
    assert "pokemon.test" not in str(bound.decision.policy_input())


def test_binding_is_equivariant_to_candidate_order() -> None:
    original = _bindings()
    reordered = (original[2], original[1], original[0])

    forward = _bound(original)
    reverse = _bound(reordered)

    assert forward.selected_plan == reverse.selected_plan
    assert forward.decision.selected_index == 0
    assert reverse.decision.selected_index == 2
    forward_candidates = forward.decision.policy_input()["candidates"]
    reverse_candidates = reverse.decision.policy_input()["candidates"]
    assert isinstance(forward_candidates, list)
    assert isinstance(reverse_candidates, list)
    assert tuple(
        {key: value for key, value in candidate.items() if key != "binding_index"}
        for candidate in reversed(forward_candidates)
    ) == tuple(
        {key: value for key, value in candidate.items() if key != "binding_index"}
        for candidate in reverse_candidates
    )


def test_unavailable_or_absent_selection_fails_before_execution() -> None:
    with pytest.raises(StrategicNavigationError, match="unavailable"):
        _bound(
            selected_destination_ref="pokemon.test:destination:reward",
        )
    with pytest.raises(StrategicNavigationError, match="absent"):
        _bound(
            selected_destination_ref="pokemon.test:destination:missing",
        )


def test_bound_decision_rejects_a_different_selected_plan() -> None:
    bound = _bound()

    with pytest.raises(StrategicNavigationError, match="not bound"):
        BoundStrategicNavigationDecision(bound.decision, _plans()[1])
    with pytest.raises(StrategicNavigationError, match="rejection state"):
        replace(
            _bindings()[0],
            unavailability_reason=DestinationUnavailableReason.TEMPORARILY_BLOCKED,
        )


def test_success_requires_the_bound_plan_and_failure_remains_consumed() -> None:
    bound = _bound()

    successful = bound.successful_record(_report(bound.selected_plan))
    failed = bound.unsuccessful_record(
        status=NavigationOutcomeStatus.FAILED,
        reason=NavigationFailureReason.REPLAN_BUDGET_EXHAUSTED,
        movement_requests=3,
        acknowledged_steps=2,
    )

    assert successful.outcome.status is NavigationOutcomeStatus.SUCCEEDED
    assert failed.outcome.status is NavigationOutcomeStatus.FAILED
    assert failed.outcome.failure_reason is NavigationFailureReason.REPLAN_BUDGET_EXHAUSTED
    with pytest.raises(StrategicNavigationError, match="did not execute"):
        bound.successful_record(_report(_plans()[1]))


def test_counted_binding_requires_exact_committed_assignment() -> None:
    registry = parse_strategic_navigation_registry(
        (PROJECT_ROOT / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    assignment = registry.learning_assignment("red-strategic-v1-01-train")
    arguments = {
        "episode_id": assignment.episode_id,
        "decision_index": 0,
        "root_lineage_id": assignment.root_lineage_id,
        "partition": assignment.partition,
        "actor": "deterministic_teacher",
        "policy_id": "qualified-completion-order-v1",
        "semantic_need_tags": (
            StrategicNavigationTag.HEALING,
            StrategicNavigationTag.RECOVERY,
        ),
        "origin_semantic_tags": (StrategicNavigationTag.OVERWORLD,),
        "origin_region_ref": "pokemon.test:region:origin",
        "bindings": _bindings(),
        "selected_destination_ref": "pokemon.test:destination:safe",
    }

    with pytest.raises(StrategicNavigationError, match="requires a committed"):
        bind_strategic_navigation_decision(**arguments)

    with pytest.raises(StrategicNavigationError, match="loaded from committed"):
        bind_strategic_navigation_decision(
            **arguments,
            collection_assignment=assignment,
        )

    committed_assignment = replace(assignment, source_commit="a" * 40)
    bound = bind_strategic_navigation_decision(
        **arguments,
        collection_assignment=committed_assignment,
    )

    assert bound.decision.partition == "train"
    assert bound.decision.root_lineage_id == assignment.root_lineage_id

    with pytest.raises(StrategicNavigationError, match="provenance differs"):
        bind_strategic_navigation_decision(
            **{**arguments, "episode_id": "spoofed-episode"},
            collection_assignment=committed_assignment,
        )
