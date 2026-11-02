"""Generation I story predicates projected onto the neutral local router.

Saffron's four guard houses have statically walkable corridors whose live
access is decided by one durable guard flag. Cerulean's robbed-house approach and Saffron's
Silph entrance have the opposite geometry problem: an object occupies the
passage before a story event and is displaced afterward. Route 12's Snorlax
uses the same pattern. Cartridge terrain remains responsible for geometry;
this adapter contributes only the title-specific predicates and object
coordinates whose static occupancy those predicates replace.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace

from pokemon_red_completion.local_router import LocalGraph
from pokemon_red_completion.observation import (
    SAFFRON_GUARD_ACCESS_MASK,
    EventFlag,
    ItemId,
    MapId,
    RawGameState,
    event_flag_is_set,
)
from pokemon_red_completion.semantic_traversal import (
    LocalPassageRequirement,
    PredicateObservation,
    PredicateState,
    apply_local_passage_requirements,
    satisfied_predicates,
)

SAFFRON_GUARDS_OPEN = "story:saffron_guards_open"
CERULEAN_ROBBED_HOUSE_OPEN = "story:cerulean_robbed_house_open"
CERULEAN_ROBBED_HOUSE_POLICE_AT = (12, 27)
SILPH_ENTRANCE_OPEN = "story:silph_entrance_open"
SAFFRON_SILPH_SECURITY_GUARD_AT = (22, 18)
SAFFRON_GYM_OPEN = "story:saffron_gym_open"
SAFFRON_GYM_ROCKET_GUARD_AT = (4, 34)
ROUTE_12_SNORLAX_CLEARED = "story:route_12_snorlax_cleared"
ROUTE_12_SNORLAX_AT = (62, 10)
SEAFOAM_CURRENT_CONTROL = "field:seafoam_current_control"
SEAFOAM_INTERIOR_MAP_IDS = frozenset(range(0x9F, 0xA3))
SAFARI_ADMISSION_SUPPORTED = "service:safari_admission_supported"
SAFARI_ADMISSION_GATE_EDGES = tuple(
    ((3, column), (2, column)) for column in (3, 4)
)
LEAGUE_REVERSE_EXIT_SUPPORTED = "service:league_reverse_exit_supported"
# Lorelei/Bruno/Agatha's native entrance scripts reject walking back out,
# including after victory. The static warps still exist, but are not a nurse
# route. Keep forward entrance/automatic-upward movement and escape from a
# rejected trigger square; no ordinary observer grants this reverse service.
# Script sources: pret/pokered scripts/{Loreleis,Brunos,Agathas}Room.asm.
LEAGUE_REVERSE_EXIT_REQUIREMENTS = tuple(
    LocalPassageRequirement(
        map_id=int(map_id),source_at=source,target_at=target,
        predicate=LEAGUE_REVERSE_EXIT_SUPPORTED,
    )
    for map_id in (MapId.LORELEIS_ROOM, MapId.BRUNOS_ROOM, MapId.AGATHAS_ROOM)
    for source,target in (
        ((9,4),(10,4)),((9,5),(10,5)),
        ((10,3),(10,4)),((10,6),(10,5)),
        ((10,4),(11,4)),((10,5),(11,5)),
        ((11,3),(11,4)),((11,6),(11,5)),
    )
)
ROUTE_5_GATE_MAP_ID = 0x46
ROUTE_6_GATE_MAP_ID = 0x49
ROUTE_8_GATE_MAP_ID = 0x4F
BICYCLE_CARRIED = "item:bicycle_carried"
CINNABAR_GYM_KEY_CARRIED = "item:cinnabar_gym_key_carried"
CINNABAR_GYM_LOCK_TRIGGER = (4, 18)
ROUTE_18_GATE_1F_MAP_ID = 0xBE
PEWTER_EAST_EXIT_OPEN = "story:pewter_east_exit_open"
# PewterCityCheckPlayerLeavingEastScript checks EVENT_BEAT_BROCK before
# entering any of these four squares. Otherwise its guide owns the joypad
# and walks Red back to the Gym; these are not ordinary Route3 walking edges.
# Coordinates are (y,x), authenticated against the supported Red cartridge.
PEWTER_EAST_EXIT_TRIGGERS = frozenset({(17, 35), (17, 36), (18, 37), (19, 37)})

# Both Cycling Road guard scripts check the live bag, not a story flag or PC
# inventory. Entering any trigger square requires the Bicycle. Outgoing edges
# to non-trigger squares remain usable so a retained rejected player can leave.
CYCLING_ROAD_GATE_REQUIREMENTS = tuple(
    LocalPassageRequirement(
        map_id=map_id,
        source_at=source,
        target_at=(row, 4),
        predicate=BICYCLE_CARRIED,
    )
    for map_id, rows in (
        (int(MapId.ROUTE_16_GATE_1F), range(7, 11)),
        (ROUTE_18_GATE_1F_MAP_ID, range(3, 7)),
    )
    for row in rows
    for source in ((row - 1, 4), (row + 1, 4), (row, 3), (row, 5))
    if source[1] != 4 or source[0] in rows
)

# The cartridge scripts trigger on x=3/4,y=3 in Route 5; x=3/4,y=2 in
# Route 6; x=3,y=3/4 in Route 7; and x=2,y=3/4 in Route 8.  Bind the edge
# crossed to enter each trigger row/column in both directions.  Covering all
# four houses matters even when Route 7 is the destination: a global shortest
# path may otherwise cut illegally through Saffron via another closed gate.
_NORTH_SOUTH_GUARD_REQUIREMENTS = tuple(
    LocalPassageRequirement(
        map_id=int(map_id),
        source_at=source,
        target_at=target,
        predicate=SAFFRON_GUARDS_OPEN,
    )
    for map_id in (ROUTE_5_GATE_MAP_ID, ROUTE_6_GATE_MAP_ID)
    for column in (3, 4)
    for source, target in (
        ((2, column), (3, column)),
        ((3, column), (2, column)),
    )
)
_EAST_WEST_GUARD_REQUIREMENTS = tuple(
    LocalPassageRequirement(
        map_id=map_id,
        source_at=source,
        target_at=target,
        predicate=SAFFRON_GUARDS_OPEN,
    )
    for map_id in (int(MapId.ROUTE_7_GATE), ROUTE_8_GATE_MAP_ID)
    for row in (3, 4)
    for source, target in (
        ((row, 2), (row, 3)),
        ((row, 3), (row, 2)),
    )
)
SAFFRON_GUARD_GATE_REQUIREMENTS = (
    *_NORTH_SOUTH_GUARD_REQUIREMENTS,
    *_EAST_WEST_GUARD_REQUIREMENTS,
)
ROUTE_7_GATE_REQUIREMENTS = tuple(
    item
    for item in SAFFRON_GUARD_GATE_REQUIREMENTS
    if item.map_id == int(MapId.ROUTE_7_GATE)
)

# Before Bill is helped, a police officer occupies this square in Cerulean and
# blocks the robbed-house passage. The event script moves the officer afterward.
# Keep the coordinate in the graph, require the durable Bill flag on every edge
# through it, and remove only this story-displaced object from static blockers.
CERULEAN_ROBBED_HOUSE_REQUIREMENTS = tuple(
    LocalPassageRequirement(
        map_id=int(MapId.CERULEAN_CITY),
        source_at=source,
        target_at=target,
        predicate=CERULEAN_ROBBED_HOUSE_OPEN,
    )
    for adjacent in ((11, 27), (12, 26), (13, 27))
    for source, target in (
        (adjacent, CERULEAN_ROBBED_HOUSE_POLICE_AT),
        (CERULEAN_ROBBED_HOUSE_POLICE_AT, adjacent),
    )
)

# Rescuing Mr. Fuji hides the security guard on the Silph doorway approach and
# shows a sleeping Rocket one square to its east. Keep the doorway coordinate
# in the graph, require both durable rescue flags on every usable edge through
# it, and leave the sleeping Rocket's separate coordinate statically blocked.
SILPH_ENTRANCE_REQUIREMENTS = tuple(
    LocalPassageRequirement(
        map_id=int(MapId.SAFFRON_CITY),
        source_at=source,
        target_at=target,
        predicate=SILPH_ENTRANCE_OPEN,
    )
    for adjacent in ((21, 18), (22, 17), (23, 18))
    for source, target in (
        (adjacent, SAFFRON_SILPH_SECURITY_GUARD_AT),
        (SAFFRON_SILPH_SECURITY_GUARD_AT, adjacent),
    )
)

# Defeating Giovanni in Silph hides the Rocket immediately below Saffron Gym.
# The warp itself is static terrain, so route access must be tied to the
# independently observed victory flag rather than inferred from map topology.
SAFFRON_GYM_REQUIREMENTS = tuple(
    LocalPassageRequirement(
        map_id=int(MapId.SAFFRON_CITY),
        source_at=source,
        target_at=target,
        predicate=SAFFRON_GYM_OPEN,
    )
    for adjacent in ((3, 34), (4, 33), (4, 35))
    for source, target in (
        (adjacent, SAFFRON_GYM_ROCKET_GUARD_AT),
        (SAFFRON_GYM_ROCKET_GUARD_AT, adjacent),
    )
)

# The flute encounter removes the Route 12 Snorlax object permanently.  Keep
# its cartridge terrain square and bind every direction through it to the
# independently observed encounter flag.
ROUTE_12_SNORLAX_REQUIREMENTS = tuple(
    LocalPassageRequirement(
        map_id=int(MapId.ROUTE_12),
        source_at=source,
        target_at=target,
        predicate=ROUTE_12_SNORLAX_CLEARED,
    )
    for adjacent in ((61, 10), (63, 10), (62, 9), (62, 11))
    for source, target in (
        (adjacent, ROUTE_12_SNORLAX_AT),
        (ROUTE_12_SNORLAX_AT, adjacent),
    )
)

GEN1_STORY_PASSAGE_REQUIREMENTS = (
    *SAFFRON_GUARD_GATE_REQUIREMENTS,
    *CERULEAN_ROBBED_HOUSE_REQUIREMENTS,
    *SILPH_ENTRANCE_REQUIREMENTS,
    *SAFFRON_GYM_REQUIREMENTS,
    *ROUTE_12_SNORLAX_REQUIREMENTS,
    *CYCLING_ROAD_GATE_REQUIREMENTS,
)

GEN1_STORY_DISPLACED_OBJECTS: Mapping[int, frozenset[tuple[int, int]]] = {
    int(MapId.CERULEAN_CITY): frozenset({CERULEAN_ROBBED_HOUSE_POLICE_AT}),
    int(MapId.SAFFRON_CITY): frozenset(
        {
            SAFFRON_SILPH_SECURITY_GUARD_AT,
            SAFFRON_GYM_ROCKET_GUARD_AT,
        }
    ),
    int(MapId.ROUTE_12): frozenset({ROUTE_12_SNORLAX_AT}),
}


def observe_gen1_story_predicates(raw: RawGameState) -> tuple[PredicateObservation, ...]:
    """Classify supported story and carried-item predicates from one observation."""

    if not raw.game_started or raw.status_flags_1 is None:
        guard_state = PredicateState.UNKNOWN
    elif raw.status_flags_1 & SAFFRON_GUARD_ACCESS_MASK:
        guard_state = PredicateState.SATISFIED
    else:
        guard_state = PredicateState.UNSATISFIED
    if not raw.game_started or raw.event_flags is None:
        house_state = PredicateState.UNKNOWN
    elif event_flag_is_set(
        raw.event_flags,
        int(EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING),
    ):
        house_state = PredicateState.SATISFIED
    else:
        house_state = PredicateState.UNSATISFIED
    if not raw.game_started or raw.event_flags is None:
        silph_state = PredicateState.UNKNOWN
    elif all(
        event_flag_is_set(raw.event_flags, int(event))
        for event in (
            EventFlag.RESCUED_MR_FUJI,
            EventFlag.RESCUED_MR_FUJI_WORLD,
        )
    ):
        silph_state = PredicateState.SATISFIED
    else:
        silph_state = PredicateState.UNSATISFIED
    if not raw.game_started or raw.event_flags is None:
        gym_state = PredicateState.UNKNOWN
    elif event_flag_is_set(
        raw.event_flags,
        int(EventFlag.BEAT_SILPH_CO_GIOVANNI),
    ):
        gym_state = PredicateState.SATISFIED
    else:
        gym_state = PredicateState.UNSATISFIED
    if not raw.game_started or raw.event_flags is None:
        route_12_snorlax_state = PredicateState.UNKNOWN
    elif event_flag_is_set(
        raw.event_flags,
        int(EventFlag.BEAT_ROUTE12_SNORLAX),
    ):
        route_12_snorlax_state = PredicateState.SATISFIED
    else:
        route_12_snorlax_state = PredicateState.UNSATISFIED
    if not raw.game_started or raw.bag_items is None:
        bicycle_state = PredicateState.UNKNOWN
    elif any(item == int(ItemId.BICYCLE) and quantity > 0 for item, quantity in raw.bag_items):
        bicycle_state = PredicateState.SATISFIED
    else:
        bicycle_state = PredicateState.UNSATISFIED
    if not raw.game_started or raw.bag_items is None:
        gym_key_state = PredicateState.UNKNOWN
    elif any(item == int(ItemId.SECRET_KEY) and quantity > 0 for item, quantity in raw.bag_items):
        gym_key_state = PredicateState.SATISFIED
    else:
        gym_key_state = PredicateState.UNSATISFIED
    if not raw.game_started or raw.event_flags is None:
        pewter_exit_state = PredicateState.UNKNOWN
    elif event_flag_is_set(raw.event_flags, int(EventFlag.BEAT_BROCK)):
        pewter_exit_state = PredicateState.SATISFIED
    else:
        pewter_exit_state = PredicateState.UNSATISFIED
    return (
        PredicateObservation(SAFFRON_GUARDS_OPEN, guard_state),
        PredicateObservation(CERULEAN_ROBBED_HOUSE_OPEN, house_state),
        PredicateObservation(SILPH_ENTRANCE_OPEN, silph_state),
        PredicateObservation(SAFFRON_GYM_OPEN, gym_state),
        PredicateObservation(ROUTE_12_SNORLAX_CLEARED, route_12_snorlax_state),
        PredicateObservation(BICYCLE_CARRIED, bicycle_state),
        PredicateObservation(CINNABAR_GYM_KEY_CARRIED, gym_key_state),
        PredicateObservation(PEWTER_EAST_EXIT_OPEN, pewter_exit_state),
    )


def gen1_story_capabilities(raw: RawGameState) -> frozenset[str]:
    """Return only story predicates independently observed as satisfied."""

    return satisfied_predicates(observe_gen1_story_predicates(raw))


def apply_gen1_story_requirements(
    graphs: Mapping[int, LocalGraph],
) -> dict[int, LocalGraph]:
    """Bind every currently modelled Generation I story threshold."""

    story_bound = apply_local_passage_requirements(graphs, GEN1_STORY_PASSAGE_REQUIREMENTS)
    story_bound = apply_gen1_pewter_exit_requirement(story_bound)
    story_bound = apply_gen1_cinnabar_gym_requirement(story_bound)
    admission_bound = apply_gen1_safari_admission_requirement(story_bound)
    current_bound = apply_gen1_seafoam_current_requirements(admission_bound)
    return apply_gen1_league_reverse_exit_requirements(current_bound)


def apply_gen1_pewter_exit_requirement(
    graphs: Mapping[int, LocalGraph],
) -> dict[int, LocalGraph]:
    """Gate existing incoming guide-trigger edges without inventing terrain.

    Missing maps and wall edges remain absent. Egress from a retained trigger
    to a non-trigger square remains possible; only the native Brock event opens
    the east exit. This same overlay applies after live terrain reconstruction.
    """
    pewter = int(MapId.PEWTER_CITY)
    return {
        map_id: LocalGraph({
            source: tuple(
                replace(edge, requirements=edge.requirements | {PEWTER_EAST_EXIT_OPEN})
                if edge.target in PEWTER_EAST_EXIT_TRIGGERS else edge
                for edge in outgoing
            )
            for source, outgoing in graph.edges.items()
        }) if map_id == pewter else graph
        for map_id, graph in graphs.items()
    }


def apply_gen1_cinnabar_gym_requirement(
    graphs: Mapping[int, LocalGraph],
) -> dict[int, LocalGraph]:
    """Gate incoming door edges on the carried key, even after Blaine.

    CinnabarIsland's script checks IsItemInBag at (4,18), not the badge or
    completed objective. Bind existing edges only: walls stay walls and a
    retained rejected player can leave the trigger without a key. Reprojecting
    live bag capabilities restores access after an ordinary PC withdrawal.
    """
    island = int(MapId.CINNABAR_ISLAND)
    return {
        map_id: LocalGraph({
            source: tuple(
                replace(edge, requirements=edge.requirements | {CINNABAR_GYM_KEY_CARRIED})
                if map_id == island and edge.target == CINNABAR_GYM_LOCK_TRIGGER
                else edge
                for edge in outgoing
            )
            for source, outgoing in graph.edges.items()
        }) if map_id == island else graph
        for map_id, graph in graphs.items()
    }


def apply_gen1_league_reverse_exit_requirements(
    graphs: Mapping[int, LocalGraph],
) -> dict[int, LocalGraph]:
    """Reject reverse scripts on existing edges; closed terrain stays closed.

    This overlay also supports a partial world without adding absent maps or
    edges. Existing mandatory story-edge identity checks remain unchanged.
    """
    keyed = {(r.map_id,r.source_at,r.target_at) for r in LEAGUE_REVERSE_EXIT_REQUIREMENTS}
    return {
        map_id: LocalGraph({
            source: tuple(
                replace(edge,requirements=edge.requirements | {LEAGUE_REVERSE_EXIT_SUPPORTED})
                if (map_id,source,edge.target) in keyed else edge
                for edge in outgoing
            )
            for source,outgoing in graph.edges.items()
        })
        for map_id,graph in graphs.items()
    }


def apply_gen1_safari_admission_requirement(
    graphs: Mapping[int, LocalGraph],
) -> dict[int, LocalGraph]:
    """Do not treat a paid, scripted admission as a free walking edge.

    The Safari receptionist can displace the player instead of acknowledging
    an upward step. Ordinary traversal never grants this capability: a future
    route must compose an explicit, metered admission skill before planning
    through the gate. This preserves the independent scripted Safari chapter.
    """

    gate_map = int(MapId.SAFARI_ZONE_GATE)
    if gate_map not in graphs:
        return dict(graphs)
    return apply_local_passage_requirements(
        graphs,
        tuple(
            LocalPassageRequirement(
                gate_map,
                source,
                target,
                SAFARI_ADMISSION_SUPPORTED,
            )
            for source, target in SAFARI_ADMISSION_GATE_EDGES
        ),
    )


def apply_gen1_seafoam_current_requirements(
    graphs: Mapping[int, LocalGraph],
) -> dict[int, LocalGraph]:
    """Fail closed on Seafoam water until both native current systems settle.

    Static collision says these water edges are traversable, but the live game
    can carry Red between floors unless the boulder-current puzzle is settled.
    Field observation grants this only for all four lower-floor boulder events;
    no single cleared hole or predicted puzzle result unlocks water travel.
    """

    projected = dict(graphs)
    for map_id in SEAFOAM_INTERIOR_MAP_IDS.intersection(projected):
        graph = projected[map_id]
        projected[map_id] = LocalGraph(
            {
                source: tuple(
                    replace(
                        edge,
                        requirements=edge.requirements | {SEAFOAM_CURRENT_CONTROL},
                    )
                    if edge.required_mode == "water" or edge.result_mode == "water"
                    else edge
                    for edge in outgoing
                )
                for source, outgoing in graph.edges.items()
            }
        )
    return projected


def gen1_story_static_object_blockers(
    map_id: int,
    object_coordinates: Iterable[tuple[int, int]],
) -> frozenset[tuple[int, int]]:
    """Remove only objects whose displacement is guarded by a story predicate."""

    coordinates = frozenset(object_coordinates)
    displaced = GEN1_STORY_DISPLACED_OBJECTS.get(map_id, frozenset())
    if not displaced.issubset(coordinates):
        raise ValueError(
            f"map {map_id} lacks story-displaced objects {sorted(displaced - coordinates)}"
        )
    return coordinates - displaced
