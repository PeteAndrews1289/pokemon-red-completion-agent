"""Closed-loop execution for game-neutral coordinate route plans.

A route step is complete only when observation acknowledges its requested
coordinate or map transition. Sending a controller input is not evidence that
the game consumed it. Unchanged safe state is retried under a finite budget;
ordinary blocked walks may instead add a live blocker and request a new plan.
Interruptions are delegated through a typed adapter, so Pokémon battles do not
leak into the routing core.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.global_router import Coordinate
from pokemon_red_completion.route_plan import RoutePlan, RouteStep


class RouteExecutionError(RuntimeError):
    """Raised when live state cannot truthfully acknowledge a route."""


@dataclass(frozen=True, slots=True)
class TraversalResource:
    """One observed step-bounded resource used while a route is executing."""

    kind: str
    remaining: int | None
    carried_units: int | None

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("a traversal resource needs a kind")
        for name, value in (
            ("remaining", self.remaining),
            ("carried_units", self.carried_units),
        ):
            if value is not None and (type(value) is not int or value < 0):  # noqa: E721
                raise ValueError(f"{name} must be a non-negative integer or unknown")


@dataclass(frozen=True, slots=True)
class TraversalSnapshot:
    """The minimum live state the generic executor is allowed to consume."""

    map_id: int
    at: Coordinate
    ready: bool
    interruption: str | None = None
    mode: str | None = None
    occupied: frozenset[Coordinate] = frozenset()
    hazards: tuple[TraversalHazard, ...] = ()
    capabilities: frozenset[str] = frozenset()
    resources: tuple[TraversalResource, ...] = ()
    last_outside_map: int | None = None


@dataclass(frozen=True, slots=True)
class TraversalHazard:
    """A temporary semantic route constraint that is not solid occupancy."""

    at: Coordinate
    kind: str

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("a traversal hazard needs a kind")


@dataclass(frozen=True, slots=True)
class InterruptionReceipt:
    """Evidence that a title adapter restored overworld control."""

    kind: str
    resumed_map: int
    resumed_at: Coordinate
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("an interruption receipt needs a kind")


class RouteActionPort(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class TraversalObserver(Protocol):
    def observe(self) -> TraversalSnapshot: ...


class InterruptionHandler(Protocol):
    def handle(self, interruption: TraversalSnapshot) -> InterruptionReceipt: ...


@dataclass(frozen=True, slots=True)
class ResourceRenewalReceipt:
    """Evidence that a depleted route resource was restored in place."""

    kind: str
    map_id: int
    at: Coordinate
    before_remaining: int
    after_remaining: int
    units_consumed: int
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("a resource renewal needs a kind")
        if self.before_remaining != 0:
            raise ValueError("a resource may be renewed only at its observed zero boundary")
        if type(self.after_remaining) is not int or self.after_remaining <= 0:  # noqa: E721
            raise ValueError("a renewal must restore a positive remaining amount")
        if type(self.units_consumed) is not int or self.units_consumed <= 0:  # noqa: E721
            raise ValueError("a renewal must consume a positive carried quantity")


class RouteResourceManager(Protocol):
    def renew_if_needed(
        self,
        current: TraversalSnapshot,
    ) -> ResourceRenewalReceipt | None: ...


@dataclass(frozen=True, slots=True)
class ReplanRequest:
    """Current truth and accumulated blockers supplied to a route planner."""

    current: TraversalSnapshot
    goal_map: int
    goal_at: Coordinate
    blocked: Mapping[int, frozenset[Coordinate]]
    ordinal: int


class RouteReplanner(Protocol):
    def __call__(self, request: ReplanRequest) -> RoutePlan: ...


@dataclass(frozen=True, slots=True)
class RouteExecutionLimits:
    max_step_attempts: int = 8
    max_readiness_waits: int = 16
    max_interruptions: int = 8
    max_replans: int = 4
    max_resource_renewals: int = 8
    replan_after_unchanged: int = 2
    retry_wait_frames: int = 24
    readiness_wait_frames: int = 24
    transition_settle_frames: int = 120

    def __post_init__(self) -> None:
        for name, value in (
            ("max_step_attempts", self.max_step_attempts),
            ("max_readiness_waits", self.max_readiness_waits),
            ("max_interruptions", self.max_interruptions),
            ("max_replans", self.max_replans),
            ("max_resource_renewals", self.max_resource_renewals),
            ("replan_after_unchanged", self.replan_after_unchanged),
            ("retry_wait_frames", self.retry_wait_frames),
            ("readiness_wait_frames", self.readiness_wait_frames),
            ("transition_settle_frames", self.transition_settle_frames),
        ):
            if type(value) is not int or value <= 0:  # noqa: E721
                raise ValueError(f"{name} must be a positive integer")
        if self.replan_after_unchanged > self.max_step_attempts:
            raise ValueError("replanning cannot begin after the step-attempt budget")


DEFAULT_ROUTE_EXECUTION_LIMITS = RouteExecutionLimits()


@dataclass(frozen=True, slots=True)
class ExecutedRouteStep:
    step: RouteStep
    movement_requests: int
    interruption_count: int


@dataclass(frozen=True, slots=True)
class RouteReplanReceipt:
    """Why a candidate changed; only settled failed steps become durable."""

    ordinal: int
    map_id: int
    at: Coordinate
    # Kept for schema compatibility with the first route evidence. For a
    # ``visible_object`` receipt this is the temporary occupied coordinate
    # that caused the replan, not a permanently blacklisted square.
    newly_blocked: Coordinate
    replacement_steps: int
    reason: str = "settled_failed_step"


@dataclass(frozen=True, slots=True)
class RouteExecutionReport:
    initial_plan: RoutePlan
    terminal: TraversalSnapshot
    executed_steps: tuple[ExecutedRouteStep, ...]
    interruptions: tuple[InterruptionReceipt, ...]
    replans: tuple[RouteReplanReceipt, ...]
    movement_requests: int
    wait_actions: int
    resource_renewals: tuple[ResourceRenewalReceipt, ...] = ()

    @property
    def passed(self) -> bool:
        return (
            self.terminal.map_id == self.initial_plan.terminal_map
            and self.terminal.at == self.initial_plan.terminal_at
            and (
                self.initial_plan.terminal_mode is None
                or self.terminal.mode == self.initial_plan.terminal_mode
            )
            and self.terminal.interruption is None
        )


def execute_route(
    plan: RoutePlan,
    actions: RouteActionPort,
    observer: TraversalObserver,
    *,
    interruption_handler: InterruptionHandler | None = None,
    replanner: RouteReplanner | None = None,
    resource_manager: RouteResourceManager | None = None,
    limits: RouteExecutionLimits = DEFAULT_ROUTE_EXECUTION_LIMITS,
) -> RouteExecutionReport:
    """Execute until every movement is acknowledged or a bound fails closed."""

    current = observer.observe()
    _require_position(
        current,
        plan.macro_path.maps[0],
        plan.start_at,
        "route start",
        mode=plan.start_mode,
    )
    pending = list(plan.steps)
    executed: list[ExecutedRouteStep] = []
    interruptions: list[InterruptionReceipt] = []
    replans: list[RouteReplanReceipt] = []
    renewals: list[ResourceRenewalReceipt] = []
    blocked: dict[int, frozenset[Coordinate]] = {}
    movement_requests = 0
    wait_actions = 0

    while pending:
        step = pending[0]
        _require_position(
            current,
            step.source_map,
            step.source_at,
            "step source",
            mode=step.source_mode,
        )
        if resource_manager is not None:
            current, renewal = _renew_resource(
                current,
                observer,
                resource_manager,
            )
            if renewal is not None:
                if len(renewals) >= limits.max_resource_renewals:
                    raise RouteExecutionError("route exceeded its resource-renewal budget")
                renewals.append(renewal)
        current, new_receipts, waits = _wait_until_ready(
            current,
            actions,
            observer,
            interruption_handler,
            limits,
            used_interruptions=len(interruptions),
        )
        interruptions.extend(new_receipts)
        wait_actions += waits
        _require_position(
            current,
            step.source_map,
            step.source_at,
            "ready step source",
            mode=step.source_mode,
        )

        if (
            step.can_discover_blocker
            and step.expected_at in current.occupied
            and replanner is not None
            and len(replans) < limits.max_replans
        ):
            ordinal = len(replans) + 1
            replacement, replan_receipt = _request_replacement(
                plan,
                current,
                _with_live_constraints(blocked, current),
                ordinal,
                step.expected_at,
                "visible_object",
                replanner,
            )
            replans.append(replan_receipt)
            pending = list(replacement.steps)
            continue

        hazard = _hazard_at(current, step.expected_at)
        if (
            step.can_discover_blocker
            and hazard is not None
            and not _handler_resolves_hazard(interruption_handler, hazard)
            and replanner is not None
            and len(replans) < limits.max_replans
        ):
            ordinal = len(replans) + 1
            replacement, replan_receipt = _request_replacement(
                plan,
                current,
                _with_live_constraints(blocked, current),
                ordinal,
                step.expected_at,
                hazard.kind,
                replanner,
            )
            replans.append(replan_receipt)
            pending = list(replacement.steps)
            continue

        attempts = 0
        step_interruptions = 0
        replaced = False
        handled_hazard = (
            hazard
            if hazard is not None and _handler_resolves_hazard(interruption_handler, hazard)
            else None
        )
        while True:
            actions.execute(step.macro_action)
            movement_requests += 1
            attempts += 1
            observed = observer.observe()

            if (
                handled_hazard is not None
                and observed.interruption is None
                and _matches(
                    observed,
                    step.expected_map,
                    step.expected_at,
                    mode=step.expected_mode,
                )
            ):
                # Generation I trainer sight moves the player first and starts
                # its engagement script a few frames later.  A handler may
                # explicitly accept that semantic hazard; give the declared
                # interruption one bounded settle before acknowledging the
                # movement that entered it.
                _wait(actions, limits.transition_settle_frames)
                wait_actions += 1
                observed = observer.observe()

            if observed.interruption is not None:
                if len(interruptions) >= limits.max_interruptions:
                    raise RouteExecutionError("route exceeded its interruption budget")
                if interruption_handler is None:
                    raise RouteExecutionError(
                        f"unhandled route interruption {observed.interruption!r}"
                    )
                receipt = interruption_handler.handle(observed)
                interruptions.append(receipt)
                step_interruptions += 1
                observed = observer.observe()
                if observed.interruption is not None:
                    raise RouteExecutionError("interruption handler did not restore traversal")
                if (receipt.resumed_map, receipt.resumed_at) != (
                    observed.map_id,
                    observed.at,
                ):
                    raise RouteExecutionError(
                        "interruption receipt disagrees with resumed observation"
                    )

            crossed_map_before_coordinates = (
                not step.stays_on_map and observed.map_id == step.expected_map
            )
            declared_transient = (
                step.transient_at is not None
                and observed.map_id == step.source_map
                and observed.at == step.transient_at
                and observed.mode == step.source_mode
            )
            if crossed_map_before_coordinates or declared_transient:
                # A title adapter may declare an intermediate coordinate for a
                # single input (Gen I ledges publish the jumped tile first).
                # Map transitions can likewise publish the destination map
                # before coordinates settle. Neither is an acknowledgement
                # until one bounded wait exposes the exact terminal state.
                _wait(actions, limits.transition_settle_frames)
                wait_actions += 1
                observed = observer.observe()
                if observed.interruption is not None:
                    if len(interruptions) >= limits.max_interruptions:
                        raise RouteExecutionError("route exceeded its interruption budget")
                    if interruption_handler is None:
                        raise RouteExecutionError(
                            f"unhandled route interruption {observed.interruption!r}"
                        )
                    receipt = interruption_handler.handle(observed)
                    interruptions.append(receipt)
                    step_interruptions += 1
                    observed = observer.observe()
                    if observed.interruption is not None:
                        raise RouteExecutionError("interruption handler did not restore traversal")
                    if (receipt.resumed_map, receipt.resumed_at) != (
                        observed.map_id,
                        observed.at,
                    ):
                        raise RouteExecutionError(
                            "interruption receipt disagrees with resumed observation"
                        )

            if _matches(
                observed,
                step.expected_map,
                step.expected_at,
                mode=step.expected_mode,
            ):
                current = observed
                executed.append(
                    ExecutedRouteStep(
                        step=step,
                        movement_requests=attempts,
                        interruption_count=step_interruptions,
                    )
                )
                pending.pop(0)
                break

            if not _matches(
                observed,
                step.source_map,
                step.source_at,
                mode=step.source_mode,
            ):
                raise RouteExecutionError(
                    f"route drifted after {step.action}: expected "
                    f"{(step.expected_map, step.expected_at)}, observed "
                    f"{(observed.map_id, observed.at)}"
                )
            current = observed

            _wait(actions, limits.retry_wait_frames)
            wait_actions += 1
            current = observer.observe()
            current, new_receipts, waits = _wait_until_ready(
                current,
                actions,
                observer,
                interruption_handler,
                limits,
                used_interruptions=len(interruptions),
            )
            interruptions.extend(new_receipts)
            step_interruptions += len(new_receipts)
            wait_actions += waits
            if _matches(
                current,
                step.expected_map,
                step.expected_at,
                mode=step.expected_mode,
            ):
                executed.append(
                    ExecutedRouteStep(
                        step=step,
                        movement_requests=attempts,
                        interruption_count=step_interruptions,
                    )
                )
                pending.pop(0)
                break
            _require_position(
                current,
                step.source_map,
                step.source_at,
                "step retry",
                mode=step.source_mode,
            )

            if (
                step.can_discover_blocker
                and step.expected_at in current.occupied
                and replanner is not None
                and len(replans) < limits.max_replans
            ):
                ordinal = len(replans) + 1
                replacement, replan_receipt = _request_replacement(
                    plan,
                    current,
                    _with_live_constraints(blocked, current),
                    ordinal,
                    step.expected_at,
                    "visible_object",
                    replanner,
                )
                replans.append(replan_receipt)
                pending = list(replacement.steps)
                replaced = True
                break

            hazard = _hazard_at(current, step.expected_at)
            if (
                step.can_discover_blocker
                and hazard is not None
                and not _handler_resolves_hazard(interruption_handler, hazard)
                and replanner is not None
                and len(replans) < limits.max_replans
            ):
                ordinal = len(replans) + 1
                replacement, replan_receipt = _request_replacement(
                    plan,
                    current,
                    _with_live_constraints(blocked, current),
                    ordinal,
                    step.expected_at,
                    hazard.kind,
                    replanner,
                )
                replans.append(replan_receipt)
                pending = list(replacement.steps)
                replaced = True
                break
            if hazard is not None and _handler_resolves_hazard(interruption_handler, hazard):
                handled_hazard = hazard

            # Only infer a live blocker after the input has had a bounded
            # chance to finish.  Gen I can leave the source coordinates
            # visible while a walk animation is in flight; replanning before
            # this settle would incorrectly blacklist a reachable square.
            if (
                step.can_discover_blocker
                and replanner is not None
                and attempts >= limits.replan_after_unchanged
                and len(replans) < limits.max_replans
            ):
                map_blocked = blocked.get(step.source_map, frozenset()) | {step.expected_at}
                blocked[step.source_map] = frozenset(map_blocked)
                ordinal = len(replans) + 1
                replacement, replan_receipt = _request_replacement(
                    plan,
                    current,
                    _with_live_constraints(blocked, current),
                    ordinal,
                    step.expected_at,
                    "settled_failed_step",
                    replanner,
                )
                replans.append(replan_receipt)
                pending = list(replacement.steps)
                replaced = True
                break

            if attempts >= limits.max_step_attempts:
                raise RouteExecutionError(
                    f"route step {step.action} at {step.source_at} exceeded "
                    f"{limits.max_step_attempts} attempts"
                )

        if replaced:
            continue

    if resource_manager is not None:
        current, renewal = _renew_resource(
            current,
            observer,
            resource_manager,
        )
        if renewal is not None:
            if len(renewals) >= limits.max_resource_renewals:
                raise RouteExecutionError("route exceeded its resource-renewal budget")
            renewals.append(renewal)
    current, new_receipts, waits = _wait_until_ready(
        current,
        actions,
        observer,
        interruption_handler,
        limits,
        used_interruptions=len(interruptions),
    )
    interruptions.extend(new_receipts)
    wait_actions += waits
    _require_position(
        current,
        plan.terminal_map,
        plan.terminal_at,
        "route terminal",
        mode=plan.terminal_mode,
    )
    report = RouteExecutionReport(
        initial_plan=plan,
        terminal=current,
        executed_steps=tuple(executed),
        interruptions=tuple(interruptions),
        replans=tuple(replans),
        movement_requests=movement_requests,
        wait_actions=wait_actions,
        resource_renewals=tuple(renewals),
    )
    if not report.passed:
        raise RouteExecutionError("route report failed its terminal contract")
    return report


def _renew_resource(
    current: TraversalSnapshot,
    observer: TraversalObserver,
    manager: RouteResourceManager,
) -> tuple[TraversalSnapshot, ResourceRenewalReceipt | None]:
    receipt = manager.renew_if_needed(current)
    if receipt is None:
        return current, None
    observed = observer.observe()
    if (receipt.map_id, receipt.at) != (current.map_id, current.at):
        raise RouteExecutionError("resource receipt disagrees with its source position")
    if (observed.map_id, observed.at) != (current.map_id, current.at):
        raise RouteExecutionError("resource renewal moved the player")
    if observed.interruption is not None:
        raise RouteExecutionError("resource renewal left an active interruption")
    resource = next((item for item in observed.resources if item.kind == receipt.kind), None)
    if resource is None or resource.remaining != receipt.after_remaining:
        raise RouteExecutionError("resource receipt disagrees with renewed observation")
    return observed, receipt


def _with_live_constraints(
    durable: Mapping[int, frozenset[Coordinate]],
    current: TraversalSnapshot,
) -> dict[int, frozenset[Coordinate]]:
    combined = dict(durable)
    current_constraints = current.occupied | frozenset(item.at for item in current.hazards)
    if current_constraints:
        combined[current.map_id] = combined.get(current.map_id, frozenset()) | current_constraints
    return combined


def _hazard_at(snapshot: TraversalSnapshot, at: Coordinate) -> TraversalHazard | None:
    return next((item for item in snapshot.hazards if item.at == at), None)


def _handler_resolves_hazard(
    handler: InterruptionHandler | None,
    hazard: TraversalHazard,
) -> bool:
    """Require an explicit handler capability before entering a known hazard."""

    if handler is None:
        return False
    kinds: object = getattr(handler, "handled_hazard_kinds", frozenset())
    return isinstance(kinds, frozenset) and hazard.kind in kinds


def _request_replacement(
    plan: RoutePlan,
    current: TraversalSnapshot,
    blocked: Mapping[int, frozenset[Coordinate]],
    ordinal: int,
    newly_blocked: Coordinate,
    reason: str,
    replanner: RouteReplanner,
) -> tuple[RoutePlan, RouteReplanReceipt]:
    replacement = replanner(
        ReplanRequest(
            current=current,
            goal_map=plan.terminal_map,
            goal_at=plan.terminal_at,
            blocked=dict(blocked),
            ordinal=ordinal,
        )
    )
    _require_position(
        current,
        replacement.macro_path.maps[0],
        replacement.start_at,
        "replacement route start",
        mode=replacement.start_mode,
    )
    if (
        replacement.terminal_map != plan.terminal_map
        or replacement.terminal_at != plan.terminal_at
        or replacement.terminal_mode != plan.terminal_mode
    ):
        raise RouteExecutionError("replacement route changed the declared goal")
    return replacement, RouteReplanReceipt(
        ordinal=ordinal,
        map_id=current.map_id,
        at=current.at,
        newly_blocked=newly_blocked,
        replacement_steps=len(replacement.steps),
        reason=reason,
    )


def _wait_until_ready(
    initial: TraversalSnapshot,
    actions: RouteActionPort,
    observer: TraversalObserver,
    interruption_handler: InterruptionHandler | None,
    limits: RouteExecutionLimits,
    *,
    used_interruptions: int,
) -> tuple[TraversalSnapshot, tuple[InterruptionReceipt, ...], int]:
    current = initial
    receipts: list[InterruptionReceipt] = []
    waits = 0
    for _ in range(limits.max_readiness_waits + 1):
        if current.interruption is not None:
            if used_interruptions + len(receipts) >= limits.max_interruptions:
                raise RouteExecutionError("route exceeded its interruption budget")
            if interruption_handler is None:
                raise RouteExecutionError(f"unhandled route interruption {current.interruption!r}")
            receipt = interruption_handler.handle(current)
            receipts.append(receipt)
            current = observer.observe()
            if current.interruption is not None:
                raise RouteExecutionError("interruption handler did not restore traversal")
            if (receipt.resumed_map, receipt.resumed_at) != (
                current.map_id,
                current.at,
            ):
                raise RouteExecutionError("interruption receipt disagrees with resumed observation")
            continue
        if current.ready:
            return current, tuple(receipts), waits
        _wait(actions, limits.readiness_wait_frames)
        waits += 1
        current = observer.observe()
    raise RouteExecutionError("route never regained input readiness")


def _wait(actions: RouteActionPort, frames: int) -> None:
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _matches(
    snapshot: TraversalSnapshot,
    map_id: int,
    at: Coordinate,
    *,
    mode: str | None = None,
) -> bool:
    return (
        snapshot.map_id == map_id and snapshot.at == at and (mode is None or snapshot.mode == mode)
    )


def _require_position(
    snapshot: TraversalSnapshot,
    map_id: int,
    at: Coordinate,
    label: str,
    *,
    mode: str | None = None,
) -> None:
    if not _matches(snapshot, map_id, at, mode=mode):
        raise RouteExecutionError(
            f"{label} expected {(map_id, at, mode)}, observed "
            f"{(snapshot.map_id, snapshot.at, snapshot.mode)}"
        )
