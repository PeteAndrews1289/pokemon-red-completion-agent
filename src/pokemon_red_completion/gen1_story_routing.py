"""Generation I story predicates projected onto the neutral local router.

The first qualified binding is Route 7's Saffron guard house. Its static
terrain exposes two east/west corridors in both states, while the engine's
durable guard-access flag decides whether either threshold is executable.
Cartridge terrain remains responsible for geometry; this adapter contributes
only the title-specific semantic predicate.
"""

from __future__ import annotations

from collections.abc import Mapping

from pokemon_red_completion.local_router import LocalGraph
from pokemon_red_completion.observation import (
    SAFFRON_GUARD_ACCESS_MASK,
    MapId,
    RawGameState,
)
from pokemon_red_completion.semantic_traversal import (
    LocalPassageRequirement,
    PredicateObservation,
    PredicateState,
    apply_local_passage_requirements,
    satisfied_predicates,
)

SAFFRON_GUARDS_OPEN = "story:saffron_guards_open"

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


def observe_gen1_story_predicates(raw: RawGameState) -> tuple[PredicateObservation, ...]:
    """Classify supported durable story predicates from one raw observation."""

    if not raw.game_started or raw.status_flags_1 is None:
        state = PredicateState.UNKNOWN
    elif raw.status_flags_1 & SAFFRON_GUARD_ACCESS_MASK:
        state = PredicateState.SATISFIED
    else:
        state = PredicateState.UNSATISFIED
    return (PredicateObservation(SAFFRON_GUARDS_OPEN, state),)


def gen1_story_capabilities(raw: RawGameState) -> frozenset[str]:
    """Return only story predicates independently observed as satisfied."""

    return satisfied_predicates(observe_gen1_story_predicates(raw))


def apply_gen1_story_requirements(
    graphs: Mapping[int, LocalGraph],
) -> dict[int, LocalGraph]:
    """Bind every currently modelled Generation I story threshold."""

    return apply_local_passage_requirements(graphs, ROUTE_7_GATE_REQUIREMENTS)
