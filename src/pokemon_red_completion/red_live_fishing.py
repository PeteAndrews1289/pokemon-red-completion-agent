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
from dataclasses import dataclass, replace
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor, FrameBudgetController
from pokemon_red_completion.fishing import (
    FishingCastExecutor,
    ShorelineStance,
    fishable_shoreline_stances,
)
from pokemon_red_completion.gen1_field_moves import (
    Gen1FieldMoveError,
    Gen1FieldMovePort,
    fly_menu_indices,
)
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.global_router import GlobalRouterError, find_macro_path
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionContext
from pokemon_red_completion.local_router import find_local_paths, without_coordinates
from pokemon_red_completion.observation import (
    RED_FLY_TOWN_NAMES,
    Badge,
    MapId,
    PokemonRedStateReader,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection_fly import red_fly_landings
from pokemon_red_completion.red_dig_recovery import (
    DigEscapePlan,
    execute_dig_escape,
    plan_dig_escape,
)
from pokemon_red_completion.red_fishing_acquisition import (
    RedFishingDestinationOffer,
    red_fishing_destination_candidates,
    red_super_rod_destination_offers,
)
from pokemon_red_completion.red_fishing_capture import (
    LiveRedFishingCapturePort,
    RedFishingCaptureReport,
    ordinary_fishing_capture_items_available,
    run_red_fishing_capture,
)
from pokemon_red_completion.red_live_option_menu import (
    RedLiveSupplementalOption,
    supplemental_live_option,
)
from pokemon_red_completion.red_resource_goal_router import _supported_plan
from pokemon_red_completion.red_safari_fishing import run_safari_fishing, safari_route_supported
from pokemon_red_completion.route_executor import TraversalSnapshot, execute_route
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)
from pokemon_red_completion.surge import DEFAULT_SURGE_TIMING, LiveWildEncounterExecutor


class RedLiveFishingError(RuntimeError):
    """Fishing option construction or execution crossed its declared boundary."""


_SINGLE_DESTINATION_ROUTE_STEP_NORMALIZATION = 1_000
_MAXIMUM_ALTERNATE_SHORELINE_PLANS = 4
_SAFARI_FISHING_MAPS = frozenset(
    {
        int(MapId.SAFARI_ZONE_EAST),
        int(MapId.SAFARI_ZONE_NORTH),
        int(MapId.SAFARI_ZONE_WEST),
        int(MapId.SAFARI_ZONE_CENTER),
    }
)


