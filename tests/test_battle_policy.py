from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.battle_policy import (
    BattlePolicyEvidenceError,
    choose_cerulean_rival_move_slot,
)
from pokemon_red_completion.observation import (
    ABRA_SPECIES_ID,
    BULBASAUR_SPECIES_ID,
    PIDGEOTTO_SPECIES_ID,
    RATTATA_SPECIES_ID,
    TACKLE_MOVE_ID,
    TAIL_WHIP_MOVE_ID,
    WATER_GUN_MOVE_ID,
    RawGameState,
)


def _rival_battle(
    *,
    enemy_species_id: int | None = PIDGEOTTO_SPECIES_ID,
    moves: tuple[int, ...] | None = (
        TACKLE_MOVE_ID,
        TAIL_WHIP_MOVE_ID,
        0x91,
        WATER_GUN_MOVE_ID,
    ),
    pp: tuple[int, ...] | None = (35, 30, 30, 11),
    player_attack_stage: int | None = 7,
    enemy_defense_stage: int | None = 6,
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=0x03,
        player_x=21,
        player_y=6,
        party_count=1,
        battle_state=2,
        first_party_moves=moves,
        first_party_pp=pp,
        enemy_species_id=enemy_species_id,
        player_attack_stage=player_attack_stage,
        enemy_defense_stage=enemy_defense_stage,
    )


def test_move_ids_match_the_pinned_pokered_source() -> None:
    assert TACKLE_MOVE_ID == 0x21
    assert WATER_GUN_MOVE_ID == 0x37


def test_cerulean_rival_species_match_the_pinned_party() -> None:
    assert (
        PIDGEOTTO_SPECIES_ID,
        ABRA_SPECIES_ID,
        RATTATA_SPECIES_ID,
        BULBASAUR_SPECIES_ID,
    ) == (0x96, 0x94, 0xA5, 0x99)


@pytest.mark.parametrize(
    "enemy_species_id",
    [PIDGEOTTO_SPECIES_ID, ABRA_SPECIES_ID, RATTATA_SPECIES_ID],
)
def test_non_bulbasaur_opponents_select_water_gun_slot_four(
    enemy_species_id: int,
) -> None:
    assert choose_cerulean_rival_move_slot(_rival_battle(enemy_species_id=enemy_species_id)) == 4


def test_bulbasaur_selects_tackle_slot_one() -> None:
    assert (
        choose_cerulean_rival_move_slot(_rival_battle(enemy_species_id=BULBASAUR_SPECIES_ID)) == 1
    )


def test_bulbasaur_selects_one_tail_whip_while_defense_is_neutral() -> None:
    assert (
        choose_cerulean_rival_move_slot(
            _rival_battle(
                enemy_species_id=BULBASAUR_SPECIES_ID,
                player_attack_stage=6,
                enemy_defense_stage=7,
            )
        )
        == 2
    )
    assert (
        choose_cerulean_rival_move_slot(
            _rival_battle(
                enemy_species_id=BULBASAUR_SPECIES_ID,
                player_attack_stage=7,
                enemy_defense_stage=7,
            )
        )
        == 2
    )
    assert (
        choose_cerulean_rival_move_slot(
            _rival_battle(
                enemy_species_id=BULBASAUR_SPECIES_ID,
                player_attack_stage=6,
                enemy_defense_stage=6,
            )
        )
        == 1
    )


@pytest.mark.parametrize(
    ("player_attack_stage", "enemy_defense_stage"),
    [(None, 7), (7, None), (0, 7), (7, 14), (True, 7)],
)
def test_bulbasaur_strategy_requires_valid_stat_stage_evidence(
    player_attack_stage: int | None,
    enemy_defense_stage: int | None,
) -> None:
    with pytest.raises(BattlePolicyEvidenceError, match="stage evidence"):
        choose_cerulean_rival_move_slot(
            _rival_battle(
                enemy_species_id=BULBASAUR_SPECIES_ID,
                player_attack_stage=player_attack_stage,
                enemy_defense_stage=enemy_defense_stage,
            )
        )


@pytest.mark.parametrize("battle_state", [None, 0, 1])
def test_policy_fails_closed_without_active_trainer_battle(
    battle_state: int | None,
) -> None:
    with pytest.raises(BattlePolicyEvidenceError, match="active trainer battle"):
        choose_cerulean_rival_move_slot(replace(_rival_battle(), battle_state=battle_state))


@pytest.mark.parametrize("enemy_species_id", [None, 0])
def test_policy_fails_closed_without_enemy_species_evidence(
    enemy_species_id: int | None,
) -> None:
    with pytest.raises(BattlePolicyEvidenceError, match="enemy species evidence"):
        choose_cerulean_rival_move_slot(_rival_battle(enemy_species_id=enemy_species_id))


