"""Optional cartridge-derived Fly transport for a real collection destination.

Red/Blue's special-warp table supplies the landing, not a recorded walk string.
Format reference: https://github.com/pret/pokered/blob/master/data/maps/special_warps.asm
The existing field-move port owns menu input; the existing semantic composer
owns destination execution, verification and total resource accounting.
"""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache, partial
from typing import TYPE_CHECKING

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_cartridge import CartridgeReadError, bank_offset
from pokemon_red_completion.gen1_field_moves import (
    Gen1FieldMoveError,
    Gen1FieldMovePort,
    fly_menu_indices,
)
from pokemon_red_completion.global_router import GlobalRouterError, find_macro_path
from pokemon_red_completion.goal_manager import GoalFailureReason
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.observation import RED_FLY_TOWN_NAMES, Badge, OverworldMovementMode
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic, RedGoalProviderSpec
from pokemon_red_completion.red_goal_manager import RedGoalBindingProvider
from pokemon_red_completion.red_living_dex_setup_source import (
    red_living_dex_setup_fresh_observation_sha256,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    FreshRedGoalObservation,
    RedFreshGoalDestinationBinder,
    RedRoutedSemanticBoundary,
    RedRoutedSemanticBudgetMeter,
    RedSemanticTransportRoute,
)
from pokemon_red_completion.route_executor import TraversalObserver
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion.routed_semantic_goal import (
    RoutedSemanticGoalComposer,
    RoutedSemanticGoalLimits,
    RoutedSemanticRouteBinding,
)

if TYPE_CHECKING:
    from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter

# Revision-specific cartridge interpretation stays in this Red adapter. The
# complete row identities and pointer/sub-block constraints reject other layouts.
_FLY_TABLE = 0x6448
_FLY_MAPS = (*range(11), 15, 21)


@lru_cache(maxsize=2)
def red_fly_landings(rom: bytes) -> tuple[tuple[int, tuple[int, int]], ...]:
    """Read (map, (y,x)) rows; do not infer Fly access from their existence."""
    if len(rom) < _FLY_TABLE + len(_FLY_MAPS) * 4:
        raise CartridgeReadError("Fly pointer table is truncated")
    result = []
    pointers = set()
    for index, map_id in enumerate(_FLY_MAPS):
        at = _FLY_TABLE + 4 * index
        if rom[at : at + 2] != bytes((map_id, 0)):
            raise CartridgeReadError("Fly table identities differ from the pinned layout")
        pointer = int.from_bytes(rom[at + 2 : at + 4], "little")
        if not 0x4000 <= pointer <= 0x7FFA or pointer in pointers:
            raise CartridgeReadError("Fly landing pointer is invalid or duplicated")
        pointers.add(pointer)
        offset = bank_offset(1, pointer)
        data = rom[offset : offset + 6]
        if len(data) != 6 or data[4:] != bytes((data[2] & 1, data[3] & 1)):
            raise CartridgeReadError("Fly landing sub-block coordinates disagree")
        result.append((map_id, (data[2], data[3])))
    return tuple(result)


