from __future__ import annotations

import pytest

from pokemon_red_completion.gen1_story_routing import (
    ROUTE_7_GATE_REQUIREMENTS,
    SAFFRON_GUARDS_OPEN,
    apply_gen1_story_requirements,
    gen1_story_capabilities,
    observe_gen1_story_predicates,
)
from pokemon_red_completion.local_router import (
    LocalEdge,
    LocalGraph,
    LocalRouterError,
    find_local_path,
)
from pokemon_red_completion.observation import (
    SAFFRON_GUARD_ACCESS_MASK,
    MapId,
    RawGameState,
    semantic_facts,
)
from pokemon_red_completion.semantic_traversal import PredicateState


def raw(*, status_flags_1: int | None) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_7_GATE,
        player_x=0,
        player_y=4,
        party_count=1,
        battle_state=0,
        status_flags_1=status_flags_1,
    )


def test_guard_access_mask_is_the_independently_measured_status_bit() -> None:
    assert SAFFRON_GUARD_ACCESS_MASK == 0x40


def gate_graph() -> LocalGraph:
    """Independent two-row fixture matching the measured six-column room."""

    edges: dict[tuple[int, int], tuple[LocalEdge, ...]] = {}
    for row in (3, 4):
        for column in range(6):
            outgoing: list[LocalEdge] = []
            if column:
                outgoing.append(LocalEdge((row, column - 1), "left"))
            if column < 5:
                outgoing.append(LocalEdge((row, column + 1), "right"))
            edges[row, column] = tuple(outgoing)
    return LocalGraph(edges)


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        (None, PredicateState.UNKNOWN),
        (0, PredicateState.UNSATISFIED),
        (0x40, PredicateState.SATISFIED),
    ),
)
def test_guard_flag_distinguishes_unknown_closed_and_open(
    status: int | None,
    expected: PredicateState,
) -> None:
    (observed,) = observe_gen1_story_predicates(raw(status_flags_1=status))

    assert observed.name == SAFFRON_GUARDS_OPEN
    assert observed.state is expected
    assert gen1_story_capabilities(raw(status_flags_1=status)) == (
        frozenset({SAFFRON_GUARDS_OPEN})
        if expected is PredicateState.SATISFIED
        else frozenset()
    )


def test_both_corridor_rows_and_directions_require_the_same_durable_fact() -> None:
    assert {
        (item.map_id, item.source_at, item.target_at, item.predicate)
        for item in ROUTE_7_GATE_REQUIREMENTS
    } == {
        (int(MapId.ROUTE_7_GATE), (3, 2), (3, 3), SAFFRON_GUARDS_OPEN),
        (int(MapId.ROUTE_7_GATE), (3, 3), (3, 2), SAFFRON_GUARDS_OPEN),
        (int(MapId.ROUTE_7_GATE), (4, 2), (4, 3), SAFFRON_GUARDS_OPEN),
        (int(MapId.ROUTE_7_GATE), (4, 3), (4, 2), SAFFRON_GUARDS_OPEN),
    }


@pytest.mark.parametrize("row", (3, 4))
def test_the_same_static_gate_is_closed_unknown_and_open_when_observed(row: int) -> None:
    projected = apply_gen1_story_requirements(
        {int(MapId.ROUTE_7_GATE): gate_graph()}
    )[int(MapId.ROUTE_7_GATE)]

    for status in (None, 0):
        with pytest.raises(LocalRouterError, match="no permitted local route"):
            find_local_path(
                projected,
                (row, 0),
                (row, 5),
                capabilities=gen1_story_capabilities(raw(status_flags_1=status)),
            )

    opened = find_local_path(
        projected,
        (row, 0),
        (row, 5),
        capabilities=gen1_story_capabilities(
            raw(status_flags_1=0x40)
        ),
    )
    assert opened.coordinates == tuple((row, column) for column in range(6))


def test_semantic_state_exposes_only_the_observed_open_guard_fact() -> None:
    assert SAFFRON_GUARDS_OPEN not in semantic_facts(raw(status_flags_1=0))
    assert SAFFRON_GUARDS_OPEN in semantic_facts(
        raw(status_flags_1=0x40)
    )