@pytest.mark.parametrize("enemy_species_id", [0x01, 0x37, 0xFF])
def test_policy_fails_closed_for_species_outside_the_qualified_rival_party(
    enemy_species_id: int,
) -> None:
    with pytest.raises(BattlePolicyEvidenceError, match="unexpected enemy species"):
        choose_cerulean_rival_move_slot(
            _rival_battle(enemy_species_id=enemy_species_id)
        )


@pytest.mark.parametrize(
    ("enemy_species_id", "moves", "expected_slot"),
    [
        (PIDGEOTTO_SPECIES_ID, None, 4),
        (PIDGEOTTO_SPECIES_ID, (), 4),
        (PIDGEOTTO_SPECIES_ID, (TACKLE_MOVE_ID,), 4),
        (BULBASAUR_SPECIES_ID, None, 1),
        (BULBASAUR_SPECIES_ID, (), 1),
    ],
)
def test_policy_fails_closed_without_required_move_slot_evidence(
    enemy_species_id: int,
    moves: tuple[int, ...] | None,
    expected_slot: int,
) -> None:
    with pytest.raises(
        BattlePolicyEvidenceError,
        match=rf"move evidence for slot {expected_slot}",
    ):
        choose_cerulean_rival_move_slot(
            _rival_battle(enemy_species_id=enemy_species_id, moves=moves)
        )


@pytest.mark.parametrize(
    ("enemy_species_id", "moves", "expected_move", "expected_slot"),
    [
        (
            PIDGEOTTO_SPECIES_ID,
            (TACKLE_MOVE_ID, 0x27, WATER_GUN_MOVE_ID, 0),
            WATER_GUN_MOVE_ID,
            4,
        ),
        (
            PIDGEOTTO_SPECIES_ID,
            (TACKLE_MOVE_ID, 0x27, 0x91, TACKLE_MOVE_ID),
            WATER_GUN_MOVE_ID,
            4,
        ),
        (
            BULBASAUR_SPECIES_ID,
            (WATER_GUN_MOVE_ID, 0x27, 0x91, WATER_GUN_MOVE_ID),
            TACKLE_MOVE_ID,
            1,
        ),
    ],
)
def test_policy_rejects_wrong_move_or_wrong_slot(
    enemy_species_id: int,
    moves: tuple[int, ...],
    expected_move: int,
    expected_slot: int,
) -> None:
    with pytest.raises(
        BattlePolicyEvidenceError,
        match=rf"expected move {expected_move:#04x} in slot {expected_slot}",
    ):
        choose_cerulean_rival_move_slot(
            _rival_battle(enemy_species_id=enemy_species_id, moves=moves)
        )


@pytest.mark.parametrize(
    ("enemy_species_id", "pp", "expected_slot"),
    [
        (PIDGEOTTO_SPECIES_ID, None, 4),
        (PIDGEOTTO_SPECIES_ID, (), 4),
        (PIDGEOTTO_SPECIES_ID, (35,), 4),
        (BULBASAUR_SPECIES_ID, None, 1),
        (BULBASAUR_SPECIES_ID, (), 1),
    ],
)
def test_policy_fails_closed_without_required_pp_slot_evidence(
    enemy_species_id: int,
    pp: tuple[int, ...] | None,
    expected_slot: int,
) -> None:
    with pytest.raises(
        BattlePolicyEvidenceError,
        match=rf"PP evidence for slot {expected_slot}",
    ):
        choose_cerulean_rival_move_slot(_rival_battle(enemy_species_id=enemy_species_id, pp=pp))


@pytest.mark.parametrize(
    ("enemy_species_id", "pp", "expected_slot"),
    [
        (PIDGEOTTO_SPECIES_ID, (35, 30, 30, 0), 4),
        (PIDGEOTTO_SPECIES_ID, (35, 30, 30, 0x40), 4),
        (BULBASAUR_SPECIES_ID, (0, 30, 30, 11), 1),
        (BULBASAUR_SPECIES_ID, (0xC0, 30, 30, 11), 1),
    ],
)
def test_policy_rejects_zero_current_pp_even_with_pp_up_bits(
    enemy_species_id: int,
    pp: tuple[int, ...],
    expected_slot: int,
) -> None:
    with pytest.raises(
        BattlePolicyEvidenceError,
        match=rf"usable PP in slot {expected_slot}",
    ):
        choose_cerulean_rival_move_slot(_rival_battle(enemy_species_id=enemy_species_id, pp=pp))


def test_policy_checks_only_the_selected_move_pp() -> None:
    assert choose_cerulean_rival_move_slot(_rival_battle(pp=(0, 0, 0, 0x41))) == 4
    assert (
        choose_cerulean_rival_move_slot(
            _rival_battle(
                enemy_species_id=BULBASAUR_SPECIES_ID,
                pp=(0xC1, 0, 0, 0),
            )
        )
        == 1
    )
    assert (
        choose_cerulean_rival_move_slot(
            _rival_battle(
                enemy_species_id=BULBASAUR_SPECIES_ID,
                pp=(0, 0x41, 0, 0),
                player_attack_stage=6,
                enemy_defense_stage=7,
            )
        )
        == 2
    )
