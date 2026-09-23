"""Cartridge-composed Red relocation to the Vermilion training boundary.

Party-outcome questions can begin at authenticated Centers whose party does
not know Fly.  This adapter reuses the game-neutral router rather than adding
another chapter arrow sequence: terrain, warps, story gates, trainer sight,
and the one supported Cut are all derived or observed at execution time.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort
from pokemon_red_completion.gen1_route_runtime import (
    Gen1TraversalObserver,
    Gen1WildFleeHandler,
)
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.gen1_traversal import cut_capabilities
from pokemon_red_completion.observation import (
    MapId,
    PokemonRedStateReader,
    RawGameState,
    ReadOnlyMemory,
)
from pokemon_red_completion.route_executor import (
    DEFAULT_ROUTE_EXECUTION_LIMITS,
    RouteActionPort,
    RouteExecutionError,
    execute_route,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    STRATEGIC_SCENARIO_MAXIMUM_FLEES,
    StrategicScenarioRouteWorld,
)

VERMILION_TRAINING_EXTERIOR = (4, 11)  # router order: (y, x)


@dataclass(frozen=True, slots=True)
class RedVermilionGroundTransition:
    """Execute one bounded ground route; Vermilion remains the legacy default."""

    rom: bytes
    route_world: StrategicScenarioRouteWorld
    maximum_flees: int = STRATEGIC_SCENARIO_MAXIMUM_FLEES
    destination_map: int = int(MapId.VERMILION_CITY)
    destination_at: tuple[int, int] = VERMILION_TRAINING_EXTERIOR
    full_event_offsets: bool = False
    observe_terrain: bool = False
    excluded_maps: frozenset[int] = frozenset()
    maximum_readiness_waits: int = DEFAULT_ROUTE_EXECUTION_LIMITS.max_readiness_waits

    def __post_init__(self) -> None:
        if not isinstance(self.rom, bytes) or not self.rom:
            raise ValueError("Red ground training transition requires immutable ROM bytes")
        if not isinstance(self.route_world, StrategicScenarioRouteWorld):
            raise TypeError("Red ground training transition requires a route world")
        if type(self.full_event_offsets) is not bool or type(self.observe_terrain) is not bool:
            raise TypeError("ground observation switches must be boolean")
        if (
            type(self.maximum_readiness_waits) is not int
            or not 1 <= self.maximum_readiness_waits <= 100
        ):
            raise ValueError("ground readiness wait bound must be1..100")
        if not isinstance(self.excluded_maps, frozenset) or any(
            type(value) is not int or value < 0 for value in self.excluded_maps
        ) or self.destination_map in self.excluded_maps:
            raise ValueError("excluded maps must be nonnegative IDs excluding the destination")
        if type(self.maximum_flees) is not int or self.maximum_flees < 0:  # noqa: E721
            raise ValueError("Red ground training transition needs a non-negative flee bound")
        if type(self.destination_map) is not int or self.destination_map < 0:  # noqa: E721
            raise ValueError("ground destination map must be a nonnegative integer")
        if not isinstance(self.destination_at, tuple) or len(self.destination_at) != 2 or any(
            type(value) is not int or value < 0 for value in self.destination_at  # noqa: E721
        ):
            raise ValueError("ground destination coordinate must be two nonnegative integers")

    @classmethod
    def from_rom(cls, rom: bytes) -> RedVermilionGroundTransition:
        """Decode one immutable world before any controller input is possible."""

        if not isinstance(rom, bytes) or not rom:
            raise ValueError("Red ground training transition requires immutable ROM bytes")
        return cls(rom=rom, route_world=StrategicScenarioRouteWorld.from_rom(rom))

    def __call__(
        self,
        actions: RouteActionPort,
        reader: PokemonRedStateReader,
        emulator: ReadOnlyMemory,
    ) -> None:
        """Plan from live truth, execute closed-loop, and prove the terminal."""

        if not callable(getattr(actions, "execute", None)):
            raise TypeError("Red ground training transition requires an action port")

        def field_capabilities(raw: RawGameState) -> frozenset[str]:
            # The two authenticated routes are land-only; Lavender needs one
            # explicit Cut.  Surf and Strength remain closed rather than being
            # granted merely because another checkpoint might carry them.
            return cut_capabilities(raw)

        observer = Gen1TraversalObserver(
            reader,
            hazard_projector=(
                Gen1TrainerSightProjector(self.rom, reader, full_event_offsets=True)
                if self.full_event_offsets else Gen1TrainerSightProjector(self.rom, reader)
            ),
            capability_projector=field_capabilities,
        )
        start = observer.observe()
        base_world = self.route_world
        if self.excluded_maps:
            base_world = replace(base_world, macro_graph=replace(base_world.macro_graph, edges={
                m: tuple(edge for edge in edges if edge.target_map not in self.excluded_maps)
                for m, edges in base_world.macro_graph.edges.items() if m not in self.excluded_maps
            }))
        world = (base_world.with_current_blocks(reader.read_current_map_blocks())
                 if self.observe_terrain else base_world)
        plan = world.plan_to_map(
            start,
            self.destination_map,
            goal_at=self.destination_at,
        )
        field_actions = Gen1FieldMovePort(
            actions,
            reader,
            emulator,
            cut_block_swaps={
                swap.before: swap.after
                for swap in self.route_world.rules.cut_block_swaps
            },
        )
        interruption_handler = Gen1WildFleeHandler(
            field_actions,
            reader,
            maximum_flees=self.maximum_flees,
            stabilization_frames=120,
            route_name="Red observed ground transition",
        )
        def replan(request):
            updated = base_world.with_current_blocks(reader.read_current_map_blocks())
            return updated.replanner()(request)

        execute_route(
            plan,
            field_actions,
            observer,
            interruption_handler=interruption_handler,
            replanner=replan if self.observe_terrain else base_world.replanner(),
            limits=replace(
                DEFAULT_ROUTE_EXECUTION_LIMITS,
                max_interruptions=max(1, self.maximum_flees),
                max_replans=16,
                max_readiness_waits=self.maximum_readiness_waits,
            ),
        )
        terminal = observer.observe()
        if (
            terminal.map_id != self.destination_map
            or terminal.at != self.destination_at
            or not terminal.ready
            or terminal.interruption is not None
        ):
            raise RouteExecutionError(
                "Red ground transition did not prove the requested boundary"
            )


__all__ = [
    "VERMILION_TRAINING_EXTERIOR",
    "RedVermilionGroundTransition",
]
