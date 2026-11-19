"""Read-only route geometry for the existing native training callbacks.

Quotes are prospective router step counts, not measured controller steps, Fly
menu costs, encounter rates or wall time. Canonical venue-to-nurse round trips
are estimates from the same route world, not future game-state observations.
"""

from dataclasses import dataclass, field, replace
from types import SimpleNamespace

from .gen1_route_runtime import Gen1TraversalObserver
from .observation import MapId
from .red_collection_fly import red_fly_landings
from .red_resource_goal_router import _supported_plan
from .red_training_ground_route import ground_route_capability_projector
from .red_training_transitions import red_training_fly_available
from .route_plan import RoutePlanningError


@dataclass(frozen=True)
class NativeVenueGeometryQuote:
    venue_identity: tuple[str, tuple[str, ...]]
    source_raw: object = field(repr=False)
    travel_steps: int | None
    recovery_steps: int | None
    planned_entry: tuple[int, tuple[int, int]] | None
    flight_count: int
    unknown_reasons: tuple[str, ...]
    ordinary_home_map: int | None = field(default=None, repr=False)

    def __post_init__(self):
        if (
            type(self.venue_identity) is not tuple
            or len(self.venue_identity) != 2
            or not isinstance(self.venue_identity[0], str)
            or not self.venue_identity[0]
            or type(self.venue_identity[1]) is not tuple
            or any(not isinstance(x, str) for x in self.venue_identity[1])
        ):
            raise ValueError("geometry quote needs its exact venue binding")
        if self.ordinary_home_map is not None and (type(self.ordinary_home_map) is not int or not 0 <= self.ordinary_home_map <= 255):
            raise ValueError("ordinary geometry home binding differs")
        for value in (self.travel_steps, self.recovery_steps):
            if value is not None and (type(value) is not int or not 0 <= value <= 1_000_000):
                raise ValueError("geometry step count differs")
        if type(self.flight_count) is not int or not 0 <= self.flight_count <= 1:
            raise ValueError("geometry flight count differs")

    def require_binding(self, raw, venue):
        if self.ordinary_home_map is not None and getattr(venue, "home_map", None) != self.ordinary_home_map:
            raise ValueError("ordinary geometry home differs from executable binding")
        if self.source_raw != raw or self.venue_identity != venue.band.identity:
            raise ValueError("geometry quote source or venue differs")
        if self.planned_entry is not None and self.planned_entry[0] != venue.map_id:
            raise ValueError("geometry endpoint differs from executable venue")

    def public_dict(self):
        return dict(
            schema="pokemon.red.native-venue-route-geometry.v1",
            travel_steps=self.travel_steps,
            recovery_steps=self.recovery_steps,
            flight_count=self.flight_count,
            unknown_reasons=list(self.unknown_reasons),
            semantics="prospective_router_steps_not_native_time",
            recovery_origin="canonical_planned_venue_entry",
        )


def quote_native_evolution_venue_geometry(runtime, world, observation, venues):
    """Quote through existing planners without ticking, input or state edits."""
    raw = observation.raw
    if runtime.reader.read() != raw or raw.battle_state or not observation.input_ready:
        raise ValueError("geometry needs the exact ready native observation")
    source = runtime.emulator.save_state_bytes()
    frames, buttons = runtime.emulator.frame_count, runtime.emulator.pressed_buttons
    result = tuple(_quote_one(runtime, world, observation, venue) for venue in venues)
    if (
        runtime.reader.read() != raw
        or runtime.emulator.save_state_bytes() != source
        or runtime.emulator.frame_count != frames
        or runtime.emulator.pressed_buttons != buttons
    ):
        raise ValueError("read-only geometry changed native control or state")
    return result


