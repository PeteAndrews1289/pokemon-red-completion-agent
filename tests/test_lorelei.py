from pokemon_red_completion.lorelei import (
    INDIGO_TO_LORELEI,
    LORELEI_APPROACH,
    LORELEI_CHECKPOINT_COUNT,
    LORELEI_PARTY,
    LORELEI_RNG_DELAY_FRAMES,
    LORELEI_SAFE_HP,
    LoreleiTurn,
    _encounter_party,
    _turns_valid,
)
from pokemon_red_completion.observation import EventFlag, MapId


def test_lorelei_routes_are_live_qualified() -> None:
    assert LORELEI_CHECKPOINT_COUNT == 3
    assert LORELEI_RNG_DELAY_FRAMES == 119
    assert INDIGO_TO_LORELEI == (
        "up",
        "up",
        "up",
        "right",
        "right",
        "right",
        "right",
        "up",
        "right",
        "right",
        "up",
    )
    assert LORELEI_APPROACH == ("right", "up", "up")


def test_lorelei_source_ids_and_party_are_exact() -> None:
    assert MapId.LORELEIS_ROOM == 0xF5
    assert MapId.BRUNOS_ROOM == 0xF6
    assert EventFlag.BEAT_LORELEI == 0x8E1
    assert LORELEI_PARTY == (
        (0x78, 54),
        (0x8B, 53),
        (0x08, 54),
        (0x48, 56),
        (0x13, 56),
    )


def test_lorelei_receipt_reconstructs_party_and_rejects_unsafe_turns() -> None:
    turns = tuple(
        LoreleiTurn(species, level, 1, LORELEI_SAFE_HP, 0, (1, 1, 1, 1), 2)
        for species, level in LORELEI_PARTY
    )
    assert _encounter_party(turns) == LORELEI_PARTY
    assert _turns_valid(turns)
    assert not _turns_valid(
        (
            LoreleiTurn(
                LORELEI_PARTY[0][0],
                LORELEI_PARTY[0][1],
                1,
                LORELEI_SAFE_HP - 1,
                0,
                (1, 1, 1, 1),
                2,
            ),
        )
    )
