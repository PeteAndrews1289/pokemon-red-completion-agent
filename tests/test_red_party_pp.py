from __future__ import annotations

import pytest

from pokemon_red_completion.red_party_pp import (
    RedPartyPpError,
    decode_red_party_pp,
    natural_pp_depletion_slots,
)


def test_red_party_pp_uses_actual_capacity_and_exact_middle_ceiling() -> None:
    state = decode_red_party_pp(
        (44, 39, 58, 57),
        (25, 30, 10, 15),
    )

    assert state.current_total == 80
    assert state.maximum_total == 80
    assert state.resource_bin == "high"
    assert state.middle_pp_ceiling == 53
    assert state.minimum_consumption_to_middle == 27
    assert natural_pp_depletion_slots(state) == (1, 3, 4)


def test_red_party_pp_decodes_pp_ups_without_a_global_ceiling() -> None:
    state = decode_red_party_pp((45, 0, 0, 0), (0xFD, 0, 0, 0))

    assert state.moves[0].current_pp == 61
    assert state.moves[0].maximum_pp == 61
    assert state.ratio == 1.0


@pytest.mark.parametrize(
    ("moves", "pp", "match"),
    (
        ((1, 2, 0), (35, 25, 0), "vectors are invalid"),
        ((0, 0, 0, 0), (1, 0, 0, 0), "empty Red move"),
        ((0, 0, 0, 0), (0x40, 0, 0, 0), "empty Red move"),
        ((1, 0, 0, 0), (63, 0, 0, 0), "above its own maximum"),
    ),
)
def test_red_party_pp_rejects_incoherent_vectors(
    moves: tuple[int, ...],
    pp: tuple[int, ...],
    match: str,
) -> None:
    with pytest.raises(RedPartyPpError, match=match):
        decode_red_party_pp(moves, pp)
