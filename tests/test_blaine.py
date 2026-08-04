from dataclasses import replace

import pytest

from pokemon_red_completion.blaine import (
    BLAINE_ANTIDOTE_SALE_VALUE,
    BLAINE_CAPACITY_SALE_ITEM,
    BLAINE_CHECKPOINT_COUNT,
    BLAINE_EARLY_BIDE_REPLACEMENT_NET_COST,
    BLAINE_INPUT_BAG_SLOT_BOUNDS,
    BLAINE_MAX_WILD_FLEES,
    BLAINE_MONEY_DELTA,
    BLAINE_PARTY,
    BLAINE_TO_GYM_EXIT,
    CENTER_TO_MANSION,
    GYM_GATE_EVENTS,
    GYM_QUIZ_ROUTES,
    GYM_RETURN_TO_BLAINE,
    GYM_TRAINER_EVENTS,
    HYDRO_PUMP_LEARN_LEVEL,
    MANSION_1F_TO_3F,
    MANSION_3F_TO_B1F,
    MANSION_B1F_TO_NORTH_STATUE,
    MANSION_B1F_TO_SECRET_KEY,
    MANSION_DEVELOPMENT_POLICY,
    MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
    MANSION_MAX_CONSECUTIVE_FLEES,
    MANSION_TEAM_POLICY,
    MANSION_TRAINER_EVENTS,
    MANSION_TRAINING_POLICY,
    MANSION_VOLATILE_ENEMY_SPECIES,
    QUIZ_ANSWERS,
    QUIZ_TEXT_PULSES,
    BlaineTurn,
    _battle_command_direction,
    _blaine_capacity_input_slots,
    _blaine_capacity_plan,
    _encounter_party,
    _mansion_training_move_slot,
    _PauseForTeamTrainingRecovery,
    _red_training_matchup_acceptable,
    _sell_antidote_before_mansion,
    _team_training_move_slot,
    _training_attack_pp,
    _training_attack_pp_reserve,
)
from pokemon_red_completion.observation import EventFlag, ItemId, MapId, RawGameState
from pokemon_red_completion.party import MoveObservation, PartyMemberObservation
from pokemon_red_completion.team_training import BalancedTeamPolicy


def test_mansion_and_gym_routes_are_source_and_live_stable() -> None:
    assert BLAINE_CHECKPOINT_COUNT == 9
    assert len(MANSION_1F_TO_3F) == 36
    assert len(MANSION_3F_TO_B1F) == 34
    assert len(MANSION_B1F_TO_NORTH_STATUE) == 54
    assert len(MANSION_B1F_TO_SECRET_KEY) == 35
    assert tuple(len(route) for route in GYM_QUIZ_ROUTES) == (14, 19, 11, 12, 12, 12)
    assert QUIZ_ANSWERS == (True, False, False, False, True, False)
    assert QUIZ_TEXT_PULSES == (9, 10, 9, 11, 11, 9)
    assert len(BLAINE_TO_GYM_EXIT) == len(GYM_RETURN_TO_BLAINE) == 59
    assert BLAINE_CAPACITY_SALE_ITEM is ItemId.ANTIDOTE
    assert BLAINE_INPUT_BAG_SLOT_BOUNDS == (15, 20)
    assert BLAINE_EARLY_BIDE_REPLACEMENT_NET_COST == 1_300
    assert BLAINE_MONEY_DELTA == 5_003
    assert BLAINE_ANTIDOTE_SALE_VALUE == 50
    assert BLAINE_MAX_WILD_FLEES == 3
    assert CENTER_TO_MANSION == (
        ("down",) * 5 + ("right",) * 7 + ("up",) * 7 + ("left", "up") + ("left",) * 11 + ("up",)
    )
    assert MANSION_TRAINING_POLICY.target_level == 75
    assert HYDRO_PUMP_LEARN_LEVEL == 52
    assert MANSION_TRAINING_POLICY.max_battles < MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL
    assert MANSION_TRAINING_POLICY.preferred_move_slots == (4, 2, 3, 1)
    assert MANSION_TRAINING_POLICY.max_battles == 800
    assert MANSION_DEVELOPMENT_POLICY.workhorse_target_level == 75
    assert MANSION_DEVELOPMENT_POLICY.workhorse_species_id in (
        MANSION_DEVELOPMENT_POLICY.roster.species_ids
    )
    assert MANSION_TEAM_POLICY.required_size == 6
    assert MANSION_TEAM_POLICY.max_battles == 7_000
    assert MANSION_TEAM_POLICY.max_healing_trips == 1_250
    assert MANSION_MAX_CONSECUTIVE_FLEES == 32
    assert frozenset({0x37, 0x8F}) == MANSION_VOLATILE_ENEMY_SPECIES


def test_blaine_antidote_capacity_plan_handles_consumed_and_retained_fillers() -> None:
    assert not _sell_antidote_before_mansion(16, 2)
    assert not _sell_antidote_before_mansion(17, 1)
    assert not _sell_antidote_before_mansion(18, 0)
    assert not _sell_antidote_before_mansion(18, 1)
    assert not _sell_antidote_before_mansion(18, 2)
    assert _sell_antidote_before_mansion(19, 1)
    assert _sell_antidote_before_mansion(19, 2)


def test_blaine_replaces_an_early_sold_bide_capacity_slot() -> None:
    assert _blaine_capacity_plan(15, bide_present=False) == (True, True, 2, 16)
    assert _blaine_capacity_plan(16, bide_present=False) == (True, False, 2, 17)
    assert _blaine_capacity_plan(17, bide_present=True) == (False, False, 2, 17)


