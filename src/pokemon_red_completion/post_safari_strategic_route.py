"""Authenticated post-Safari objective choice and generated route to Koga."""

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

POST_SAFARI_CHALLENGE_DESTINATION = "pokemon.red:destination:fuchsia_gym"
POST_SAFARI_RESOURCE_DESTINATION = "pokemon.red:destination:warden_house"
POST_SAFARI_ROUTE_LIMITS = RouteExecutionLimits(
    max_step_attempts=8,
    max_interruptions=2,
    max_replans=4,
    replan_after_unchanged=2,
    retry_wait_frames=24,
    transition_settle_frames=120,
)


class PostSafariStrategicRouteError(RuntimeError):
    """Raised when the post-Safari branch or its terminal context differs."""


def post_safari_destination_bindings(
    challenge_plan: RoutePlan,
    resource_plan: RoutePlan,
) -> tuple[DestinationRouteBinding, ...]:
    """Bind the qualified Gym choice beside the genuine Warden alternative."""

    if not isinstance(challenge_plan, RoutePlan) or not isinstance(resource_plan, RoutePlan):
        raise TypeError("post-Safari candidates must be RoutePlan values")
    return (
        DestinationRouteBinding.available(
            POST_SAFARI_CHALLENGE_DESTINATION,
            (
                StrategicNavigationTag.CHALLENGE,
                StrategicNavigationTag.STORY_PROGRESS,
            ),
            challenge_plan,
        ),
        DestinationRouteBinding.available(
            POST_SAFARI_RESOURCE_DESTINATION,
            (
                StrategicNavigationTag.ACQUIRE_RESOURCE,
                StrategicNavigationTag.STORY_PROGRESS,
            ),
            resource_plan,
        ),
    )


@dataclass(frozen=True, slots=True)
class PostSafariStrategicApproach:
    """Plan both Fuchsia objectives and execute the teacher's Gym choice."""

    rom: bytes
    reader: PokemonRedStateReader
    trajectory: StrategicNavigationTrajectoryObserver
    maximum_flees: int = 2
    maximum_trainer_battles: int = 0
    stabilization_frames: int = 120
    limits: RouteExecutionLimits = POST_SAFARI_ROUTE_LIMITS

    def __post_init__(self) -> None:
        if not isinstance(self.rom, bytes) or not self.rom:
            raise ValueError("post-Safari routing requires immutable ROM bytes")
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
        local_graphs = apply_gen1_story_requirements(
            {
                map_id: local_graph(
                    terrain,
                    rules,
                    blocked={event.at for event in map_object_events(self.rom, {map_id})},
                )
                for map_id, terrain in world.items()
            }
        )
        observer = Gen1TraversalObserver(
            self.reader,
            hazard_projector=Gen1TrainerSightProjector(self.rom, self.reader),
        )
        start = observer.observe()
        if (
            start.map_id != MapId.FUCHSIA_POKECENTER
            or start.at != (3, 3)
            or not start.ready
            or start.last_outside_map != MapId.FUCHSIA_CITY
        ):
            raise PostSafariStrategicRouteError(
                "strategic Koga approach requires the ready post-Safari Fuchsia boundary"
            )

        challenge_plan = plan_route(
            macro,
            local_graphs,
            start.map_id,
            start.at,
            MapId.FUCHSIA_GYM.value,
            capabilities=start.capabilities,
            last_outside=start.last_outside_map,
            start_mode=start.mode,
        )
        resource_plan = plan_route(
            macro,
            local_graphs,
            start.map_id,
            start.at,
            MapId.WARDENS_HOUSE.value,
            capabilities=start.capabilities,
            last_outside=start.last_outside_map,
            start_mode=start.mode,
        )
        bindings = post_safari_destination_bindings(challenge_plan, resource_plan)
        interruption_handler = Gen1RouteInterruptionHandler(
            executor,
            self.reader,
            maximum_flees=self.maximum_flees,
            maximum_trainer_battles=self.maximum_trainer_battles,
            stabilization_frames=self.stabilization_frames,
            route_name="generated post-Safari Fuchsia-to-Gym route",
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
                StrategicNavigationTag.ADVANCE_STORY,
                StrategicNavigationTag.REACH_NEXT_CHALLENGE,
            ),
            origin_semantic_tags=(
                StrategicNavigationTag.OVERWORLD,
                StrategicNavigationTag.SAFE_HUB,
            ),
            origin_region_ref="pokemon.red:region:fuchsia",
            bindings=bindings,
            selected_destination_ref=POST_SAFARI_CHALLENGE_DESTINATION,
            actions=executor,
            traversal_observer=observer,
            interruption_handler=interruption_handler,
            replanner=replan,
            limits=self.limits,
        )
        if (
            report.terminal.map_id != MapId.FUCHSIA_GYM
            or report.terminal.at != (17, 4)
            or report.terminal.last_outside_map != MapId.FUCHSIA_CITY
        ):
            raise PostSafariStrategicRouteError(
                "generated strategic route missed the Fuchsia Gym entry context"
            )
        return report
