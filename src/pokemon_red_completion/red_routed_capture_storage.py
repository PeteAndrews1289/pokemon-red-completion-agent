"""Reserve active-box capacity before a selected one-capture goal.

This is deterministic skill preparation, not another policy choice. Capture
helper preparation wraps this binding so needed boxed helpers are retrieved
before rotation. After any movement, rebind the original source from reality.
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_dual_capability_curriculum_runtime import dependency_specimen_ledger
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_goal_skills import (
    _POKEMON_CENTER_MAPS,
    RedAreaSurveyGoalProvider,
    prepare_center_departure,
)
from pokemon_red_completion.red_pc_storage import face_pc_boundary, open_bills_pc, switch_box
from pokemon_red_completion.red_routed_capture_support import _without_capture
from pokemon_red_completion.red_team_training import close_menu
from pokemon_red_completion.route_executor import execute_route
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError

if TYPE_CHECKING:
    from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter


class RedCaptureStorageError(RuntimeError):
    """Storage preparation cannot preserve the selected goal and collection."""


def bind_capture_storage_support(
    router: RedResourceGoalRouter, bindings: GoalBindingSet, observation: RedGoalObservation,
) -> GoalBindingSet:
    """Action-free offer; leave one spare slot after the declared single capture.

    Full boxes already mask acquisition in the underlying provider. This seam
    prevents the last-slot dead end; it does not claim arbitrary cross-box
    retrieval or recovery from an already-full active box.
    """
    original = next((b for b in bindings.bindings if b.kind is GoalKind.ACQUIRE_SPECIES), None)
    if original is None or observation.immediate_capture_slots >= 2:
        return bindings
    runtime = router.runtime
    provider = runtime.provider_for(GoalKind.ACQUIRE_SPECIES, router.actions)
    if (
        not isinstance(provider, RedAreaSurveyGoalProvider)
        or provider.policy.capture_quota != 1
        or observation.immediate_capture_slots != 1
    ):
        return _without_capture(bindings, original)
    collection = observation.collection_observation
    initial_box, initial_counts = collection.current_box_index, collection.box_counts
    initial_headroom = observation.immediate_capture_slots
    targets = [index for index, count in enumerate(collection.box_counts)
               if index != collection.current_box_index and collection.box_capacity - count >= 2]
    if not targets:
        return _without_capture(bindings, original)
    target = min(targets, key=lambda index: (collection.box_counts[index], index))
    source_ref = f"pokemon.red:acquisition:{provider.source_id}"
    if not (
        original.search_source_ref == source_ref or original.binding_ref == source_ref
        or original.binding_ref.startswith(f"{source_ref}:profile-")
    ):
        return _without_capture(bindings, original)
    from pokemon_red_completion.red_resource_goal_router import _ROUTE_LIMITS, _walking_plan

    traversal = Gen1TraversalObserver(runtime.reader)
    start = traversal.observe()
    routes: list[RoutePlan] = []
    for center in sorted(_POKEMON_CENTER_MAPS):
        try:
            route = router.world.plan_feasible_to_map(start, int(center), goal_at=(4, 13))
        except RoutePlanningError:
            continue
        if _walking_plan(route):
            routes.append(route)
    if not routes:
        return _without_capture(bindings, original)
    route = min(routes, key=lambda value: (len(value.steps), value.terminal_map))
    initial_ledger = dependency_specimen_ledger(collection)
    executed: list[tuple[ExecutableGoalBinding, GoalExecutionReport]] = []
    claimed = False

    def execute() -> GoalExecutionReport:
        nonlocal claimed
        if claimed:
            raise RedCaptureStorageError("capture storage binding was already consumed")
        claimed = True
        current = runtime.adapter.observe()
        if (
            traversal.observe() != start
            or current.collection_observation.current_box_index != initial_box
            or current.collection_observation.box_counts != initial_counts
            or dependency_specimen_ledger(current.collection_observation) != initial_ledger
            or current.immediate_capture_slots != 1
        ):
            raise RedCaptureStorageError("capture storage plan changed before input")
        action_start, frame_start = router.actions.actions_executed, runtime.emulator.frame_count
        prepare_center_departure(router.actions, runtime.reader)
        transport = execute_route(
            route, router.actions, traversal,
            interruption_handler=Gen1RouteInterruptionHandler(
                router.actions, runtime.reader, maximum_flees=16, maximum_trainer_battles=8,
                stabilization_frames=180, route_name="bounded capture-storage PC access",
            ),
            replanner=router._replan, limits=_ROUTE_LIMITS,
        )
        at_pc = runtime.adapter.observe()
        if (
            not transport.passed
            or (at_pc.raw.map_id, at_pc.raw.player_y, at_pc.raw.player_x)
            != (route.terminal_map, 4, 13)
            or at_pc.raw.battle_state or not at_pc.input_ready
            or at_pc.collection_observation.current_box_index != initial_box
            or at_pc.collection_observation.box_counts != initial_counts
            or dependency_specimen_ledger(at_pc.collection_observation) != initial_ledger
        ):
            raise RedCaptureStorageError("capture storage route or collection differs")
        bag, money = at_pc.raw.bag_items, at_pc.raw.player_money
        face_pc_boundary(router.actions, runtime.reader, "up")
        open_bills_pc(router.actions, runtime.reader)
        report = switch_box(router.actions, runtime.reader, target_box_index=target)
        close_menu(router.actions, runtime.reader)
        fresh = runtime.adapter.observe()
        if (
            not report.passed
            or fresh.collection_observation.current_box_index != target
            or dependency_specimen_ledger(fresh.collection_observation) != initial_ledger
            or fresh.immediate_capture_slots < 2
            or fresh.raw.bag_items != bag or fresh.raw.player_money != money
            or fresh.raw.battle_state or not fresh.input_ready
        ):
            raise RedCaptureStorageError("capture storage preparation was not preserved")
        rebound = replace(router, prepare_capture_storage=False).enumerate(fresh)
        selected = next((b for b in rebound.bindings if b.kind is original.kind), None)
        if selected is None or not (
            selected.search_source_ref == source_ref
            or selected.binding_ref == source_ref
            or selected.binding_ref.startswith(f"{source_ref}:profile-")
        ):
            raise RedCaptureStorageError("capture storage preparation lost its selected source")
        prepared_headroom = fresh.immediate_capture_slots
        preparation_actions = router.actions.actions_executed - action_start
        preparation_frames = runtime.emulator.frame_count - frame_start
        result = selected.execute()
        executed.append((selected, result))
        return GoalExecutionReport(
            router.actions.actions_executed - action_start,
            runtime.emulator.frame_count - frame_start,
            {**result.evidence, "storage_preparation": {
                "box_rotations": 1, "initial_headroom": initial_headroom,
                "prepared_headroom": prepared_headroom,
                "collection_preserved": True, "setup_training_rows": 0,
                "actions_executed": preparation_actions, "frames_executed": preparation_frames,
            }},
        )

    def verify(_report: GoalExecutionReport) -> GoalVerification:
        if len(executed) != 1:
            raise RedCaptureStorageError("storage preparation has no executed acquisition")
        selected, report = executed[0]
        if runtime.adapter.observe().immediate_capture_slots < 1:
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return selected.verify(report)

    supported = replace(
        original, execute=execute, verify=verify,
        binding_ref=f"{original.binding_ref}:storage-support:{canonical_sha256({'box': target})}",
        search_source_ref=source_ref,
        estimated_effort=min(1.0, original.estimated_effort + .1 + len(route.steps) / 1_000),
    )
    return GoalBindingSet(
        tuple(supported.opportunity if item.binding_ref == original.binding_ref else item
              for item in bindings.opportunities),
        tuple(supported if item.binding_ref == original.binding_ref else item
              for item in bindings.bindings),
    )
