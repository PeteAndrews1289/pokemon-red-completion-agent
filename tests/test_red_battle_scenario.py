from __future__ import annotations

from dataclasses import replace

from pokemon_red_completion.battle_runtime import BattleTurnExecution
from pokemon_red_completion.observation import (
    PIDGEOTTO_SPECIES_ID,
    TACKLE_MOVE_ID,
    WATER_GUN_MOVE_ID,
    BattleMenuPhase,
    BattleMenuState,
    InputReadiness,
    MapId,
    RawGameState,
)
from pokemon_red_completion.red_battle_scenario import (
    prepare_red_battle_scenario,
    project_red_battle_turn_outcome,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder

TAIL_WHIP_MOVE_ID = 0x27
MEGA_PUNCH_MOVE_ID = 0x05


class Reader:
    def read(self) -> RawGameState:
        return _raw()

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(0, 0, 0, 0, 0, 0)

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
        del raw
        return BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.POKEMON_MANSION_1F,
        player_x=5,
        player_y=20,
        party_count=1,
        battle_state=1,
        badge_bits=0xFF,
        party_species_ids=(0x1C,),
        party_levels=(50,),
        party_hp=(120,),
        party_max_hp=(150,),
        party_status=(0,),
        party_moves=((TACKLE_MOVE_ID, TAIL_WHIP_MOVE_ID, MEGA_PUNCH_MOVE_ID, WATER_GUN_MOVE_ID),),
        party_pp=((35, 30, 20, 25),),
        first_party_level=50,
        first_party_hp=120,
        first_party_max_hp=150,
        first_party_status=0,
        first_party_moves=(
            TACKLE_MOVE_ID,
            TAIL_WHIP_MOVE_ID,
            MEGA_PUNCH_MOVE_ID,
            WATER_GUN_MOVE_ID,
        ),
        first_party_pp=(35, 30, 20, 25),
        enemy_species_id=PIDGEOTTO_SPECIES_ID,
        enemy_level=30,
        enemy_hp=60,
        enemy_max_hp=60,
        player_attack_stage=7,
        player_special_stage=7,
        player_accuracy_stage=7,
        enemy_defense_stage=7,
        player_disabled_move_slot=None,
        player_disable_turns=0,
        enemy_using_trapping_move=False,
        active_party_index=0,
        active_party_species_id=0x1C,
        active_party_level=50,
        active_party_hp=120,
        active_party_max_hp=150,
        active_party_status=0,
        active_party_moves=(
            TACKLE_MOVE_ID,
            TAIL_WHIP_MOVE_ID,
            MEGA_PUNCH_MOVE_ID,
            WATER_GUN_MOVE_ID,
        ),
        active_party_pp=(35, 30, 20, 25),
    )


def _execution(
    final: RawGameState,
    *,
    slot: int = 1,
    move_executed: bool = True,
) -> BattleTurnExecution:
    return BattleTurnExecution(
        initial_state=_raw(),
        final_state=final,
        selected_slot=slot,
        actions_executed=2,
        frames_executed=48,
        move_executed=move_executed,
    )


def test_red_preparation_masks_status_moves_from_first_outcome_family() -> None:
    prepared = prepare_red_battle_scenario(
        PokemonRedObservationEncoder(Reader()),
        _raw(),
    )

    assert prepared.features.slot_indices == (0, 1, 2, 3)
    assert prepared.supported_candidate_mask == (True, False, True, True)
    assert prepared.features.legal_mask == prepared.supported_candidate_mask
    assert len(prepared.initial_observation_sha256) == 64


def test_red_outcome_projector_measures_damage_and_pp_not_teacher_choice() -> None:
    final = replace(
        _raw(),
        enemy_hp=39,
        active_party_hp=112,
        active_party_pp=(34, 30, 20, 25),
    )

    outcome = project_red_battle_turn_outcome(_execution(final))

    assert outcome.move_executed
    assert outcome.opponent_damage_fraction == 21 / 60
    assert outcome.player_damage_fraction == 8 / 150
    assert not outcome.opponent_fainted
    assert outcome.learner_update_eligible


def test_red_terminal_wild_outcome_distinguishes_opponent_and_player_faint() -> None:
    opponent_faint = replace(
        _raw(),
        battle_state=0,
        enemy_hp=0,
        active_party_pp=(34, 30, 20, 25),
    )
    won = project_red_battle_turn_outcome(_execution(opponent_faint))
    assert won.opponent_fainted
    assert not won.player_fainted
    assert won.opponent_damage_fraction == 1.0

    player_faint = replace(
        _raw(),
        battle_state=0,
        enemy_hp=45,
        active_party_hp=0,
        active_party_pp=(34, 30, 20, 25),
    )
    lost = project_red_battle_turn_outcome(_execution(player_faint))
    assert lost.player_fainted
    assert not lost.opponent_fainted
    assert lost.utility < won.utility

    double_ko = replace(
        _raw(),
        battle_state=0,
        enemy_hp=0,
        active_party_hp=0,
        active_party_pp=(34, 30, 20, 25),
    )
    tied_faints = project_red_battle_turn_outcome(_execution(double_ko))
    assert tied_faints.player_fainted
    assert tied_faints.opponent_fainted


def test_red_suppressed_move_retains_the_selected_turn_outcome() -> None:
    suppressed = replace(_raw(), enemy_hp=60, active_party_hp=110)

    outcome = project_red_battle_turn_outcome(
        _execution(suppressed, move_executed=False)
    )

    assert not outcome.move_executed
    assert outcome.learner_update_eligible
    assert outcome.utility == -10 / 150


def test_red_suppressed_move_retains_opponent_terminal_value() -> None:
    self_destructed = replace(
        _raw(),
        battle_state=0,
        enemy_hp=0,
        active_party_hp=80,
    )

    outcome = project_red_battle_turn_outcome(
        _execution(self_destructed, move_executed=False)
    )

    assert not outcome.move_executed
    assert outcome.opponent_fainted
    assert outcome.battle_exited
    assert outcome.utility > 0


def test_red_terminal_exit_with_living_opponent_is_not_scored_as_a_faint() -> None:
    fled = replace(
        _raw(),
        battle_state=0,
        enemy_species_id=None,
        enemy_hp=45,
        active_party_index=None,
        active_party_pp=(34, 30, 20, 25),
    )

    outcome = project_red_battle_turn_outcome(_execution(fled))

    assert outcome.move_executed
    assert not outcome.opponent_fainted
    assert not outcome.player_fainted
    assert outcome.opponent_damage_fraction == 15 / 60


def test_red_move_execution_does_not_depend_on_replacement_party_pp() -> None:
    replacement_unchanged = replace(
        _raw(),
        battle_state=0,
        enemy_hp=0,
        active_party_index=1,
        active_party_hp=90,
        active_party_pp=(35, 30, 20, 25),
    )
    replacement_coincidental = replace(
        replacement_unchanged,
        active_party_pp=(34, 30, 20, 25),
    )

    executed = project_red_battle_turn_outcome(
        _execution(replacement_unchanged, move_executed=True)
    )
    suppressed = project_red_battle_turn_outcome(
        _execution(replacement_coincidental, move_executed=False)
    )

    assert executed.move_executed
    assert not suppressed.move_executed