def _quote_one(runtime, world, observation, venue):
    raw = observation.raw
    mansion = venue.map_id == int(MapId.POKEMON_MANSION_1F)
    regional = venue.map_id in {int(MapId.ROUTE_11), int(MapId.DIGLETTS_CAVE)}
    if not (mansion or regional):
        return NativeVenueGeometryQuote(
            venue.band.identity, raw, None, None, None, 0, ("undeclared_training_transport",)
        )
    city = int(MapId.CINNABAR_ISLAND if mansion else MapId.VERMILION_CITY)
    center = int(MapId.CINNABAR_POKECENTER if mansion else MapId.VERMILION_POKECENTER)
    permissions = ground_route_capability_projector(
        SimpleNamespace(allow_surf=mansion), runtime.emulator
    )
    start = Gen1TraversalObserver(runtime.reader, capability_projector=permissions).observe()
    if not start.ready or start.interruption is not None or start.mode != "land":
        return NativeVenueGeometryQuote(
            venue.band.identity, raw, None, None, None, 0, ("unsettled_traversal",)
        )
    current = world.with_current_observation(runtime.reader)
    reasons = []
    flight_count = 0

    def arrive(origin, plan):
        return replace(
            origin,
            map_id=plan.terminal_map,
            at=plan.terminal_at,
            mode=plan.terminal_mode,
            occupied=frozenset(),
            hazards=(),
            last_outside_map=(
                plan.terminal_map if plan.terminal_map <= 0x24 else origin.last_outside_map
            ),
        )

    def quote(origin, destination, at=None):
        plan = current.plan_feasible_to_map(
            origin, destination, **({"goal_at": at} if at is not None else {})
        )
        if not _supported_plan(plan, allow_cut=True, allow_surf=mansion, seafoam_state=raw):
            raise RoutePlanningError("unsupported training quote mechanics")
        return plan

    def venue_arrival(origin):
        # Cave's existing executor enters from Route11, not the Route2 gate.
        steps = 0
        if venue.map_id == int(MapId.DIGLETTS_CAVE):
            leg = quote(origin, int(MapId.ROUTE_11))
            steps += len(leg.steps)
            origin = arrive(origin, leg)
        leg = quote(origin, venue.map_id, (27, 5) if mansion else None)
        return arrive(origin, leg), steps + len(leg.steps)

    travel = None
    entry = None
    try:
        origin, steps = start, 0
        local = {city, center, venue.map_id}
        if regional:
            local |= {
                int(MapId.ROUTE_11),
                int(MapId.DIGLETTS_CAVE),
                int(MapId.DIGLETTS_CAVE_ROUTE_11),
            }
        if origin.map_id not in local and red_training_fly_available(raw):
            landings = dict(red_fly_landings(world.rom))
            outside = origin.map_id if origin.map_id <= 0x24 else origin.last_outside_map
            if city not in runtime.reader.read_fly_destinations() or outside not in landings:
                raise RoutePlanningError("training Fly quote lacks observed destinations")
            if origin.map_id != outside:
                leg = quote(origin, outside)
                steps += len(leg.steps)
                origin = arrive(origin, leg)
            origin = replace(
                origin,
                map_id=city,
                at=landings[city],
                mode="land",
                occupied=frozenset(),
                hazards=(),
                last_outside_map=city,
            )
            flight_count = 1
        nurse = quote(origin, center, (3, 3))
        steps += len(nurse.steps)
        entry, onward = venue_arrival(arrive(origin, nurse))
        travel = steps + onward
    except RoutePlanningError as error:
        reasons.append("travel: " + str(error))

    recovery = None
    try:
        # If departure is unknown, quote only this independent canonical leg.
        if entry is None:
            nurse = replace(
                start,
                map_id=center,
                at=(3, 3),
                mode="land",
                occupied=frozenset(),
                hazards=(),
                last_outside_map=city,
            )
            entry, _ = venue_arrival(nurse)
        to_nurse = quote(entry, center, (3, 3))
        _, back = venue_arrival(arrive(entry, to_nurse))
        recovery = len(to_nurse.steps) + back
    except RoutePlanningError as error:
        reasons.append("recovery: " + str(error))
    return NativeVenueGeometryQuote(
        venue.band.identity,
        raw,
        travel,
        recovery,
        None if entry is None else (entry.map_id, entry.at),
        flight_count,
        tuple(reasons),
    )


def quote_ordinary_preparation_venue_geometry(runtime, route, venues):
    """Quote the existing ground source->home->corridor executor and return.

    Uses canonical corridor entry for recovery, not a forecast of battle exits,
    encounters, Fly menus, healing duration or actual controller inputs. A failed
    geometric leg remains unknown and never manufactures an availability mask.
    """
    from .red_living_dex_provider_plan import red_living_dex_route_terminal_snapshot
    from .red_ordinary_preparation_venue import OrdinaryPreparationVenue
    if type(venues) is not tuple or any(type(v) is not OrdinaryPreparationVenue for v in venues):
        raise ValueError("ordinary geometry requires the exact typed venue inventory")
    raw = runtime.reader.read()
    if raw.battle_state or runtime.emulator.pressed_buttons:
        raise ValueError("ordinary geometry requires released field control")
    state = runtime.emulator.save_state_bytes()
    frames = runtime.emulator.frame_count
    world = route.route_world
    start = Gen1TraversalObserver(runtime.reader,
        capability_projector=ground_route_capability_projector(route, runtime.emulator)).observe()
    result = []
    for venue in venues:
        travel_steps, recovery_steps, entry = None, None, None
        reasons = []
        nurse = (7, 7) if venue.home_map == int(MapId.INDIGO_PLATEAU_LOBBY) else (3, 3)
        try:
            approach = world.plan_feasible_to_map(start, venue.home_map, goal_at=nurse)
            home = red_living_dex_route_terminal_snapshot(world, start, approach)
            outbound = world.plan_feasible_to_map(home, venue.corridor.map_id, goal_at=venue.corridor.origin_at)
            field = red_living_dex_route_terminal_snapshot(world, home, outbound)
            travel_steps = len(approach.steps) + len(outbound.steps)
            entry = (venue.corridor.map_id, venue.corridor.origin_at)
        except RoutePlanningError:
            reasons.append("ordinary_ground_approach_unknown")
        if entry is not None:
            try:
                recovery_steps = len(world.plan_feasible_to_map(field, venue.home_map, goal_at=nurse).steps)
            except RoutePlanningError:
                reasons.append("ordinary_canonical_nurse_return_unknown")
        else:
            reasons.append("ordinary_canonical_entry_unknown")
        result.append(NativeVenueGeometryQuote((venue.source_id, ()), raw,
            travel_steps, recovery_steps, entry, 0, tuple(reasons), ordinary_home_map=venue.home_map))
    if (runtime.reader.read() != raw or runtime.emulator.save_state_bytes() != state
        or runtime.emulator.frame_count != frames or runtime.emulator.pressed_buttons):
        raise ValueError("ordinary geometry changed native state or controls")
    return tuple(result)