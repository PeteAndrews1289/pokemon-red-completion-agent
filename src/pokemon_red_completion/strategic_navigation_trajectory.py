"""Write strategic navigation choices into the authenticated trajectory streams.

Binding references remain in the live record used by the executor. The durable
model-facing decision contains only semantic candidate features and an
ephemeral selected index. Its paired outcome event likewise omits map ids,
coordinates, destination names and movement actions.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from pokemon_red_completion.strategic_navigation import StrategicNavigationRecord
from pokemon_red_completion.trajectory import (
    DecisionContext,
    DecisionRecord,
    JSONValue,
    SemanticSnapshot,
    SparseEvent,
)

STRATEGIC_NAVIGATION_SKILL_ID = "pokemon.core.strategic-navigation.v1"
STRATEGIC_NAVIGATION_DECISION_TYPE = "strategic_navigation_selection"
STRATEGIC_NAVIGATION_OUTCOME_KIND = "strategic_navigation_outcome"


def _validated_json_mapping(value: dict[str, object]) -> Mapping[str, JSONValue]:
    """Let trajectory constructors perform the authoritative deep validation."""

    return cast(Mapping[str, JSONValue], value)


def strategic_navigation_decision_record(
    record: StrategicNavigationRecord,
    snapshot: SemanticSnapshot,
    *,
    step_index: int,
) -> DecisionRecord:
    """Encode a strategic choice without exposing its title-specific binding."""

    if not isinstance(record, StrategicNavigationRecord):
        raise TypeError("record must be a StrategicNavigationRecord")
    if not isinstance(snapshot, SemanticSnapshot):
        raise TypeError("snapshot must be a SemanticSnapshot")
    decision = record.decision
    return DecisionRecord(
        decision_id=decision.decision_id,
        episode_id=decision.episode_id,
        step_index=step_index,
        snapshot=snapshot,
        context=DecisionContext(
            policy_id=decision.policy_id,
            actor=decision.actor,
            metadata=_validated_json_mapping(
                {
                    "skill_id": STRATEGIC_NAVIGATION_SKILL_ID,
                    "root_lineage_id": decision.root_lineage_id,
                    "partition": decision.partition,
                    "strategic_decision_index": decision.decision_index,
                    "policy_input": decision.policy_input(),
                }
            ),
        ),
        decision_type=STRATEGIC_NAVIGATION_DECISION_TYPE,
        action={
            "kind": "select_destination",
            "selected_candidate_index": decision.selected_index,
        },
    )


def strategic_navigation_outcome_event(
    record: StrategicNavigationRecord,
    *,
    step_index: int,
) -> SparseEvent:
    """Encode the consumed outcome without copying exception or binding text."""

    if not isinstance(record, StrategicNavigationRecord):
        raise TypeError("record must be a StrategicNavigationRecord")
    outcome = record.outcome
    return SparseEvent(
        event_id=f"{record.decision.decision_id}:outcome",
        episode_id=record.decision.episode_id,
        step_index=step_index,
        kind=STRATEGIC_NAVIGATION_OUTCOME_KIND,
        payload=_validated_json_mapping(
            {
                "decision_id": record.decision.decision_id,
                "selected_candidate_index": record.decision.selected_index,
                "status": outcome.status.value,
                "terminal_reached": outcome.terminal_reached,
                "movement_requests": outcome.movement_requests,
                "acknowledged_steps": outcome.acknowledged_steps,
                "wait_actions": outcome.wait_actions,
                "replans": [item.public_dict() for item in outcome.replans],
                "interruptions": [item.public_dict() for item in outcome.interruptions],
                "resource_renewals": [item.value for item in outcome.resource_renewals],
                "failure_reason": (
                    None
                    if outcome.failure_reason is None
                    else outcome.failure_reason.value
                ),
            }
        ),
    )
