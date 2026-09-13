"""Reusable live fishing options for model-directed Red collection.

Candidate discovery is action-free: cartridge encounter tables, the observed
registration set, the current traversal snapshot, and the route world produce
private reachable destinations.  Only normalized effort and productivity enter
the learned menu.  A selected private binding then replans and executes one
bounded route-and-capture attempt; the model never receives a map, coordinate,
species, or button sequence.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.executor import CountingExecutor, FrameBudgetController
from pokemon_red_completion.fishing import (
    FishingCastExecutor,
    ShorelineStance,
    fishable_shoreline_stances,
)
from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionContext
from pokemon_red_completion.local_router import find_local_paths, without_coordinates
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_fishing_acquisition import (
    RedFishingDestinationOffer,
    red_fishing_destination_menu,
    red_super_rod_destination_offers,
)
from pokemon_red_completion.red_fishing_capture import (
    LiveRedFishingCapturePort,
    RedFishingCaptureReport,
    run_red_fishing_capture,
)
from pokemon_red_completion.red_live_option_menu import (
    RedLiveSupplementalOption,
    supplemental_live_option,
)
from pokemon_red_completion.red_resource_goal_router import _supported_plan
from pokemon_red_completion.route_executor import TraversalSnapshot, execute_route
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)
from pokemon_red_completion.surge import DEFAULT_SURGE_TIMING, LiveWildEncounterExecutor


class RedLiveFishingError(RuntimeError):
    """Fishing option construction or execution crossed its declared boundary."""


class RedLiveFishingEmulator(Protocol):
    """Small live-state surface needed to meter and verify one fishing attempt."""

    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...


@dataclass(frozen=True, slots=True)
class RedReachableFishingDestination:
    """One private route terminal and its identity-free menu measurements."""

    offer: RedFishingDestinationOffer
    stance: ShorelineStance
    route_steps: int
    route_cost: int

    def __post_init__(self) -> None:
        if not isinstance(self.offer, RedFishingDestinationOffer):
            raise TypeError("reachable fishing destination needs a cartridge offer")
        if not isinstance(self.stance, ShorelineStance):
            raise TypeError("reachable fishing destination needs a shoreline stance")
        if (
            type(self.route_steps) is not int
            or self.route_steps < 0
            or type(self.route_cost) is not int
            or self.route_cost < 0
        ):
            raise ValueError("reachable fishing route measurements must be non-negative")

    def public_dict(self) -> dict[str, object]:
        """Return measurements without private destination or species identity."""

        return {
            "cartridge_derived": True,
            "feature_values": self.offer.policy_features(),
            "private_map_fields": 0,
            "private_path_fields": 0,
            "private_species_fields": 0,
            "route_cost": self.route_cost,
            "route_steps": self.route_steps,
        }


@dataclass(frozen=True, slots=True)
class RedLiveFishingInventory:
    """Aligned private destinations and mixed-menu supplemental bindings."""

    destinations: tuple[RedReachableFishingDestination, ...]
    supplements: tuple[RedLiveSupplementalOption, ...]

    def __post_init__(self) -> None:
        if (
            len(self.destinations) < 2
            or len(self.destinations) != len(self.supplements)
            or any(
                supplement.binding.kind is not GoalKind.ACQUIRE_SPECIES
                for supplement in self.supplements
            )
        ):
            raise RedLiveFishingError("live fishing inventory is not executable")

    def public_dict(self) -> dict[str, object]:
        return {
            "candidate_count": len(self.destinations),
            "candidates": [item.public_dict() for item in self.destinations],
            "identity_fields_public": 0,
            "private_binding_fields": 0,
            "schema": "pokemon.red.live-fishing-inventory.v1",
        }


def discover_reachable_red_fishing_destinations(
    rom: bytes,
    registered_species_numbers: Collection[int],
    *,
    world: StrategicScenarioRouteWorld,
    traversal: TraversalSnapshot,
    maximum_candidates: int = 4,
) -> tuple[RedReachableFishingDestination, ...]:
    """Find bounded productive fishing terminals without controller input."""

    if type(maximum_candidates) is not int or maximum_candidates < 2:
        raise ValueError("fishing inventory needs at least two candidate slots")
    if not isinstance(traversal, TraversalSnapshot):
        raise TypeError("fishing inventory needs an observed traversal snapshot")
    offers = red_super_rod_destination_offers(rom, registered_species_numbers)
    executable: list[RedReachableFishingDestination] = []
    for offer in offers:
        terrain = world.terrain.get(offer.map_id)
        graph = world.local_graphs.get(offer.map_id)
        if terrain is None or graph is None:
            continue
        try:
            route = world.plan_feasible_to_map(traversal, offer.map_id)
        except RoutePlanningError:
            continue
        if route.steps and not _supported_plan(route, allow_cut=True, allow_surf=True):
            continue
        blocked = set(world.object_blockers.get(offer.map_id, frozenset()))
        blocked.update(world.macro_graph.warp_locations.get(offer.map_id, ()))
        stances = tuple(
            stance
            for stance in fishable_shoreline_stances(terrain)
            if stance.at not in blocked
        )
        if not stances:
            continue
        paths = find_local_paths(
            without_coordinates(graph, blocked),
            route.terminal_at,
            {(stance.at, None) for stance in stances},
            capabilities=traversal.capabilities,
            start_mode=route.terminal_mode,
        )
        local = tuple(
            (
                sum(edge.cost for edge in path.edges),
                len(path.edges),
                stance,
            )
            for stance in stances
            if (path := paths.get((stance.at, None))) is not None
        )
        if not local:
            continue
        _local_cost, _local_steps, stance = min(
            local,
            key=lambda row: (row[0], row[1], row[2].at, row[2].direction.value),
        )
        try:
            terminal_route = world.plan_feasible_to_map(
                traversal,
                offer.map_id,
                goal_at=stance.at,
            )
        except RoutePlanningError:
            continue
        if not _supported_plan(terminal_route, allow_cut=True, allow_surf=True):
            continue
        executable.append(
            RedReachableFishingDestination(
                offer,
                stance,
                len(terminal_route.steps),
                terminal_route.cost,
            )
        )
    executable.sort(
        key=lambda row: (
            row.route_steps,
            row.route_cost,
            -row.offer.productive_slot_count,
            row.offer.map_id,
            row.stance.at,
            row.stance.direction.value,
        )
    )
    return tuple(executable[:maximum_candidates])


def build_red_live_fishing_supplements(
    context: LivingDexOptionContext,
    destinations: tuple[RedReachableFishingDestination, ...],
    *,
    free_storage_slots: int,
    world: StrategicScenarioRouteWorld,
    observer: Gen1TraversalObserver,
    field: Gen1FieldMovePort,
    controller: FrameBudgetController,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: RedLiveFishingEmulator,
    maximum_casts: int = 24,
) -> tuple[RedLiveSupplementalOption, ...]:
    """Bind an action-free fishing menu to single-use live executors."""

    if not isinstance(destinations, tuple) or any(
        not isinstance(item, RedReachableFishingDestination) for item in destinations
    ):
        raise TypeError("live fishing destinations must be immutable")
    if type(maximum_casts) is not int or maximum_casts <= 0:
        raise ValueError("live fishing cast bound must be positive")
    if len(destinations) < 2:
        raise RedLiveFishingError("live fishing needs at least two reachable destinations")
    menu = red_fishing_destination_menu(
        context,
        tuple(item.offer for item in destinations),
        route_steps=tuple(item.route_steps for item in destinations),
        maximum_route_steps=max(1, max(item.route_steps for item in destinations)),
        free_storage_slots=free_storage_slots,
    )
    return tuple(
        supplemental_live_option(
            _live_fishing_binding(
                destination=destination,
                world=world,
                observer=observer,
                field=field,
                controller=controller,
                actions=actions,
                reader=reader,
                emulator=emulator,
                maximum_casts=maximum_casts,
            ),
            menu.candidates[index],
        )
        for index, destination in enumerate(destinations)
    )


def build_red_live_fishing_inventory(
    rom: bytes,
    registered_species_numbers: Collection[int],
    context: LivingDexOptionContext,
    *,
    free_storage_slots: int,
    world: StrategicScenarioRouteWorld,
    traversal: TraversalSnapshot,
    observer: Gen1TraversalObserver,
    field: Gen1FieldMovePort,
    controller: FrameBudgetController,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: RedLiveFishingEmulator,
    maximum_candidates: int = 4,
    maximum_casts: int = 24,
) -> RedLiveFishingInventory:
    """Assemble reachable fishing candidates and executors without input."""

    destinations = discover_reachable_red_fishing_destinations(
        rom,
        registered_species_numbers,
        world=world,
        traversal=traversal,
        maximum_candidates=maximum_candidates,
    )
    supplements = build_red_live_fishing_supplements(
        context,
        destinations,
        free_storage_slots=free_storage_slots,
        world=world,
        observer=observer,
        field=field,
        controller=controller,
        actions=actions,
        reader=reader,
        emulator=emulator,
        maximum_casts=maximum_casts,
    )
    return RedLiveFishingInventory(destinations, supplements)


def _live_fishing_binding(
    *,
    destination: RedReachableFishingDestination,
    world: StrategicScenarioRouteWorld,
    observer: Gen1TraversalObserver,
    field: Gen1FieldMovePort,
    controller: FrameBudgetController,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: RedLiveFishingEmulator,
    maximum_casts: int,
) -> ExecutableGoalBinding:
    attempt: dict[str, object] = {}
    claimed = False

    def execute() -> GoalExecutionReport:
        nonlocal claimed
        if claimed:
            raise RedLiveFishingError("live fishing binding was already consumed")
        claimed = True
        before_actions = actions.actions_executed
        before_frames = emulator.frame_count
        before_registered = frozenset(reader.read_pokedex_state().owned_species)
        try:
            plan = world.plan_feasible_to_map(
                observer.observe(),
                destination.offer.map_id,
                goal_at=destination.stance.at,
            )
        except RoutePlanningError as error:
            raise RedLiveFishingError("selected fishing destination became unreachable") from error
        if not _supported_plan(plan, allow_cut=True, allow_surf=True):
            raise RedLiveFishingError("selected fishing route needs unsupported transport")
        interruptions = Gen1RouteInterruptionHandler(
            actions,
            reader,
            maximum_flees=16,
            maximum_trainer_battles=0,
            stabilization_frames=180,
            route_name="model-directed fishing destination",
            maximum_scripted_dialogues=4,
        )
        route = execute_route(
            plan,
            field,
            observer,
            interruption_handler=interruptions,
            replanner=world.replanner(),
        )
        if not route.passed:
            raise RedLiveFishingError("selected fishing route missed its shoreline")
        encounters = LiveWildEncounterExecutor(
            controller,
            actions,
            reader,
            DEFAULT_SURGE_TIMING,
            label="model-directed fishing capture",
            capture_status_support=True,
        )
        port = LiveRedFishingCapturePort(
            FishingCastExecutor(actions, reader, controller),
            encounters,
            reader,
            destination.stance,
        )
        result = run_red_fishing_capture(
            destination.offer,
            port,
            maximum_casts=maximum_casts,
        )
        after_registered = frozenset(reader.read_pokedex_state().owned_species)
        attempt.update(
            before_registered=before_registered,
            after_registered=after_registered,
            result=result,
        )
        return GoalExecutionReport(
            actions.actions_executed - before_actions,
            emulator.frame_count - before_frames,
            result.public_dict(),
        )

    def verify(_report: GoalExecutionReport) -> GoalVerification:
        result = attempt.get("result")
        before = attempt.get("before_registered")
        after = attempt.get("after_registered")
        if (
            not isinstance(result, RedFishingCaptureReport)
            or not isinstance(before, frozenset)
            or not isinstance(after, frozenset)
            or not before <= after
            or len(after - before) != result.new_registrations
            or emulator.pressed_buttons
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if result.passed:
            return GoalVerification.succeeded()
        return GoalVerification.failed(GoalFailureReason.SEARCH_EXHAUSTED)

    return ExecutableGoalBinding(
        binding_ref="pokemon.red:fishing-live:"
        + canonical_sha256(
            {
                "map": destination.offer.map_id,
                "stance": destination.stance.at,
                "facing": destination.stance.direction.value,
                "water": destination.stance.water_at,
                "missing": destination.offer.missing_species_numbers,
                "casts": maximum_casts,
            }
        ),
        kind=GoalKind.ACQUIRE_SPECIES,
        estimated_effort=min(1.0, 0.2 + destination.route_steps / 1_000),
        estimated_risk=0.1,
        execute=execute,
        verify=verify,
    )


__all__ = [
    "RedLiveFishingInventory",
    "RedLiveFishingError",
    "RedReachableFishingDestination",
    "build_red_live_fishing_inventory",
    "build_red_live_fishing_supplements",
    "discover_reachable_red_fishing_destinations",
]
