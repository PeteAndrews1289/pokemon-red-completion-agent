"""Opt-in cartridge route plus fresh, source-bound static acquisition.

The model selects the whole acquisition; transport is mechanical support.
No route strings, trainer fallback, puzzle bypass or automatic ball purchase.
Offers are read-only. A current-map occupancy refresh does not invent cleared
guards or solved puzzles on maps which have not been observed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256

from .gen1_field_moves import Gen1FieldMovePort
from .gen1_route_runtime import Gen1WildFleeHandler
from .goal_manager import GoalFailureReason, GoalKind, GoalUnavailableReason
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .provenance import canonical_sha256
from .red_goal_manager import RedGoalBindingOffer
from .red_living_dex_setup_source import red_living_dex_setup_fresh_observation_sha256
from .red_resource_goal_router import _supported_plan
from .red_routed_semantic_goal import (
    FreshRedGoalObservation,
    RedFreshGoalDestinationBinder,
    RedSemanticTransportRoute,
    build_red_routed_semantic_goal_composer,
)
from .red_static_capture import observe_static_capture, red_static_capture_targets
from .red_static_capture_goal import RedStaticCaptureGoalProvider
from .route_executor import DEFAULT_ROUTE_EXECUTION_LIMITS
from .route_plan import RoutePlanningError
from .routed_semantic_goal import RoutedSemanticGoalLimits


def _prepared_route_recovery_report(runtime, actions, loss, counters):
    """Retain a typed native route setback without executing its capture target."""
    from .red_routed_recovery import settled_route_field_recovery_evidence
    from .route_executor import RouteExecutionFailureReport, RouteExecutionFailureReason
    from .route_plan import RoutePlan

    failure, proof = loss.failure, loss.evidence
    after = runtime.adapter.observe()
    count = actions.actions_executed - counters[0]
    frames = runtime.emulator.frame_count - counters[1]
    if (not isinstance(failure, RouteExecutionFailureReport)
        or not isinstance(failure.initial_plan, RoutePlan)
        or failure.reason is not RouteExecutionFailureReason.INTERRUPTION_UNRECOVERED
        or not settled_route_field_recovery_evidence(proof)
        or not after.input_ready or after.raw.battle_state != 0
        or runtime.emulator.pressed_buttons
        or sha256(runtime.emulator.save_state_bytes()).hexdigest() != proof['terminal_sha256']
        or list(after.raw.party_hp or ()) != proof['party_hp']
        or after.raw.player_money != proof['cash_after']
        or count < loss.report.actions_executed or frames < loss.report.frames_executed):
        raise loss
    return GoalExecutionReport(count, frames, dict(
        schema='pokemon.core.routed-semantic-goal-report.v1',
        destination_kind=GoalKind.ACQUIRE_SPECIES.value,
        route_verified=False, destination_bound=False, destination_executed=False,
        budget_reconciled=True, within_budget=True, route_is_policy_kind=False,
        private_binding_fields=0, private_route_fields=0,
        route_setback=dict(proof), prepared_static_capture_not_executed=True,
        acknowledged_steps=len(failure.executed_steps),
        movement_requests=failure.movement_requests,wait_actions=failure.wait_actions,
    ))


def prepared_static_acquisition_binding(
    runtime, actions, *, rom, target, execute_prepared, verify_return,
    estimated_effort, estimated_risk,
    allow_route16_snorlax=False,
):
    """Expose a prepared route/capture/return recipe without choosing its target.

    The caller authenticates and quotes an existing executable recipe. It may
    supply mechanical preparation, but only selected execution calls it. Native
    registration, source consumption and the original-party return are required
    before success; the recipe cannot certify itself with a label alone.
    """
    if type(allow_route16_snorlax) is not bool:
        raise ValueError("Route16 source permission must be Boolean")
    targets = red_static_capture_targets(rom)
    if allow_route16_snorlax:
        from .red_snorlax_capture import route16_snorlax_target

        targets = (*targets, route16_snorlax_target(rom))
    if target not in targets:
        raise ValueError("prepared acquisition target differs from cartridge")
    if not callable(execute_prepared) or not callable(verify_return):
        raise TypeError("prepared acquisition needs execution and return verification")
    observation = runtime.adapter.observe()
    source = runtime.emulator.save_state_bytes()
    counters = (actions.actions_executed, runtime.emulator.frame_count)
    availability = observe_static_capture(runtime.reader, target)
    if (
        availability.registered or availability.consumed
        or observation.raw.battle_state or not observation.input_ready
        or runtime.emulator.pressed_buttons
    ):
        return None
    owned = runtime.reader.read_pokedex_state().owned_species
    used = False
    report = terminal = None
    recovered_route = False

    def execute():
        nonlocal used, report, terminal, recovered_route
        if used or (
            runtime.emulator.save_state_bytes() != source
            or runtime.adapter.observe() != observation
            or (actions.actions_executed, runtime.emulator.frame_count) != counters
        ):
            raise RuntimeError("prepared acquisition source changed or was already attempted")
        used = True
        from .red_routed_recovery import SettledNativeFieldRecovery
        try:
            inner = execute_prepared(target)
        except SettledNativeFieldRecovery as loss:
            # Only an attached, independently verified native route failure is
            # eligible. Its capture target must remain entirely unexecuted.
            status = observe_static_capture(runtime.reader, target)
            if (status.registered or status.consumed
                or runtime.reader.read_pokedex_state().owned_species != owned):
                raise
            report = _prepared_route_recovery_report(runtime, actions, loss, counters)
            terminal = runtime.emulator.save_state_bytes()
            recovered_route = True
            return report
        if not isinstance(inner, GoalExecutionReport):
            raise TypeError("prepared acquisition needs a native execution report")
        report = GoalExecutionReport(
            actions.actions_executed - counters[0],
            runtime.emulator.frame_count - counters[1],
            dict(
                mechanic="prepared_static_acquisition",
                native_capture=dict(inner.evidence),
                learned_preparation=False,
                learned_ball_selection=False,
                transport_and_return="declared mechanical support",
            ),
        )
        terminal = runtime.emulator.save_state_bytes()
        return report

    def verify(candidate_report):
        after = runtime.adapter.observe()
        status = observe_static_capture(runtime.reader, target)
        if recovered_route:
            proof = report.evidence['route_setback']
            if (candidate_report is report and runtime.emulator.save_state_bytes() == terminal
                and not runtime.emulator.pressed_buttons and after.input_ready
                and after.raw.battle_state == 0 and not status.registered and not status.consumed
                and runtime.reader.read_pokedex_state().owned_species == owned
                and list(after.raw.party_hp or ()) == proof['party_hp']
                and after.raw.player_money == proof['cash_after']):
                return GoalVerification.failed(GoalFailureReason.RECOVERY_REQUIRED)
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if (
            used and candidate_report is report and terminal is not None
            and runtime.emulator.save_state_bytes() == terminal
            and not runtime.emulator.pressed_buttons
            and after.input_ready and not after.raw.battle_state
            and status.registered and status.consumed
            and runtime.reader.read_pokedex_state().owned_species == owned | {target.species_number}
            and verify_return() is True
        ):
            return GoalVerification.succeeded()
        return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

    binding = ExecutableGoalBinding(
        binding_ref=f"red-prepared-static:{sha256(source).hexdigest()}:{canonical_sha256(asdict(target))}",
        kind=GoalKind.ACQUIRE_SPECIES,
        estimated_effort=estimated_effort, estimated_risk=estimated_risk,
        execute=execute, verify=verify,
        search_source_ref=f"pokemon.red:static-capture:{target.map_id}:{target.object_index}",
    )
    if runtime.emulator.save_state_bytes() != source or (
        actions.actions_executed, runtime.emulator.frame_count
    ) != counters:
        raise RuntimeError("prepared acquisition discovery changed the game")
    return binding


@dataclass(frozen=True, slots=True)
class RedRoutedStaticCaptureGoalProvider:
    capture: RedStaticCaptureGoalProvider
    world: object
    traversal_observer: object
    maximum_route_steps: int = 1500
    maximum_actions: int = 6000
    maximum_frames: int = 600000
    maximum_flees: int = 32
    kind: GoalKind = GoalKind.ACQUIRE_SPECIES

    def __post_init__(self):
        if not isinstance(self.capture, RedStaticCaptureGoalProvider):
            raise TypeError("static approach requires the source-bound capture provider")
        if not self.capture.prepare_facing or self.kind is not GoalKind.ACQUIRE_SPECIES:
            raise ValueError("routed static acquisition requires explicit facing support")
        for name in ("maximum_route_steps", "maximum_actions", "maximum_frames", "maximum_flees"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError("static approach requires finite positive limits")

    def offer(self, observation):
        p = self.capture
        if observation != p.adapter.observe():
            raise ValueError("static approach offered from stale goal state")
        original = p.emulator.save_state_bytes()
        counters = (p.actions.actions_executed, p.emulator.frame_count)
        status = observe_static_capture(p.reader, p.target)
        raw = p.reader.read()

        def unavailable(reason):
            return RedGoalBindingOffer.unavailable(self.kind, reason)

        if status.registered or status.consumed:
            return unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
        if p.readiness_budget is not None:
            from .red_capture_readiness import assess_capture_readiness

            readiness = assess_capture_readiness(
                observation, p.readiness_budget, target_available=True,
                enemy_species_id=p.target.internal_species,
            )
            if readiness.hard_blocks:
                return unavailable(GoalUnavailableReason.MISSING_RESOURCE)
        if p.checkpoint_directory.exists() or raw.battle_state or not observation.input_ready:
            return unavailable(GoalUnavailableReason.TEMPORARILY_BLOCKED)
        if (
            dict(raw.bag_items or ()).get(int(p.ball), 0) < p.max_throws
            or raw.party_hp is None
            or not any(hp > 0 for hp in raw.party_hp)
        ):
            return unavailable(GoalUnavailableReason.MISSING_RESOURCE)
        boxes = p.reader.read_all_box_states()
        if raw.party_count == 6 and len(boxes.boxes[boxes.current_box_index].species_ids) >= 20:
            return unavailable(GoalUnavailableReason.STORAGE_BLOCKED)
        local = p.offer(observation)
        if local.binding is not None:
            return local
        start = self.traversal_observer.observe()
        if not start.ready or start.interruption is not None:
            return unavailable(GoalUnavailableReason.TEMPORARILY_BLOCKED)
        world = self.world.with_current_observation(p.reader)
        plans = []
        for dy, dx in ((1, 0), (0, -1), (0, 1), (-1, 0)):
            at = (p.target.at[0] + dy, p.target.at[1] + dx)
            if min(at) < 0:
                continue
            try:
                plan = world.plan_feasible_to_map(start, p.target.map_id, goal_at=at)
            except RoutePlanningError:
                continue
            if (
                plan.steps
                and len(plan.steps) <= self.maximum_route_steps
                and plan.terminal_mode in (None, "land")
                and _supported_plan(plan, allow_cut=True, allow_surf=True, seafoam_state=raw)
            ):
                plans.append(plan)
        if not plans:
            return unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        plan = min(plans, key=lambda q: (len(q.steps), q.terminal_at))
        origin = sha256(original).hexdigest()
        configuration = canonical_sha256(
            {
                "capture": p.configuration_sha256,
                "steps": [asdict(step) for step in plan.steps],
                "maximum_actions": self.maximum_actions,
                "maximum_frames": self.maximum_frames,
                "maximum_flees": self.maximum_flees,
            }
        )
        port = Gen1FieldMovePort(
            p.actions,
            p.reader,
            p.emulator,
            cut_block_swaps={x.before: x.after for x in world.rules.cut_block_swaps},
        )

        def replan(request):
            updated = world.with_current_observation(p.reader)
            replacement = updated.replanner()(request)
            if not _supported_plan(
                replacement, allow_cut=True, allow_surf=True, seafoam_state=p.reader.read()
            ):
                raise RoutePlanningError("static approach replan needs unsupported mechanics")
            return replacement

        transport = RedSemanticTransportRoute(
            binding_ref=f"red-static-route:{origin}:{configuration}",
            origin_observation_sha256=origin,
            planner_binding_sha256=configuration,
            plan=plan,
            actions=p.actions,
            traversal_observer=self.traversal_observer,
            emulator=p.emulator,
            interruption_handler=Gen1WildFleeHandler(
                port,
                p.reader,
                maximum_flees=self.maximum_flees,
                stabilization_frames=120,
                route_name="model-selected static acquisition approach",
            ),
            replanner=replan,
            field_actions=port,
            route_limits=replace(
                DEFAULT_ROUTE_EXECUTION_LIMITS, max_interruptions=self.maximum_flees, max_replans=16
            ),
        )

        def observe_fresh():
            fresh = FreshRedGoalObservation(
                "0" * 64, p.adapter.observe(), self.traversal_observer.observe()
            )
            return replace(
                fresh, observation_sha256=red_living_dex_setup_fresh_observation_sha256(fresh)
            )

        destination = RedFreshGoalDestinationBinder(
            self.kind, transport.terminal_boundary, observe_fresh, p
        )
        binding = build_red_routed_semantic_goal_composer(
            binding_ref=f"red-static-acquisition:{origin}:{configuration}",
            transport=transport,
            destination=destination,
            estimated_effort=min(1.0, p.estimated_effort + len(plan.steps) / 1000),
            estimated_risk=p.estimated_risk,
            limits=RoutedSemanticGoalLimits(self.maximum_actions, self.maximum_frames),
        ).binding()

        def execute():
            if (
                p.emulator.save_state_bytes() != original
                or (p.actions.actions_executed, p.emulator.frame_count) != counters
                or p.adapter.observe() != observation
            ):
                raise RuntimeError("static acquisition route source changed before input")
            return binding.execute()

        if (
            p.emulator.save_state_bytes() != original
            or (p.actions.actions_executed, p.emulator.frame_count) != counters
        ):
            raise RuntimeError("static acquisition route offer changed the game")
        return RedGoalBindingOffer.available(
            replace(
                binding,
                execute=execute,
                search_source_ref=f"pokemon.red:static-capture:{p.target.map_id}:{p.target.object_index}",
            )
        )
