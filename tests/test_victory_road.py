from pokemon_red_completion.observation import EventFlag, ItemId, MapId
from pokemon_red_completion.victory_road import (
    BADGE_CHECK_EVENTS,
    CENTER_TO_ROUTE_22,
    EARTH_APPROACH,
    RIVAL_PARTY,
    RIVAL_POLICY,
    ROUTE_22_TO_GATE,
    ROUTE_22_TO_RIVAL,
    ROUTE_23_TO_INDIGO,
    SAFFRON_TO_MART,
    VICTORY_ROAD_CHECKPOINT_COUNT,
    VIRIDIAN_TO_ROUTE_22,
    VR1_TO_2F,
    VR2_FINAL_TO_3F,
    VR2_TO_3F,
    VR3_SOUTHEAST_TO_2F,
    VR3_SWITCH_TO_HOLE,
    RivalTurn,
    _encounter_party,
)


def test_victory_road_routes_are_live_qualified() -> None:
    assert VICTORY_ROAD_CHECKPOINT_COUNT == 9
    assert len(CENTER_TO_ROUTE_22) == 38
    assert len(ROUTE_22_TO_RIVAL) == 19
    assert len(SAFFRON_TO_MART) == 59
    assert len(VIRIDIAN_TO_ROUTE_22) == 33
    assert len(ROUTE_22_TO_GATE) == 66
    assert len(EARTH_APPROACH) == 34
    assert len(VR1_TO_2F) == 51
    assert len(VR2_TO_3F) == 56
    assert len(VR3_SWITCH_TO_HOLE) == 85
    assert len(VR2_FINAL_TO_3F) == 17
    assert len(VR3_SOUTHEAST_TO_2F) == 8
    assert len(ROUTE_23_TO_INDIGO) == 45


def test_victory_road_source_ids_are_exact() -> None:
    assert MapId.ROUTE_22 == 0x21
    assert MapId.ROUTE_23 == 0x22
    assert MapId.VICTORY_ROAD_1F == 0x6C
    assert MapId.VICTORY_ROAD_2F == 0xC2
    assert MapId.VICTORY_ROAD_3F == 0xC6
    assert MapId.INDIGO_PLATEAU_LOBBY == 0xAE
    assert EventFlag.BEAT_ROUTE_22_RIVAL_2ND_BATTLE == 0x526
    assert tuple(int(event) for event in BADGE_CHECK_EVENTS) == tuple(range(0x530, 0x537))
    assert EventFlag.VICTORY_ROAD_2F_BOULDER_ON_SWITCH_1 == 0x538
    assert EventFlag.VICTORY_ROAD_2F_BOULDER_ON_SWITCH_2 == 0x53F
    assert EventFlag.VICTORY_ROAD_3F_BOULDER_ON_SWITCH_1 == 0x660
    assert EventFlag.VICTORY_ROAD_3F_BOULDER_IN_HOLE == 0x666
    assert EventFlag.VICTORY_ROAD_1F_BOULDER_ON_SWITCH == 0x917
    assert ItemId.FULL_RESTORE == 0x10
    assert ItemId.REVIVE == 0x35
    assert ItemId.TM01_MEGA_PUNCH == 0xC9
    assert ItemId.TM09_TAKE_DOWN == 0xD1
    assert ItemId.TM17_SUBMISSION == 0xD9


def test_route22_rival_receipt_matches_source_party_and_policy() -> None:
    turns = tuple(
        RivalTurn(species, level, 1, 1, (1, 1, 1, 1), RIVAL_POLICY[species])
        for species, level in RIVAL_PARTY
    )
    assert _encounter_party(turns) == RIVAL_PARTY
    assert tuple(turn.move_slot for turn in turns) == (3, 4, 3, 4, 4, 3)
