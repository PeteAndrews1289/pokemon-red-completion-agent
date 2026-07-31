from pokemon_red_completion.agatha import (
    AGATHA_APPROACH,
    AGATHA_CHECKPOINT_COUNT,
    AGATHA_PARTY,
    AGATHA_RNG_DELAY_FRAMES,
    AGATHA_SAFE_HP,
    AgathaTurn,
    _encounter_party,
    _turns_valid,
)
from pokemon_red_completion.observation import EventFlag, MapId


def test_agatha_source_contract_is_exact() -> None:
    assert AGATHA_CHECKPOINT_COUNT == 3
    assert AGATHA_APPROACH == ("right", "up", "up")
    assert AGATHA_RNG_DELAY_FRAMES == 85
    assert MapId.AGATHAS_ROOM == 0xF7
    assert MapId.LANCES_ROOM == 0x71
    assert EventFlag.BEAT_AGATHA == 0x8F1
    assert AGATHA_PARTY == (
        (0x0E, 56),
        (0x82, 56),
        (0x93, 55),
        (0x2D, 58),
        (0x0E, 60),
    )


def test_agatha_receipt_deduplicates_switches() -> None:
    identities = (
        (AGATHA_PARTY[0], 0),
        (AGATHA_PARTY[1], 1),
        (AGATHA_PARTY[0], 0),
        (AGATHA_PARTY[2], 2),
        (AGATHA_PARTY[3], 3),
        (AGATHA_PARTY[4], 4),
    )
    turns = tuple(
        AgathaTurn(
            species,
            level,
            1,
            AGATHA_SAFE_HP,
            0,
            (1, 1, 1, 1),
            3,
            party_position,
        )
        for (species, level), party_position in identities
    )
    assert _encounter_party(turns) == AGATHA_PARTY
    assert _turns_valid(turns)
    assert _turns_valid(
        (AgathaTurn(0x82, 56, 1, AGATHA_SAFE_HP, 0, (1, 0, 1, 1), 1),)
    )