def _ordinary_fishing_origin(map_id: int) -> bool:
    # Safari uses BALL/BAIT/ROCK/RUN rather than the ordinary battle menu.
    # Ordinary route interruptions and capture controls cannot operate there.
    return map_id not in _SAFARI_FISHING_MAPS


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
    # Execution-only transport identities never enter public policy features.
    dig_escape: DigEscapePlan | None = None
    flight_origin: TraversalSnapshot | None = None
    departure_origin: TraversalSnapshot | None = None

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
        if self.dig_escape is not None and not isinstance(self.dig_escape, DigEscapePlan):
            raise TypeError("fishing escape quote must be typed")
        if self.flight_origin is not None and not isinstance(self.flight_origin, TraversalSnapshot):
            raise TypeError("fishing flight landing must be an observed projection")
        if self.departure_origin is not None and not isinstance(
            self.departure_origin, TraversalSnapshot
        ):
            raise TypeError("fishing departure must be an observed projection")

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
        if not isinstance(self.destinations, tuple) or any(
            not isinstance(item, RedReachableFishingDestination) for item in self.destinations
        ):
            raise TypeError("live fishing destinations must be immutable")
        if not isinstance(self.supplements, tuple) or any(
            not isinstance(item, RedLiveSupplementalOption) for item in self.supplements
        ):
            raise TypeError("live fishing supplements must be immutable")
        if len(self.destinations) != len(self.supplements) or any(
            supplement.binding.kind is not GoalKind.ACQUIRE_SPECIES
            for supplement in self.supplements
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
    stop_when_full: bool = False,
    safari_session_steps: int | None = None,
    dig_escape: DigEscapePlan | None = None,
    flight_origins: tuple[TraversalSnapshot, ...] = (),
    departure_origin: TraversalSnapshot | None = None,
    departure_steps: int = 0,
    departure_cost: int = 0,
    physical_demand: Collection[int] = (),
) -> tuple[RedReachableFishingDestination, ...]:
    """Find bounded productive fishing terminals without controller input."""

    if type(maximum_candidates) is not int or maximum_candidates < 1:
        raise ValueError("fishing inventory needs at least one candidate slot")
    if type(stop_when_full) is not bool:
        raise ValueError("fishing bounded discovery mode must be boolean")
    if not isinstance(traversal, TraversalSnapshot):
        raise TypeError("fishing inventory needs an observed traversal snapshot")
    safari = safari_session_steps is not None
    if safari and (type(safari_session_steps) is not int or safari_session_steps <= 0):
        raise ValueError("Safari discovery requires observed positive remaining steps")
    if safari and (dig_escape is not None or flight_origins or departure_origin is not None):
        raise ValueError("paid Safari fishing cannot use escape or flight")
    if safari == _ordinary_fishing_origin(traversal.map_id):
        return ()
    offers = red_super_rod_destination_offers(
        rom, registered_species_numbers,
        **({"physical_demand": physical_demand} if physical_demand else {}),
    )
    executable: list[RedReachableFishingDestination] = []
    walk_origin = (
        (departure_origin or traversal)
        if dig_escape is None
        else replace(
            traversal,
            map_id=dig_escape.anchor,
            at=dig_escape.landing,
            last_outside_map=dig_escape.anchor,
            occupied=frozenset(),
            hazards=(),
        )
    )
    for offer in offers:
        if (offer.map_id in _SAFARI_FISHING_MAPS) != safari:
            continue
        terrain = world.terrain.get(offer.map_id)
        graph = world.local_graphs.get(offer.map_id)
        if terrain is None or graph is None:
            continue
        # Shoreline eligibility is independent of the approach route. Reject
        # impossible destinations before expensive walking/Cut/Fly searches;
        # every surviving stance still gets the same exact route verification.
        blocked = set(world.object_blockers.get(offer.map_id, frozenset()))
        blocked.update(world.macro_graph.warp_locations.get(offer.map_id, ()))
        stances = tuple(
            stance for stance in fishable_shoreline_stances(terrain) if stance.at not in blocked
        )
        if not stances:
            continue
        # Reuse the existing Fly binder's topology-first feasible landing rule.
        # Do not repeatedly cross the entire cave/world for every shoreline.
        origins = []
        if flight_origins:
            for candidate in (walk_origin, *flight_origins):
                try:
                    topology = find_macro_path(
                        world.macro_graph,
                        candidate.map_id,
                        offer.map_id,
                        last_outside=candidate.last_outside_map,
                    )
                except GlobalRouterError:
                    continue
                origins.append((len(topology.edges), candidate.map_id, candidate))
        else:
            # Historical callers need neither topology enumeration nor Fly data.
            origins = [(0, walk_origin.map_id, walk_origin)]
        route = selected_origin = None
        for _, _, candidate in sorted(origins, key=lambda row: row[:2]):
            try:
                candidate_route = world.plan_feasible_to_map(candidate, offer.map_id)
            except RoutePlanningError:
                continue
            if candidate_route.steps and not _supported_plan(
                candidate_route, allow_cut=True, allow_surf=True
            ):
                continue
            route, selected_origin = candidate_route, candidate
            break
        if route is None or selected_origin is None:
            continue
        if route.steps and not _supported_plan(route, allow_cut=True, allow_surf=True):
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
        terminals: tuple[ShorelineStance, ...]
        if local:
            _local_cost, _local_steps, best = min(
                local,
                key=lambda row: (row[0], row[1], row[2].at, row[2].direction.value),
            )
            terminals = (best,)
        else:
            # The cheapest map entry may be in another connected component.
            # An exact terminal route can leave/re-enter through a building or
            # another passage. Lack of a local path is not proof of no route.
            # Bound the fallback; never claim exhaustive reachability.
            by_coordinate: dict[tuple[int, int], ShorelineStance] = {}
            for stance in sorted(stances, key=lambda s: (s.at, s.direction.value)):
                by_coordinate.setdefault(stance.at, stance)
            terminals = tuple(by_coordinate.values())[:_MAXIMUM_ALTERNATE_SHORELINE_PLANS]
        for stance in terminals:
            try:
                terminal_route = world.plan_feasible_to_map(
                    selected_origin,
                    offer.map_id,
                    goal_at=stance.at,
                )
            except RoutePlanningError:
                continue
            if not _supported_plan(terminal_route, allow_cut=True, allow_surf=True):
                continue
            if safari and not safari_route_supported(terminal_route, safari_session_steps):
                continue
            executable.append(
                RedReachableFishingDestination(
                    offer,
                    stance,
                    len(terminal_route.steps) + departure_steps,
                    terminal_route.cost + departure_cost,
                    dig_escape,
                    selected_origin if selected_origin is not walk_origin else None,
                    departure_origin,
                )
            )
            break
        if stop_when_full and len(executable) >= maximum_candidates:
            # Every admitted terminal has already passed the same exact route,
            # shoreline and paid-session checks. This opt-in changes only the
            # supplied shortlist, not execution legality or exhaustive coverage.
            break
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
    safari_session: bool = False,
    interruption_handler_wrapper=None,
) -> tuple[RedLiveSupplementalOption, ...]:
    """Bind an action-free fishing menu to single-use live executors."""

    if not isinstance(destinations, tuple) or any(
        not isinstance(item, RedReachableFishingDestination) for item in destinations
    ):
        raise TypeError("live fishing destinations must be immutable")
    if not isinstance(context, LivingDexOptionContext):
        raise TypeError("live fishing needs an option-value context")
    if type(maximum_casts) is not int or maximum_casts <= 0:
        raise ValueError("live fishing cast bound must be positive")
    if type(safari_session) is not bool:
        raise ValueError("Fishing session mode must be an explicit boolean")
    if interruption_handler_wrapper is not None and not callable(interruption_handler_wrapper):
        raise TypeError("fishing interruption wrapper must be callable")
    if not destinations:
        return ()
    maximum_route_steps = (
        _SINGLE_DESTINATION_ROUTE_STEP_NORMALIZATION
        if len(destinations) == 1
        else max(1, max(item.route_steps for item in destinations))
    )
    candidates = red_fishing_destination_candidates(
        tuple(item.offer for item in destinations),
        route_steps=tuple(item.route_steps for item in destinations),
        maximum_route_steps=maximum_route_steps,
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
                safari_session=safari_session,
                interruption_handler_wrapper=interruption_handler_wrapper,
            ),
            candidates[index],
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
    safari_session_steps: int | None = None,
    allow_fast_transport: bool = False,
    interruption_handler_wrapper=None,
    physical_demand: Collection[int] = (),
) -> RedLiveFishingInventory:
    """Assemble reachable fishing candidates and executors without input."""

    if type(allow_fast_transport) is not bool:
        raise ValueError("fishing transport scope must be explicit")
    if interruption_handler_wrapper is not None and not callable(interruption_handler_wrapper):
        raise TypeError("fishing interruption wrapper must be callable")
    if physical_demand and safari_session_steps is not None:
        raise ValueError("physical fishing dependency requires ordinary capture controls")
    escape = None
    flight_origins = ()
    departure = None
    departure_steps = departure_cost = 0
    if allow_fast_transport and safari_session_steps is None:
        raw = reader.read()
        escape = plan_dig_escape(world, reader, raw, traversal)
        outside = (
            traversal
            if escape is None
            else replace(
                traversal,
                map_id=escape.anchor,
                at=escape.landing,
                last_outside_map=escape.anchor,
                occupied=frozenset(),
                hazards=(),
            )
        )
        # Fishing can finish inside a gym. Reuse the ordinary indoor-to-last-
        # outside walking route before quoting Fly, instead of a world walk.
        if (
            escape is None
            and traversal.map_id >= 0x25
            and traversal.mode == "land"
            and traversal.ready
            and traversal.interruption is None
            and not raw.battle_state
            and traversal.last_outside_map is not None
            and 0 <= traversal.last_outside_map <= 0x24
            and traversal.last_outside_map != 0x0B
        ):
            try:
                walking = replace(
                    traversal,
                    capabilities=frozenset(
                        c for c in traversal.capabilities if not c.startswith("move:")
                    ),
                )
                exit_plan = world.plan_feasible_to_map(walking, traversal.last_outside_map)
            except RoutePlanningError:
                pass
            else:
                if (
                    exit_plan.steps
                    and len(exit_plan.steps) <= 256
                    and exit_plan.terminal_map == traversal.last_outside_map
                    and exit_plan.terminal_mode in {None, "land"}
                    and _supported_plan(exit_plan)
                ):
                    departure = outside = replace(
                        traversal,
                        map_id=exit_plan.terminal_map,
                        at=exit_plan.terminal_at,
                        mode="land",
                        last_outside_map=exit_plan.terminal_map,
                        occupied=frozenset(),
                        hazards=(),
                    )
                    departure_steps, departure_cost = len(exit_plan.steps), exit_plan.cost
        if 0 <= outside.map_id <= 0x24 and outside.map_id != 0x0B and outside.mode == "land":
            try:
                fly_menu_indices(raw)
            except Gen1FieldMoveError:
                pass
            else:
                if int(raw.badge_bits or 0) & int(Badge.THUNDER):
                    flight_origins = tuple(
                        replace(
                            outside,
                            map_id=town,
                            at=landing,
                            last_outside_map=town,
                            occupied=frozenset(),
                            hazards=(),
                        )
                        for town, landing in red_fly_landings(rom)
                        if town in reader.read_fly_destinations()
                        and town != outside.map_id
                        and town in world.local_graphs
                        and landing in world.local_graphs[town].edges
                        and landing not in world.object_blockers.get(town, frozenset())
                    )
    destinations = discover_reachable_red_fishing_destinations(
        rom,
        registered_species_numbers,
        world=world,
        traversal=traversal,
        maximum_candidates=maximum_candidates,
        safari_session_steps=safari_session_steps,
        **({"physical_demand": physical_demand} if physical_demand else {}),
        **(
            {}
            if not allow_fast_transport
            else dict(
                dig_escape=escape,
                flight_origins=flight_origins,
                departure_origin=departure,
                departure_steps=departure_steps,
                departure_cost=departure_cost,
            )
        ),
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
        safari_session=safari_session_steps is not None,
        interruption_handler_wrapper=interruption_handler_wrapper,
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
    safari_session: bool = False,
    interruption_handler_wrapper=None,
) -> ExecutableGoalBinding:
    from .red_resource_goal_router import _MAX_ROUTE_FLEES, _ROUTE_LIMITS

    attempt: dict[str, object] = {}
    claimed = False

    def route_interruptions(label):
        inner = Gen1RouteInterruptionHandler(
            actions, reader, maximum_flees=_MAX_ROUTE_FLEES, maximum_trainer_battles=0,
            stabilization_frames=180, route_name=label, maximum_scripted_dialogues=4,
        )
        return (inner if interruption_handler_wrapper is None
                else interruption_handler_wrapper(inner))

    def execute() -> GoalExecutionReport:
        nonlocal claimed
        if claimed:
            raise RedLiveFishingError("live fishing binding was already consumed")
        claimed = True
        origin = observer.observe()
        if not safari_session and (
            not _ordinary_fishing_origin(origin.map_id)
            or destination.offer.map_id in _SAFARI_FISHING_MAPS
        ):
            raise RedLiveFishingError("ordinary fishing does not support Safari battle controls")
        before_actions = actions.actions_executed
        before_frames = emulator.frame_count
        before_registered = frozenset(reader.read_pokedex_state().owned_species)
        if safari_session:
            result = run_safari_fishing(
                destination,
                world=world,
                observer=observer,
                controller=controller,
                actions=actions,
                reader=reader,
                maximum_casts=maximum_casts,
            )
        else:
            transport = {}
            if destination.dig_escape is not None:
                transport["dig"] = execute_dig_escape(
                    world, reader, emulator, actions, destination.dig_escape
                )
                origin = observer.observe()
            if destination.departure_origin is not None:
                outside = destination.departure_origin
                if (
                    destination.dig_escape is not None
                    or origin.map_id < 0x25
                    or origin.mode != "land"
                    or not origin.ready
                    or origin.interruption is not None
                    or origin.last_outside_map != outside.map_id
                    or reader.read().battle_state
                    or reader.read_bottom_dialogue_box_visible()
                    or reader.read_pending_trainer_battle_identity() is not None
                    or reader.read_fly_menu_state() is not None
                ):
                    raise RedLiveFishingError("selected fishing departure is no longer legal")
                walking = replace(
                    origin,
                    capabilities=frozenset(
                        c for c in origin.capabilities if not c.startswith("move:")
                    ),
                )
                departure_plan = world.plan_feasible_to_map(
                    walking, outside.map_id, goal_at=outside.at
                )
                if (
                    not departure_plan.steps
                    or len(departure_plan.steps) > 256
                    or not _supported_plan(departure_plan)
                ):
                    raise RedLiveFishingError(
                        "selected fishing departure needs unsupported transport"
                    )
                departed = execute_route(
                    departure_plan,
                    field,
                    observer,
                    interruption_handler=route_interruptions(
                        "model-directed fishing indoor departure"
                    ),
                    replanner=world.replanner(),
                    limits=_ROUTE_LIMITS,
                )
                origin = observer.observe()
                if not departed.passed or (
                    origin.map_id,
                    origin.at,
                    origin.mode,
                    origin.ready,
                    origin.interruption,
                ) != (outside.map_id, outside.at, "land", True, None):
                    raise RedLiveFishingError(
                        "selected fishing departure missed its outside boundary"
                    )
                transport["indoor_departure"] = dict(
                    verified_departures=1, route_steps=len(departure_plan.steps)
                )
            if destination.flight_origin is not None:
                landing = destination.flight_origin
                raw = reader.read()
                if (
                    not origin.ready
                    or origin.interruption is not None
                    or origin.mode != "land"
                    or not 0 <= origin.map_id <= 0x24
                    or origin.map_id == 0x0B
                    or raw.battle_state
                    or reader.read_bottom_dialogue_box_visible()
                    or reader.read_pending_trainer_battle_identity() is not None
                    or reader.read_fly_menu_state() is not None
                    or not int(raw.badge_bits or 0) & int(Badge.THUNDER)
                    or landing.map_id not in reader.read_fly_destinations()
                ):
                    raise RedLiveFishingError("selected fishing flight is no longer legal")
                fly_menu_indices(raw)
                if dict(red_fly_landings(world.rom)).get(landing.map_id) != landing.at:
                    raise RedLiveFishingError("selected fishing landing differs from cartridge")
                field.execute(
                    MacroAction(
                        MacroActionKind.FIELD_MOVE,
                        "fly:" + RED_FLY_TOWN_NAMES[landing.map_id].lower().replace(" ", "_"),
                    )
                )
                origin = observer.observe()
                if (origin.map_id, origin.at, origin.mode, origin.ready, origin.interruption) != (
                    landing.map_id,
                    landing.at,
                    "land",
                    True,
                    None,
                ):
                    raise RedLiveFishingError("selected fishing flight missed its landing")
                transport["fly"] = dict(verified_flights=1, cartridge_landing_verified=True)
            try:
                plan = world.plan_feasible_to_map(
                    origin,
                    destination.offer.map_id,
                    goal_at=destination.stance.at,
                )
            except RoutePlanningError as error:
                raise RedLiveFishingError(
                    "selected fishing destination became unreachable"
                ) from error
            if not _supported_plan(plan, allow_cut=True, allow_surf=True):
                raise RedLiveFishingError("selected fishing route needs unsupported transport")
            interruptions = route_interruptions("model-directed fishing destination")
            route = execute_route(
                plan,
                field,
                observer,
                interruption_handler=interruptions,
                replanner=world.replanner(),
                limits=_ROUTE_LIMITS,
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

            def observe_fishing_diagnostics():
                from .capture_survey import capture_diagnostic_observation

                counters = actions.actions_executed, emulator.frame_count
                raw = reader.read()
                facts = dict(
                    diagnostic_only=True, native_actions=counters[0], native_frames=counters[1],
                    map_id=raw.map_id, player_x=raw.player_x, player_y=raw.player_y,
                    movement_mode=int(reader.read_overworld_movement_mode()),
                    repel_remaining_steps=raw.repel_remaining_steps, party_levels=raw.party_levels,
                    player_money=raw.player_money, bag_items=raw.bag_items,
                    capture_conditions=capture_diagnostic_observation(raw),
                    registered_species=sorted(port.registered_species_numbers()),
                    physical_target_stock={str(n): port.physical_species_count(n)
                                           for n in destination.offer.physical_species_numbers},
                )
                if counters != (actions.actions_executed, emulator.frame_count):
                    raise RedLiveFishingError("fishing diagnostics advanced native execution")
                return facts

            result = run_red_fishing_capture(
                destination.offer,
                port,
                maximum_casts=maximum_casts,
                capture_items_available=lambda: ordinary_fishing_capture_items_available(reader),
                record_diagnostic_event=getattr(actions, "record_diagnostic_event", None),
                observe_diagnostics=observe_fishing_diagnostics,
            )
        after_registered = frozenset(reader.read_pokedex_state().owned_species)
        attempt.update(
            before_registered=before_registered,
            after_registered=after_registered,
            result=result,
        )
        if destination.offer.physical_species_numbers:
            attempt["physical_terminal"] = emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - before_actions,
            emulator.frame_count - before_frames,
            {**result.public_dict(), **({} if safari_session else {"transport": transport})},
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
            or (destination.offer.physical_species_numbers
                and attempt.get("physical_terminal") != emulator.save_state_bytes())
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if result.passed:
            return GoalVerification.succeeded()
        if result.capture_items_exhausted:
            if (
                ordinary_fishing_capture_items_available(reader)
                or reader.read().battle_state
                or not reader.read_input_readiness().ready
                or reader.read_bottom_dialogue_box_visible()
            ):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.failed(GoalFailureReason.CAPTURE_ITEMS_EXHAUSTED)
        return GoalVerification.failed(GoalFailureReason.SEARCH_EXHAUSTED)

    return ExecutableGoalBinding(
        binding_ref=(
            "pokemon.red:safari-fishing-live:" if safari_session else "pokemon.red:fishing-live:"
        )
        + canonical_sha256(
            {
                "map": destination.offer.map_id,
                "stance": destination.stance.at,
                "facing": destination.stance.direction.value,
                "water": destination.stance.water_at,
                "missing": destination.offer.missing_species_numbers,
                **({"physical": destination.offer.physical_species_numbers}
                   if destination.offer.physical_species_numbers else {}),
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