def bind_collection_fly(
    router: RedResourceGoalRouter,
    spec: RedGoalProviderSpec,
    provider: RedGoalBindingProvider,
    fresh: FreshRedGoalObservation,
    traversal: TraversalObserver,
) -> ExecutableGoalBinding | None:
    """Offer only a legal flight with a feasible onward walking plan.

    Scope is capture, evolution or explicitly opted-in Mart access. Profiles without the flag retain
    their historical walking-only behavior. No controller actions occur here.
    """
    from pokemon_red_completion.observation import MapId
    from pokemon_red_completion.red_resource_goal_router import (
        _ROUTE_LIMITS,
        _cut_enabled,
        _supported_plan,
        _surf_enabled,
    )
    from pokemon_red_completion.red_routed_recovery import guarded_collection_route_handler
    from pokemon_red_completion.red_travel_capture_runtime import (
        bind_travel_capture_destination,
        bind_travel_capture_handler,
    )
    from pokemon_red_completion.route_executor import InterruptionHandler

    travel_handlers: list[InterruptionHandler] = []

    if (
        spec.mechanic not in {
            RedGoalMechanic.TARGETED_LEVEL_EVOLUTION, RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
            RedGoalMechanic.MART_RESUPPLY,
        }
        or spec.parameters.get("fly_transport") is not True
    ):
        return None
    runtime, actions = router.runtime, router.actions
    reader = runtime.reader
    raw, start = fresh.observation.raw, fresh.traversal
    if start.map_id >= 0x25:
        from pokemon_red_completion.red_indoor_collection_departure import (
            bind_indoor_collection_departure,
        )

        return bind_indoor_collection_departure(router, spec, provider, fresh, traversal)
    if (
        not fresh.observation.input_ready
        or raw.battle_state
        or start.interruption is not None
        or not 0 <= start.map_id <= 0x24
        or start.map_id == 0x0B
        or start.mode != "land"
        or not int(raw.badge_bits or 0) & int(Badge.THUNDER)
        or reader.read_overworld_movement_mode() is not OverworldMovementMode.WALKING
        or reader.read_bottom_dialogue_box_visible()
        or reader.read_pending_trainer_battle_identity() is not None
        or reader.read_fly_menu_state() is not None
    ):
        return None
    try:
        fly_menu_indices(raw)
    except Gen1FieldMoveError:
        return None
    landings = dict(red_fly_landings(router.world.rom))
    destinations: tuple[tuple[int, tuple[int, int]], ...]
    if spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION:
        destinations = (
            (int(MapId.CINNABAR_POKECENTER), (3, 3)),
            (int(MapId.VERMILION_POKECENTER), (3, 3)),
        )
    else:
        target, x, y = (spec.parameters[key] for key in ("map_id", "player_x", "player_y"))
        if type(target) is not int or type(x) is not int or type(y) is not int:
            raise Gen1FieldMoveError("field-transport destination is not an integer boundary")
        destinations = ((target, (y, x)),)
    possibilities = []
    for town in reader.read_fly_destinations():
        if town == start.map_id or town not in landings or not 0 <= town < len(RED_FLY_TOWN_NAMES):
            continue
        landing = landings[town]
        graph = router.world.local_graphs.get(town)
        if (
            graph is None
            or landing not in graph.edges
            or landing in router.world.object_blockers[town]
        ):
            continue
        projected = replace(
            start, map_id=town, at=landing, last_outside_map=town, occupied=frozenset()
        )
        for target, goal_at in destinations:
            try:
                topology = find_macro_path(
                    router.world.macro_graph, town, target, last_outside=town
                )
            except GlobalRouterError:
                continue
            possibilities.append((len(topology.edges), town, target, goal_at, projected))
    chosen = None
    for _, town, target, goal_at, projected in sorted(possibilities, key=lambda p: p[:3]):
        try:
            plan = router.world.plan_feasible_to_map(projected, target, goal_at=goal_at)
        except RoutePlanningError:
            continue
        if plan.steps and _supported_plan(
            plan, allow_cut=_cut_enabled(spec), allow_surf=_surf_enabled(spec),
        ):
            chosen = town, projected, plan
            break
    if chosen is None:
        return None
    town, expected_landing, plan = chosen
    boundary = RedRoutedSemanticBoundary.from_plan(plan)
    origin = red_living_dex_setup_fresh_observation_sha256(fresh)
    meter = RedRoutedSemanticBudgetMeter(actions, runtime.emulator)
    route_report: GoalExecutionReport | None = None
    executed = False
    verified = False

    def observe() -> FreshRedGoalObservation:
        current = FreshRedGoalObservation("0" * 64, runtime.adapter.observe(), traversal.observe())
        return replace(
            current, observation_sha256=red_living_dex_setup_fresh_observation_sha256(current)
        )

    def execute() -> GoalExecutionReport:
        nonlocal route_report, executed
        if executed:
            raise Gen1FieldMoveError("collection flight was already attempted")
        executed = True
        before = meter.checkpoint()
        if observe().observation_sha256 != origin:
            raise Gen1FieldMoveError("collection flight origin changed before input")
        # Reserve every dispatch before shared counters and hard frame budgets.
        flight_actions = HardCompositionActionLimiter(
            actions,
            maximum_actions_per_decision=min(256, router.maximum_controller_actions),
            maximum_episode_actions=min(256, router.maximum_controller_actions),
        )
        port = Gen1FieldMovePort(flight_actions, reader, runtime.emulator)
        port.execute(
            MacroAction(
                MacroActionKind.FIELD_MOVE,
                "fly:" + RED_FLY_TOWN_NAMES[town].lower().replace(" ", "_"),
            )
        )
        actual = observe()
        if (actual.traversal.map_id, actual.traversal.at, actual.traversal.mode) != (
            town,
            expected_landing.at,
            "land",
        ):
            raise Gen1FieldMoveError("Fly landing differs from cartridge; no onward walk")
        after_fly = meter.checkpoint()
        if (
            after_fly.controller_actions - before.controller_actions
            >= router.maximum_controller_actions
            or after_fly.emulator_frames - before.emulator_frames >= router.maximum_emulator_frames
        ):
            raise Gen1FieldMoveError("Fly exhausted the collection transport budget")
        travel_handler = bind_travel_capture_handler(router, spec, guarded_collection_route_handler(
            actions, reader, route_name="collection Fly onward walk",
        ))
        travel_handlers.append(travel_handler)
        walk = RedSemanticTransportRoute(
            binding_ref="red-collection-fly-walk:" + spec.configuration_sha256,
            origin_observation_sha256=actual.observation_sha256,
            planner_binding_sha256=canonical_sha256(
                {
                    "schema": "pokemon.red.collection-fly.v1",
                    "profile": runtime.profile.profile_sha256,
                }
            ),
            plan=plan,
            actions=actions,
            traversal_observer=traversal,
            emulator=runtime.emulator,
            interruption_handler=travel_handler,
            replanner=partial(
                router._replan, allow_cut=_cut_enabled(spec), allow_surf=_surf_enabled(spec),
            ),
            field_actions=(router.field_actions_for(spec)
                           if _cut_enabled(spec) or _surf_enabled(spec) else None),
            route_limits=_ROUTE_LIMITS,
        )
        walking = walk.route_binding()
        result = walking.execute()
        passed = walking.verify(result).status.value == "succeeded"
        after = meter.checkpoint()
        from pokemon_red_completion.field_move_summary import FieldMoveSummary
        fields = FieldMoveSummary.from_evidence(result.evidence) or FieldMoveSummary()
        fields = fields.plus(FieldMoveSummary(flights=len(port.fly_receipts)))
        route_report = GoalExecutionReport(
            actions_executed=after.controller_actions - before.controller_actions,
            frames_executed=after.emulator_frames - before.emulator_frames,
            evidence={
                "schema": "pokemon.red.collection-fly-transport.v1",
                "passed": passed,
                "verified_flights": len(port.fly_receipts),
                "field_moves": fields.public_dict(),
                "cartridge_landing_verified": True,
                "onward_walk": dict(result.evidence),
                "transport_is_policy_kind": False,
            },
        )
        return route_report

    def verify(report: GoalExecutionReport) -> GoalVerification:
        nonlocal verified
        if verified or route_report is None or report is not route_report:
            raise Gen1FieldMoveError(
                "collection flight report is absent, replaced or already verified"
            )
        verified = True
        if report.evidence["passed"] is not True or not boundary.matches_traversal(
            traversal.observe()
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    from pokemon_red_completion.red_goal_skills import RedAreaSurveyGoalProvider

    destination_provider = provider
    if router.routed_recovery and isinstance(provider, RedAreaSurveyGoalProvider):
        from pokemon_red_completion.red_capture_preparation import EscortPreparedCaptureProvider

        destination_provider = EscortPreparedCaptureProvider(provider, runtime, actions)
    destination_provider = bind_travel_capture_destination(
        router, spec, destination_provider, provider, fresh.observation, travel_handlers,
    )
    binding = RoutedSemanticGoalComposer(
        binding_ref="red-collection-fly-goal:" + origin + ":" + spec.configuration_sha256,
        destination_kind=spec.kind,
        estimated_effort=min(1.0, 0.42 + len(plan.steps) / 1000),
        estimated_risk=0.18,
        route=RoutedSemanticRouteBinding(
            "red-collection-fly:" + origin, origin, boundary.sha256, execute, verify
        ),
        bind_fresh_destination=RedFreshGoalDestinationBinder(
            spec.kind, boundary, observe, destination_provider
        ),
        budget_meter=meter,
        limits=RoutedSemanticGoalLimits(
            router.maximum_controller_actions, router.maximum_emulator_frames
        ),
    ).binding()
    if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
        binding = replace(
            binding,
            search_source_ref="pokemon.red:acquisition:" + str(spec.parameters["source_id"]),
        )
    return binding
