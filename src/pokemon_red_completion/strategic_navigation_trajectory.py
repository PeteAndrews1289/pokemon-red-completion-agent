"""Write strategic navigation choices into the authenticated trajectory streams.

Binding references remain in the live record used by the executor. The durable
model-facing decision contains only semantic candidate features and an
ephemeral selected index. Its paired outcome event likewise omits map ids,
coordinates, destination names and movement actions.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, cast

from pokemon_red_completion.strategic_navigation import (
    StrategicNavigationDecision,
    StrategicNavigationError,
    StrategicNavigationRecord,
    StrategicNavigationTag,
)
from pokemon_red_completion.strategic_navigation_binding import (
    BoundStrategicNavigationDecision,
    DestinationRouteBinding,
    bind_strategic_navigation_decision,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_ACTOR,
    STRATEGIC_NAVIGATION_POLICY_ID,
    StrategicNavigationEpisodeAssignment,
    StrategicNavigationProtocolError,
)
from pokemon_red_completion.trajectory import (
    DecisionContext,
    DecisionRecord,
    JSONValue,
    SemanticSnapshot,
    SnapshotProvider,
    SparseEvent,
    TrajectorySink,
)

STRATEGIC_NAVIGATION_SKILL_ID = "pokemon.core.strategic-navigation.v1"
STRATEGIC_NAVIGATION_DECISION_TYPE = "strategic_navigation_selection"
STRATEGIC_NAVIGATION_OUTCOME_KIND = "strategic_navigation_outcome"


def _assignment_ordered_bindings(
    assignment_id: str,
    decision_index: int,
    bindings: tuple[DestinationRouteBinding, ...],
) -> tuple[DestinationRouteBinding, ...]:
    """Permute candidates without using outcome, split, or destination features.

    A fixed teacher declaration would otherwise put the correct answer in the
    same candidate slot in every whole-game root.  The source-bound assignment
    provides a deterministic nonce, while the destination reference is used
    only inside the private binding layer and remains absent from policy input.
    """

    def order_key(binding: DestinationRouteBinding) -> bytes:
        value = f"{assignment_id}:{decision_index}:{binding.destination_ref}".encode()
        return hashlib.sha256(value).digest()

    return tuple(sorted(bindings, key=order_key))


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
    return strategic_navigation_decision_record_from_decision(
        record.decision,
        snapshot,
        step_index=step_index,
    )


def strategic_navigation_decision_record_from_decision(
    decision: StrategicNavigationDecision,
    snapshot: SemanticSnapshot,
    *,
    step_index: int,
) -> DecisionRecord:
    """Encode a strategic choice before execution has produced an outcome."""

    if not isinstance(decision, StrategicNavigationDecision):
        raise TypeError("decision must be a StrategicNavigationDecision")
    if not isinstance(snapshot, SemanticSnapshot):
        raise TypeError("snapshot must be a SemanticSnapshot")
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


class StrategicNavigationDecisionRecorder(Protocol):
    """Recorder subset used by whole-run strategic instrumentation."""

    episode_id: str
    sink: TrajectorySink

    @property
    def next_step_index(self) -> int: ...

    def record_standalone_decision(self, decision: DecisionRecord) -> bool: ...

    def note_instrumentation_failure(self) -> None: ...


@dataclass(slots=True)
class StrategicNavigationTrajectoryObserver:
    """Bind and durably join strategic choices inside one assigned episode.

    The choice is written before any route action. A later consumed outcome is
    accepted only for that exact pending decision. Sink failures do not change
    game control, but they mark the enclosing episode ineligible through the
    shared recording executor.
    """

    assignment: StrategicNavigationEpisodeAssignment
    snapshot_provider: SnapshotProvider
    recorder: StrategicNavigationDecisionRecorder
    sink: TrajectorySink
    allow_test: bool = False
    _next_decision_index: int = field(default=0, init=False)
    _pending: StrategicNavigationDecision | None = field(default=None, init=False)
    _pending_was_recorded: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.assignment.source_commit is None:
            raise StrategicNavigationProtocolError(
                "strategic trajectory recording requires a committed assignment"
            )
        if self.assignment.partition == "test" and not self.allow_test:
            raise StrategicNavigationProtocolError(
                "the strategic navigation test partition must remain unopened"
            )
        if self.recorder.episode_id != self.assignment.episode_id:
            raise StrategicNavigationProtocolError(
                "strategic trajectory recorder episode differs from its assignment"
            )
        if self.recorder.sink is not self.sink:
            raise StrategicNavigationProtocolError(
                "strategic decision and outcome sinks differ"
            )

    @property
    def pending_decision(self) -> StrategicNavigationDecision | None:
        return self._pending

    def bind_decision(
        self,
        *,
        semantic_need_tags: tuple[StrategicNavigationTag, ...],
        origin_semantic_tags: tuple[StrategicNavigationTag, ...],
        origin_region_ref: str,
        bindings: tuple[DestinationRouteBinding, ...],
        selected_destination_ref: str,
    ) -> BoundStrategicNavigationDecision:
        """Authenticate and record one choice before returning its private plan."""

        if self._pending is not None:
            raise StrategicNavigationError(
                "a strategic decision still awaits its consumed outcome"
            )
        ordered_bindings = _assignment_ordered_bindings(
            self.assignment.assignment_id,
            self._next_decision_index,
            bindings,
        )
        bound = bind_strategic_navigation_decision(
            episode_id=self.assignment.episode_id,
            decision_index=self._next_decision_index,
            root_lineage_id=self.assignment.root_lineage_id,
            partition=self.assignment.partition,
            actor=STRATEGIC_NAVIGATION_ACTOR,
            policy_id=STRATEGIC_NAVIGATION_POLICY_ID,
            semantic_need_tags=semantic_need_tags,
            origin_semantic_tags=origin_semantic_tags,
            origin_region_ref=origin_region_ref,
            bindings=ordered_bindings,
            selected_destination_ref=selected_destination_ref,
            collection_assignment=self.assignment,
        )
        snapshot = self.snapshot_provider.snapshot()
        recorded = self.recorder.record_standalone_decision(
            strategic_navigation_decision_record_from_decision(
                bound.decision,
                snapshot,
                step_index=self.recorder.next_step_index,
            )
        )
        self._next_decision_index += 1
        self._pending = bound.decision
        self._pending_was_recorded = recorded
        return bound

    def record_outcome(self, record: StrategicNavigationRecord) -> bool:
        """Consume the pending choice with exactly one semantic route outcome."""

        if not isinstance(record, StrategicNavigationRecord):
            raise TypeError("record must be a StrategicNavigationRecord")
        if self._pending is None:
            raise StrategicNavigationError("strategic outcome has no pending decision")
        if record.decision != self._pending:
            raise StrategicNavigationError(
                "strategic outcome does not match the pending decision"
            )
        decision_was_recorded = self._pending_was_recorded
        self._pending = None
        self._pending_was_recorded = False
        if not decision_was_recorded:
            return False
        try:
            self.sink.record_event(
                strategic_navigation_outcome_event(
                    record,
                    step_index=self.recorder.next_step_index,
                )
            )
        except Exception:
            self.recorder.note_instrumentation_failure()
            return False
        return True

    def require_settled(self) -> None:
        """Fail if episode finalization would leave a choice without an outcome."""

        if self._pending is not None:
            raise StrategicNavigationError(
                "strategic decision has no consumed outcome"
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
