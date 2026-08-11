"""Strategic navigation records without shortest-path imitation labels.

The transferable decision is *where to go next*, not whether the next button is
UP.  Exact movement remains a deterministic planner/executor responsibility.
This module records destination candidates, semantic need, total route cost and
the observed outcome so a later model can rank goals without memorizing Red's
map ids, coordinates or arrow sequences.

Failed and interrupted decisions are first-class records.  Dropping a power
loss, exhausted replan budget or unrecovered interruption would make the
dataset outcome-dependent in exactly the same way rerunning a failed evaluation
seed would make a success rate dishonest.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.route_executor import RouteExecutionReport
from pokemon_red_completion.route_plan import RoutePlan
from pokemon_red_completion.trajectory import canonical_sha256

_PARTITIONS = frozenset({"train", "validation", "test", "unassigned"})


class StrategicNavigationError(RuntimeError):
    """Raised when a strategic record would misstate its authority or outcome."""


class DestinationAvailability(StrEnum):
    """Whether the deterministic planner could bind a candidate right now."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class DestinationUnavailableReason(StrEnum):
    """Game-neutral reasons a strategic destination cannot be selected."""

    MISSING_CAPABILITY = "missing_capability"
    PLANNER_NO_ROUTE = "planner_no_route"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    STORY_GATE_CLOSED = "story_gate_closed"
    TEMPORARILY_BLOCKED = "temporarily_blocked"
    WORLD_STATE_UNKNOWN = "world_state_unknown"


