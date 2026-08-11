from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.gen1_traversal import (
    CUT_CAPABILITY,
    CUT_MOVE_ID,
    LAND_MODE,
    SURF_CAPABILITY,
    SURF_MOVE_ID,
    WATER_MODE,
    CutBlockSwap,
    Direction,
    LedgeRule,
    TilePairRestriction,
    TraversalRules,
    boulder_events,
    cut_block_swaps,
    cut_capabilities,
    land_pair_restrictions,
    ledge_rules,
    local_graph,
    map_object_events,
    surf_capabilities,
    surf_local_graph,
    water_pair_restrictions,
)
from pokemon_red_completion.local_router import LocalRouterError, find_local_path
from pokemon_red_completion.observation import Badge, RawGameState

TEST_LEDGE_TABLE = 0x1A6CF
TEST_LAND_PAIRS = 0x0C7E
TEST_WATER_PAIRS = 0x0CA0
TEST_CUT_SWAPS = 0x0F100
TEST_HEADER_POINTERS = 0x01AE
TEST_HEADER_BANKS = 0xC23D
TEST_HEADER = 0x4100
TEST_OBJECTS = 0x4200
RECORD = Path("docs/evidence/traversal-rules-2026-08-10.json")


def traversal_cartridge() -> bytearray:
    data = bytearray(0x20000)
    data[TEST_LEDGE_TABLE : TEST_LEDGE_TABLE + 33] = bytes(
        (
            0x00,
            0x2C,
            0x37,
            0x80,
            0x00,
            0x39,
            0x36,
            0x80,
            0x00,
            0x39,
            0x37,
            0x80,
            0x08,
            0x2C,
            0x27,
            0x20,
            0x08,
            0x39,
            0x27,
            0x20,
            0x0C,
            0x2C,
            0x0D,
            0x10,
            0x0C,
            0x2C,
            0x1D,
            0x10,
            0x0C,
            0x39,
            0x0D,
            0x10,
            0xFF,
        )
    )
    data[TEST_LAND_PAIRS : TEST_LAND_PAIRS + 34] = bytes(
        (
            17,
            0x20,
            0x05,
            17,
            0x41,
            0x05,
            3,
            0x30,
            0x2E,
            17,
            0x2A,
            0x05,
            17,
            0x05,
            0x21,
            3,
            0x52,
            0x2E,
            3,
            0x55,
            0x2E,
            3,
            0x56,
            0x2E,
            3,
            0x20,
            0x2E,
            3,
            0x5E,
            0x2E,
            3,
            0x5F,
            0x2E,
            0xFF,
        )
    )
    data[TEST_WATER_PAIRS : TEST_WATER_PAIRS + 10] = bytes(
        (3, 0x14, 0x2E, 3, 0x48, 0x2E, 17, 0x14, 0x05, 0xFF)
    )
    data[TEST_CUT_SWAPS : TEST_CUT_SWAPS + 19] = bytes(
        (
            0x32,
            0x6D,
            0x33,
            0x6C,
            0x34,
            0x6F,
            0x35,
            0x4C,
            0x60,
            0x6E,
            0x0B,
            0x0A,
            0x3C,
            0x35,
            0x3F,
            0x35,
            0x3D,
            0x36,
            0xFF,
        )
    )
    return data


def object_cartridge() -> bytearray:
    data = bytearray(0x10000)
    data[TEST_HEADER_BANKS] = 1
    data[TEST_HEADER_POINTERS : TEST_HEADER_POINTERS + 2] = (0x4100).to_bytes(2, "little")
    data[TEST_HEADER + 9] = 0  # no connections; object pointer immediately follows
    data[TEST_HEADER + 10 : TEST_HEADER + 12] = (0x4200).to_bytes(2, "little")
    cursor = TEST_OBJECTS
    data[cursor] = 0x0A  # border block
    data[cursor + 1] = 1  # one warp exercises its four-byte stride
    data[cursor + 2 : cursor + 6] = bytes((1, 2, 3, 4))
    data[cursor + 6] = 2  # two background events exercise their three-byte stride
    data[cursor + 7 : cursor + 13] = bytes((5, 6, 7, 8, 9, 10))
    data[cursor + 13] = 4
    data[cursor + 14 : cursor + 20] = bytes((1, 8, 9, 0xFE, 0, 1))
    data[cursor + 20 : cursor + 27] = bytes((0x3D, 9, 10, 0xFF, 0xFF, 0x82, 4))
    data[cursor + 27 : cursor + 35] = bytes((4, 10, 11, 0xFF, 0xD0, 0x43, 1, 2))
    data[cursor + 35 : cursor + 41] = bytes((0x3F, 19, 9, 0xFF, 0x10, 4))
    return data


def rules(
    *,
    ledges: tuple[LedgeRule, ...] = (),
    land: tuple[TilePairRestriction, ...] = (),
) -> TraversalRules:
    return TraversalRules(
        ledges=ledges,
        land_pair_restrictions=land,
        water_pair_restrictions=(),
        cut_block_swaps=(),
        boulders=(),
    )


