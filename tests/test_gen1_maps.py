"""Kanto's map graph, read from the cartridge rather than typed.

This is the structure that decides whether "plays every mainline title" is a
finite project. Every chapter module here is hand-written walk directions, and a
route written that way is worth nothing to the next game.

The module it tests replaced a hand-written five-node sketch. The sketch was
wrong as well as small: it joined Viridian City to the Route 22 gate, which the
cartridge says is reached from Routes 22 and 23 and from nowhere else. It also
missed one of Pallet Town's three buildings. Both are pinned below, because a
correction nobody tests is a correction that comes back.

These tests need no ROM: the read is the measurement and lives in
``docs/evidence/map-graph-2026-08-10.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import pokemon_red_completion.gen1_maps as gen1_maps
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_maps import (
    ConnectionGeometry,
    Heading,
    MapNode,
    Passage,
    PassageKind,
    macro_graph_from_nodes,
    map_graph,
    routes_between,
    verify_connections_are_two_sided,
)
from pokemon_red_completion.global_router import MacroTransition
from pokemon_red_completion.observation import MapId

RECORD = Path("docs/evidence/map-graph-2026-08-10.json")


@pytest.fixture(scope="module")
def record() -> dict:
    if not RECORD.exists():  # pragma: no cover - the record is committed
        pytest.skip(f"{RECORD} has not been produced")
    return json.loads(RECORD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def adjacency(record: dict) -> dict[int, set[int]]:
    return {
        int(map_id): set(neighbours)
        for map_id, neighbours in record["by_title"]["red"]["adjacency"].items()
    }


def test_every_named_map_is_reachable_from_the_start(record: dict) -> None:
    """The cross-check that proves the header offsets.

    ``MapId`` is maintained by hand and entirely independent of this read, so
    the two agreeing is evidence rather than restatement. A wrong offset would
    strand some of them.
    """

    reachable = set(record["by_title"]["red"]["named_maps_reachable"])

    assert reachable == {m.value for m in MapId}
    assert len(reachable) == 147


def test_the_graph_agrees_with_the_encounter_reads(record: dict) -> None:
    """Three independent reads of the same cartridge have to be consistent.

    Every map that can be walked in and every map that can be fished has to be
    somewhere a player can get to.
    """

    found = record["by_title"]["red"]
    reachable = set(found["adjacency"])

    assert found["maps_with_wild_tables_reachable"]
    assert found["fishable_maps_reachable"]
    for map_id in found["maps_with_wild_tables_reachable"]:
        assert str(map_id) in reachable
    for map_id in found["fishable_maps_reachable"]:
        assert str(map_id) in reachable


def test_pass_through_gate_entry_actions_derive_from_destination_boundary() -> None:
    header = gen1_maps._Header(tileset=0, height=4, width=3, connections={})

    assert gen1_maps._boundary_entry_action(header, (3, 0)) == "left"
    assert gen1_maps._boundary_entry_action(header, (3, 5)) == "right"
    assert gen1_maps._boundary_entry_action(header, (0, 3)) == "down"
    assert gen1_maps._boundary_entry_action(header, (7, 3)) is None
    assert gen1_maps._boundary_entry_action(header, (3, 2)) is None
    assert gen1_maps._boundary_entry_action(header, (0, 0)) is None


def test_cartridge_tile_semantics_override_geometric_warp_guess() -> None:
    automatic = Passage(
        to_map=None,
        kind=PassageKind.RETURN,
        at=(0, 1),
        exit_action="up",
        destination_warp_index=0,
    )
    directional = Passage(
        to_map=None,
        kind=PassageKind.RETURN,
        at=(0, 2),
        exit_action="up",
        destination_warp_index=1,
    )
    graph = {
        9: MapNode(
            map_id=9,
            height=1,
            width=2,
            passages=(automatic, directional),
            tileset=8,
        )
    }

    projected = gen1_maps._with_automatic_warp_triggers(
        graph,
        {9: ((0x11, 0x54, 0x37, 0x11), (0x11, 0x11, 0x11, 0x11))},
        {8: frozenset({0x54})},
    )

    assert projected[9].passages[0].exit_action is None
    assert projected[9].passages[1].exit_action == "up"


def test_both_cartridges_carry_the_same_world(record: dict) -> None:
    """Keep the legacy comparison's narrower evidence boundary visible."""

    assert record["cartridges_agree"] is True
    assert "every decoded MapNode and Passage" in record["comparison_scope"]
    assert record["by_title"]["red"]["passage_counts"] == {
        "connection": 78,
        "warp": 558,
        "return": 242,
        "scripted": 2,
    }


