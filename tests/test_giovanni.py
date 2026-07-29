from pokemon_red_completion.giovanni import (
    CENTER_EXIT_TO_GYM,
    FLY_ARRIVAL_TO_MART,
    GIOVANNI_CHECKPOINT_COUNT,
    GIOVANNI_PARTY,
    GIOVANNI_TO_GYM_EXIT,
    GYM_ENTRY_TO_HIKER,
    GYM_EXIT_TO_CENTER,
    GYM_GATE_TO_EXIT,
    GYM_REENTRY_TO_GIOVANNI,
    GYM_TRAINER_EVENTS,
    HIKER_TO_BLACKBELT,
    MART_EXIT_TO_GYM,
    REQUIRED_TRAINER_EVENTS,
    REQUIRED_TRAINERS,
    GiovanniTurn,
    _encounter_party,
)
from pokemon_red_completion.observation import EventFlag, ItemId, MapId


def test_viridian_routes_are_live_qualified() -> None:
    assert GIOVANNI_CHECKPOINT_COUNT == 8
    assert len(FLY_ARRIVAL_TO_MART) == 13
    assert len(MART_EXIT_TO_GYM) == 50
    assert len(GYM_ENTRY_TO_HIKER) == 10
    assert len(HIKER_TO_BLACKBELT) == 10
    assert len(GYM_GATE_TO_EXIT) == 16
    assert len(GYM_EXIT_TO_CENTER) == 35
    assert len(CENTER_EXIT_TO_GYM) == 50
    assert len(GYM_REENTRY_TO_GIOVANNI) == 39
    assert len(GIOVANNI_TO_GYM_EXIT) == 22


def test_giovanni_source_ids_are_exact() -> None:
    assert MapId.VIRIDIAN_POKECENTER == 0x29
    assert MapId.VIRIDIAN_MART == 0x2A
    assert MapId.VIRIDIAN_GYM == 0x2D
    assert ItemId.TM27_FISSURE == 0xE3
    assert ItemId.TM46_PSYWAVE == 0xF6
    assert EventFlag.GOT_TM27 == 0x050
    assert EventFlag.BEAT_VIRIDIAN_GYM_GIOVANNI == 0x051
    assert tuple(int(event) for event in GYM_TRAINER_EVENTS) == tuple(range(0x052, 0x05A))
    assert EventFlag.SECOND_ROUTE_22_RIVAL_BATTLE == 0x521
    assert EventFlag.ROUTE_22_RIVAL_WANTS_BATTLE == 0x527


def test_required_gym_battles_match_source_headers() -> None:
    assert REQUIRED_TRAINER_EVENTS == (
        True,
        True,
        True,
        False,
        True,
        True,
        False,
        True,
    )
    assert tuple((label, identity, party) for label, identity, party, _ in REQUIRED_TRAINERS) == (
        ("hiker_set_8", (0xE0, 0xE0, 8), ((0x29, 38), (0x6A, 38), (0x29, 38))),
        ("blackbelt_set_6", (0xE0, 0xE0, 6), ((0x6A, 40), (0x29, 40))),
        ("cooltrainer_set_9", (0xE7, 0xE7, 9), ((0x61, 39), (0x76, 39))),
        ("tamer_set_3", (0xDE, 0xDE, 3), ((0x12, 43),)),
        ("cooltrainer_set_10", (0xE7, 0xE7, 10), ((0x12, 43),)),
        ("cooltrainer_set_1", (0xE7, 0xE7, 1), ((0xA7, 39), (0x07, 39))),
    )
    assert tuple(move_slot for *_, move_slot in REQUIRED_TRAINERS) == (2, 2, 3, 3, 3, 3)


def test_giovanni_turn_receipt_matches_source_party() -> None:
    turns = tuple(
        GiovanniTurn(species, level, 1, 1, 0, (1, 1, 1, 1), 4)
        for species, level in GIOVANNI_PARTY
    )
    assert _encounter_party(turns) == GIOVANNI_PARTY
