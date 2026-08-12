from __future__ import annotations

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_story_routing import (
    CERULEAN_ROBBED_HOUSE_OPEN,
    CERULEAN_ROBBED_HOUSE_POLICE_AT,
    CERULEAN_ROBBED_HOUSE_REQUIREMENTS,
    ROUTE_7_GATE_REQUIREMENTS,
    ROUTE_12_SNORLAX_AT,
    ROUTE_12_SNORLAX_CLEARED,
    ROUTE_12_SNORLAX_REQUIREMENTS,
    SAFFRON_GUARDS_OPEN,
    SAFFRON_GYM_OPEN,
    SAFFRON_GYM_REQUIREMENTS,
    SAFFRON_GYM_ROCKET_GUARD_AT,
    SAFFRON_SILPH_SECURITY_GUARD_AT,
    SEAFOAM_CURRENT_CONTROL,
    SEAFOAM_INTERIOR_MAP_IDS,
    SILPH_ENTRANCE_OPEN,
    SILPH_ENTRANCE_REQUIREMENTS,
    apply_gen1_seafoam_current_requirements,
    apply_gen1_story_requirements,
    gen1_story_capabilities,
    gen1_story_static_object_blockers,
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
    EventFlag,
    MapId,
    RawGameState,
    semantic_facts,
)
from pokemon_red_completion.semantic_traversal import PredicateState


def raw(
    *,
    status_flags_1: int | None,
    event_flags: bytes | None = None,
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_7_GATE,
        player_x=0,
        player_y=4,
        party_count=1,
        battle_state=0,
        status_flags_1=status_flags_1,
        event_flags=event_flags,
    )


def test_guard_access_mask_is_the_independently_measured_status_bit() -> None:
    assert SAFFRON_GUARD_ACCESS_MASK == 0x40


def test_seafoam_water_edges_fail_closed_without_current_control() -> None:
    seafoam_map = min(SEAFOAM_INTERIOR_MAP_IDS)
    graph = LocalGraph(
        {
            (0, 0): (
                LocalEdge(
                    (0, 1),
                    "right",
                    action_kind=MacroActionKind.FIELD_MOVE,
                    required_mode="land",
                    result_mode="water",
                ),
                LocalEdge((1, 0), "down", required_mode="land"),
            ),
            (0, 1): (LocalEdge((0, 2), "right", required_mode="water"),),
        }
    )

    projected = apply_gen1_seafoam_current_requirements({seafoam_map: graph})[seafoam_map]

    assert projected.neighbors((0, 0))[0].requirements == {SEAFOAM_CURRENT_CONTROL}
    assert projected.neighbors((0, 0))[1].requirements == frozenset()
    assert projected.neighbors((0, 1))[0].requirements == {SEAFOAM_CURRENT_CONTROL}


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


def police_graph() -> LocalGraph:
    center = (12, 27)
    adjacent = ((11, 27), (12, 26), (13, 27))
    return LocalGraph(
        {
            center: tuple(LocalEdge(coordinate, "out") for coordinate in adjacent),
            **{
                coordinate: (LocalEdge(center, "in"),)
                for coordinate in adjacent
            },
        }
    )


def saffron_story_graph() -> LocalGraph:
    passages = (
        (
            SAFFRON_SILPH_SECURITY_GUARD_AT,
            ((21, 18), (22, 17), (23, 18)),
        ),
        (
            SAFFRON_GYM_ROCKET_GUARD_AT,
            ((3, 34), (4, 33), (4, 35)),
        ),
    )
    return LocalGraph(
        {
            **{
                center: tuple(LocalEdge(coordinate, "out") for coordinate in adjacent)
                for center, adjacent in passages
            },
            **{
                coordinate: (LocalEdge(center, "in"),)
                for center, adjacent in passages
                for coordinate in adjacent
            },
        }
    )


def route_12_snorlax_graph() -> LocalGraph:
    adjacent = ((61, 10), (63, 10), (62, 9), (62, 11))
    return LocalGraph(
        {
            ROUTE_12_SNORLAX_AT: tuple(
                LocalEdge(coordinate, "out") for coordinate in adjacent
            ),
            **{
                coordinate: (LocalEdge(ROUTE_12_SNORLAX_AT, "in"),)
                for coordinate in adjacent
            },
        }
    )


def story_graphs() -> dict[int, LocalGraph]:
    return {
        int(MapId.ROUTE_7_GATE): gate_graph(),
        int(MapId.CERULEAN_CITY): police_graph(),
        int(MapId.SAFFRON_CITY): saffron_story_graph(),
        int(MapId.ROUTE_12): route_12_snorlax_graph(),
    }


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
    observations = {
        item.name: item
        for item in observe_gen1_story_predicates(raw(status_flags_1=status))
    }
    observed = observations[SAFFRON_GUARDS_OPEN]

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
    projected = apply_gen1_story_requirements(story_graphs())[int(MapId.ROUTE_7_GATE)]

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


