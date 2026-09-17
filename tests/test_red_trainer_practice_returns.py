from __future__ import annotations

from copy import deepcopy

from pokemon_red_completion.red_trainer_practice_returns import (
    score_trainer_practice_episode,
    tied_best_indices,
)


def _episode(kind: str, *, party_hp_after: int, enemy_hp_after: int = 40):
    before = {
        "party_hp": [50, 50],
        "party_max_hp": [60, 60],
        "party_pp": [[10, 0, 0, 0], [10, 0, 0, 0]],
    }
    after = deepcopy(before)
    after["party_hp"][1] = party_hp_after
    return {
        "stop_reason": "player_turn_budget",
        "frames_executed": 500,
        "player_turn_count": 1,
        "metrics": {
            "opponent_faints": 0,
            "party_faints": 0,
            "party_pp_spent": 1 if kind == "attack" else 0,
        },
        "decisions": [
            {
                "kind": kind,
                "state_before": before,
                "state_after": after,
                "opponent_hp_before": 40,
                "opponent_hp_after": enemy_hp_after,
                "opponent_faints": 0,
                "observation": {"features": {"battle": {"opponent_max_hp": 50}}},
            }
        ],
    }


def test_common_return_counts_losing_switch_damage_even_without_attack():
    safe = score_trainer_practice_episode(_episode("voluntary_switch", party_hp_after=50))
    harmful = score_trainer_practice_episode(_episode("voluntary_switch", party_hp_after=19))
    assert safe.value > harmful.value
    assert harmful.party_damage_fraction == round(31 / 120, 9)
    assert tied_best_indices((safe.value, harmful.value)) == (0,)


def test_attack_damage_pp_and_terminal_are_explicit():
    attack = score_trainer_practice_episode(
        _episode("attack", party_hp_after=50, enemy_hp_after=20)
    )
    assert attack.opponent_damage_fraction == 0.4
    assert attack.pp_spent_fraction == 0.05
    assert attack.frames_executed == 500
    win = _episode("attack", party_hp_after=50, enemy_hp_after=0)
    win["stop_reason"] = "battle_won"
    win["metrics"]["opponent_faints"] = 1
    win["decisions"][0]["opponent_faints"] = 1
    assert score_trainer_practice_episode(win).value > attack.value


def test_replacement_hp_is_not_subtracted_from_defeated_opponent():
    episode = _episode("attack", party_hp_after=50, enemy_hp_after=10)
    episode["metrics"]["opponent_faints"] = 1
    episode["decisions"][0]["opponent_faints"] = 1
    assert score_trainer_practice_episode(episode).opponent_damage_fraction == 0.8


def test_selected_turn_damage_survives_living_opponent_switch():
    episode = _episode("attack", party_hp_after=50, enemy_hp_after=83)
    decision = episode["decisions"][0]
    decision["observation"]["features"]["battle"]["opponent_max_hp"] = 83
    decision["opponent_hp_before"] = 83
    decision["state_before"]["opponent_party_position"] = 0
    decision["state_after"]["opponent_party_position"] = 1
    decision["outcome"] = {"opponent_damage_fraction": 52 / 83}
    decision["referee_opponent_roster_hp_before"] = [83, 83]
    decision["referee_opponent_roster_hp_after"] = [31, 83]
    assert score_trainer_practice_episode(episode).opponent_damage_fraction == round(52 / 83, 9)


def test_roster_tracks_old_foe_when_switch_decision_changes_active_position():
    episode = _episode("voluntary_switch", party_hp_after=50, enemy_hp_after=83)
    decision = episode["decisions"][0]
    decision["observation"]["features"]["battle"]["opponent_max_hp"] = 83
    decision["opponent_hp_before"] = 83
    decision["state_before"]["opponent_party_position"] = 0
    decision["state_after"]["opponent_party_position"] = 1
    decision["referee_opponent_roster_hp_before"] = [83, 83]
    decision["referee_opponent_roster_hp_after"] = [31, 83]
    assert score_trainer_practice_episode(episode).opponent_damage_fraction == round(52 / 83, 9)


def test_four_opponent_battle_conserves_four_hp_bars_across_switches() -> None:
    episode = _episode("attack", party_hp_after=50, enemy_hp_after=100)
    episode["stop_reason"] = "battle_won"
    episode["player_turn_count"] = 5
    episode["metrics"]["opponent_faints"] = 4
    sequence = (
        (0, 1, 100, 100, 0.5, 0),
        (1, 2, 100, 100, 1.0, 1),
        (2, 3, 100, 100, 1.0, 1),
        (3, 0, 100, 50, 1.0, 1),
        (0, 0, 50, 0, 0.5, 1),
    )
    decisions = []
    for before_slot, after_slot, before_hp, after_hp, damage, fainted in sequence:
        decision = deepcopy(episode["decisions"][0])
        decision["observation"]["features"]["battle"]["opponent_max_hp"] = 100
        decision["state_before"]["opponent_party_position"] = before_slot
        decision["state_after"]["opponent_party_position"] = after_slot
        decision["opponent_hp_before"] = before_hp
        decision["opponent_hp_after"] = after_hp
        decision["outcome"] = {"opponent_damage_fraction": damage}
        decision["opponent_faints"] = fainted
        decisions.append(decision)
    episode["decisions"] = decisions

    result = score_trainer_practice_episode(episode)

    assert result.opponent_faints == 4
    assert result.opponent_damage_fraction == 4.0


def test_tie_rule_preserves_near_equal_outcomes():
    assert tied_best_indices((1.0, 0.99, 0.9)) == (0, 1)
