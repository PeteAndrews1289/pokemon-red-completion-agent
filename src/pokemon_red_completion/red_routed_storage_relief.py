"""Route to a PC and recover capture capacity from an already-full box."""
from __future__ import annotations

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
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    dependency_specimen_ledger,
)
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_goal_skills import (
    _POKEMON_CENTER_MAPS,
    RedBoxSwitchGoalProvider,
    prepare_center_departure,
)
from pokemon_red_completion.red_pc_storage import face_pc_boundary
from pokemon_red_completion.route_executor import InterruptionHandler, execute_route
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError

if TYPE_CHECKING:
    from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter


class RedRoutedStorageReliefError(RuntimeError):
    """A routed box switch cannot preserve its declared starting state."""


def bind_routed_storage_relief(
    router: RedResourceGoalRouter,
    bindings: GoalBindingSet,
    observation: RedGoalObservation,
) -> GoalBindingSet:
    """Offer standalone storage relief when the active box is already full.

    This differs from capture-storage preparation, which reserves a final slot
    and then performs a selected capture. Storage relief is its own measured
    ``MANAGE_STORAGE`` decision and never masquerades as a capture outcome.
    """
    if any(binding.kind is GoalKind.MANAGE_STORAGE for binding in bindings.bindings):
        return bindings
    if observation.raw.battle_state or not observation.input_ready:
        return bindings

    collection = observation.collection_observation
    initial_box = collection.current_box_index
    initial_counts = collection.box_counts
    current_room = collection.box_capacity - initial_counts[initial_box]
    if current_room != 0 or observation.immediate_capture_slots != 0:
        return bindings
    targets = [
        index for index, count in enumerate(initial_counts)
        if index != initial_box and count < collection.box_capacity
    ]
    if not targets:
        return bindings
    target = min(targets, key=lambda index: (initial_counts[index], index))
    target_room = collection.box_capacity - initial_counts[target]

    from pokemon_red_completion.red_resource_goal_router import _ROUTE_LIMITS, _walking_plan

    runtime = router.runtime
    traversal = Gen1TraversalObserver(runtime.reader)
    start = traversal.observe()
    routes: list[RoutePlan] = []
    for center in sorted(_POKEMON_CENTER_MAPS):
        try:
            route = router.plan_feasible_to_map(start, int(center), goal_at=(4, 13))
        except RoutePlanningError:
            continue
        if _walking_plan(route):
            routes.append(route)
    if not routes:
        return bindings
    route = min(routes, key=lambda value: (len(value.steps), value.terminal_map))

    initial_ledger = dependency_specimen_ledger(collection)
    initial_bag = observation.raw.bag_items
    initial_money = observation.raw.player_money
    executed: list[tuple[ExecutableGoalBinding, GoalExecutionReport]] = []
    claimed = False

    def execute() -> GoalExecutionReport:
        nonlocal claimed
        if claimed:
            raise RedRoutedStorageReliefError("routed storage binding was already consumed")
        claimed = True
        current = runtime.adapter.observe()
        if (
            traversal.observe() != start
            or current.raw.battle_state
            or not current.input_ready
            or current.collection_observation.current_box_index != initial_box
            or current.collection_observation.box_counts != initial_counts
            or dependency_specimen_ledger(current.collection_observation) != initial_ledger
            or current.immediate_capture_slots != 0
            or current.raw.bag_items != initial_bag
            or current.raw.player_money != initial_money
        ):
            raise RedRoutedStorageReliefError("routed storage plan changed before input")

        action_start = router.actions.actions_executed
        frame_start = runtime.emulator.frame_count
        prepare_center_departure(router.actions, runtime.reader)
        interruption_handler: InterruptionHandler = Gen1RouteInterruptionHandler(
            router.actions, runtime.reader, maximum_flees=16, maximum_trainer_battles=8,
            stabilization_frames=180, route_name="bounded standalone storage PC access",
        )
        if getattr(router, "routed_recovery", False):
            from pokemon_red_completion.red_routed_recovery import (
                guarded_collection_route_handler,
            )
            interruption_handler = guarded_collection_route_handler(
                router.actions, runtime.reader,
                route_name="guarded standalone storage PC access",
            )
        transport = execute_route(
            route, router.actions, traversal, interruption_handler=interruption_handler,
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
            or at_pc.raw.bag_items != initial_bag
            or at_pc.raw.player_money != initial_money
        ):
            raise RedRoutedStorageReliefError(
                "routed storage transport changed protected state"
            )

        face_pc_boundary(router.actions, runtime.reader, "up")
        provider = RedBoxSwitchGoalProvider(
            target_box_index=target,
            pc_boundary=lambda fresh: (
                fresh.raw.map_id == route.terminal_map
                and fresh.raw.player_y == 4 and fresh.raw.player_x == 13
            ),
            actions=router.actions, reader=runtime.reader, emulator=runtime.emulator,
            adapter=runtime.adapter,
        )
        offer = provider.offer(runtime.adapter.observe())
        if offer.binding is None:
            raise RedRoutedStorageReliefError(
                "box switch unavailable at routed PC boundary"
            )
        report = offer.binding.execute()
        executed.append((offer.binding, report))
        return GoalExecutionReport(
            router.actions.actions_executed - action_start,
            runtime.emulator.frame_count - frame_start,
            {
                **report.evidence,
                "routed_storage_relief": {
                    "initial_box_index": initial_box,
                    "target_box_index": target,
                    "headroom_gained": target_room,
                    "collection_preserved": True,
                    "setup_training_rows": 0,
                    "route_steps": len(route.steps),
                },
            },
        )

    def verify(report: GoalExecutionReport) -> GoalVerification:
        if len(executed) != 1:
            raise RedRoutedStorageReliefError(
                "storage relief has no completed box switch"
            )
        selected, selected_report = executed[0]
        underlying = selected.verify(selected_report)
        if underlying.status.value != "succeeded":
            return underlying
        fresh = runtime.adapter.observe()
        relief = report.evidence.get("routed_storage_relief")
        if (
            fresh.collection_observation.current_box_index != target
            or fresh.collection_observation.box_counts != initial_counts
            or dependency_specimen_ledger(fresh.collection_observation) != initial_ledger
            or fresh.immediate_capture_slots <= 0
            or fresh.raw.bag_items != initial_bag or fresh.raw.player_money != initial_money
            or fresh.raw.battle_state or not fresh.input_ready
            or report.actions_executed <= 0
            or not isinstance(relief, dict)
            or relief.get("collection_preserved") is not True
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    binding_digest = canonical_sha256({
        "target_map": route.terminal_map, "target_box": target, "steps": len(route.steps),
    })
    binding = ExecutableGoalBinding(
        binding_ref=f"pokemon.red:storage:routed-box-switch:{binding_digest}",
        kind=GoalKind.MANAGE_STORAGE,
        estimated_effort=min(1.0, 0.12 + len(route.steps) / 1_000),
        estimated_risk=0.05,
        execute=execute,
        verify=verify,
    )
    has_opportunity = any(item.kind is GoalKind.MANAGE_STORAGE
                          for item in bindings.opportunities)
    return GoalBindingSet(
        tuple(binding.opportunity if item.kind is GoalKind.MANAGE_STORAGE else item
              for item in bindings.opportunities)
        + (() if has_opportunity else (binding.opportunity,)),
        (*bindings.bindings, binding),
    )