def terrain(
    tiles: tuple[tuple[int, ...], ...],
    *,
    tileset: int = 0,
    walkable: tuple[tuple[bool, ...], ...] | None = None,
    water: tuple[tuple[bool, ...], ...] | None = None,
) -> Terrain:
    land_grid = walkable or tuple(tuple(True for _ in row) for row in tiles)
    water_grid = water or tuple(tuple(False for _ in row) for row in tiles)
    return Terrain(
        map_id=0,
        tileset=tileset,
        walkable=land_grid,
        grass=tuple(tuple(False for _ in row) for row in tiles),
        water=water_grid,
        tiles=tiles,
    )


def test_all_four_static_rule_tables_are_decoded_from_independent_bytes() -> None:
    rom = bytes(traversal_cartridge())

    ledges = ledge_rules(rom)
    assert len(ledges) == 8
    assert ledges[0] == LedgeRule(Direction.DOWN, 0x2C, 0x37)
    assert ledges[-1] == LedgeRule(Direction.RIGHT, 0x39, 0x0D)
    assert len(land_pair_restrictions(rom)) == 11
    assert len(water_pair_restrictions(rom)) == 3
    assert cut_block_swaps(rom) == (
        CutBlockSwap(0x32, 0x6D),
        CutBlockSwap(0x33, 0x6C),
        CutBlockSwap(0x34, 0x6F),
        CutBlockSwap(0x35, 0x4C),
        CutBlockSwap(0x60, 0x6E),
        CutBlockSwap(0x0B, 0x0A),
        CutBlockSwap(0x3C, 0x35),
        CutBlockSwap(0x3F, 0x35),
        CutBlockSwap(0x3D, 0x36),
    )


def test_an_invalid_ledge_direction_and_an_early_end_are_refused() -> None:
    invalid = traversal_cartridge()
    invalid[TEST_LEDGE_TABLE] = 0x04  # facing up paired with a down input
    with pytest.raises(CartridgeReadError, match="incompatible facing/input"):
        ledge_rules(bytes(invalid))

    short = traversal_cartridge()
    short[TEST_LEDGE_TABLE + 4] = 0xFF
    with pytest.raises(CartridgeReadError, match="incomplete"):
        ledge_rules(bytes(short))


def test_tile_pair_restrictions_are_symmetric() -> None:
    restriction = TilePairRestriction(17, 0x20, 0x05)

    assert restriction.blocks(17, 0x20, 0x05)
    assert restriction.blocks(17, 0x05, 0x20)
    assert not restriction.blocks(3, 0x20, 0x05)
    assert not restriction.blocks(17, 0x20, 0x21)


def test_variable_object_strides_reach_the_boulder_after_items_and_trainers() -> None:
    rom = bytes(object_cartridge())
    events = map_object_events(rom, {0})

    assert [event.sprite_id for event in events] == [1, 0x3D, 4, 0x3F]
    assert events[-1].at == (15, 5)
    assert events[-1].is_strength_boulder
    assert boulder_events(rom, {0}) == (events[-1],)


def test_an_impossible_object_count_is_refused() -> None:
    rom = object_cartridge()
    rom[TEST_OBJECTS + 13] = 17

    with pytest.raises(CartridgeReadError, match="too many object events"):
        map_object_events(bytes(rom), {0})


def test_a_ledge_is_one_directed_action_that_skips_the_ledge_tile() -> None:
    world = terrain(((0x2C,), (0x37,), (0x2C,)))
    graph = local_graph(
        world,
        rules(ledges=(LedgeRule(Direction.DOWN, 0x2C, 0x37),)),
    )

    down = graph.neighbors((0, 0))
    assert [(edge.target, edge.action, edge.kind) for edge in down] == [((2, 0), "down", "ledge")]


def test_an_elevation_pair_blocks_two_otherwise_walkable_tiles() -> None:
    world = terrain(((0x20, 0x05),), tileset=17)
    graph = local_graph(
        world,
        rules(land=(TilePairRestriction(17, 0x20, 0x05),)),
    )

    assert graph.neighbors((0, 0)) == ()
    assert graph.neighbors((0, 1)) == ()


def test_an_observed_dynamic_object_blocks_its_coordinate() -> None:
    world = terrain(((1, 1, 1),))

    graph = local_graph(world, rules(), blocked={(0, 1)})

    assert graph.neighbors((0, 0)) == ()
    assert (0, 1) not in graph.edges


def test_surf_requires_the_badge_and_a_living_observed_move_holder() -> None:
    def observed(
        *,
        badges: Badge = Badge.SOUL,
        hp: tuple[int, ...] = (20,),
        moves: tuple[tuple[int, ...], ...] = ((SURF_MOVE_ID,),),
    ) -> RawGameState:
        return RawGameState(
            game_started=True,
            map_id=0,
            player_x=0,
            player_y=0,
            party_count=len(hp),
            battle_state=0,
            badge_bits=int(badges),
            party_hp=hp,
            party_moves=moves,
        )

    assert surf_capabilities(observed(), surf_allowed=True) == frozenset({SURF_CAPABILITY})
    assert not surf_capabilities(observed(), surf_allowed=False)
    assert not surf_capabilities(observed(badges=Badge.CASCADE), surf_allowed=True)
    assert not surf_capabilities(observed(hp=(0,)), surf_allowed=True)
    assert not surf_capabilities(observed(moves=((0x0F,),)), surf_allowed=True)
    assert not surf_capabilities(
        observed(hp=(20, 20), moves=((SURF_MOVE_ID,),)),
        surf_allowed=True,
    )


