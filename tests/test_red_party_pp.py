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


def test_red_party_pp_middle_ceiling_excludes_the_exact_67_percent_boundary() -> None:
    state = decode_red_party_pp(
        (2, 2, 2, 2),
        (25, 25, 25, 25),
    )

    assert state.maximum_total == 100
    assert state.middle_pp_ceiling == 66
    assert state.minimum_consumption_to_middle == 34


def test_red_party_pp_decodes_pp_ups_without_a_global_ceiling() -> None:
    state = decode_red_party_pp((45, 0, 0, 0), (0xFD, 0, 0, 0))

    assert state.moves[0].current_pp == 61
    assert state.moves[0].maximum_pp == 61
    assert state.ratio == 1.0


@pytest.mark.parametrize(
    ("move_id", "expected_maximum"),
    (
        (12, 8),
        (3, 16),
        (4, 24),
        (5, 32),
        (2, 40),
        (11, 48),
        (1, 56),
        (45, 61),
    ),
)
def test_red_party_pp_matches_every_gen_i_base_pp_band_after_three_pp_ups(
    move_id: int,
    expected_maximum: int,
) -> None:
    packed = (3 << 6) | expected_maximum

    state = decode_red_party_pp((move_id, 0, 0, 0), (packed, 0, 0, 0))

    assert state.moves[0].current_pp == expected_maximum
    assert state.moves[0].maximum_pp == expected_maximum
    assert state.maximum_total == expected_maximum


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
