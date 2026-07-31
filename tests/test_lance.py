from pokemon_red_completion.lance import (
    LANCE_APPROACH,
    LANCE_CHECKPOINT_COUNT,
    LANCE_PARTY,
    LANCE_RNG_DELAY_FRAMES,
    LANCE_SAFE_HP,
    LanceTurn,
    _encounter_party,
    _turns_valid,
)
from pokemon_red_completion.observation import EventFlag, MapId


def test_lance_source_contract_is_exact() -> None:
    assert LANCE_CHECKPOINT_COUNT == 3
    assert LANCE_RNG_DELAY_FRAMES == 40
    assert LANCE_SAFE_HP == 120
    assert LANCE_APPROACH == ("up",) * 9
    assert MapId.LANCES_ROOM == 0x71
    assert MapId.CHAMPIONS_ROOM == 0x78
    assert EventFlag.BEAT_LANCE == 0x8FE
    assert LANCE_PARTY == (
        (0x16, 58),
        (0x59, 56),
        (0x59, 56),
        (0xAB, 60),
        (0x42, 62),
    )


def test_lance_receipt_reconstructs_party_and_policy() -> None:
    turns = (
        LanceTurn(0x16, 58, 100, 110, 0, (1, 1, 0, 1), 2, 0),
        LanceTurn(0x59, 56, 100, 110, 0, (1, 1, 1, 1), 3, 1),
        LanceTurn(0x59, 56, 1, 110, 0, (1, 1, 1, 1), 3, 1),
        LanceTurn(0x59, 56, 100, 110, 0, (1, 1, 1, 1), 3, 2),
        LanceTurn(0xAB, 60, 100, 110, 0, (1, 1, 0, 1), 4, 3),
        LanceTurn(0x42, 62, 100, 110, 0, (1, 1, 1, 1), 3, 4),
    )
    assert _encounter_party(turns) == LANCE_PARTY
    assert _turns_valid(turns)
