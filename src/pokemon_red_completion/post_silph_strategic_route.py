"""Authenticated post-Silph objective choice and generated route to the Dojo."""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.executor import ChapterExecutor
from pokemon_red_completion.gen1_maps import macro_graph_from_nodes, map_graph
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.gen1_story_routing import apply_gen1_story_requirements
from pokemon_red_completion.gen1_terrain import walkable_world
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.gen1_traversal import (
    local_graph,
    map_object_events,
    traversal_rules,
)
from pokemon_red_completion.observation import MapId, PokemonRedStateReader
from pokemon_red_completion.route_executor import (
    ReplanRequest,
    RouteExecutionLimits,
    RouteExecutionReport,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route
from pokemon_red_completion.strategic_navigation import StrategicNavigationTag
from pokemon_red_completion.strategic_navigation_binding import DestinationRouteBinding
from pokemon_red_completion.strategic_navigation_runtime import (
    execute_strategic_navigation_route,
)
from pokemon_red_completion.strategic_navigation_trajectory import (
    StrategicNavigationTrajectoryObserver,
)

POST_SILPH_COLLECTION_DESTINATION = "pokemon.red:destination:fighting_dojo"
POST_SILPH_CHALLENGE_DESTINATION = "pokemon.red:destination:saffron_gym"
POST_SILPH_ROUTE_LIMITS = RouteExecutionLimits(
    max_step_attempts=8,
    max_interruptions=4,
    max_replans=8,
    replan_after_unchanged=2,
    retry_wait_frames=24,
    transition_settle_frames=120,
)
_REMOVED_POST_SILPH_SAFFRON_OBJECTS = frozenset({(4, 34)})


class PostSilphStrategicRouteError(RuntimeError):
    """Raised when the post-Silph branch or its terminal context differs."""


def post_silph_destination_bindings(
    collection_plan: RoutePlan,
    challenge_plan: RoutePlan,
) -> tuple[DestinationRouteBinding, ...]:
    """Bind Hitmonlee recruitment beside the now-open Sabrina challenge."""

    if not isinstance(collection_plan, RoutePlan) or not isinstance(challenge_plan, RoutePlan):
        raise TypeError("post-Silph candidates must be RoutePlan values")
    return (
        DestinationRouteBinding.available(
            POST_SILPH_COLLECTION_DESTINATION,
            (
                StrategicNavigationTag.ACQUIRE_PARTY_MEMBER,
                StrategicNavigationTag.COLLECTION,
                StrategicNavigationTag.IMPROVE_TEAM,
            ),
            collection_plan,
        ),
        DestinationRouteBinding.available(
            POST_SILPH_CHALLENGE_DESTINATION,
            (
                StrategicNavigationTag.CHALLENGE,
                StrategicNavigationTag.STORY_PROGRESS,
            ),
            challenge_plan,
        ),
    )


@dataclass(frozen=True, slots=True)
class PostSilphStrategicApproach:
    """Plan both Saffron objectives and execute Hitmonlee recruitment first."""

    rom: bytes
    reader: PokemonRedStateReader
    trajectory: StrategicNavigationTrajectoryObserver
    maximum_flees: int = 0
    maximum_trainer_battles: int = 0
    stabilization_frames: int = 120
    limits: RouteExecutionLimits = POST_SILPH_ROUTE_LIMITS

    def __post_init__(self) -> None:
        if not isinstance(self.rom, bytes) or not self.rom:
            raise ValueError("post-Silph routing requires immutable ROM bytes")
        for name, value in (
            ("maximum_flees", self.maximum_flees),
            ("maximum_trainer_battles", self.maximum_trainer_battles),
        ):
            if type(value) is not int or value < 0:  # noqa: E721
                raise ValueError(f"{name} must be a non-negative integer")
        if type(self.stabilization_frames) is not int or self.stabilization_frames <= 0:  # noqa: E721
            raise ValueError("stabilization_frames must be a positive integer")

    def execute(self, executor: ChapterExecutor) -> RouteExecutionReport:
        maps = map_graph(self.rom)
        macro = macro_graph_from_nodes(maps)
        world = walkable_world(self.rom)
        rules = traversal_rules(self.rom, maps)

        def blocked_objects(map_id: int) -> set[tuple[int, int]]:
            blocked = {event.at for event in map_object_events(self.rom, {map_id})}
            if map_id == MapId.SAFFRON_CITY:
                # The fixed guard in front of Sabrina disappears when Silph Co.
                # is cleared, which is an authenticated precondition here.
                blocked.difference_update(_REMOVED_POST_SILPH_SAFFRON_OBJECTS)
            return blocked

        local_graphs = apply_gen1_story_requirements(
            {
                map_id: local_graph(terrain, rules, blocked=blocked_objects(map_id))
                for map_id, terrain in world.items()
            }
        )
        observer = Gen1TraversalObserver(
            self.reader,
            hazard_projector=Gen1TrainerSightProjector(self.rom, self.reader),
        )
        start = observer.observe()
        if (
            start.map_id != MapId.SAFFRON_POKECENTER
            or start.at != (3, 3)
            or not start.ready
            or start.last_outside_map != MapId.SAFFRON_CITY
        ):
            raise PostSilphStrategicRouteError(
                "strategic Dojo approach requires the ready post-Silph Saffron boundary"
            )

        collection_plan = plan_route(
            macro,
            local_graphs,
            start.map_id,
            start.at,
            MapId.FIGHTING_DOJO.value,
            capabilities=start.capabilities,
            last_outside=start.last_outside_map,
            start_mode=start.mode,
        )
        challenge_plan = plan_route(
            macro,
            local_graphs,
            start.map_id,
            start.at,
            MapId.SAFFRON_GYM.value,
            capabilities=start.capabilities,
            last_outside=start.last_outside_map,
            start_mode=start.mode,
        )
        bindings = post_silph_destination_bindings(collection_plan, challenge_plan)
        interruption_handler = Gen1RouteInterruptionHandler(
            executor,
            self.reader,
            maximum_flees=self.maximum_flees,
            maximum_trainer_battles=self.maximum_trainer_battles,
            stabilization_frames=self.stabilization_frames,
            route_name="generated post-Silph Saffron-to-Dojo route",
        )

        def replan(request: ReplanRequest) -> RoutePlan:
            return plan_route(
                macro,
                local_graphs,
                request.current.map_id,
                request.current.at,
                request.goal_map,
                blocked=request.blocked,
                capabilities=request.current.capabilities,
                last_outside=request.current.last_outside_map,
                start_mode=request.current.mode,
                goal_at=request.goal_at,
            )

        report = execute_strategic_navigation_route(
            self.trajectory,
            semantic_need_tags=(
                StrategicNavigationTag.COLLECTION,
                StrategicNavigationTag.IMPROVE_TEAM,
            ),
            origin_semantic_tags=(
                StrategicNavigationTag.OVERWORLD,
                StrategicNavigationTag.SAFE_HUB,
            ),
            origin_region_ref="pokemon.red:region:saffron",
            bindings=bindings,
            selected_destination_ref=POST_SILPH_COLLECTION_DESTINATION,
            actions=executor,
            traversal_observer=observer,
            interruption_handler=interruption_handler,
            replanner=replan,
            limits=self.limits,
        )
        if (
            report.terminal.map_id != MapId.FIGHTING_DOJO
            or report.terminal.at != (11, 4)
            or report.terminal.last_outside_map != MapId.SAFFRON_CITY
        ):
            raise PostSilphStrategicRouteError(
                "generated strategic route missed the Fighting Dojo entry context"
            )
        return report
