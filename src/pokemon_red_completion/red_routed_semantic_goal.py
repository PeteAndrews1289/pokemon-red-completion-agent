"""Pokemon Red adapter for route-then-semantic-goal composition.

The portable goal manager chooses a semantic destination such as resupply or
acquire-species.  Red privately supplies a semantic-router plan to that
destination, executes and verifies the transport, then takes a fresh coherent
Red observation before asking an existing goal provider for the actual skill.
Travel never becomes an ``EXPLORE`` label and no controller sequence crosses
the learner-facing boundary.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import (
    GoalFailureReason,
    GoalKind,
)
from pokemon_red_completion.goal_manager_runtime import (
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_manager import (
    RedGoalBindingOffer,
    RedGoalBindingProvider,
    RedGoalObservation,
)
from pokemon_red_completion.route_executor import (
    DEFAULT_ROUTE_EXECUTION_LIMITS,
    InterruptionHandler,
    RouteExecutionLimits,
    RouteExecutionReport,
    RouteReplanner,
    RouteResourceManager,
    TraversalObserver,
    TraversalSnapshot,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan
from pokemon_red_completion.routed_semantic_goal import (
    FreshDestinationGoalOffer,
    RoutedSemanticBudgetCheckpoint,
    RoutedSemanticGoalComposer,
    RoutedSemanticGoalLimits,
    RoutedSemanticRouteBinding,
)

RED_ROUTED_SEMANTIC_TRANSPORT_SCHEMA = (
    "pokemon.red.routed-semantic-transport.v1"
)
RED_ROUTED_SEMANTIC_ROUTE_REPORT_SCHEMA = (
    "pokemon.red.routed-semantic-route-report.v1"
)
RED_FRESH_DESTINATION_OBSERVATION_SCHEMA = (
    "pokemon.red.fresh-destination-observation.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedRoutedSemanticGoalError(RuntimeError):
    """A Red transport or fresh destination crossed its declared boundary."""


class RedRoutedSemanticFrameCounter(Protocol):
    """Minimum emulator counter needed for independent frame accounting."""

    @property
    def frame_count(self) -> int: ...


@dataclass(frozen=True, slots=True)
class RedRoutedSemanticBoundary:
    """Private exact terminal shared by transport and destination binding."""

    map_id: int
    at: tuple[int, int]
    mode: str | None

    def __post_init__(self) -> None:
        if type(self.map_id) is not int or self.map_id < 0:  # noqa: E721
            raise RedRoutedSemanticGoalError(
                "Red routed semantic boundary map differs"
            )
        if (
            not isinstance(self.at, tuple)
            or len(self.at) != 2
            or any(type(value) is not int or value < 0 for value in self.at)  # noqa: E721
        ):
            raise RedRoutedSemanticGoalError(
                "Red routed semantic boundary coordinate differs"
            )
        if self.mode is not None and (
            not isinstance(self.mode, str) or not self.mode
        ):
            raise RedRoutedSemanticGoalError(
                "Red routed semantic boundary mode differs"
            )

    @property
    def sha256(self) -> str:
        """Hash the private terminal without publishing its coordinates."""

        return canonical_sha256(
            {
                "schema": RED_ROUTED_SEMANTIC_TRANSPORT_SCHEMA,
                "map_id": self.map_id,
                "at": list(self.at),
                "mode": self.mode,
            }
        )

    @classmethod
    def from_plan(cls, plan: RoutePlan) -> RedRoutedSemanticBoundary:
        if not isinstance(plan, RoutePlan):
            raise TypeError("Red routed semantic boundary needs a RoutePlan")
        return cls(plan.terminal_map, plan.terminal_at, plan.terminal_mode)

    def matches_traversal(self, value: TraversalSnapshot) -> bool:
        return (
            isinstance(value, TraversalSnapshot)
            and value.map_id == self.map_id
            and value.at == self.at
            and value.mode == self.mode
            and value.ready
            and value.interruption is None
        )

    def matches_goal_observation(self, value: RedGoalObservation) -> bool:
        if not isinstance(value, RedGoalObservation):
            return False
        raw = value.raw
        return (
            raw.map_id == self.map_id
            # Route coordinates are always (row, column), which is Red's
            # (player_y, player_x).  Keep this aligned with
            # Gen1TraversalObserver and RoutePlan.
            and (raw.player_y, raw.player_x) == self.at
            and value.input_ready
            and not raw.battle_state
        )


@dataclass(frozen=True, slots=True)
class FreshRedGoalObservation:
    """One post-route Red observation joined to the traversal boundary."""

    observation_sha256: str
    observation: RedGoalObservation
    traversal: TraversalSnapshot

    def __post_init__(self) -> None:
        _require_sha256(self.observation_sha256, "fresh Red observation")
        if not isinstance(self.observation, RedGoalObservation):
            raise TypeError("fresh Red destination needs a RedGoalObservation")
        if not isinstance(self.traversal, TraversalSnapshot):
            raise TypeError("fresh Red destination needs a traversal snapshot")
        raw = self.observation.raw
        if (raw.map_id, raw.player_y, raw.player_x) != (
            self.traversal.map_id,
            *self.traversal.at,
        ):
            raise RedRoutedSemanticGoalError(
                "fresh Red goal and traversal observations disagree"
            )
        if self.observation.input_ready != self.traversal.ready:
            raise RedRoutedSemanticGoalError(
                "fresh Red readiness observations disagree"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_FRESH_DESTINATION_OBSERVATION_SCHEMA,
            "coherent_red_and_traversal_observation": True,
            "private_observation_fields": 0,
            "private_location_fields": 0,
        }


FreshRedGoalObserver = Callable[[], FreshRedGoalObservation]


@dataclass(frozen=True, slots=True)
class RedRoutedSemanticBudgetMeter:
    """Read the controller and emulator counters shared by both stages."""

    actions: CountingExecutor
    emulator: RedRoutedSemanticFrameCounter

    def __post_init__(self) -> None:
        if not isinstance(self.actions, CountingExecutor):
            raise TypeError("Red routed semantic meter needs a CountingExecutor")
        _read_counter(self.emulator.frame_count, "emulator frame")

    def checkpoint(self) -> RoutedSemanticBudgetCheckpoint:
        return RoutedSemanticBudgetCheckpoint(
            _read_counter(self.actions.actions_executed, "controller action"),
            _read_counter(self.emulator.frame_count, "emulator frame"),
        )


@dataclass(slots=True)
class RedSemanticTransportRoute:
    """Execute one authenticated semantic-router plan as private transport."""

    binding_ref: str
    origin_observation_sha256: str
    planner_binding_sha256: str
    plan: RoutePlan
    actions: CountingExecutor
    traversal_observer: TraversalObserver
    emulator: RedRoutedSemanticFrameCounter
    interruption_handler: InterruptionHandler | None = None
    replanner: RouteReplanner | None = None
    resource_manager: RouteResourceManager | None = None
    route_limits: RouteExecutionLimits = DEFAULT_ROUTE_EXECUTION_LIMITS
    route_source: str = "authenticated_semantic_router"
    profile_direction_steps: int = 0
    curriculum_direction_steps: int = 0
    prepare_departure: Callable[[], None] | None = None
    _binding_built: bool = field(default=False, init=False, repr=False)
    _executed: bool = field(default=False, init=False, repr=False)
    _verified: bool = field(default=False, init=False, repr=False)
    _route_report: RouteExecutionReport | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _goal_report: GoalExecutionReport | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.binding_ref, str) or not self.binding_ref:
            raise RedRoutedSemanticGoalError(
                "Red semantic transport binding reference is absent"
            )
        _require_sha256(self.origin_observation_sha256, "origin observation")
        _require_sha256(self.planner_binding_sha256, "planner binding")
        if not isinstance(self.plan, RoutePlan):
            raise TypeError("Red semantic transport needs a RoutePlan")
        if not self.plan.steps:
            raise RedRoutedSemanticGoalError(
                "Red semantic transport must cross a real route boundary"
            )
        if not isinstance(self.actions, CountingExecutor):
            raise TypeError("Red semantic transport needs a CountingExecutor")
        if not callable(getattr(self.traversal_observer, "observe", None)):
            raise TypeError("Red semantic transport needs a traversal observer")
        _read_counter(self.emulator.frame_count, "emulator frame")
        if not isinstance(self.route_limits, RouteExecutionLimits):
            raise TypeError("Red semantic transport needs route limits")
        if self.route_source != "authenticated_semantic_router":
            raise RedRoutedSemanticGoalError(
                "Red semantic transport is not semantic-router derived"
            )
        if (
            type(self.profile_direction_steps) is not int  # noqa: E721
            or type(self.curriculum_direction_steps) is not int  # noqa: E721
            or self.profile_direction_steps != 0
            or self.curriculum_direction_steps != 0
        ):
            raise RedRoutedSemanticGoalError(
                "profile and curriculum direction sequences are forbidden"
            )

    @property
    def terminal_boundary(self) -> RedRoutedSemanticBoundary:
        return RedRoutedSemanticBoundary.from_plan(self.plan)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_ROUTED_SEMANTIC_TRANSPORT_SCHEMA,
            "semantic_router_authenticated": True,
            "acknowledged_step_contracts": len(self.plan.steps),
            "profile_direction_steps": 0,
            "curriculum_direction_steps": 0,
            "transport_is_policy_kind": False,
            "private_map_fields": 0,
            "private_route_fields": 0,
            "raw_controller_sequence": False,
        }

    def route_binding(self) -> RoutedSemanticRouteBinding:
        """Bind once after proving the private route starts at live truth."""

        if self._binding_built:
            raise RedRoutedSemanticGoalError(
                "Red semantic transport binding was already constructed"
            )
        before = self._checkpoint()
        current = self.traversal_observer.observe()
        after = self._checkpoint()
        if after != before:
            raise RedRoutedSemanticGoalError(
                "Red semantic route binding changed controller or emulator state"
            )
        if not self._matches_start(current):
            raise RedRoutedSemanticGoalError(
                "Red semantic route is not executable from the live origin"
            )
        self._binding_built = True
        return RoutedSemanticRouteBinding(
            binding_ref=self.binding_ref,
            origin_observation_sha256=self.origin_observation_sha256,
            terminal_boundary_sha256=self.terminal_boundary.sha256,
            execute=self._execute,
            verify=self._verify,
        )

    def authenticated_report(self) -> RouteExecutionReport:
        """Expose the concrete closed-loop report only after verification."""

        if not self._verified or self._route_report is None:
            raise RedRoutedSemanticGoalError(
                "Red semantic route report is unavailable before verification"
            )
        return self._route_report

    def _execute(self) -> GoalExecutionReport:
        if self._executed:
            raise RedRoutedSemanticGoalError(
                "Red semantic transport was already executed"
            )
        self._executed = True
        before = self._checkpoint()
        if self.prepare_departure is not None:
            if not self._matches_start(self.traversal_observer.observe()):
                raise RedRoutedSemanticGoalError("departure preparation lost the route origin")
            self.prepare_departure()
            if not self._matches_start(self.traversal_observer.observe()):
                raise RedRoutedSemanticGoalError("departure preparation changed the route origin")
        route_report = execute_route(
            self.plan,
            self.actions,
            self.traversal_observer,
            interruption_handler=self.interruption_handler,
            replanner=self.replanner,
            resource_manager=self.resource_manager,
            limits=self.route_limits,
        )
        after = self._checkpoint()
        actions = after.controller_actions - before.controller_actions
        frames = after.emulator_frames - before.emulator_frames
        if actions < 0 or frames < 0:
            raise RedRoutedSemanticGoalError(
                "Red semantic transport counters moved backwards"
            )
        if route_report.initial_plan is not self.plan:
            raise RedRoutedSemanticGoalError(
                "Red semantic transport executed a different initial plan"
            )
        report = GoalExecutionReport(
            actions_executed=actions,
            frames_executed=frames,
            evidence={
                "schema": RED_ROUTED_SEMANTIC_ROUTE_REPORT_SCHEMA,
                "passed": route_report.passed,
                "acknowledged_steps": len(route_report.executed_steps),
                "movement_requests": route_report.movement_requests,
                "wait_actions": route_report.wait_actions,
                "interruptions": len(route_report.interruptions),
                "replans": len(route_report.replans),
                "resource_renewals": len(route_report.resource_renewals),
                "semantic_router_authenticated": True,
                "transport_is_policy_kind": False,
                "private_route_fields": 0,
            },
        )
        self._route_report = route_report
        self._goal_report = report
        return report

    def _verify(self, report: GoalExecutionReport) -> GoalVerification:
        if not self._executed or self._goal_report is None or self._route_report is None:
            raise RedRoutedSemanticGoalError(
                "Red semantic transport cannot verify before execution"
            )
        if self._verified:
            raise RedRoutedSemanticGoalError(
                "Red semantic transport was already verified"
            )
        self._verified = True
        if report is not self._goal_report:
            raise RedRoutedSemanticGoalError(
                "Red semantic transport verifier received a different report"
            )
        before = self._checkpoint()
        current = self.traversal_observer.observe()
        after = self._checkpoint()
        if after != before:
            return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
        if (
            not self._route_report.passed
            or not self.terminal_boundary.matches_traversal(
                self._route_report.terminal
            )
            or not self.terminal_boundary.matches_traversal(current)
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    def _checkpoint(self) -> RoutedSemanticBudgetCheckpoint:
        return RedRoutedSemanticBudgetMeter(self.actions, self.emulator).checkpoint()

    def _matches_start(self, value: TraversalSnapshot) -> bool:
        return (
            isinstance(value, TraversalSnapshot)
            and value.map_id == self.plan.macro_path.maps[0]
            and value.at == self.plan.start_at
            and value.mode == self.plan.start_mode
            and value.ready
            and value.interruption is None
        )


@dataclass(frozen=True, slots=True)
class RedFreshGoalDestinationBinder:
    """Bind one existing Red semantic provider from fresh terminal truth."""

    kind: GoalKind
    boundary: RedRoutedSemanticBoundary
    observe_fresh: FreshRedGoalObserver
    provider: RedGoalBindingProvider

    def __post_init__(self) -> None:
        if not isinstance(self.kind, GoalKind):
            raise RedRoutedSemanticGoalError(
                "Red routed destination kind differs"
            )
        if not isinstance(self.boundary, RedRoutedSemanticBoundary):
            raise TypeError("Red routed destination needs a terminal boundary")
        if not callable(self.observe_fresh):
            raise TypeError("Red routed destination needs a fresh observer")
        if not callable(getattr(self.provider, "offer", None)):
            raise TypeError("Red routed destination needs a goal provider")
        if self.provider.kind is not self.kind:
            raise RedRoutedSemanticGoalError(
                "Red routed destination provider kind differs"
            )

    def __call__(self) -> FreshDestinationGoalOffer:
        fresh = self.observe_fresh()
        if not isinstance(fresh, FreshRedGoalObservation):
            raise RedRoutedSemanticGoalError(
                "Red routed destination observer returned invalid evidence"
            )
        fresh.__post_init__()
        if (
            not self.boundary.matches_traversal(fresh.traversal)
            or not self.boundary.matches_goal_observation(fresh.observation)
        ):
            raise RedRoutedSemanticGoalError(
                "fresh Red destination differs from the route terminal"
            )
        offer = self.provider.offer(fresh.observation)
        if not isinstance(offer, RedGoalBindingOffer) or offer.kind is not self.kind:
            raise RedRoutedSemanticGoalError(
                "Red routed destination provider returned a different goal"
            )
        if offer.binding is None:
            assert offer.unavailable_reason is not None
            return FreshDestinationGoalOffer.unavailable(
                observation_sha256=fresh.observation_sha256,
                terminal_boundary_sha256=self.boundary.sha256,
                kind=self.kind,
                reason=offer.unavailable_reason,
            )
        return FreshDestinationGoalOffer.available(
            observation_sha256=fresh.observation_sha256,
            terminal_boundary_sha256=self.boundary.sha256,
            binding=offer.binding,
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_FRESH_DESTINATION_OBSERVATION_SCHEMA,
            "destination_kind": self.kind.value,
            "fresh_red_observation_required": True,
            "exact_route_terminal_required": True,
            "private_provider_fields": 0,
            "private_location_fields": 0,
        }


def build_red_routed_semantic_goal_composer(
    *,
    binding_ref: str,
    transport: RedSemanticTransportRoute,
    destination: RedFreshGoalDestinationBinder,
    estimated_effort: float,
    estimated_risk: float,
    limits: RoutedSemanticGoalLimits,
) -> RoutedSemanticGoalComposer:
    """Join Red transport and a semantic provider under one measured budget."""

    if not isinstance(transport, RedSemanticTransportRoute):
        raise TypeError("Red routed semantic composer needs Red transport")
    if not isinstance(destination, RedFreshGoalDestinationBinder):
        raise TypeError("Red routed semantic composer needs a destination binder")
    if transport.terminal_boundary != destination.boundary:
        raise RedRoutedSemanticGoalError(
            "Red transport and destination boundaries differ"
        )
    provider_actions = getattr(destination.provider, "actions", transport.actions)
    if provider_actions is not transport.actions:
        raise RedRoutedSemanticGoalError(
            "Red route and destination do not share one counted action port"
        )
    provider_emulator = getattr(destination.provider, "emulator", transport.emulator)
    if provider_emulator is not transport.emulator:
        raise RedRoutedSemanticGoalError(
            "Red route and destination do not share one emulator counter"
        )
    return RoutedSemanticGoalComposer(
        binding_ref=binding_ref,
        destination_kind=destination.kind,
        estimated_effort=estimated_effort,
        estimated_risk=estimated_risk,
        route=transport.route_binding(),
        bind_fresh_destination=destination,
        budget_meter=RedRoutedSemanticBudgetMeter(
            transport.actions,
            transport.emulator,
        ),
        limits=limits,
    )


def _read_counter(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedRoutedSemanticGoalError(
            f"Red routed semantic {subject} counter differs"
        )
    return value


def _require_sha256(value: str, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedRoutedSemanticGoalError(
            f"Red routed semantic {subject} SHA-256 differs"
        )


__all__ = [
    "RED_FRESH_DESTINATION_OBSERVATION_SCHEMA",
    "RED_ROUTED_SEMANTIC_ROUTE_REPORT_SCHEMA",
    "RED_ROUTED_SEMANTIC_TRANSPORT_SCHEMA",
    "FreshRedGoalObservation",
    "RedFreshGoalDestinationBinder",
    "RedRoutedSemanticBoundary",
    "RedRoutedSemanticBudgetMeter",
    "RedRoutedSemanticGoalError",
    "RedSemanticTransportRoute",
    "build_red_routed_semantic_goal_composer",
]
