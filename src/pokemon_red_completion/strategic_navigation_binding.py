"""Bind semantic destination choices to deterministic route plans.

The collector needs both sides of the authority boundary at once: a portable
candidate view for the policy and the exact title-specific plan that may be
executed. This module builds them from one ordered binding set and proves that
the selected plan is the plan whose metrics produced the selected candidate.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.route_executor import RouteExecutionReport
from pokemon_red_completion.route_plan import RoutePlan
from pokemon_red_completion.strategic_navigation import (
    DestinationUnavailableReason,
    NavigationDestinationCandidate,
    NavigationFailureReason,
    NavigationOutcomeStatus,
    StrategicInterruptionOutcome,
    StrategicNavigationDecision,
    StrategicNavigationError,
    StrategicNavigationRecord,
    StrategicNavigationTag,
    StrategicReplanOutcome,
    StrategicResourceKind,
    successful_navigation_outcome,
    unsuccessful_navigation_outcome,
)


@dataclass(frozen=True, slots=True)
class DestinationRouteBinding:
    """One private destination identity and either a plan or semantic rejection."""

    destination_ref: str
    semantic_tags: tuple[StrategicNavigationTag, ...]
    plan: RoutePlan | None
    unavailability_reason: DestinationUnavailableReason | None = None
    availability_unknown: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.destination_ref, str) or not self.destination_ref:
            raise StrategicNavigationError("route binding destination is empty")
        if self.plan is not None:
            if not isinstance(self.plan, RoutePlan):
                raise StrategicNavigationError("route binding plan is invalid")
            if self.unavailability_reason is not None or self.availability_unknown:
                raise StrategicNavigationError(
                    "an available route binding cannot carry rejection state"
                )
        elif not isinstance(self.unavailability_reason, DestinationUnavailableReason):
            raise StrategicNavigationError(
                "an unavailable route binding needs a semantic rejection reason"
            )

    @classmethod
    def available(
        cls,
        destination_ref: str,
        semantic_tags: tuple[StrategicNavigationTag, ...],
        plan: RoutePlan,
    ) -> DestinationRouteBinding:
        return cls(destination_ref, semantic_tags, plan)

    @classmethod
    def unavailable(
        cls,
        destination_ref: str,
        semantic_tags: tuple[StrategicNavigationTag, ...],
        reason: DestinationUnavailableReason,
        *,
        unknown: bool = False,
    ) -> DestinationRouteBinding:
        return cls(
            destination_ref,
            semantic_tags,
            None,
            unavailability_reason=reason,
            availability_unknown=unknown,
        )

    @property
    def candidate(self) -> NavigationDestinationCandidate:
        if self.plan is not None:
            return NavigationDestinationCandidate.from_plan(
                self.destination_ref,
                self.semantic_tags,
                self.plan,
            )
        assert self.unavailability_reason is not None
        return NavigationDestinationCandidate.unavailable(
            self.destination_ref,
            self.semantic_tags,
            self.unavailability_reason,
            unknown=self.availability_unknown,
        )


@dataclass(frozen=True, slots=True)
class BoundStrategicNavigationDecision:
    """A strategic decision plus the exact selected private route binding."""

    decision: StrategicNavigationDecision
    selected_plan: RoutePlan

    def __post_init__(self) -> None:
        if not isinstance(self.decision, StrategicNavigationDecision):
            raise TypeError("decision must be a StrategicNavigationDecision")
        if not isinstance(self.selected_plan, RoutePlan):
            raise TypeError("selected_plan must be a RoutePlan")
        projected = NavigationDestinationCandidate.from_plan(
            self.decision.selected_destination_ref,
            self.decision.selected_candidate.semantic_tags,
            self.selected_plan,
        )
        if projected != self.decision.selected_candidate:
            raise StrategicNavigationError(
                "selected strategic candidate is not bound to the selected route plan"
            )

    def successful_record(
        self,
        report: RouteExecutionReport,
    ) -> StrategicNavigationRecord:
        if report.initial_plan != self.selected_plan:
            raise StrategicNavigationError(
                "route report did not execute the bound strategic plan"
            )
        return StrategicNavigationRecord(
            self.decision,
            successful_navigation_outcome(self.decision, report),
        )

    def unsuccessful_record(
        self,
        *,
        status: NavigationOutcomeStatus,
        reason: NavigationFailureReason,
        movement_requests: int = 0,
        acknowledged_steps: int = 0,
        wait_actions: int = 0,
        replans: tuple[StrategicReplanOutcome, ...] = (),
        interruptions: tuple[StrategicInterruptionOutcome, ...] = (),
        resource_renewals: tuple[StrategicResourceKind, ...] = (),
    ) -> StrategicNavigationRecord:
        return StrategicNavigationRecord(
            self.decision,
            unsuccessful_navigation_outcome(
                self.decision,
                status=status,
                reason=reason,
                movement_requests=movement_requests,
                acknowledged_steps=acknowledged_steps,
                wait_actions=wait_actions,
                replans=replans,
                interruptions=interruptions,
                resource_renewals=resource_renewals,
            ),
        )


def bind_strategic_navigation_decision(
    *,
    episode_id: str,
    decision_index: int,
    root_lineage_id: str,
    partition: str,
    actor: str,
    policy_id: str,
    semantic_need_tags: tuple[StrategicNavigationTag, ...],
    origin_semantic_tags: tuple[StrategicNavigationTag, ...],
    origin_region_ref: str,
    bindings: tuple[DestinationRouteBinding, ...],
    selected_destination_ref: str,
) -> BoundStrategicNavigationDecision:
    """Build one choice and return only the selected exact route for execution."""

    if not isinstance(bindings, tuple):
        raise StrategicNavigationError("route bindings must be an immutable tuple")
    if any(not isinstance(binding, DestinationRouteBinding) for binding in bindings):
        raise StrategicNavigationError("route bindings contain an invalid value")
    refs = tuple(binding.destination_ref for binding in bindings)
    try:
        selected_binding = bindings[refs.index(selected_destination_ref)]
    except ValueError as error:
        raise StrategicNavigationError("selected route binding is absent") from error
    if selected_binding.plan is None:
        raise StrategicNavigationError("selected route binding is unavailable")
    decision = StrategicNavigationDecision(
        episode_id=episode_id,
        decision_index=decision_index,
        root_lineage_id=root_lineage_id,
        partition=partition,
        actor=actor,
        policy_id=policy_id,
        semantic_need_tags=semantic_need_tags,
        origin_semantic_tags=origin_semantic_tags,
        origin_region_ref=origin_region_ref,
        candidates=tuple(binding.candidate for binding in bindings),
        selected_destination_ref=selected_destination_ref,
    )
    return BoundStrategicNavigationDecision(decision, selected_binding.plan)
