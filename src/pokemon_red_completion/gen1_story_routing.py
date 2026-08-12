"""Generation I story predicates projected onto the neutral local router.

Route 7's guard house has statically walkable corridors whose live access is
decided by a durable guard flag. Cerulean's robbed-house approach and Saffron's
Silph entrance have the opposite geometry problem: an object occupies the
passage before a story event and is displaced afterward. Route 12's Snorlax
uses the same pattern. Cartridge terrain remains responsible for geometry;
this adapter contributes only the title-specific predicates and object
coordinates whose static occupancy those predicates replace.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pokemon_red_completion.local_router import LocalGraph
from pokemon_red_completion.observation import (
    SAFFRON_GUARD_ACCESS_MASK,
    EventFlag,
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

# The two corridor rows are independent. Requiring both directions prevents a
# planner from treating an unknown reverse crossing as free merely because a
# run cannot normally begin inside Saffron before the flag is set.
ROUTE_7_GATE_REQUIREMENTS = tuple(
    LocalPassageRequirement(
        map_id=int(MapId.ROUTE_7_GATE),
        source_at=source,
        target_at=target,
        predicate=SAFFRON_GUARDS_OPEN,
    )
    for row in (3, 4)
    for source, target in (
        ((row, 2), (row, 3)),
        ((row, 3), (row, 2)),
    )
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
    *ROUTE_7_GATE_REQUIREMENTS,
    *CERULEAN_ROBBED_HOUSE_REQUIREMENTS,
    *SILPH_ENTRANCE_REQUIREMENTS,
    *SAFFRON_GYM_REQUIREMENTS,
    *ROUTE_12_SNORLAX_REQUIREMENTS,
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
    """Classify supported durable story predicates from one raw observation."""

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
        int(EventFlag.FIGHT_ROUTE12_SNORLAX),
    ):
        route_12_snorlax_state = PredicateState.SATISFIED
    else:
        route_12_snorlax_state = PredicateState.UNSATISFIED
    return (
        PredicateObservation(SAFFRON_GUARDS_OPEN, guard_state),
        PredicateObservation(CERULEAN_ROBBED_HOUSE_OPEN, house_state),
        PredicateObservation(SILPH_ENTRANCE_OPEN, silph_state),
        PredicateObservation(SAFFRON_GYM_OPEN, gym_state),
        PredicateObservation(ROUTE_12_SNORLAX_CLEARED, route_12_snorlax_state),
    )


def gen1_story_capabilities(raw: RawGameState) -> frozenset[str]:
    """Return only story predicates independently observed as satisfied."""

    return satisfied_predicates(observe_gen1_story_predicates(raw))


def apply_gen1_story_requirements(
    graphs: Mapping[int, LocalGraph],
) -> dict[int, LocalGraph]:
    """Bind every currently modelled Generation I story threshold."""

    return apply_local_passage_requirements(graphs, GEN1_STORY_PASSAGE_REQUIREMENTS)


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
