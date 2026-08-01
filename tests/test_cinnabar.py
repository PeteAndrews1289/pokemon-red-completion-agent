from pokemon_red_completion.cinnabar import (
    CINNABAR_CHECKPOINT_COUNT,
    CINNABAR_INPUT_BAG_SLOTS,
    CINNABAR_TO_CENTER,
    DUX_MOVES_AFTER,
    DUX_MOVES_BEFORE,
    DUX_PP_AFTER,
    DUX_PP_BEFORE,
    PALLET_TO_SHORE,
    ROUTE_21_EVENTS,
    ROUTE_21_TO_CINNABAR,
    TREE_TO_FLY_HOUSE,
)
from pokemon_red_completion.observation import (
    EventFlag,
    ItemId,
    MapId,
    RawGameState,
    location_label,
    semantic_facts,
)


def test_cinnabar_routes_and_field_move_contract_are_pinned() -> None:
    assert CINNABAR_CHECKPOINT_COUNT == 6
    assert CINNABAR_INPUT_BAG_SLOTS == 18
    assert len(TREE_TO_FLY_HOUSE) == 37
    assert len(PALLET_TO_SHORE) == 13
    assert len(ROUTE_21_TO_CINNABAR) == 93
    assert ROUTE_21_TO_CINNABAR[:17] == ("down",) * 17
    assert ROUTE_21_TO_CINNABAR[17:20] == ("right", "down", "left")
    assert ROUTE_21_TO_CINNABAR[-67:] == ("down",) * 67
    assert CINNABAR_TO_CENTER == ("down",) * 12 + ("right",) * 8 + ("up",)
    assert DUX_MOVES_BEFORE == (0x40, 0x1C, 0x0F, 0x1F)
    assert DUX_MOVES_AFTER == (0x40, 0x1C, 0x0F, 0x13)
    assert DUX_PP_BEFORE == (35, 15, 30, 20)
    assert DUX_PP_AFTER == (35, 15, 30, 15)


def test_cinnabar_source_ids_are_exact() -> None:
    assert MapId.ROUTE_16 == 0x1B
    assert MapId.ROUTE_21 == 0x20
    assert MapId.CINNABAR_ISLAND == 0x08
    assert MapId.CINNABAR_POKECENTER == 0xAB
    assert MapId.ROUTE_16_GATE_1F == 0xBA
    assert MapId.ROUTE_16_FLY_HOUSE == 0xBC
    assert ItemId.HM02_FLY == 0xC5
    assert EventFlag.GOT_HM02 == 0x4CE
    assert tuple(range(0x511, 0x51A)) == ROUTE_21_EVENTS
    assert EventFlag.BEAT_ROUTE_21_TRAINER_0 == 0x511
    assert EventFlag.BEAT_ROUTE_21_TRAINER_8 == 0x519


def test_cinnabar_center_preserves_identity_and_cinnabar_location_fact() -> None:
    raw = RawGameState(True, MapId.CINNABAR_POKECENTER, 3, 3, 3, 0)

    assert raw.map_id == MapId.CINNABAR_POKECENTER
    assert location_label(raw.map_id) == "cinnabar_pokecenter"
    assert "location:cinnabar_island" in semantic_facts(raw)
