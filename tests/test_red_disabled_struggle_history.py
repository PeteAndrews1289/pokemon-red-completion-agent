"""Native Disable history stays separate from unchanged zero-PP TRAIN admission."""
import pytest
from test_red_post_battle_strategy import project, resumed_struggle_episode

from pokemon_red_completion.post_battle_strategy import BattleResult
from pokemon_red_completion.red_trainer_practice_admission import _valid_forced_struggle


def disabled_episode():
    episode = resumed_struggle_episode()
    row = episode["decisions"][0]
    row["state_before"].update(
        party_pp=[[30, 0, 0, 0]], active_pp=[30, 0, 0, 0],
        active_party_slot=1, active_hp=100, battle_state=2, active_status=0,
        player_disabled_move_slot=1, player_disable_turns=4,
    )
    row["state_after"]["party_pp"] = [[30, 0, 0, 0]]
    row["frames_executed"] = 122
    row["outcome"].update(
        availability_basis="last_usable_move_disabled", encoded_pp_before=[30, 0, 0, 0],
        disabled_move_slot=1, disable_turns=4, learned_choice=False,
        train_admission_authorized=False, move_slot=None, departed_main_menu=True,
        frames_executed=122, cartridge_selection_observed=True, suppression=None,
        selected_move_ref="pokemon.red.gb.us.rev0:move:165", execution_claim="attempt_only",
    )
    return episode


def test_disabled_singleton_history_preserves_native_result_not_train_authority():
    episode = disabled_episode()
    result = project(episode)
    assert result.result is BattleResult.WON and result.pp_spent_fraction == 0
    assert not _valid_forced_struggle(episode["decisions"][0])


@pytest.mark.parametrize("mutation", [
    "missing_basis", "unknown_basis", "no_disabled_pp", "other_pp", "other_encoded_pp_up",
    "slot", "bool_slot", "expired", "bool_turns", "contradict_slot", "contradict_turns",
    "encoded_mismatch", "pp_spent", "wrong_active", "hp", "wild_state", "learned",
    "train", "selection", "move_ref", "departure", "frames", "latency",
])
def test_disabled_history_requires_full_matching_mechanics(mutation):
    episode = disabled_episode()
    row = episode["decisions"][0]
    before, after, outcome = row["state_before"], row["state_after"], row["outcome"]
    if mutation == "missing_basis":
        outcome.pop("availability_basis")
    elif mutation == "unknown_basis":
        outcome["availability_basis"] = "assume_disabled"
    elif mutation == "no_disabled_pp":
        outcome["encoded_pp_before"][0] = 0
    elif mutation == "other_pp":
        outcome["encoded_pp_before"][1] = 1
    elif mutation == "other_encoded_pp_up":
        outcome["encoded_pp_before"][1] = 64
    elif mutation == "slot":
        outcome["disabled_move_slot"] = 0
    elif mutation == "bool_slot":
        outcome["disabled_move_slot"] = True
    elif mutation == "expired":
        outcome["disable_turns"] = 0
    elif mutation == "bool_turns":
        outcome["disable_turns"] = True
    elif mutation == "contradict_slot":
        before["player_disabled_move_slot"] = 2
    elif mutation == "contradict_turns":
        before["player_disable_turns"] = 3
    elif mutation == "encoded_mismatch":
        before["active_pp"] = [29, 0, 0, 0]
    elif mutation == "pp_spent":
        after["party_pp"][0][0] = 29
        episode["metrics"]["party_pp_spent"] = 1
    elif mutation == "wrong_active":
        before["active_party_slot"] = 2
    elif mutation == "hp":
        before["active_hp"] = 99
    elif mutation == "wild_state":
        before["battle_state"] = 1
    elif mutation == "learned":
        outcome["learned_choice"] = True
    elif mutation == "train":
        outcome["train_admission_authorized"] = True
    elif mutation == "selection":
        outcome["cartridge_selection_observed"] = False
    elif mutation == "move_ref":
        outcome["selected_move_ref"] = None
    elif mutation == "departure":
        outcome["departed_main_menu"] = False
    elif mutation == "frames":
        outcome["frames_executed"] = 121
    else:
        row["policy_elapsed_ns"] = True
    with pytest.raises(ValueError, match="mechanical evidence"):
        project(episode)


@pytest.mark.parametrize("suppression,status,trapped", [
    ("sleep", 2, False), ("freeze", 32, False), ("trapping", 0, True),
])
def test_disabled_history_preserves_proved_suppression_not_fresh_selection(
    suppression, status, trapped
):
    episode = disabled_episode()
    row = episode["decisions"][0]
    row["state_before"].update(active_status=status, enemy_using_trapping_move=trapped)
    row["outcome"].update(cartridge_selection_observed=False, selected_move_ref=None,
                          execution_claim="suppressed_before_selection", suppression=suppression)
    assert project(episode).result is BattleResult.WON
    row["state_before"].update(active_status=0, enemy_using_trapping_move=False)
    with pytest.raises(ValueError, match="mechanical evidence"):
        project(episode)
