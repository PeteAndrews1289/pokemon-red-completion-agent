"""Authenticated post-Hideout story choice and generated route to Pokémon Tower."""

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

POST_HIDEOUT_STORY_DESTINATION = "pokemon.red:destination:pokemon_tower"
POST_HIDEOUT_COLLECTION_DESTINATION = "pokemon.red:destination:eevee_gift"
POST_HIDEOUT_ROUTE_LIMITS = RouteExecutionLimits(
    max_step_attempts=8,
    max_interruptions=8,
    max_replans=8,
    replan_after_unchanged=2,
    retry_wait_frames=24,
    transition_settle_frames=120,
)


class PostHideoutStrategicRouteError(RuntimeError):
    """Raised when the authenticated branch or its terminal context differs."""


def post_hideout_destination_bindings(
    story_plan: RoutePlan,
    collection_plan: RoutePlan,
) -> tuple[DestinationRouteBinding, ...]:
    """Freeze the genuine story-over-shorter-collection candidate order."""

    if not isinstance(story_plan, RoutePlan) or not isinstance(collection_plan, RoutePlan):
        raise TypeError("post-Hideout candidates must be RoutePlan values")
    if story_plan.cost <= collection_plan.cost:
        raise PostHideoutStrategicRouteError(
            "post-Hideout story choice no longer rejects the unique cost minimum"
        )
    return (
        DestinationRouteBinding.available(
            POST_HIDEOUT_STORY_DESTINATION,
            (
                StrategicNavigationTag.REMOVE_BLOCKER,
                StrategicNavigationTag.STORY_PROGRESS,
            ),
            story_plan,
        ),
        DestinationRouteBinding.available(
            POST_HIDEOUT_COLLECTION_DESTINATION,
            (
                StrategicNavigationTag.ACQUIRE_PARTY_MEMBER,
                StrategicNavigationTag.COLLECTION,
                StrategicNavigationTag.OPTIONAL_REWARD,
            ),
            collection_plan,
        ),
    )


@dataclass(frozen=True, slots=True)
class PostHideoutStrategicApproach:
    """Plan both destinations, bind the teacher choice, and reach Tower 1F."""

    rom: bytes
    reader: PokemonRedStateReader
    trajectory: StrategicNavigationTrajectoryObserver
    maximum_flees: int = 8
    maximum_trainer_battles: int = 8
    stabilization_frames: int = 120
    limits: RouteExecutionLimits = POST_HIDEOUT_ROUTE_LIMITS

    def __post_init__(self) -> None:
        if not isinstance(self.rom, bytes) or not self.rom:
            raise ValueError("post-Hideout routing requires immutable ROM bytes")
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
            start.map_id != MapId.CELADON_POKECENTER
            or start.at != (3, 3)
            or not start.ready
            or start.last_outside_map != MapId.CELADON_CITY
        ):
            raise PostHideoutStrategicRouteError(
                "strategic Tower approach requires the ready post-Hideout Celadon boundary"
            )

        story_plan = plan_route(
            macro,
            local_graphs,
            start.map_id,
            start.at,
            MapId.POKEMON_TOWER_1F.value,
            capabilities=start.capabilities,
            last_outside=start.last_outside_map,
            start_mode=start.mode,
        )
        collection_plan = plan_route(
            macro,
            local_graphs,
            start.map_id,
            start.at,
            MapId.CELADON_MANSION_ROOF_HOUSE.value,
            capabilities=start.capabilities,
            last_outside=start.last_outside_map,
            start_mode=start.mode,
        )
        bindings = post_hideout_destination_bindings(story_plan, collection_plan)
        interruption_handler = Gen1RouteInterruptionHandler(
            executor,
            self.reader,
            maximum_flees=self.maximum_flees,
            maximum_trainer_battles=self.maximum_trainer_battles,
            stabilization_frames=self.stabilization_frames,
            route_name="generated post-Hideout Celadon-to-Tower route",
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
                StrategicNavigationTag.REMOVE_BLOCKER,
            ),
            origin_semantic_tags=(
                StrategicNavigationTag.OVERWORLD,
                StrategicNavigationTag.SAFE_HUB,
            ),
            origin_region_ref="pokemon.red:region:celadon",
            bindings=bindings,
            selected_destination_ref=POST_HIDEOUT_STORY_DESTINATION,
            actions=executor,
            traversal_observer=observer,
            interruption_handler=interruption_handler,
            replanner=replan,
            limits=self.limits,
        )
        if (
            report.terminal.map_id != MapId.POKEMON_TOWER_1F
            or report.terminal.at != (17, 10)
            or report.terminal.last_outside_map != MapId.LAVENDER_TOWN
        ):
            raise PostHideoutStrategicRouteError(
                "generated strategic route missed the Tower entry return context"
            )
        return report