class NavigationOutcomeStatus(StrEnum):
    """Terminal status of one consumed strategic choice."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


def _semantic_tags(values: tuple[str, ...], *, subject: str) -> tuple[str, ...]:
    if not values or any(not isinstance(value, str) or not value for value in values):
        raise StrategicNavigationError(f"{subject} must contain non-empty strings")
    if values != tuple(sorted(set(values))):
        raise StrategicNavigationError(f"{subject} must be unique and sorted")
    return values


@dataclass(frozen=True, slots=True)
class NavigationDestinationCandidate:
    """One semantic destination and its deterministic route projection.

    ``destination_ref`` is a binding identity stored beside the label.  It is
    deliberately omitted from :meth:`policy_features`; the model sees the
    candidate's semantic tags and relative costs, not a Red map identifier.
    """

    destination_ref: str
    semantic_tags: tuple[str, ...]
    availability: DestinationAvailability
    route_cost: int | None = None
    route_steps: int | None = None
    map_transitions: int | None = None
    field_actions: int | None = None
    mode_changes: int | None = None
    unavailability_reason: DestinationUnavailableReason | None = None

    def __post_init__(self) -> None:
        if not self.destination_ref:
            raise StrategicNavigationError("a destination candidate needs a binding reference")
        _semantic_tags(self.semantic_tags, subject="destination semantic tags")
        metrics = (
            self.route_cost,
            self.route_steps,
            self.map_transitions,
            self.field_actions,
            self.mode_changes,
        )
        if self.availability is DestinationAvailability.AVAILABLE:
            if any(type(value) is not int or value < 0 for value in metrics):  # noqa: E721
                raise StrategicNavigationError(
                    "an available destination needs non-negative route metrics"
                )
            if self.unavailability_reason is not None:
                raise StrategicNavigationError(
                    "an available destination cannot have an unavailability reason"
                )
            assert self.route_steps is not None
            assert self.field_actions is not None
            assert self.mode_changes is not None
            if self.field_actions > self.route_steps or self.mode_changes > self.route_steps:
                raise StrategicNavigationError("route sub-counts exceed total steps")
        else:
            if any(value is not None for value in metrics):
                raise StrategicNavigationError(
                    "an unavailable or unknown destination cannot advertise route metrics"
                )
            if not isinstance(self.unavailability_reason, DestinationUnavailableReason):
                raise StrategicNavigationError(
                    "an unavailable or unknown destination needs a semantic reason"
                )

    @classmethod
    def from_plan(
        cls,
        destination_ref: str,
        semantic_tags: tuple[str, ...],
        plan: RoutePlan,
    ) -> NavigationDestinationCandidate:
        """Project strategic metrics without retaining any movement action."""

        return cls(
            destination_ref=destination_ref,
            semantic_tags=semantic_tags,
            availability=DestinationAvailability.AVAILABLE,
            route_cost=plan.cost,
            route_steps=len(plan.steps),
            map_transitions=len(plan.segments),
            field_actions=sum(
                step.action_kind is MacroActionKind.FIELD_MOVE for step in plan.steps
            ),
            mode_changes=sum(
                step.source_mode != step.expected_mode for step in plan.steps
            ),
        )

    @classmethod
    def unavailable(
        cls,
        destination_ref: str,
        semantic_tags: tuple[str, ...],
        reason: DestinationUnavailableReason,
        *,
        unknown: bool = False,
    ) -> NavigationDestinationCandidate:
        return cls(
            destination_ref=destination_ref,
            semantic_tags=semantic_tags,
            availability=(
                DestinationAvailability.UNKNOWN
                if unknown
                else DestinationAvailability.UNAVAILABLE
            ),
            unavailability_reason=reason,
        )

    def policy_features(self, *, binding_index: int) -> dict[str, object]:
        """Identity-free candidate view presented to a ranking policy."""

        if type(binding_index) is not int or binding_index < 0:  # noqa: E721
            raise ValueError("binding index must be a non-negative integer")
        return {
            "binding_index": binding_index,
            "semantic_tags": list(self.semantic_tags),
            "availability": self.availability.value,
            "route_cost": self.route_cost,
            "route_steps": self.route_steps,
            "map_transitions": self.map_transitions,
            "field_actions": self.field_actions,
            "mode_changes": self.mode_changes,
            "unavailability_reason": (
                None
                if self.unavailability_reason is None
                else self.unavailability_reason.value
            ),
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "destination_ref": self.destination_ref,
            "semantic_tags": list(self.semantic_tags),
            "availability": self.availability.value,
            "route_cost": self.route_cost,
            "route_steps": self.route_steps,
            "map_transitions": self.map_transitions,
            "field_actions": self.field_actions,
            "mode_changes": self.mode_changes,
            "unavailability_reason": (
                None
                if self.unavailability_reason is None
                else self.unavailability_reason.value
            ),
        }


@dataclass(frozen=True, slots=True)
class StrategicNavigationDecision:
    """One genuine destination-ranking branch and its teacher/model label."""

    episode_id: str
    decision_index: int
    root_lineage_id: str
    partition: str
    actor: str
    policy_id: str
    semantic_need_tags: tuple[str, ...]
    origin_semantic_tags: tuple[str, ...]
    origin_region_ref: str
    candidates: tuple[NavigationDestinationCandidate, ...]
    selected_destination_ref: str

    def __post_init__(self) -> None:
        for name in (
            "episode_id",
            "root_lineage_id",
            "actor",
            "policy_id",
            "origin_region_ref",
            "selected_destination_ref",
        ):
            if not getattr(self, name):
                raise StrategicNavigationError(f"{name} must be non-empty")
        if type(self.decision_index) is not int or self.decision_index < 0:  # noqa: E721
            raise StrategicNavigationError("decision index must be a non-negative integer")
        if self.partition not in _PARTITIONS:
            raise StrategicNavigationError("strategic navigation partition is unsupported")
        _semantic_tags(self.semantic_need_tags, subject="semantic need tags")
        _semantic_tags(self.origin_semantic_tags, subject="origin semantic tags")
        if len(self.candidates) < 2:
            raise StrategicNavigationError(
                "a strategic navigation decision needs at least two candidates"
            )
        refs = tuple(candidate.destination_ref for candidate in self.candidates)
        if len(set(refs)) != len(refs):
            raise StrategicNavigationError("destination binding references are duplicated")
        try:
            selected = self.candidates[refs.index(self.selected_destination_ref)]
        except ValueError as error:
            raise StrategicNavigationError("selected destination is not a candidate") from error
        if selected.availability is not DestinationAvailability.AVAILABLE:
            raise StrategicNavigationError("selected destination is not currently available")

    @property
    def selected_index(self) -> int:
        return next(
            index
            for index, candidate in enumerate(self.candidates)
            if candidate.destination_ref == self.selected_destination_ref
        )

    @property
    def selected_candidate(self) -> NavigationDestinationCandidate:
        return self.candidates[self.selected_index]

    @property
    def decision_id(self) -> str:
        return canonical_sha256(
            {
                "episode_id": self.episode_id,
                "decision_index": self.decision_index,
                "root_lineage_id": self.root_lineage_id,
                "semantic_need_tags": list(self.semantic_need_tags),
                "origin_region_ref": self.origin_region_ref,
                "candidate_refs": [item.destination_ref for item in self.candidates],
            }
        )

    def policy_input(self) -> dict[str, object]:
        """Model-facing view, with label and game-specific bindings withheld."""

        return {
            "schema": "strategic-navigation-policy-input-v1",
            "semantic_need_tags": list(self.semantic_need_tags),
            "origin_semantic_tags": list(self.origin_semantic_tags),
            "candidates": [
                candidate.policy_features(binding_index=index)
                for index, candidate in enumerate(self.candidates)
            ],
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "strategic-navigation-decision-v1",
            "decision_id": self.decision_id,
            "episode_id": self.episode_id,
            "decision_index": self.decision_index,
            "root_lineage_id": self.root_lineage_id,
            "partition": self.partition,
            "provenance": {"actor": self.actor, "policy_id": self.policy_id},
            "semantic_need_tags": list(self.semantic_need_tags),
            "origin_semantic_tags": list(self.origin_semantic_tags),
            "origin_region_ref": self.origin_region_ref,
            "candidates": [
                {
                    "destination_ref": candidate.destination_ref,
                    **candidate.policy_features(binding_index=index),
                }
                for index, candidate in enumerate(self.candidates)
            ],
            "selected_destination_ref": self.selected_destination_ref,
            "selected_index": self.selected_index,
        }


@dataclass(frozen=True, slots=True)
class StrategicReplanOutcome:
    ordinal: int
    reason: str
    replacement_route_steps: int

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal <= 0:  # noqa: E721
            raise StrategicNavigationError("replan ordinal must be positive")
        if not self.reason:
            raise StrategicNavigationError("replan outcome needs a reason")
        if (
            type(self.replacement_route_steps) is not int  # noqa: E721
            or self.replacement_route_steps < 0
        ):
            raise StrategicNavigationError("replacement route steps must be non-negative")

    def public_dict(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "reason": self.reason,
            "replacement_route_steps": self.replacement_route_steps,
        }


@dataclass(frozen=True, slots=True)
class StrategicInterruptionOutcome:
    kind: str
    outcome: str

    def __post_init__(self) -> None:
        if not self.kind or not self.outcome:
            raise StrategicNavigationError("interruption kind and outcome must be non-empty")

    def public_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "outcome": self.outcome}


@dataclass(frozen=True, slots=True)
class StrategicNavigationOutcome:
    """Aggregated live result; exact map positions and button actions are absent."""

    decision_id: str
    selected_destination_ref: str
    status: NavigationOutcomeStatus
    terminal_reached: bool
    movement_requests: int
    acknowledged_steps: int
    wait_actions: int
    replans: tuple[StrategicReplanOutcome, ...] = ()
    interruptions: tuple[StrategicInterruptionOutcome, ...] = ()
    resource_renewals: tuple[str, ...] = ()
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.decision_id or not self.selected_destination_ref:
            raise StrategicNavigationError("navigation outcome identity is incomplete")
        for name in ("movement_requests", "acknowledged_steps", "wait_actions"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise StrategicNavigationError(f"{name} must be a non-negative integer")
        if tuple(item.ordinal for item in self.replans) != tuple(
            range(1, len(self.replans) + 1)
        ):
            raise StrategicNavigationError("replan outcomes must be contiguous")
        if any(not kind for kind in self.resource_renewals):
            raise StrategicNavigationError("resource renewal kinds must be non-empty")
        if self.status is NavigationOutcomeStatus.SUCCEEDED:
            if not self.terminal_reached or self.failure_reason is not None:
                raise StrategicNavigationError(
                    "a successful navigation outcome must reach its terminal without failure"
                )
        elif self.terminal_reached or not self.failure_reason:
            raise StrategicNavigationError(
                "a failed or interrupted navigation outcome needs a reason and no terminal"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "strategic-navigation-outcome-v1",
            "decision_id": self.decision_id,
            "selected_destination_ref": self.selected_destination_ref,
            "status": self.status.value,
            "terminal_reached": self.terminal_reached,
            "movement_requests": self.movement_requests,
            "acknowledged_steps": self.acknowledged_steps,
            "wait_actions": self.wait_actions,
            "replans": [item.public_dict() for item in self.replans],
            "interruptions": [item.public_dict() for item in self.interruptions],
            "resource_renewals": list(self.resource_renewals),
            "failure_reason": self.failure_reason,
        }


def successful_navigation_outcome(
    decision: StrategicNavigationDecision,
    report: RouteExecutionReport,
) -> StrategicNavigationOutcome:
    """Bind a selected strategic candidate to a successful live route report."""

    if not report.passed:
        raise StrategicNavigationError("a successful strategic record needs a passing report")
    selected = decision.selected_candidate
    expected = (
        report.initial_plan.cost,
        len(report.initial_plan.steps),
        len(report.initial_plan.segments),
        sum(
            step.action_kind is MacroActionKind.FIELD_MOVE
            for step in report.initial_plan.steps
        ),
        sum(
            step.source_mode != step.expected_mode for step in report.initial_plan.steps
        ),
    )
    observed = (
        selected.route_cost,
        selected.route_steps,
        selected.map_transitions,
        selected.field_actions,
        selected.mode_changes,
    )
    if observed != expected:
        raise StrategicNavigationError(
            "the selected candidate metrics do not match the executed initial plan"
        )
    return StrategicNavigationOutcome(
        decision_id=decision.decision_id,
        selected_destination_ref=decision.selected_destination_ref,
        status=NavigationOutcomeStatus.SUCCEEDED,
        terminal_reached=True,
        movement_requests=report.movement_requests,
        acknowledged_steps=len(report.executed_steps),
        wait_actions=report.wait_actions,
        replans=tuple(
            StrategicReplanOutcome(item.ordinal, item.reason, item.replacement_steps)
            for item in report.replans
        ),
        interruptions=tuple(
            StrategicInterruptionOutcome(item.kind, "resumed")
            for item in report.interruptions
        ),
        resource_renewals=tuple(item.kind for item in report.resource_renewals),
    )


def unsuccessful_navigation_outcome(
    decision: StrategicNavigationDecision,
    *,
    status: NavigationOutcomeStatus,
    reason: str,
    movement_requests: int = 0,
    acknowledged_steps: int = 0,
    wait_actions: int = 0,
    replans: tuple[StrategicReplanOutcome, ...] = (),
    interruptions: tuple[StrategicInterruptionOutcome, ...] = (),
    resource_renewals: tuple[str, ...] = (),
) -> StrategicNavigationOutcome:
    """Preserve a consumed failure or external interruption without rerunning it."""

    if status is NavigationOutcomeStatus.SUCCEEDED:
        raise StrategicNavigationError("use successful_navigation_outcome for success")
    return StrategicNavigationOutcome(
        decision_id=decision.decision_id,
        selected_destination_ref=decision.selected_destination_ref,
        status=status,
        terminal_reached=False,
        movement_requests=movement_requests,
        acknowledged_steps=acknowledged_steps,
        wait_actions=wait_actions,
        replans=replans,
        interruptions=interruptions,
        resource_renewals=resource_renewals,
        failure_reason=reason,
    )


@dataclass(frozen=True, slots=True)
class StrategicNavigationRecord:
    decision: StrategicNavigationDecision
    outcome: StrategicNavigationOutcome

    def __post_init__(self) -> None:
        if self.decision.decision_id != self.outcome.decision_id:
            raise StrategicNavigationError("navigation decision and outcome identities differ")
        if self.decision.selected_destination_ref != self.outcome.selected_destination_ref:
            raise StrategicNavigationError("navigation decision and outcome bindings differ")

    @property
    def record_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "strategic-navigation-record-v1",
            "decision": self.decision.public_dict(),
            "outcome": self.outcome.public_dict(),
        }


@dataclass(slots=True)
class StrategicNavigationLedger:
    """Append-only one-outcome ledger for strategic navigation decisions."""

    _records: list[StrategicNavigationRecord] = field(default_factory=list)
    _decision_ids: set[str] = field(default_factory=set)

    @property
    def records(self) -> tuple[StrategicNavigationRecord, ...]:
        return tuple(self._records)

    def append(self, record: StrategicNavigationRecord) -> None:
        if not isinstance(record, StrategicNavigationRecord):
            raise TypeError("record must be a StrategicNavigationRecord")
        if record.decision.decision_id in self._decision_ids:
            raise StrategicNavigationError("strategic navigation decision is duplicated")
        self._decision_ids.add(record.decision.decision_id)
        self._records.append(record)

    def public_summary(self) -> dict[str, object]:
        outcomes = Counter(record.outcome.status.value for record in self._records)
        replan_reasons = Counter(
            replan.reason for record in self._records for replan in record.outcome.replans
        )
        interruption_kinds = Counter(
            interruption.kind
            for record in self._records
            for interruption in record.outcome.interruptions
        )
        return {
            "schema": "strategic-navigation-ledger-summary-v1",
            "records": len(self._records),
            "outcomes": dict(sorted(outcomes.items())),
            "replan_reasons": dict(sorted(replan_reasons.items())),
            "interruption_kinds": dict(sorted(interruption_kinds.items())),
            "movement_action_labels": 0,
            "promotion_eligible": False,
        }
