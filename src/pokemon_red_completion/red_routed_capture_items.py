"""Retrieve one stored prerequisite item before an already identified capture."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.observation import MAX_BAG_ITEMS
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    dependency_specimen_ledger,
)
from pokemon_red_completion.red_goal_context_profile import RedGoalProviderSpec
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_goal_skills import (
    _POKEMON_CENTER_MAPS,
    RedAreaSurveyGoalProvider,
    prepare_center_departure,
)
from pokemon_red_completion.red_pc_storage import (
    close_generic_pc_session,
    face_pc_boundary,
    open_reds_pc,
    withdraw_single_pc_item,
)
from pokemon_red_completion.route_executor import InterruptionHandler, execute_route
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError

if TYPE_CHECKING:
    from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter
    from pokemon_red_completion.red_routed_semantic_goal import FreshRedGoalObservation


class RedCaptureItemSupportError(RuntimeError):
    """Stored-item preparation cannot preserve its selected capture source."""


def bind_capture_item_support(
    router: RedResourceGoalRouter,
    spec: RedGoalProviderSpec,
    provider: RedAreaSurveyGoalProvider,
    observation: RedGoalObservation,
    fresh: FreshRedGoalObservation,
    traversal: Gen1TraversalObserver,
) -> ExecutableGoalBinding | None:
    """Offer one capture only when a singleton PC item removes its sole resource block."""

    if len(provider.required_capture_items) != 1:
        return None
    required_item = provider.required_capture_items[0]
    bag = observation.raw.bag_items or ()
    if len(bag) >= MAX_BAG_ITEMS or int(required_item) in dict(bag):
        return None
    if replace(provider, required_capture_items=()).resource_availability(
        observation
    ).executable is not True:
        return None
    pc_items = router.runtime.reader.read_pc_items()
    if dict(pc_items).get(int(required_item)) != 1:
        return None

    from pokemon_red_completion.red_resource_goal_router import (
        _ROUTE_LIMITS,
        _supported_plan,
        _walking_plan,
    )

    start = fresh.traversal
    routes: list[RoutePlan] = []
    for center in sorted(_POKEMON_CENTER_MAPS):
        try:
            route = router.plan_feasible_to_map(start, int(center), goal_at=(4, 13))
        except RoutePlanningError:
            continue
        if _walking_plan(route):
            routes.append(route)
    if not routes:
        return None
    pc_route = min(routes, key=lambda value: (len(value.steps), value.terminal_map))
    projected = replace(
        start,
        map_id=pc_route.terminal_map,
        at=(4, 13),
        occupied=frozenset(),
    )
    target_map = spec.parameters.get("map_id")
    target_x = spec.parameters.get("player_x")
    target_y = spec.parameters.get("player_y")
    if any(type(value) is not int for value in (target_map, target_x, target_y)):
        return None
    assert isinstance(target_map, int) and isinstance(target_x, int) and isinstance(target_y, int)
    try:
        capture_route = router.plan_feasible_to_map(
            projected, target_map, goal_at=(target_y, target_x)
        )
    except RoutePlanningError:
        return None
    if not capture_route.steps or not _supported_plan(
        capture_route,
        allow_cut=spec.parameters.get("cut_transport") is True,
        allow_surf=spec.parameters.get("surf_transport") is True,
    ):
        return None

    runtime = router.runtime
    source_ref = f"pokemon.red:acquisition:{provider.source_id}"
    initial_ledger = dependency_specimen_ledger(observation.collection_observation)
    initial_boxes = runtime.reader.read_all_box_states()
    initial_money = observation.raw.player_money
    executed: list[tuple[ExecutableGoalBinding, GoalExecutionReport]] = []
    claimed = False

    def execute() -> GoalExecutionReport:
        nonlocal claimed
        if claimed:
            raise RedCaptureItemSupportError("capture-item support was already consumed")
        claimed = True
        current = runtime.adapter.observe()
        if (
            traversal.observe() != start
            or current.raw.bag_items != observation.raw.bag_items
            or current.raw.player_money != initial_money
            or runtime.reader.read_pc_items() != pc_items
            or runtime.reader.read_all_box_states() != initial_boxes
            or dependency_specimen_ledger(current.collection_observation) != initial_ledger
        ):
            raise RedCaptureItemSupportError("capture-item support changed before input")
        action_start = router.actions.actions_executed
        frame_start = runtime.emulator.frame_count
        prepare_center_departure(router.actions, runtime.reader)
        interruption_handler: InterruptionHandler = Gen1RouteInterruptionHandler(
            router.actions,
            runtime.reader,
            maximum_flees=16,
            maximum_trainer_battles=8,
            stabilization_frames=180,
            route_name="bounded capture-item PC access",
        )
        if getattr(router, "routed_recovery", False):
            from pokemon_red_completion.red_routed_recovery import (
                guarded_collection_route_handler,
            )

            interruption_handler = guarded_collection_route_handler(
                router.actions,
                runtime.reader,
                route_name="guarded capture-item PC access",
            )
        transport = execute_route(
            pc_route,
            router.actions,
            traversal,
            interruption_handler=interruption_handler,
            replanner=router._replan,
            limits=_ROUTE_LIMITS,
        )
        at_pc = runtime.adapter.observe()
        if (
            not transport.passed
            or (at_pc.raw.map_id, at_pc.raw.player_y, at_pc.raw.player_x)
            != (pc_route.terminal_map, 4, 13)
            or at_pc.raw.battle_state
            or not at_pc.input_ready
            or at_pc.raw.bag_items != observation.raw.bag_items
            or at_pc.raw.player_money != initial_money
            or runtime.reader.read_all_box_states() != initial_boxes
            or dependency_specimen_ledger(at_pc.collection_observation) != initial_ledger
        ):
            raise RedCaptureItemSupportError("capture-item PC route changed protected state")
        face_pc_boundary(router.actions, runtime.reader, "up")
        open_reds_pc(router.actions, runtime.reader)
        withdrawal = withdraw_single_pc_item(
            router.actions,
            runtime.reader,
            item_id=int(required_item),
        )
        close_generic_pc_session(router.actions, runtime.reader)
        prepared = runtime.adapter.observe()
        if (
            not withdrawal.passed
            or dict(prepared.raw.bag_items or ()).get(int(required_item)) != 1
            or prepared.raw.player_money != initial_money
            or runtime.reader.read_all_box_states() != initial_boxes
            or dependency_specimen_ledger(prepared.collection_observation) != initial_ledger
            or prepared.raw.battle_state
            or not prepared.input_ready
        ):
            raise RedCaptureItemSupportError("capture-item withdrawal was not preserved")
        preparation_actions = router.actions.actions_executed - action_start
        preparation_frames = runtime.emulator.frame_count - frame_start
        successor = replace(
            router,
            prepare_capture_items=False,
            route_plan_cache=None,
        )
        rebound = successor.enumerate_routed_kinds(
            prepared, frozenset({GoalKind.ACQUIRE_SPECIES})
        )
        selected = next(
            (
                binding
                for binding in rebound.bindings
                if binding.kind is GoalKind.ACQUIRE_SPECIES
                and (
                    binding.search_source_ref == source_ref
                    or binding.binding_ref == source_ref
                    or binding.binding_ref.startswith(f"{source_ref}:profile-")
                )
            ),
            None,
        )
        if selected is None:
            raise RedCaptureItemSupportError("prepared item lost its selected capture source")
        result = selected.execute()
        executed.append((selected, result))
        return GoalExecutionReport(
            router.actions.actions_executed - action_start,
            runtime.emulator.frame_count - frame_start,
            {
                **result.evidence,
                "capture_item_support": {
                    "item_id": int(required_item),
                    "pc_route_steps": len(pc_route.steps),
                    "capture_route_steps": len(capture_route.steps),
                    "collection_preserved_before_capture": True,
                    "setup_training_rows": 0,
                    "actions_executed": preparation_actions,
                    "frames_executed": preparation_frames,
                },
            },
        )

    def verify(_report: GoalExecutionReport) -> GoalVerification:
        if len(executed) != 1:
            raise RedCaptureItemSupportError("capture-item support has no executed capture")
        selected, result = executed[0]
        return selected.verify(result)

    digest = canonical_sha256(
        {
            "item_id": int(required_item),
            "pc_map": pc_route.terminal_map,
            "source_id": provider.source_id,
        }
    )
    return ExecutableGoalBinding(
        binding_ref=f"{source_ref}:pc-item-support:{digest}",
        kind=GoalKind.ACQUIRE_SPECIES,
        estimated_effort=min(
            1.0,
            0.14 + (len(pc_route.steps) + len(capture_route.steps)) / 1_000,
        ),
        estimated_risk=0.20,
        execute=execute,
        verify=verify,
        search_source_ref=source_ref,
    )