def test_the_hand_written_graph_had_an_edge_the_cartridge_denies(
    adjacency: dict[int, set[int]],
) -> None:
    """Viridian City does not reach the Route 22 gate.

    The sketch this replaced said it did. The gate is entered from Route 22 and
    Route 23, and the error survived because nothing could contradict it.
    """

    assert MapId.ROUTE_22_GATE.value not in adjacency[MapId.VIRIDIAN_CITY.value]
    assert MapId.ROUTE_22_GATE.value in adjacency[MapId.ROUTE_22.value]
    assert MapId.ROUTE_22_GATE.value in adjacency[MapId.ROUTE_23.value]
    # The gate's exit is a dynamic LAST_MAP return, so a context-free adjacency
    # view must not claim either exterior as its fixed target.
    assert adjacency[MapId.ROUTE_22_GATE.value] == set()


def test_a_pokemon_centre_can_be_left_again(record: dict) -> None:
    """The exit warp names no destination, so it has to be inferred.

    An interior that serves many towns returns the player to whichever one they
    entered from, which is knowable only from the maps that point at it.
    Dropping those warps would strand every Pokémon Centre in the game.
    """

    journeys = record["by_title"]["red"]["contextual_return_journeys"]

    assert journeys["VIRIDIAN_POKECENTER->VIRIDIAN_CITY"] == [
        MapId.VIRIDIAN_POKECENTER.value,
        MapId.VIRIDIAN_CITY.value,
    ]


def test_entrance_scripts_retarget_their_tunnel_returns(record: dict) -> None:
    """The second entrance must return to its own route, not the first one's."""

    found = record["by_title"]["red"]

    assert found["retained_outside_overrides"] == {
        str(MapId.DIGLETTS_CAVE_ROUTE_2.value): MapId.ROUTE_2.value,
        str(MapId.UNDERGROUND_PATH_ROUTE_5.value): MapId.ROUTE_5.value,
        str(MapId.UNDERGROUND_PATH_ROUTE_6.value): MapId.ROUTE_6.value,
        str(MapId.UNDERGROUND_PATH_ROUTE_7.value): MapId.ROUTE_7.value,
        str(MapId.UNDERGROUND_PATH_ROUTE_8.value): MapId.ROUTE_8.value,
        str(MapId.DIGLETTS_CAVE_ROUTE_11.value): MapId.ROUTE_11.value,
    }
    assert found["contextual_return_journeys"]["UNDERGROUND_PATH_WEST_EAST->ROUTE_8"] == [
        MapId.UNDERGROUND_PATH_WEST_EAST.value,
        MapId.UNDERGROUND_PATH_ROUTE_8.value,
        MapId.ROUTE_8.value,
    ]


def test_pallet_town_has_three_buildings_and_two_roads(adjacency: dict[int, set[int]]) -> None:
    """The sketch listed four neighbours; the cartridge gives five."""

    assert adjacency[MapId.PALLET_TOWN.value] == {
        MapId.ROUTE_1.value,
        MapId.ROUTE_21.value,
        MapId.REDS_HOUSE_1F.value,
        MapId.OAKS_LAB.value,
        39,  # the rival's house, which the hand-written sketch omitted
    }


def test_routes_are_computed_rather_than_scripted(record: dict) -> None:
    """The point of the whole exercise.

    None of these paths is written down anywhere; each is searched for in a
    graph read from the cartridge.
    """

    journeys = record["by_title"]["red"]["sample_journeys"]

    assert journeys["PALLET_TOWN->PEWTER_CITY"] == [
        MapId.PALLET_TOWN.value,
        MapId.ROUTE_1.value,
        MapId.VIRIDIAN_CITY.value,
        MapId.ROUTE_2.value,
        MapId.PEWTER_CITY.value,
    ]
    # Saffron is ten maps out and was asserted *unreachable* by the test this
    # one replaces, because the sketch it searched did not go that far.
    assert journeys["PALLET_TOWN->SAFFRON_CITY"][0] == MapId.PALLET_TOWN.value
    assert journeys["PALLET_TOWN->SAFFRON_CITY"][-1] == MapId.SAFFRON_CITY.value
    assert len(journeys["PALLET_TOWN->SAFFRON_CITY"]) == 10


