from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.misty_policy import (
    STARMIE_SPECIES_ID,
    STARYU_SPECIES_ID,
    MistyPolicyEvidenceError,
    choose_misty_move_slot,
)
from pokemon_red_completion.observation import (
    MEGA_PUNCH_MOVE_ID,
    TACKLE_MOVE_ID,
    MapId,
    RawGameState,
)


def _misty_battle(
    *,
    map_id: int | None = MapId.CERULEAN_GYM,
    battle_state: int | None = 2,
    enemy_species_id: int | None = STARYU_SPECIES_ID,
    moves: tuple[int, ...] | None = (
        TACKLE_MOVE_ID,
        0x27,
        MEGA_PUNCH_MOVE_ID,
        0x37,
    ),
    pp: tuple[int, ...] | None = (35, 30, 30, 25),
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=5,
        player_y=2,
        party_count=1,
        battle_state=battle_state,
        first_party_moves=moves,
        first_party_pp=pp,
        enemy_species_id=enemy_species_id,
    )


def test_misty_species_ids_match_the_pinned_pokered_source() -> None:
    assert (STARYU_SPECIES_ID, STARMIE_SPECIES_ID) == (0x1B, 0x98)


@pytest.mark.parametrize("enemy_species_id", [STARYU_SPECIES_ID, STARMIE_SPECIES_ID])
def test_misty_party_selects_mega_punch_slot_three(enemy_species_id: int) -> None:
    assert (
        choose_misty_move_slot(
            _misty_battle(enemy_species_id=enemy_species_id)
        )
        == 3
    )


@pytest.mark.parametrize("battle_state", [None, 0, 1])
def test_policy_fails_closed_without_active_trainer_battle(
    battle_state: int | None,
) -> None:
    with pytest.raises(MistyPolicyEvidenceError, match="active trainer battle"):
        choose_misty_move_slot(
            replace(_misty_battle(), battle_state=battle_state)
        )


@pytest.mark.parametrize("map_id", [None, MapId.CERULEAN_CITY, MapId.PEWTER_GYM])
def test_policy_fails_closed_outside_cerulean_gym(map_id: int | None) -> None:
    with pytest.raises(MistyPolicyEvidenceError, match="Cerulean Gym map"):
        choose_misty_move_slot(_misty_battle(map_id=map_id))


@pytest.mark.parametrize("enemy_species_id", [None, 0])
def test_policy_fails_closed_without_enemy_species_evidence(
    enemy_species_id: int | None,
) -> None:
    with pytest.raises(MistyPolicyEvidenceError, match="enemy species evidence"):
        choose_misty_move_slot(
            _misty_battle(enemy_species_id=enemy_species_id)
        )


@pytest.mark.parametrize("enemy_species_id", [0x01, 0x9D, 0xFF])
def test_policy_fails_closed_for_species_outside_mistys_party(
    enemy_species_id: int,
) -> None:
    with pytest.raises(MistyPolicyEvidenceError, match="unexpected enemy species"):
        choose_misty_move_slot(
            _misty_battle(enemy_species_id=enemy_species_id)
        )


@pytest.mark.parametrize("moves", [None, ()])
def test_policy_fails_closed_without_mega_punch_slot_evidence(
    moves: tuple[int, ...] | None,
) -> None:
    with pytest.raises(MistyPolicyEvidenceError, match="move evidence for slot 3"):
        choose_misty_move_slot(_misty_battle(moves=moves))


@pytest.mark.parametrize(
    "moves",
    [
        (TACKLE_MOVE_ID, 0x27, 0x91, 0x37),
        (TACKLE_MOVE_ID, 0x27, 0x37, MEGA_PUNCH_MOVE_ID),
    ],
)
def test_policy_rejects_wrong_move_or_wrong_slot(
    moves: tuple[int, ...],
) -> None:
    with pytest.raises(
        MistyPolicyEvidenceError,
        match=rf"expected move {MEGA_PUNCH_MOVE_ID:#04x} in slot 3",
    ):
        choose_misty_move_slot(_misty_battle(moves=moves))


@pytest.mark.parametrize("pp", [None, ()])
def test_policy_fails_closed_without_mega_punch_pp_evidence(
    pp: tuple[int, ...] | None,
) -> None:
    with pytest.raises(MistyPolicyEvidenceError, match="PP evidence for slot 3"):
        choose_misty_move_slot(_misty_battle(pp=pp))


@pytest.mark.parametrize("current_pp", [0, 0x40, 0x80, 0xC0])
def test_policy_rejects_zero_current_pp_even_with_pp_up_bits(
    current_pp: int,
) -> None:
    with pytest.raises(MistyPolicyEvidenceError, match="usable PP in slot 3"):
        choose_misty_move_slot(
            _misty_battle(pp=(0, 0, current_pp, 0))
        )


def test_policy_accepts_usable_current_pp_with_pp_up_bits() -> None:
    assert choose_misty_move_slot(_misty_battle(pp=(0, 0, 0xC1, 0))) == 3
