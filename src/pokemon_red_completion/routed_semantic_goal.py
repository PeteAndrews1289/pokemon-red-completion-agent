"""Title-neutral route-then-semantic-goal composition.

The learner selects only the destination semantic goal.  A title adapter owns
transport to that goal's physical boundary, proves the route terminal, takes a
fresh observation, and binds an already-existing destination provider.  Route
identity and movement never become a policy kind or learner label.

This module owns no cartridge, controller, route planner, teacher, model, or
filesystem path.  It composes two independently verified bounded stages and
reconciles their self-reports against one external action/frame meter.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pokemon_red_completion.goal_manager import (
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)

ROUTED_SEMANTIC_GOAL_CONTRACT_SCHEMA = (
    "pokemon.core.routed-semantic-goal-contract.v1"
)
ROUTED_SEMANTIC_GOAL_REPORT_SCHEMA = (
    "pokemon.core.routed-semantic-goal-report.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RoutedSemanticGoalError(RuntimeError):
    """A composite binding crossed its route, destination, or budget boundary."""


@dataclass(frozen=True, slots=True)
class RoutedSemanticBudgetCheckpoint:
    """Independent cumulative controller and emulator accounting."""

    controller_actions: int
    emulator_frames: int

    def __post_init__(self) -> None:
        for name in ("controller_actions", "emulator_frames"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise RoutedSemanticGoalError(
                    f"routed semantic {name.replace('_', ' ')} differs"
                )


@runtime_checkable
class RoutedSemanticBudgetMeter(Protocol):
    """Trusted counters shared by transport and destination execution."""

    def checkpoint(self) -> RoutedSemanticBudgetCheckpoint: ...


@dataclass(frozen=True, slots=True)
class RoutedSemanticRouteBinding:
    """Private transport stage with an independent exact-terminal verifier."""

    binding_ref: str
    origin_observation_sha256: str
    terminal_boundary_sha256: str
    execute: Callable[[], GoalExecutionReport]
    verify: Callable[[GoalExecutionReport], GoalVerification]

    def __post_init__(self) -> None:
        if not isinstance(self.binding_ref, str) or not self.binding_ref:
            raise RoutedSemanticGoalError("routed semantic route reference is absent")
        _require_sha256(self.origin_observation_sha256, "origin observation")
        _require_sha256(self.terminal_boundary_sha256, "terminal boundary")
        if not callable(self.execute) or not callable(self.verify):
            raise RoutedSemanticGoalError(
                "routed semantic route needs execution and verification"
            )


@dataclass(frozen=True, slots=True)
class FreshDestinationGoalOffer:
    """One post-route observation joined to a destination provider offer."""

    observation_sha256: str
    terminal_boundary_sha256: str
    kind: GoalKind
    binding: ExecutableGoalBinding | None = None
    unavailable_reason: GoalUnavailableReason | None = None

    def __post_init__(self) -> None:
        _require_sha256(self.observation_sha256, "fresh destination observation")
        _require_sha256(self.terminal_boundary_sha256, "destination boundary")
        if not isinstance(self.kind, GoalKind):
            raise RoutedSemanticGoalError("routed destination kind differs")
        if self.binding is not None:
            if self.binding.kind is not self.kind:
                raise RoutedSemanticGoalError(
                    "routed destination binding kind differs"
                )
            if self.unavailable_reason is not None:
                raise RoutedSemanticGoalError(
                    "available routed destination has an unavailable reason"
                )
        elif not isinstance(self.unavailable_reason, GoalUnavailableReason):
            raise RoutedSemanticGoalError(
                "unavailable routed destination needs a reason"
            )

    @classmethod
    def available(
        cls,
        *,
        observation_sha256: str,
        terminal_boundary_sha256: str,
        binding: ExecutableGoalBinding,
    ) -> FreshDestinationGoalOffer:
        return cls(
            observation_sha256=observation_sha256,
            terminal_boundary_sha256=terminal_boundary_sha256,
            kind=binding.kind,
            binding=binding,
        )

    @classmethod
    def unavailable(
        cls,
        *,
        observation_sha256: str,
        terminal_boundary_sha256: str,
        kind: GoalKind,
        reason: GoalUnavailableReason,
    ) -> FreshDestinationGoalOffer:
        return cls(
            observation_sha256=observation_sha256,
            terminal_boundary_sha256=terminal_boundary_sha256,
            kind=kind,
            unavailable_reason=reason,
        )


FreshDestinationBinder = Callable[[], FreshDestinationGoalOffer]


@dataclass(frozen=True, slots=True)
class RoutedSemanticGoalLimits:
    """Whole-composite action and frame ceilings."""

    maximum_controller_actions: int
    maximum_emulator_frames: int

    def __post_init__(self) -> None:
        for name in ("maximum_controller_actions", "maximum_emulator_frames"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:  # noqa: E721
                raise RoutedSemanticGoalError(
                    f"routed semantic {name.replace('_', ' ')} differs"
                )


@dataclass(slots=True)
class _RoutedSemanticAttempt:
    route_execution: GoalExecutionReport
    route_verification: GoalVerification
    destination_offer: FreshDestinationGoalOffer | None
    destination_execution: GoalExecutionReport | None
    after_execution: RoutedSemanticBudgetCheckpoint
    report: GoalExecutionReport
    preliminary_failure: GoalFailureReason | None
    budget_reconciled: bool
    within_budget: bool


@dataclass(slots=True)
class RoutedSemanticGoalComposer:
    """Build one single-use destination binding around private transport."""

    binding_ref: str
    destination_kind: GoalKind
    estimated_effort: float
    estimated_risk: float
    route: RoutedSemanticRouteBinding
    bind_fresh_destination: FreshDestinationBinder
    budget_meter: RoutedSemanticBudgetMeter
    limits: RoutedSemanticGoalLimits
    _binding_built: bool = field(default=False, init=False, repr=False)
    _executed: bool = field(default=False, init=False, repr=False)
    _verified: bool = field(default=False, init=False, repr=False)
    _attempt: _RoutedSemanticAttempt | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.binding_ref, str) or not self.binding_ref:
            raise RoutedSemanticGoalError("routed semantic binding reference is absent")
        if not isinstance(self.destination_kind, GoalKind):
            raise RoutedSemanticGoalError("routed semantic destination kind differs")
        if not isinstance(self.route, RoutedSemanticRouteBinding):
            raise TypeError("routed semantic goal needs a route binding")
        if not callable(self.bind_fresh_destination):
            raise RoutedSemanticGoalError(
                "routed semantic goal needs a fresh destination binder"
            )
        if not isinstance(self.budget_meter, RoutedSemanticBudgetMeter):
            raise TypeError("routed semantic goal needs an independent budget meter")
        if not isinstance(self.limits, RoutedSemanticGoalLimits):
            raise TypeError("routed semantic goal needs whole-composite limits")
        # ExecutableGoalBinding performs the canonical strict metric validation.
        ExecutableGoalBinding(
            binding_ref=self.binding_ref,
            kind=self.destination_kind,
            estimated_effort=self.estimated_effort,
            estimated_risk=self.estimated_risk,
            execute=lambda: GoalExecutionReport(0, 0, {}),
            verify=lambda _report: GoalVerification.succeeded(),
        )

    def binding(self) -> ExecutableGoalBinding:
        """Return the one learner-facing destination binding."""

        if self._binding_built:
            raise RoutedSemanticGoalError(
                "routed semantic binding was already constructed"
            )
        self._binding_built = True
        return ExecutableGoalBinding(
            binding_ref=self.binding_ref,
            kind=self.destination_kind,
            estimated_effort=self.estimated_effort,
            estimated_risk=self.estimated_risk,
            execute=self._execute,
            verify=self._verify,
        )

    def public_dict(self) -> dict[str, object]:
        """Describe the reusable contract without route or binding identity."""

        return {
            "schema": ROUTED_SEMANTIC_GOAL_CONTRACT_SCHEMA,
            "destination_kind": self.destination_kind.value,
            "route_is_policy_kind": False,
            "fresh_destination_observation_required": True,
            "route_verification_required": True,
            "destination_verification_required": True,
            "destination_executes_at_most_once": True,
            "independent_budget_reconciliation_required": True,
            "maximum_controller_actions": self.limits.maximum_controller_actions,
            "maximum_emulator_frames": self.limits.maximum_emulator_frames,
            "private_binding_fields": 0,
            "private_path_fields": 0,
            "raw_controller_sequence": False,
            "teacher_route": False,
        }

    def _execute(self) -> GoalExecutionReport:
        if self._executed:
            raise RoutedSemanticGoalError(
                "routed semantic goal was already executed"
            )
        self._executed = True
        before = self._checkpoint()
        route_execution = self.route.execute()
        _require_execution_report(route_execution, "route")
        after_route_execution = self._checkpoint()
        route_actions, route_frames = _checkpoint_delta(
            before,
            after_route_execution,
        )
        route_accounted = (
            route_actions == route_execution.actions_executed
            and route_frames == route_execution.frames_executed
        )
        route_verification = self.route.verify(route_execution)
        _require_verification(route_verification, "route")
        after_route_verification = self._checkpoint()
        route_verifier_was_action_free = (
            after_route_verification == after_route_execution
        )
        preliminary: GoalFailureReason | None = None
        within_budget = self._within_budget(route_actions, route_frames)
        if not route_accounted or not route_verifier_was_action_free:
            preliminary = GoalFailureReason.BINDING_FAILED
        elif not within_budget:
            preliminary = GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
        if (
            preliminary is not None
            or route_verification.status is not GoalDecisionOutcome.SUCCEEDED
        ):
            return self._finish(
                before=before,
                route_execution=route_execution,
                route_verification=route_verification,
                destination_offer=None,
                destination_execution=None,
                preliminary_failure=preliminary,
                budget_reconciled=route_accounted and route_verifier_was_action_free,
                within_budget=within_budget,
            )

        before_binding = self._checkpoint()
        destination_offer = self.bind_fresh_destination()
        if not isinstance(destination_offer, FreshDestinationGoalOffer):
            raise RoutedSemanticGoalError(
                "fresh destination binder returned an invalid offer"
            )
        destination_offer.__post_init__()
        after_binding = self._checkpoint()
        if after_binding != before_binding:
            return self._finish(
                before=before,
                route_execution=route_execution,
                route_verification=route_verification,
                destination_offer=destination_offer,
                destination_execution=None,
                preliminary_failure=GoalFailureReason.BINDING_FAILED,
                budget_reconciled=False,
                within_budget=within_budget,
            )
        self._require_destination_offer(destination_offer)
        if destination_offer.binding is None:
            return self._finish(
                before=before,
                route_execution=route_execution,
                route_verification=route_verification,
                destination_offer=destination_offer,
                destination_execution=None,
                preliminary_failure=GoalFailureReason.BINDING_FAILED,
                budget_reconciled=True,
                within_budget=within_budget,
            )

        destination_execution = destination_offer.binding.execute()
        _require_execution_report(destination_execution, "destination")
        after_destination = self._checkpoint()
        destination_actions, destination_frames = _checkpoint_delta(
            after_binding,
            after_destination,
        )
        destination_accounted = (
            destination_actions == destination_execution.actions_executed
            and destination_frames == destination_execution.frames_executed
        )
        total_actions, total_frames = _checkpoint_delta(before, after_destination)
        sum_reconciled = (
            total_actions
            == route_execution.actions_executed
            + destination_execution.actions_executed
            and total_frames
            == route_execution.frames_executed
            + destination_execution.frames_executed
        )
        budget_reconciled = route_accounted and destination_accounted and sum_reconciled
        within_budget = self._within_budget(total_actions, total_frames)
        if not budget_reconciled:
            preliminary = GoalFailureReason.BINDING_FAILED
        elif not within_budget:
            preliminary = GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
        return self._finish(
            before=before,
            route_execution=route_execution,
            route_verification=route_verification,
            destination_offer=destination_offer,
            destination_execution=destination_execution,
            preliminary_failure=preliminary,
            budget_reconciled=budget_reconciled,
            within_budget=within_budget,
        )

    def _verify(self, report: GoalExecutionReport) -> GoalVerification:
        if not self._executed or self._attempt is None:
            raise RoutedSemanticGoalError(
                "routed semantic goal cannot verify before execution"
            )
        if self._verified:
            raise RoutedSemanticGoalError(
                "routed semantic goal was already verified"
            )
        self._verified = True
        attempt = self._attempt
        if report is not attempt.report:
            raise RoutedSemanticGoalError(
                "routed semantic verifier received a different report"
            )
        if attempt.destination_execution is None:
            if self._checkpoint() != attempt.after_execution:
                return GoalVerification.failed(
                    GoalFailureReason.WORLD_STATE_DIVERGED
                )
            if attempt.preliminary_failure is not None:
                return GoalVerification.failed(attempt.preliminary_failure)
            return attempt.route_verification

        destination_offer = attempt.destination_offer
        assert destination_offer is not None
        destination_binding = destination_offer.binding
        assert destination_binding is not None
        before_verifier = self._checkpoint()
        destination_verification = destination_binding.verify(
            attempt.destination_execution
        )
        _require_verification(destination_verification, "destination")
        after_verifier = self._checkpoint()
        if (
            before_verifier != attempt.after_execution
            or after_verifier != before_verifier
        ):
            return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
        if attempt.preliminary_failure is not None:
            return GoalVerification.failed(attempt.preliminary_failure)
        return destination_verification

    def _finish(
        self,
        *,
        before: RoutedSemanticBudgetCheckpoint,
        route_execution: GoalExecutionReport,
        route_verification: GoalVerification,
        destination_offer: FreshDestinationGoalOffer | None,
        destination_execution: GoalExecutionReport | None,
        preliminary_failure: GoalFailureReason | None,
        budget_reconciled: bool,
        within_budget: bool,
    ) -> GoalExecutionReport:
        after = self._checkpoint()
        actions, frames = _checkpoint_delta(before, after)
        report = GoalExecutionReport(
            actions_executed=actions,
            frames_executed=frames,
            evidence={
                "schema": ROUTED_SEMANTIC_GOAL_REPORT_SCHEMA,
                "route_verified": (
                    route_verification.status is GoalDecisionOutcome.SUCCEEDED
                ),
                "destination_bound": (
                    destination_offer is not None
                    and destination_offer.binding is not None
                ),
                "destination_executed": destination_execution is not None,
                "destination_kind": self.destination_kind.value,
                "budget_reconciled": budget_reconciled,
                "within_budget": within_budget,
                "route_is_policy_kind": False,
                "private_binding_fields": 0,
                "private_route_fields": 0,
            },
        )
        self._attempt = _RoutedSemanticAttempt(
            route_execution=route_execution,
            route_verification=route_verification,
            destination_offer=destination_offer,
            destination_execution=destination_execution,
            after_execution=after,
            report=report,
            preliminary_failure=preliminary_failure,
            budget_reconciled=budget_reconciled,
            within_budget=within_budget,
        )
        return report

    def _require_destination_offer(
        self,
        offer: FreshDestinationGoalOffer,
    ) -> None:
        if offer.observation_sha256 == self.route.origin_observation_sha256:
            raise RoutedSemanticGoalError(
                "routed destination reused the origin observation"
            )
        if offer.terminal_boundary_sha256 != self.route.terminal_boundary_sha256:
            raise RoutedSemanticGoalError(
                "routed destination boundary differs from the route terminal"
            )
        if offer.kind is not self.destination_kind:
            raise RoutedSemanticGoalError(
                "routed destination changed the declared goal kind"
            )
        if offer.binding is not None and offer.binding.binding_ref == self.route.binding_ref:
            raise RoutedSemanticGoalError(
                "routed transport cannot masquerade as the destination binding"
            )

    def _checkpoint(self) -> RoutedSemanticBudgetCheckpoint:
        value = self.budget_meter.checkpoint()
        if not isinstance(value, RoutedSemanticBudgetCheckpoint):
            raise RoutedSemanticGoalError(
                "routed semantic budget meter returned an invalid checkpoint"
            )
        return value

    def _within_budget(self, actions: int, frames: int) -> bool:
        return (
            actions <= self.limits.maximum_controller_actions
            and frames <= self.limits.maximum_emulator_frames
        )


def _checkpoint_delta(
    before: RoutedSemanticBudgetCheckpoint,
    after: RoutedSemanticBudgetCheckpoint,
) -> tuple[int, int]:
    actions = after.controller_actions - before.controller_actions
    frames = after.emulator_frames - before.emulator_frames
    if actions < 0 or frames < 0:
        raise RoutedSemanticGoalError(
            "routed semantic independent budget moved backwards"
        )
    return actions, frames


def _require_execution_report(value: object, stage: str) -> None:
    if not isinstance(value, GoalExecutionReport):
        raise RoutedSemanticGoalError(
            f"routed semantic {stage} returned an invalid execution report"
        )


def _require_verification(value: object, stage: str) -> None:
    if not isinstance(value, GoalVerification):
        raise RoutedSemanticGoalError(
            f"routed semantic {stage} returned an invalid verification"
        )


def _require_sha256(value: str, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RoutedSemanticGoalError(
            f"routed semantic {subject} SHA-256 differs"
        )


__all__ = [
    "ROUTED_SEMANTIC_GOAL_CONTRACT_SCHEMA",
    "ROUTED_SEMANTIC_GOAL_REPORT_SCHEMA",
    "FreshDestinationGoalOffer",
    "RoutedSemanticBudgetCheckpoint",
    "RoutedSemanticBudgetMeter",
    "RoutedSemanticGoalComposer",
    "RoutedSemanticGoalError",
    "RoutedSemanticGoalLimits",
    "RoutedSemanticRouteBinding",
]
