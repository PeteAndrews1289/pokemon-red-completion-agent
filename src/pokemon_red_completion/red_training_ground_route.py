"""Cartridge-composed Red relocation to the Vermilion training boundary.

Party-outcome questions can begin at authenticated Centers whose party does
not know Fly.  This adapter reuses the game-neutral router rather than adding
another chapter arrow sequence: terrain, warps, story gates, trainer sight,
and the one supported Cut are all derived or observed at execution time.
Explicit Surf opt-in reuses the same live permission and field-move adapters;
all existing callers remain land-only unless they request it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort, surf_permission
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
    Gen1WildFleeHandler,
)
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.gen1_traversal import cut_capabilities, surf_capabilities
from pokemon_red_completion.observation import (
    MapId,
    PokemonRedStateReader,
    RawGameState,
    ReadOnlyMemory,
)
from pokemon_red_completion.route_plan import RoutePlanningError
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


def ground_route_capability_projector(route, memory):
    """Share the executor's explicit field-move boundary with route quotes."""
    if getattr(route, "allow_surf", False) is not True:
        return cut_capabilities

    def project(raw: RawGameState) -> frozenset[str]:
        return cut_capabilities(raw) | surf_capabilities(
            raw, surf_allowed=surf_permission(memory, raw).allowed
        )

    return project


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
    transition_settle_frames: int = DEFAULT_ROUTE_EXECUTION_LIMITS.transition_settle_frames
    maximum_scripted_dialogues: int = 0
    require_cash_safe: bool = False
    allow_surf: bool = False
    allow_complete_cut_search: bool = False
    trainer_binding_factory: Callable[[], object | None] | None = field(
        default=None, repr=False, compare=False,
    )
    maximum_learned_trainers: int = 8
    allow_wild_faints: bool = False
    allow_field_faint_dialogue: bool = False

    def __post_init__(self) -> None:
        if self.trainer_binding_factory is not None and not callable(self.trainer_binding_factory):
            raise TypeError("ground trainer recovery needs an exact binding factory")
        if type(self.maximum_learned_trainers) is not int or not 1 <= self.maximum_learned_trainers <= 32:
            raise ValueError("ground learned-trainer allowance must be1..32")
        if self.trainer_binding_factory is not None and self.require_cash_safe:
            raise ValueError("learned ground trainers conflict with cash-safe transport")
        if type(self.allow_complete_cut_search) is not bool:
            raise TypeError("complete Cut search opt-in must be boolean")
        if type(self.allow_surf) is not bool:
            raise TypeError("Surf transport opt-in must be boolean")
        if type(self.allow_wild_faints) is not bool:
            raise TypeError("wild faint recovery opt-in must be boolean")
        if type(self.allow_field_faint_dialogue) is not bool:
            raise TypeError("field faint dialogue opt-in must be boolean")
        if self.allow_field_faint_dialogue and not self.allow_wild_faints:
            raise ValueError("field faint dialogue requires ordinary faint admission")
        if type(self.require_cash_safe) is not bool or (
            self.require_cash_safe and (self.maximum_flees or self.maximum_scripted_dialogues)
        ):
            raise ValueError("cash-safe walking cannot authorize battle/dialogue recovery")
        if (
            type(self.maximum_scripted_dialogues) is not int
            or not 0 <= self.maximum_scripted_dialogues <= 4
        ):
            raise ValueError("ground scripted dialogue allowance must be0..4")
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
        if (type(self.transition_settle_frames) is not int
                or not 1 <= self.transition_settle_frames <= 1200):
            raise ValueError("ground transition settlement must be1..1200frames")
        if (
            not isinstance(self.excluded_maps, frozenset)
            or any(type(value) is not int or value < 0 for value in self.excluded_maps)
            or self.destination_map in self.excluded_maps
        ):
            raise ValueError("excluded maps must be nonnegative IDs excluding the destination")
        if type(self.maximum_flees) is not int or self.maximum_flees < 0:  # noqa: E721
            raise ValueError("Red ground training transition needs a non-negative flee bound")
        if type(self.destination_map) is not int or self.destination_map < 0:  # noqa: E721
            raise ValueError("ground destination map must be a nonnegative integer")
        if (
            not isinstance(self.destination_at, tuple)
            or len(self.destination_at) != 2
            or any(
                type(value) is not int or value < 0
                for value in self.destination_at  # noqa: E721
            )
        ):
            raise ValueError("ground destination coordinate must be two nonnegative integers")

    @classmethod
    def from_rom(cls, rom: bytes) -> RedVermilionGroundTransition:
        """Decode one immutable world before any controller input is possible."""

        if not isinstance(rom, bytes) or not rom:
            raise ValueError("Red ground training transition requires immutable ROM bytes")
        return cls(rom=rom, route_world=StrategicScenarioRouteWorld.from_rom(rom))

    def _initial_plan(self, world, start):
        """Retry one selected endpoint with the existing complete Cut search.

        The default remains the bounded corridor. Explicit callers may pay for
        the broader existing search after that corridor fails. This does not
        grant Cut or any other field permission, silently bypass hazards, select another
        destination, or issue input. Sight lanes remain blocked unless the caller
        explicitly supplies the existing exact learned trainer recovery. Other
        hazard kinds and solid occupancy remain blocked in either mode.
        """
        try:
            return world.plan_feasible_to_map(
                start, self.destination_map, goal_at=self.destination_at,
            )
        except RoutePlanningError:
            if not self.allow_complete_cut_search:
                raise
            return world._plan_candidate(
                start, self.destination_map, goal_at=self.destination_at,
                blocked={start.map_id: start.occupied | frozenset(
                    h.at for h in start.hazards
                    if h.kind != "trainer_sight" or self.trainer_binding_factory is None
                )},
            )

    def __call__(
        self,
        actions: RouteActionPort,
        reader: PokemonRedStateReader,
        emulator: ReadOnlyMemory,
    ) -> None:
        """Plan from live truth, execute closed-loop, and prove the terminal."""

        if not callable(getattr(actions, "execute", None)):
            raise TypeError("Red ground training transition requires an action port")

        observer = Gen1TraversalObserver(
            reader,
            hazard_projector=(
                Gen1TrainerSightProjector(self.rom, reader, full_event_offsets=True)
                if self.full_event_offsets
                else Gen1TrainerSightProjector(self.rom, reader)
            ),
            capability_projector=ground_route_capability_projector(self, emulator),
        )
        start = observer.observe()
        base_world = self.route_world
        if self.excluded_maps:
            base_world = replace(
                base_world,
                macro_graph=replace(
                    base_world.macro_graph,
                    edges={
                        m: tuple(
                            edge for edge in edges if edge.target_map not in self.excluded_maps
                        )
                        for m, edges in base_world.macro_graph.edges.items()
                        if m not in self.excluded_maps
                    },
                ),
            )
        world = (
            base_world.with_current_blocks(reader.read_current_map_blocks())
            if self.observe_terrain
            else base_world
        )
        # Execute the same hazard-aware class of route used by capability
        # quotes. A relocation must not walk through known trainer sight.
        plan = self._initial_plan(world, start)
        if self.require_cash_safe:
            from .red_player_cash_exposure import require_cash_safe_plan

            require_cash_safe_plan(self.rom, reader.read(), plan)
        field_actions = Gen1FieldMovePort(
            actions,
            reader,
            emulator,
            cut_block_swaps={
                swap.before: swap.after for swap in self.route_world.rules.cut_block_swaps
            },
        )
        def declared_faint_warps(candidate):
            # A faint message can interrupt an already-started native doorway.
            # Admit only endpoints from the route being executed, as in item
            # transport. The strict handler still verifies every resource.
            return tuple(
                (segment.source_map, segment.transition.exit_at,
                 segment.target_map, segment.transition.arrival_at)
                for segment in candidate.segments if segment.passage_kind == "warp"
                and segment.source_map != segment.target_map
            ) if self.allow_field_faint_dialogue else ()

        interruption_handler: Gen1WildFleeHandler | Gen1RouteInterruptionHandler
        wild_handler = Gen1WildFleeHandler(
            field_actions,
            reader,
            maximum_flees=self.maximum_flees,
            stabilization_frames=120,
            route_name="Red observed ground transition",
            allow_party_faints=self.allow_wild_faints,
            emulator=emulator if self.allow_wild_faints else None,
            allow_field_faint_dialogue=self.allow_field_faint_dialogue,
            field_faint_warps=declared_faint_warps(plan),
        )
        interruption_handler = wild_handler
        if self.maximum_scripted_dialogues or self.trainer_binding_factory is not None:
            interruption_handler = Gen1RouteInterruptionHandler(
                field_actions,
                reader,
                maximum_flees=self.maximum_flees,
                maximum_trainer_battles=(
                    self.maximum_learned_trainers if self.trainer_binding_factory is not None else 0
                ),
                stabilization_frames=120,
                maximum_scripted_dialogues=self.maximum_scripted_dialogues,
                max_scripted_dialogue_pulses=32,
                route_name="Red observed scripted ground transition",
                allow_wild_faints=self.allow_wild_faints,
                emulator=emulator if self.allow_wild_faints else None,
                wild_handler=wild_handler,
            )

        if self.trainer_binding_factory is not None:
            from .red_player_engaged_story import EngagedStoryRouteHandler

            # Only the existing exact native engagement binding may resolve a
            # sight trainer. Combat stays with the supplied frozen local battler;
            # the referee must verify the win and unchanged field boundary.
            interruption_handler = EngagedStoryRouteHandler(
                interruption_handler, reader, self.trainer_binding_factory,
                maximum_trainers=self.maximum_learned_trainers,
            )

        def replan(request):
            updated = (
                base_world.with_current_blocks(reader.read_current_map_blocks())
                if self.observe_terrain
                else base_world
            )
            candidate = (updated if self.observe_terrain else base_world).replanner()(request)
            if self.require_cash_safe:
                require_cash_safe_plan(self.rom, reader.read(), candidate)
            if self.allow_field_faint_dialogue:
                wild_handler.field_faint_warps = declared_faint_warps(candidate)
            return candidate

        execute_route(
            plan,
            field_actions,
            observer,
            interruption_handler=interruption_handler,
            replanner=(
                replan if (self.observe_terrain or self.require_cash_safe
                           or self.allow_field_faint_dialogue) else base_world.replanner()
            ),
            limits=replace(
                DEFAULT_ROUTE_EXECUTION_LIMITS,
                max_interruptions=max(1, self.maximum_flees + self.maximum_scripted_dialogues
                                      + (6 if self.allow_field_faint_dialogue else 0)
                                      + (self.maximum_learned_trainers
                                         if self.trainer_binding_factory is not None else 0)),
                max_replans=16,
                max_readiness_waits=self.maximum_readiness_waits,
                transition_settle_frames=self.transition_settle_frames,
            ),
        )
        terminal = observer.observe()
        if (
            terminal.map_id != self.destination_map
            or terminal.at != self.destination_at
            or not terminal.ready
            or terminal.interruption is not None
        ):
            raise RouteExecutionError("Red ground transition did not prove the requested boundary")


__all__ = [
    "VERMILION_TRAINING_EXTERIOR",
    "RedVermilionGroundTransition",
]
