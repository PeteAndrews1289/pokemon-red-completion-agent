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
    """Execute one bounded route to the existing Vermilion venue entrance."""

    rom: bytes
    route_world: StrategicScenarioRouteWorld
    maximum_flees: int = STRATEGIC_SCENARIO_MAXIMUM_FLEES

    def __post_init__(self) -> None:
        if not isinstance(self.rom, bytes) or not self.rom:
            raise ValueError("Red ground training transition requires immutable ROM bytes")
        if not isinstance(self.route_world, StrategicScenarioRouteWorld):
            raise TypeError("Red ground training transition requires a route world")
        if type(self.maximum_flees) is not int or self.maximum_flees < 0:  # noqa: E721
            raise ValueError("Red ground training transition needs a non-negative flee bound")

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
            hazard_projector=Gen1TrainerSightProjector(self.rom, reader),
            capability_projector=field_capabilities,
        )
        start = observer.observe()
        plan = self.route_world.plan_to_map(
            start,
            int(MapId.VERMILION_CITY),
            goal_at=VERMILION_TRAINING_EXTERIOR,
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
            route_name="Red ground transition to Vermilion training",
        )
        execute_route(
            plan,
            field_actions,
            observer,
            interruption_handler=interruption_handler,
            replanner=self.route_world.replanner(),
            limits=replace(
                DEFAULT_ROUTE_EXECUTION_LIMITS,
                max_interruptions=max(1, self.maximum_flees),
                max_replans=16,
            ),
        )
        terminal = observer.observe()
        if (
            terminal.map_id != int(MapId.VERMILION_CITY)
            or terminal.at != VERMILION_TRAINING_EXTERIOR
            or not terminal.ready
            or terminal.interruption is not None
        ):
            raise RouteExecutionError(
                "Red ground training transition did not prove the Vermilion boundary"
            )


__all__ = [
    "VERMILION_TRAINING_EXTERIOR",
    "RedVermilionGroundTransition",
]
