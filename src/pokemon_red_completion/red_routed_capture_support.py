"""Bind one capability-derived PC preparation before the already selected goal."""
from __future__ import annotations

from dataclasses import asdict, replace
from typing import TYPE_CHECKING

from pokemon_red_completion.capture_support import CaptureSupportSummary
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_capture_party import (
    RedCapturePartyError,
    execute_capture_party_at_pc,
    plan_capture_party,
)
from pokemon_red_completion.red_dual_capability_curriculum_runtime import dependency_specimen_ledger
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_goal_skills import _POKEMON_CENTER_MAPS, prepare_center_departure
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.route_executor import InterruptionHandler, execute_route
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError

if TYPE_CHECKING:
    from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter


def bind_capture_party_support(
    router: RedResourceGoalRouter, bindings: GoalBindingSet, observation: RedGoalObservation,
) -> GoalBindingSet:
    """Planning is action-free; a selected acquisition keeps the same destination.

    Re-observe/rebind after PC work because the old origin is no longer true.
    Never re-query the policy, change the selected goal, or fit a setup row.
    """
    original = next((b for b in bindings.bindings if b.kind is GoalKind.ACQUIRE_SPECIES), None)
    if original is None:
        return bindings
    runtime = router.runtime
    capture_spec = next(s for s in runtime.profile.providers if s.kind is original.kind)
    source_ref = f"pokemon.red:acquisition:{capture_spec.parameters['source_id']}"
    box = runtime.reader.read_current_box_state()
    try:
        plan = plan_capture_party(
            observation.party, runtime.reader.read_current_box_move_members(),
            box_index=box.box_index,
        )
    except RedCapturePartyError:
        return _without_capture(bindings, original)
    if plan is None:
        return bindings
    from pokemon_red_completion.red_resource_goal_router import _ROUTE_LIMITS, _walking_plan

    traversal = Gen1TraversalObserver(runtime.reader)
    start = traversal.observe()
    routes: list[RoutePlan] = []
    current_map = getattr(start, "map_id", None)
    centers = ((current_map,) if current_map in _POKEMON_CENTER_MAPS
               else sorted(_POKEMON_CENTER_MAPS))
    for center in centers:
        try:
            route = router.plan_feasible_to_map(start, int(center), goal_at=(4, 13))
        except RoutePlanningError:
            continue
        if _walking_plan(route):
            routes.append(route)
    if not routes:
        return _without_capture(bindings, original)
    route = min(routes, key=lambda value: (len(value.steps), value.terminal_map))
    executed: list[tuple[ExecutableGoalBinding, GoalExecutionReport]] = []
    claimed = False

    def execute() -> GoalExecutionReport:
        nonlocal claimed
        if claimed:
            raise RedCapturePartyError("capture preparation binding was already consumed")
        claimed = True
        action_start, frame_start = router.actions.actions_executed, runtime.emulator.frame_count
        before = dependency_specimen_ledger(runtime.adapter.observe().collection_observation)
        prepare_center_departure(router.actions, runtime.reader)
        interruption_handler: InterruptionHandler = Gen1RouteInterruptionHandler(
            router.actions, runtime.reader, maximum_flees=16, maximum_trainer_battles=8,
            stabilization_frames=180, route_name="bounded capture-helper PC access",
        )
        if getattr(router, "routed_recovery", False):
            from pokemon_red_completion.red_routed_recovery import guarded_collection_route_handler
            interruption_handler = guarded_collection_route_handler(
                router.actions, runtime.reader, route_name="guarded capture-helper PC access",
            )
        transport = execute_route(
            route, router.actions, traversal,
            interruption_handler=interruption_handler,
            replanner=router._replan, limits=_ROUTE_LIMITS,
        )
        if not transport.passed:
            raise RedCapturePartyError("capture-helper PC route failed")
        recovery_kwargs = {}
        if getattr(router, "routed_recovery", False):
            from pokemon_red_completion.red_capture_helper_recovery import restore_capture_helper

            recovery_kwargs["restore_helper"] = lambda: restore_capture_helper(router)
        setup = execute_capture_party_at_pc(
            plan, router.actions, runtime.reader, pc_map_id=route.terminal_map,
            read_party=PokemonRedPartyReader(runtime.emulator).read,
            **recovery_kwargs,
        )
        fresh = runtime.adapter.observe()
        if dependency_specimen_ledger(fresh.collection_observation) != before:
            raise RedCapturePartyError("PC preparation changed the complete living collection")
        successor = replace(router, prepare_capture_party=False)
        if getattr(router, "routed_recovery", False):
            successor = replace(successor, prepare_capture_escort=True)
        rebound = successor.enumerate(fresh)
        selected = next((b for b in rebound.bindings if b.kind is original.kind), None)
        if selected is None or not (
            selected.search_source_ref == source_ref
            or selected.binding_ref == source_ref
            or selected.binding_ref.startswith(f"{source_ref}:profile-")
        ):
            raise RedCapturePartyError("capture preparation lost its selected source")
        report = selected.execute()
        executed.append((selected, report))
        summary = (
            CaptureSupportSummary.from_evidence(report.evidence) or CaptureSupportSummary(0, 0)
        )
        summary = replace(summary, party_preparations=1)
        return GoalExecutionReport(
            actions_executed=router.actions.actions_executed-action_start,
            frames_executed=runtime.emulator.frame_count-frame_start,
            evidence={**report.evidence, **setup, "capture_support": summary.public_dict()},
        )

    def verify(_report: GoalExecutionReport) -> GoalVerification:
        if len(executed) != 1:
            raise RedCapturePartyError("capture preparation has no completed underlying execution")
        selected, report = executed[0]
        return selected.verify(report)

    supported = replace(
        original, execute=execute, verify=verify,
        binding_ref=f"{original.binding_ref}:capture-support:{canonical_sha256(asdict(plan))}",
        search_source_ref=source_ref,
        estimated_effort=min(1.0, original.estimated_effort + 0.1 + len(route.steps)/1_000),
    )
    return GoalBindingSet(
        tuple(supported.opportunity if item.binding_ref == original.binding_ref else item
              for item in bindings.opportunities),
        tuple(supported if item.binding_ref == original.binding_ref else item
              for item in bindings.bindings),
    )


def _without_capture(bindings: GoalBindingSet, original: ExecutableGoalBinding) -> GoalBindingSet:
    """Missing preparation masks capture, not unrelated recovery/resupply goals."""
    return GoalBindingSet(
        tuple(replace(item, availability=GoalAvailability.UNAVAILABLE,
                      estimated_effort=None, estimated_risk=None,
                      unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY)
              if item.binding_ref == original.binding_ref else item
              for item in bindings.opportunities),
        tuple(item for item in bindings.bindings if item.binding_ref != original.binding_ref),
    )