def test_a_lift_is_recorded_as_a_lift_rather_than_a_dead_end(record: dict) -> None:
    """One exit in Kanto has no destination in the data.

    Silph Co's lift is told where to go by a menu at runtime, so the warp points
    at a slot holding no map. Discarding it silently would make the lift look
    like a dead end; it is kept and marked instead.
    """

    scripted = record["by_title"]["red"]["maps_with_a_scripted_exit"]

    assert scripted == [MapId.SILPH_CO_ELEVATOR.value]
    assert record["by_title"]["red"]["passage_counts"]["scripted"] == 2


def test_a_route_prefers_the_cheaper_way_around() -> None:
    """Search, not adjacency: the shortest path is found, not the first one."""

    graph = {
        1: MapNode(
            1,
            4,
            4,
            (
                Passage(2, PassageKind.CONNECTION, Heading.NORTH),
                Passage(4, PassageKind.WARP, at=(1, 1)),
            ),
        ),
        2: MapNode(2, 4, 4, (Passage(3, PassageKind.CONNECTION, Heading.NORTH),)),
        3: MapNode(3, 4, 4, (Passage(5, PassageKind.CONNECTION, Heading.NORTH),)),
        4: MapNode(4, 4, 4, (Passage(5, PassageKind.WARP, at=(2, 2)),)),
        5: MapNode(5, 4, 4, ()),
    }

    assert routes_between(graph, 1, 5) == (1, 4, 5)
    assert routes_between(graph, 1, 1) == (1,)
    assert routes_between(graph, 5, 1) == ()


def test_a_scripted_exit_is_not_followed_when_routing() -> None:
    """A destination the cartridge does not name cannot be planned through."""

    graph = {
        1: MapNode(1, 2, 2, (Passage(None, PassageKind.SCRIPTED, at=(3, 1)),)),
        2: MapNode(2, 2, 2, ()),
    }

    assert routes_between(graph, 1, 2) == ()
    assert graph[1].neighbours() == frozenset()
    assert graph[1].has_a_scripted_exit


def test_the_game_neutral_projection_keeps_endpoints_and_return_context() -> None:
    transition = MacroTransition((2, 7), (2, 0), "east")
    decoded = {
        1: MapNode(
            1,
            4,
            4,
            (
                Passage(
                    2,
                    PassageKind.CONNECTION,
                    heading=Heading.EAST,
                    connection=ConnectionGeometry(4, 4, 0, 0),
                    coordinate_transitions=(transition,),
                ),
                Passage(
                    None,
                    PassageKind.RETURN,
                    at=(7, 2),
                    exit_action="down",
                    destination_warp_index=0,
                ),
            ),
            tileset=0,
            warp_locations=((7, 2),),
        )
    }

    projected = macro_graph_from_nodes(decoded)
    connection, return_warp = projected.edges[1]

    assert connection.heading == "east"
    assert connection.coordinate_transitions == (transition,)
    assert return_warp.at == (7, 2)
    assert return_warp.exit_action == "down"
    assert return_warp.target_map is None
    assert return_warp.destination_warp_index == 0
    assert projected.outside_nodes == frozenset({1})
    assert projected.warp_locations[1] == ((7, 2),)


def test_a_one_sided_connection_on_a_real_map_is_refused() -> None:
    """The guard that holds the filter to account.

    Reciprocity both proves the offsets and removes unused slots, so discarding
    a one-sided connection is only safe when it comes from a slot no player can
    stand on. One belonging to a reachable map means the read is fiction, and
    the difference between those two cases is the whole basis for trusting the
    graph.
    """

    reachable = {0, 1, 2}

    verify_connections_are_two_sided(reachable, [(250, Heading.NORTH, 3)])

    with pytest.raises(CartridgeReadError, match="read wrongly"):
        verify_connections_are_two_sided(reachable, [(1, Heading.NORTH, 3)])


def test_a_cartridge_without_these_headers_is_refused() -> None:
    """A header read at the wrong address still decodes into something."""

    with pytest.raises(CartridgeReadError):
        map_graph(bytes(0x100000))
