from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroTransition
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import (
    ExecutedRouteStep,
    InterruptionReceipt,
    ResourceRenewalReceipt,
    RouteExecutionReport,
    RouteReplanReceipt,
    TraversalSnapshot,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route
from pokemon_red_completion.strategic_navigation import (
    DestinationAvailability,
    DestinationUnavailableReason,
    NavigationDestinationCandidate,
    NavigationFailureReason,
    NavigationOutcomeStatus,
    StrategicInterruptionKind,
    StrategicInterruptionOutcome,
    StrategicInterruptionResolution,
    StrategicNavigationDecision,
    StrategicNavigationError,
    StrategicNavigationLedger,
    StrategicNavigationRecord,
    StrategicNavigationTag,
    StrategicReplanOutcome,
    StrategicReplanReason,
    StrategicResourceKind,
    successful_navigation_outcome,
    unsuccessful_navigation_outcome,
)


def _connection_plan(*, passage_cost: int = 1) -> RoutePlan:
    transition = MacroTransition((0, 1), (5, 0), "up")
    macro = MacroGraph(
        {
            1: (
                MacroEdge(
                    2,
                    cost=passage_cost,
                    coordinate_transitions=(transition,),
                ),
            )
        }
    )
    local = {
        1: LocalGraph(
            {
                (0, 0): (LocalEdge((0, 1), action="right"),),
                (0, 1): (),
            }
        )
    }
    return plan_route(macro, local, 1, (0, 0), 2)


def _decision(plan: RoutePlan | None = None) -> StrategicNavigationDecision:
    selected_plan = plan or _connection_plan()
    return StrategicNavigationDecision(
        episode_id="episode-001",
        decision_index=4,
        root_lineage_id="root-001",
        partition="train",
        actor="deterministic_teacher",
        policy_id="strategic-teacher-v1",
        semantic_need_tags=(
            StrategicNavigationTag.ADVANCE_STORY,
            StrategicNavigationTag.REACH_NEXT_CHALLENGE,
        ),
        origin_semantic_tags=(
            StrategicNavigationTag.OVERWORLD,
            StrategicNavigationTag.SAFE_HUB,
        ),
        origin_region_ref="pokemon.red:region:origin",
        candidates=(
            NavigationDestinationCandidate.from_plan(
                "pokemon.red:destination:progression",
                (
                    StrategicNavigationTag.CHALLENGE,
                    StrategicNavigationTag.STORY_PROGRESS,
                ),
                selected_plan,
            ),
            NavigationDestinationCandidate.unavailable(
                "pokemon.red:destination:optional_reward",
                (StrategicNavigationTag.OPTIONAL_REWARD,),
                DestinationUnavailableReason.MISSING_CAPABILITY,
            ),
        ),
        selected_destination_ref="pokemon.red:destination:progression",
    )


def _report(plan: RoutePlan) -> RouteExecutionReport:
    executed = tuple(
        ExecutedRouteStep(step, movement_requests=1, interruption_count=0)
        for step in plan.steps
    )
    return RouteExecutionReport(
        initial_plan=plan,
        terminal=TraversalSnapshot(
            map_id=plan.terminal_map,
            at=plan.terminal_at,
            ready=True,
            mode=plan.terminal_mode,
        ),
        executed_steps=executed,
        interruptions=(
            InterruptionReceipt(
                "wild_battle",
                resumed_map=plan.terminal_map,
                resumed_at=plan.terminal_at,
            ),
        ),
        replans=(
            RouteReplanReceipt(
                1,
                map_id=1,
                at=(0, 0),
                newly_blocked=(0, 1),
                replacement_steps=4,
                reason="visible_object",
            ),
        ),
        movement_requests=len(plan.steps) + 1,
        wait_actions=2,
        resource_renewals=(
            ResourceRenewalReceipt(
                "encounter_suppression",
                map_id=1,
                at=(0, 0),
                before_remaining=0,
                after_remaining=250,
                units_consumed=1,
            ),
        ),
    )


def test_policy_view_has_destination_choices_but_no_label_or_red_bindings() -> None:
    decision = _decision()

    policy_input = decision.policy_input()
    encoded = json.dumps(policy_input, sort_keys=True)

    assert policy_input == {
        "schema": "strategic-navigation-policy-input-v1",
        "semantic_need_tags": ["advance_story", "reach_next_challenge"],
        "origin_semantic_tags": ["overworld", "safe_hub"],
        "candidates": [
            {
                "binding_index": 0,
                "semantic_tags": ["challenge", "story_progress"],
                "availability": "available",
                "route_cost": 2,
                "route_steps": 2,
                "map_transitions": 1,
                "field_actions": 0,
                "mode_changes": 0,
                "unavailability_reason": None,
            },
            {
                "binding_index": 1,
                "semantic_tags": ["optional_reward"],
                "availability": "unavailable",
                "route_cost": None,
                "route_steps": None,
                "map_transitions": None,
                "field_actions": None,
                "mode_changes": None,
                "unavailability_reason": "missing_capability",
            },
        ],
    }
    for forbidden in (
        "selected_destination_ref",
        "destination_ref",
        "origin_region_ref",
        "pokemon.red",
        '"action"',
        '"direction"',
        '"coordinate"',
        '"map_id"',
    ):
        assert forbidden not in encoded
    assert decision.selected_index == 0


def test_decision_requires_a_genuine_available_choice() -> None:
    decision = _decision()

    with pytest.raises(StrategicNavigationError, match="at least two"):
        replace(decision, candidates=decision.candidates[:1])
    with pytest.raises(StrategicNavigationError, match="not currently available"):
        replace(
            decision,
            selected_destination_ref="pokemon.red:destination:optional_reward",
        )
    with pytest.raises(StrategicNavigationError, match="duplicated"):
        replace(decision, candidates=(decision.candidates[0], decision.candidates[0]))
    with pytest.raises(StrategicNavigationError, match="unique and sorted"):
        replace(
            decision,
            semantic_need_tags=(
                StrategicNavigationTag.TRAINING,
                StrategicNavigationTag.ADVANCE_STORY,
            ),
        )
    with pytest.raises(StrategicNavigationError, match="immutable tuple"):
        replace(decision, candidates=list(decision.candidates))  # type: ignore[arg-type]
    with pytest.raises(StrategicNavigationError, match="actor must be non-empty"):
        replace(decision, actor=7)  # type: ignore[arg-type]


def test_free_text_unavailability_reasons_cannot_leak_game_specific_state() -> None:
    with pytest.raises(StrategicNavigationError, match="semantic reason"):
        NavigationDestinationCandidate(
            destination_ref="pokemon.red:destination:blocked",
            semantic_tags=(StrategicNavigationTag.OPTIONAL_REWARD,),
            availability=DestinationAvailability.UNAVAILABLE,
            unavailability_reason="blocked at map 13 coordinate 4,7",  # type: ignore[arg-type]
        )


def test_outcome_runtime_types_fail_closed_before_serialization() -> None:
    decision = _decision()

    with pytest.raises(StrategicNavigationError, match="status is unsupported"):
        replace(
            unsuccessful_navigation_outcome(
                decision,
                status=NavigationOutcomeStatus.FAILED,
                reason=NavigationFailureReason.WORLD_STATE_DIVERGED,
            ),
            status="failed",  # type: ignore[arg-type]
        )
    with pytest.raises(StrategicNavigationError, match="immutable tuple"):
        replace(
            unsuccessful_navigation_outcome(
                decision,
                status=NavigationOutcomeStatus.FAILED,
                reason=NavigationFailureReason.WORLD_STATE_DIVERGED,
            ),
            replans=[],  # type: ignore[arg-type]
        )


def test_success_aggregates_live_route_events_without_arrow_labels() -> None:
    plan = _connection_plan()
    decision = _decision(plan)

    outcome = successful_navigation_outcome(decision, _report(plan))
    record = StrategicNavigationRecord(decision, outcome)
    encoded = json.dumps(record.public_dict(), sort_keys=True)

    assert outcome.status is NavigationOutcomeStatus.SUCCEEDED
    assert outcome.acknowledged_steps == 2
    assert outcome.replans == (
        StrategicReplanOutcome(1, StrategicReplanReason.VISIBLE_OBJECT, 4),
    )
    assert outcome.interruptions == (
        StrategicInterruptionOutcome(
            StrategicInterruptionKind.WILD_BATTLE,
            StrategicInterruptionResolution.RESUMED,
        ),
    )
    assert outcome.resource_renewals == (StrategicResourceKind.ENCOUNTER_SUPPRESSION,)
    assert len(record.record_sha256) == 64
    for forbidden in ('"action"', '"direction"', '"coordinate"', '"map_id"'):
        assert forbidden not in encoded


def test_success_rejects_a_route_that_does_not_match_the_selected_projection() -> None:
    plan = _connection_plan()
    decision = _decision(plan)
    mismatched = replace(
        decision.candidates[0],
        route_cost=decision.candidates[0].route_cost + 1,  # type: ignore[operator]
    )

    with pytest.raises(StrategicNavigationError, match="metrics do not match"):
        successful_navigation_outcome(
            replace(decision, candidates=(mismatched, decision.candidates[1])),
            _report(plan),
        )


def test_interrupted_decisions_are_consumed_once_in_the_append_only_ledger() -> None:
    decision = _decision()
    outcome = unsuccessful_navigation_outcome(
        decision,
        status=NavigationOutcomeStatus.INTERRUPTED,
        reason=NavigationFailureReason.EXTERNAL_POWER_LOSS,
        movement_requests=3,
        acknowledged_steps=2,
        interruptions=(
            StrategicInterruptionOutcome(
                StrategicInterruptionKind.EXTERNAL_POWER_LOSS,
                StrategicInterruptionResolution.CENSORED,
            ),
        ),
    )
    record = StrategicNavigationRecord(decision, outcome)
    ledger = StrategicNavigationLedger()

    ledger.append(record)

    assert ledger.public_summary() == {
        "schema": "strategic-navigation-ledger-summary-v1",
        "records": 1,
        "outcomes": {"interrupted": 1},
        "replan_reasons": {},
        "interruption_kinds": {"external_power_loss": 1},
        "movement_action_labels": 0,
        "promotion_eligible": False,
    }
    with pytest.raises(StrategicNavigationError, match="duplicated"):
        ledger.append(record)
    with pytest.raises(StrategicNavigationError, match="successful_navigation_outcome"):
        unsuccessful_navigation_outcome(
            decision,
            status=NavigationOutcomeStatus.SUCCEEDED,
            reason=NavigationFailureReason.WORLD_STATE_DIVERGED,
        )


def test_decision_hash_is_stable_but_changes_with_lineage() -> None:
    decision = _decision()

    assert decision.decision_id == _decision().decision_id
    assert replace(decision, root_lineage_id="root-002").decision_id != decision.decision_id
