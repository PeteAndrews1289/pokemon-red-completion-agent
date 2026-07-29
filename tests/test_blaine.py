from pokemon_red_completion.blaine import (
    BLAINE_CHECKPOINT_COUNT,
    BLAINE_PARTY,
    BLAINE_TO_GYM_EXIT,
    GYM_GATE_EVENTS,
    GYM_QUIZ_ROUTES,
    GYM_RETURN_TO_BLAINE,
    GYM_TRAINER_EVENTS,
    MANSION_1F_TO_3F,
    MANSION_3F_TO_B1F,
    MANSION_B1F_TO_NORTH_STATUE,
    MANSION_B1F_TO_SECRET_KEY,
    MANSION_TRAINER_EVENTS,
    QUIZ_ANSWERS,
    QUIZ_TEXT_PULSES,
    BlaineTurn,
    _encounter_party,
)
from pokemon_red_completion.observation import EventFlag, ItemId, MapId


def test_mansion_and_gym_routes_are_source_and_live_stable() -> None:
    assert BLAINE_CHECKPOINT_COUNT == 8
    assert len(MANSION_1F_TO_3F) == 36
    assert len(MANSION_3F_TO_B1F) == 34
    assert len(MANSION_B1F_TO_NORTH_STATUE) == 54
    assert len(MANSION_B1F_TO_SECRET_KEY) == 35
    assert tuple(len(route) for route in GYM_QUIZ_ROUTES) == (14, 19, 11, 12, 12, 12)
    assert QUIZ_ANSWERS == (True, False, False, False, True, False)
    assert QUIZ_TEXT_PULSES == (9, 10, 9, 11, 11, 9)
    assert len(BLAINE_TO_GYM_EXIT) == len(GYM_RETURN_TO_BLAINE) == 59


def test_blaine_source_ids_are_exact() -> None:
    assert MapId.POKEMON_MANSION_1F == 0xA5
    assert MapId.CINNABAR_GYM == 0xA6
    assert MapId.CINNABAR_MART == 0xAC
    assert MapId.POKEMON_MANSION_2F == 0xD6
    assert MapId.POKEMON_MANSION_3F == 0xD7
    assert MapId.POKEMON_MANSION_B1F == 0xD8
    assert ItemId.SECRET_KEY == 0x2B
    assert ItemId.TM38_FIRE_BLAST == 0xEE
    assert EventFlag.MANSION_SWITCH_ON == 0x278
    assert EventFlag.GOT_TM38 == 0x298
    assert EventFlag.BEAT_BLAINE == 0x299
    assert tuple(int(event) for event in GYM_TRAINER_EVENTS) == tuple(range(0x29A, 0x2A1))
    assert tuple(int(event) for event in GYM_GATE_EVENTS) == tuple(range(0x2A8, 0x2AF))
    assert tuple(int(event) for event in MANSION_TRAINER_EVENTS) == (
        0x289,
        0x801,
        0x811,
        0x812,
        0x821,
        0x822,
    )


def test_blaine_turn_receipt_collapses_repeated_arcanine_turns() -> None:
    turns = (
        BlaineTurn(0x21, 42, 104, 142, 0, (15, 15, 10, 15), 4),
        BlaineTurn(0xA3, 40, 96, 142, 0, (15, 15, 10, 14), 4),
        BlaineTurn(0xA4, 42, 113, 142, 0, (15, 15, 10, 13), 4),
        BlaineTurn(0x14, 47, 149, 142, 0, (15, 15, 10, 12), 4),
        BlaineTurn(0x14, 47, 76, 142, 0, (15, 15, 10, 11), 4),
    )

    assert _encounter_party(turns) == BLAINE_PARTY