def test_blaine_sells_obsolete_potions_only_at_twenty_slots() -> None:
    assert _blaine_capacity_input_slots(19, 5) == (19, 0)
    assert _blaine_capacity_input_slots(20, 5) == (19, 5)


def test_team_training_navigates_the_two_column_battle_menu() -> None:
    assert _battle_command_direction(0, 2) == "right"
    assert _battle_command_direction(1, 2) == "right"
    assert _battle_command_direction(3, 2) == "up"
    assert _battle_command_direction(2, 2) is None
    assert _battle_command_direction(None, 2) is None


def test_lead_training_skips_a_live_disabled_move() -> None:
    raw = RawGameState(
        True,
        MapId.POKEMON_MANSION_1F,
        5,
        20,
        6,
        1,
        first_party_pp=(8, 4, 0, 3),
        player_disabled_move_slot=4,
        player_disable_turns=3,
    )

    assert _mansion_training_move_slot(raw) == 2
    with pytest.raises(_PauseForTeamTrainingRecovery):
        _mansion_training_move_slot(
            replace(raw, first_party_pp=(8, 0, 0, 0), player_disabled_move_slot=1)
        )


def test_team_training_selects_damaging_moves_for_the_active_species() -> None:
    base = RawGameState(True, MapId.POKEMON_MANSION_1F, 5, 20, 3, 1)

    assert (
        _team_training_move_slot(
            replace(
                base,
                active_party_species_id=0x1C,
                active_party_moves=(0x82, 0x46, 0x3A, 0x39),
                active_party_pp=(15, 15, 10, 15),
            )
        )
        == 4
    )
    assert (
        _team_training_move_slot(
            replace(
                base,
                active_party_species_id=0x40,
                active_party_moves=(0x40, 0x1C, 0x0F, 0x13),
                active_party_pp=(35, 15, 30, 15),
            )
        )
        == 3
    )


def test_team_training_requests_escape_when_all_species_attacks_are_unusable() -> None:
    base = RawGameState(True, MapId.POKEMON_MANSION_1F, 5, 20, 3, 1)

    with pytest.raises(_PauseForTeamTrainingRecovery):
        _team_training_move_slot(
            replace(
                base,
                active_party_species_id=0x40,
                active_party_moves=(0x40, 0x1C, 0x0F, 0x13),
                active_party_pp=(0, 15, 0, 15),
            )
        )
    with pytest.raises(_PauseForTeamTrainingRecovery):
        _team_training_move_slot(
            replace(
                base,
                active_party_species_id=0x40,
                active_party_moves=(0x40, 0x1C, 0x0F, 0x13),
                active_party_pp=(35, 15, 0, 15),
                player_disabled_move_slot=1,
            )
        )
    assert (
        _team_training_move_slot(
            replace(
                base,
                active_party_species_id=0x84,
                active_party_moves=(0x22, 0x85, 0x9C, 0),
                active_party_pp=(15, 4, 10, 0),
            )
        )
        == 1
    )
    assert (
        _team_training_move_slot(
            replace(
                base,
                active_party_species_id=0x3B,
                active_party_moves=(0x0A, 0x2D, 0x5B, 0x1C),
                active_party_pp=(35, 40, 10, 15),
            )
        )
        == 3
    )


def test_red_training_matchup_requires_extra_margin_for_dux() -> None:
    dux = PartyMemberObservation(
        slot=1,
        species_id=0x40,
        level=45,
        hp=100,
        max_hp=100,
        moves=(MoveObservation(0x0F, 30),),
    )
    policy = BalancedTeamPolicy(
        required_size=3,
        max_enemy_level_delta=0,
        minimum_direct_level_advantage=8,
    )

    assert _red_training_matchup_acceptable(dux, 30, policy)
    assert not _red_training_matchup_acceptable(dux, 31, policy)
    assert not _red_training_matchup_acceptable(dux, 20, policy, 0x88)
    assert _training_attack_pp_reserve(dux, policy) == 6

    dux_with_only_fly = replace(
        dux,
        moves=(
            MoveObservation(0x40, 0),
            MoveObservation(0x1C, 15),
            MoveObservation(0x0F, 0),
            MoveObservation(0x13, 15),
        ),
    )
    assert _training_attack_pp(dux_with_only_fly) == 0

    dugtrio = replace(dux, species_id=0x76, moves=(MoveObservation(0x5B, 10),))
    assert _training_attack_pp_reserve(dugtrio, policy) == 2


def test_red_training_matchup_routes_volatile_species_to_the_safe_escort() -> None:
    trainee = PartyMemberObservation(
        slot=1,
        species_id=0x40,
        level=80,
        hp=100,
        max_hp=100,
        moves=(MoveObservation(0x0F, 30),),
    )
    policy = BalancedTeamPolicy(required_size=3)

    for enemy_species in MANSION_VOLATILE_ENEMY_SPECIES:
        assert not _red_training_matchup_acceptable(
            trainee,
            enemy_level=30,
            policy=policy,
            enemy_species=enemy_species,
        )


def test_blaine_source_ids_are_exact() -> None:
    assert MapId.POKEMON_MANSION_1F == 0xA5
    assert MapId.CINNABAR_GYM == 0xA6
    assert MapId.CINNABAR_MART == 0xAC
    assert MapId.POKEMON_MANSION_2F == 0xD6
    assert MapId.POKEMON_MANSION_3F == 0xD7
    assert MapId.POKEMON_MANSION_B1F == 0xD8
    assert ItemId.SECRET_KEY == 0x2B
    assert ItemId.TM14_BLIZZARD == 0xD6
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