def test_cut_requires_the_badge_and_a_complete_living_observed_holder() -> None:
    def observed(
        *,
        badges: Badge = Badge.CASCADE,
        hp: tuple[int, ...] = (20,),
        moves: tuple[tuple[int, ...], ...] = ((CUT_MOVE_ID,),),
    ) -> RawGameState:
        return RawGameState(
            game_started=True,
            map_id=0,
            player_x=0,
            player_y=0,
            party_count=len(hp),
            battle_state=0,
            badge_bits=int(badges),
            party_hp=hp,
            party_moves=moves,
        )

    assert cut_capabilities(observed()) == frozenset({CUT_CAPABILITY})
    assert not cut_capabilities(observed(badges=Badge.SOUL))
    assert not cut_capabilities(observed(hp=(0,)))
    assert not cut_capabilities(observed(moves=((SURF_MOVE_ID,),)))
    assert not cut_capabilities(observed(hp=(20, 20), moves=((CUT_MOVE_ID,),)))


def test_surf_graph_keeps_land_and_water_as_explicit_search_modes() -> None:
    world = terrain(
        ((1, 0x14, 0x14, 1),),
        walkable=((True, False, False, True),),
        water=((False, True, True, False),),
    )
    graph = surf_local_graph(world, rules())

    with pytest.raises(LocalRouterError, match="no permitted local route"):
        find_local_path(graph, (0, 0), (0, 3), start_mode=LAND_MODE)

    path = find_local_path(
        graph,
        (0, 0),
        (0, 3),
        capabilities=frozenset({SURF_CAPABILITY}),
        start_mode=LAND_MODE,
        goal_mode=LAND_MODE,
    )

    assert path.coordinates == ((0, 0), (0, 1), (0, 2), (0, 3))
    assert path.modes == (LAND_MODE, WATER_MODE, WATER_MODE, LAND_MODE)
    assert [(edge.action, edge.kind, edge.action_kind.value) for edge in path.edges] == [
        ("surf:right", "water_entry", "field_move"),
        ("right", "water_travel", "move"),
        ("right", "water_exit", "move"),
    ]


def test_water_pair_restrictions_close_boarding_and_water_travel() -> None:
    world = terrain(
        ((0x2E, 0x14, 0x14),),
        tileset=3,
        walkable=((True, False, False),),
        water=((False, True, True),),
    )
    blocked_boarding = surf_local_graph(
        world,
        rules(),
    )
    # No rule means the topology is present, proving the fixture itself routes.
    assert find_local_path(
        blocked_boarding,
        (0, 0),
        (0, 2),
        capabilities=frozenset({SURF_CAPABILITY}),
        start_mode=LAND_MODE,
    ).coordinates[-1] == (0, 2)

    restricted = surf_local_graph(
        world,
        TraversalRules(
            ledges=(),
            land_pair_restrictions=(),
            water_pair_restrictions=(TilePairRestriction(3, 0x2E, 0x14),),
            cut_block_swaps=(),
            boulders=(),
        ),
    )
    with pytest.raises(LocalRouterError, match="no permitted local route"):
        find_local_path(
            restricted,
            (0, 0),
            (0, 2),
            capabilities=frozenset({SURF_CAPABILITY}),
            start_mode=LAND_MODE,
        )


def test_both_cartridges_produce_the_same_truthful_static_graph() -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    red = record["by_title"]["red"]

    assert record["schema"] == "pokemon-gen1-traversal-rules-v1"
    assert record["static_rule_tables_agree"] is True
    assert record["initial_boulder_events_agree"] is True
    assert record["static_local_graphs_agree"] is True
    assert len(record["rules"]["ledges"]) == 8
    assert len(record["rules"]["land_pair_restrictions"]) == 11
    assert len(record["rules"]["water_pair_restrictions"]) == 3
    assert len(record["rules"]["cut_block_swaps"]) == 9
    assert red["static_local_graph"]["coordinate_nodes"] == 48_216
    assert red["static_local_graph"]["directed_edges"] == 154_653
    assert red["static_local_graph"]["transition_kinds"] == {
        "ledge": 749,
        "walk": 153_904,
    }
    assert red["static_local_graph"]["pair_restricted_directed_transitions"] == 1_152
    assert red["boulders"]["total"] == 25
    assert red["boulders"]["strength_enabled"] == 21
    assert red["boulders"]["fixed_or_already_dropped"] == 4
    assert len(red["boulders"]["by_map"]) == 9
    assert "not permission" in record["interpretation"]