def _event_flags(*events: EventFlag) -> bytes:
    payload = bytearray(max(int(event) for event in events) // 8 + 1)
    for event in events:
        byte, bit = divmod(int(event), 8)
        payload[byte] |= 1 << bit
    return bytes(payload)


@pytest.mark.parametrize(
    ("event_flags", "expected"),
    (
        (None, PredicateState.UNKNOWN),
        (bytes(172), PredicateState.UNSATISFIED),
        (
            _event_flags(EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING),
            PredicateState.SATISFIED,
        ),
    ),
)
def test_bill_flag_distinguishes_unknown_closed_and_open(
    event_flags: bytes | None,
    expected: PredicateState,
) -> None:
    observations = {
        item.name: item
        for item in observe_gen1_story_predicates(
            raw(status_flags_1=0, event_flags=event_flags)
        )
    }

    assert observations[CERULEAN_ROBBED_HOUSE_OPEN].state is expected


def test_bill_completion_opens_only_the_story_guarded_police_square() -> None:
    assert CERULEAN_ROBBED_HOUSE_POLICE_AT == (12, 27)
    assert {
        (item.source_at, item.target_at, item.predicate)
        for item in CERULEAN_ROBBED_HOUSE_REQUIREMENTS
    } == {
        (source, target, CERULEAN_ROBBED_HOUSE_OPEN)
        for adjacent in ((11, 27), (12, 26), (13, 27))
        for source, target in (
            (adjacent, (12, 27)),
            ((12, 27), adjacent),
        )
    }
    projected = apply_gen1_story_requirements(story_graphs())[int(MapId.CERULEAN_CITY)]
    unknown = raw(status_flags_1=0)
    before_bill = raw(status_flags_1=0, event_flags=bytes(172))
    after_bill = raw(
        status_flags_1=0,
        event_flags=_event_flags(EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING),
    )

    for unavailable in (unknown, before_bill):
        with pytest.raises(LocalRouterError, match="no permitted local route"):
            find_local_path(
                projected,
                (13, 27),
                (11, 27),
                capabilities=gen1_story_capabilities(unavailable),
            )
    opened = find_local_path(
        projected,
        (13, 27),
        (11, 27),
        capabilities=gen1_story_capabilities(after_bill),
    )

    assert opened.coordinates == ((13, 27), (12, 27), (11, 27))
    assert CERULEAN_ROBBED_HOUSE_OPEN in gen1_story_capabilities(after_bill)
    assert CERULEAN_ROBBED_HOUSE_OPEN not in gen1_story_capabilities(before_bill)


@pytest.mark.parametrize(
    ("event_flags", "expected"),
    (
        (None, PredicateState.UNKNOWN),
        (bytes(172), PredicateState.UNSATISFIED),
        (
            _event_flags(EventFlag.RESCUED_MR_FUJI),
            PredicateState.UNSATISFIED,
        ),
        (
            _event_flags(
                EventFlag.RESCUED_MR_FUJI,
                EventFlag.RESCUED_MR_FUJI_WORLD,
            ),
            PredicateState.SATISFIED,
        ),
    ),
)
def test_fuji_flags_distinguish_unknown_closed_and_open_silph_entrance(
    event_flags: bytes | None,
    expected: PredicateState,
) -> None:
    observations = {
        item.name: item
        for item in observe_gen1_story_predicates(
            raw(status_flags_1=0, event_flags=event_flags)
        )
    }

    assert observations[SILPH_ENTRANCE_OPEN].state is expected


def test_fuji_rescue_opens_only_the_displaced_silph_guard_square() -> None:
    assert SAFFRON_SILPH_SECURITY_GUARD_AT == (22, 18)
    assert {
        (item.source_at, item.target_at, item.predicate)
        for item in SILPH_ENTRANCE_REQUIREMENTS
    } == {
        (source, target, SILPH_ENTRANCE_OPEN)
        for adjacent in ((21, 18), (22, 17), (23, 18))
        for source, target in (
            (adjacent, SAFFRON_SILPH_SECURITY_GUARD_AT),
            (SAFFRON_SILPH_SECURITY_GUARD_AT, adjacent),
        )
    }
    projected = apply_gen1_story_requirements(story_graphs())[int(MapId.SAFFRON_CITY)]
    before_rescue = raw(status_flags_1=0, event_flags=bytes(172))
    after_rescue = raw(
        status_flags_1=0,
        event_flags=_event_flags(
            EventFlag.RESCUED_MR_FUJI,
            EventFlag.RESCUED_MR_FUJI_WORLD,
        ),
    )

    with pytest.raises(LocalRouterError, match="no permitted local route"):
        find_local_path(
            projected,
            (23, 18),
            (21, 18),
            capabilities=gen1_story_capabilities(before_rescue),
        )
    opened = find_local_path(
        projected,
        (23, 18),
        (21, 18),
        capabilities=gen1_story_capabilities(after_rescue),
    )

    assert opened.coordinates == ((23, 18), (22, 18), (21, 18))
    assert SILPH_ENTRANCE_OPEN in gen1_story_capabilities(after_rescue)


def test_silph_victory_opens_only_the_displaced_saffron_gym_guard_square() -> None:
    assert SAFFRON_GYM_ROCKET_GUARD_AT == (4, 34)
    assert {
        (item.source_at, item.target_at, item.predicate)
        for item in SAFFRON_GYM_REQUIREMENTS
    } == {
        (source, target, SAFFRON_GYM_OPEN)
        for adjacent in ((3, 34), (4, 33), (4, 35))
        for source, target in (
            (adjacent, SAFFRON_GYM_ROCKET_GUARD_AT),
            (SAFFRON_GYM_ROCKET_GUARD_AT, adjacent),
        )
    }
    projected = apply_gen1_story_requirements(story_graphs())[int(MapId.SAFFRON_CITY)]
    before_silph = raw(status_flags_1=0, event_flags=bytes(243))
    after_silph = raw(
        status_flags_1=0,
        event_flags=_event_flags(EventFlag.BEAT_SILPH_CO_GIOVANNI),
    )

    with pytest.raises(LocalRouterError, match="no permitted local route"):
        find_local_path(
            projected,
            (4, 33),
            (3, 34),
            capabilities=gen1_story_capabilities(before_silph),
        )
    opened = find_local_path(
        projected,
        (4, 33),
        (3, 34),
        capabilities=gen1_story_capabilities(after_silph),
    )

    assert opened.coordinates == ((4, 33), (4, 34), (3, 34))
    assert SAFFRON_GYM_OPEN in gen1_story_capabilities(after_silph)


def test_route_12_snorlax_flag_opens_only_its_displaced_object_square() -> None:
    assert ROUTE_12_SNORLAX_AT == (62, 10)
    assert {
        (item.source_at, item.target_at, item.predicate)
        for item in ROUTE_12_SNORLAX_REQUIREMENTS
    } == {
        (source, target, ROUTE_12_SNORLAX_CLEARED)
        for adjacent in ((61, 10), (63, 10), (62, 9), (62, 11))
        for source, target in (
            (adjacent, ROUTE_12_SNORLAX_AT),
            (ROUTE_12_SNORLAX_AT, adjacent),
        )
    }
    projected = apply_gen1_story_requirements(story_graphs())[int(MapId.ROUTE_12)]
    before = raw(status_flags_1=0, event_flags=bytes(172))
    after = raw(
        status_flags_1=0,
        event_flags=_event_flags(EventFlag.BEAT_ROUTE12_SNORLAX),
    )

    with pytest.raises(LocalRouterError, match="no permitted local route"):
        find_local_path(
            projected,
            (61, 10),
            (63, 10),
            capabilities=gen1_story_capabilities(before),
        )
    opened = find_local_path(
        projected,
        (61, 10),
        (63, 10),
        capabilities=gen1_story_capabilities(after),
    )

    assert opened.coordinates == ((61, 10), (62, 10), (63, 10))
    assert ROUTE_12_SNORLAX_CLEARED in gen1_story_capabilities(after)
    assert ROUTE_12_SNORLAX_CLEARED not in gen1_story_capabilities(before)


def test_static_blockers_remove_only_story_displaced_objects() -> None:
    assert gen1_story_static_object_blockers(
        int(MapId.CERULEAN_CITY),
        {(12, 27), (12, 28)},
    ) == frozenset({(12, 28)})
    assert gen1_story_static_object_blockers(
        int(MapId.SAFFRON_CITY),
        {(4, 34), (22, 18), (22, 19), (23, 23)},
    ) == frozenset({(22, 19), (23, 23)})
    assert gen1_story_static_object_blockers(99, {(1, 2)}) == frozenset({(1, 2)})
    assert gen1_story_static_object_blockers(
        int(MapId.ROUTE_12),
        {ROUTE_12_SNORLAX_AT, (31, 14)},
    ) == frozenset({(31, 14)})
    with pytest.raises(ValueError, match="lacks story-displaced"):
        gen1_story_static_object_blockers(int(MapId.CERULEAN_CITY), {(12, 28)})
