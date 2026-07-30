from pokemon_red_completion.champion import (
    CHAMPION_CHECKPOINT_COUNT,
    CHAMPION_PARTY,
    CHAMPION_RNG_DELAY_FRAMES,
    CHAMPION_SAFE_HP,
    ChampionTurn,
    _encounter_party,
    _turns_valid,
)
from pokemon_red_completion.observation import EventFlag, MapId


def test_champion_source_contract_is_exact() -> None:
    assert CHAMPION_CHECKPOINT_COUNT == 3
    assert CHAMPION_RNG_DELAY_FRAMES == 25
    assert CHAMPION_SAFE_HP == 40
    assert MapId.CHAMPIONS_ROOM == 0x78
    assert MapId.HALL_OF_FAME == 0x76
    assert EventFlag.BEAT_CHAMPION_RIVAL == 0x901
    assert CHAMPION_PARTY == (
        (0x97, 61),
        (0x95, 59),
        (0x01, 61),
        (0x16, 61),
        (0x14, 63),
        (0x9A, 65),
    )


def test_champion_receipt_reconstructs_party_and_policy() -> None:
    turns = tuple(
        ChampionTurn(
            species,
            level,
            100,
            CHAMPION_SAFE_HP,
            0,
            (1, 1, 0, 1),
            4 if species in {0x01, 0x14} else 1,
            position,
        )
        for position, (species, level) in enumerate(CHAMPION_PARTY)
    )
    assert _encounter_party(turns) == CHAMPION_PARTY
    assert _turns_valid(turns)
