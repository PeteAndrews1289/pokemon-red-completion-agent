from copy import deepcopy

import pytest
from test_red_status_battle_features import status_observation

from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref
from pokemon_red_completion.red_status_closed_loop_returns import (
    closed_loop_return,
    unchanged_status_turns,
)


def episode(move=79, before=None, after=None, *, executed=True):
    obs = status_observation()
    obs["features"]["battle"]["opponent_status"] = before
    obs["features"]["battle"]["opponent_max_hp"] = 100
    obs["features"]["party"]["lead"]["moves"][1]["move_ref"] = pokemon_red_move_ref(move)
    final = deepcopy(obs)
    final["features"]["battle"]["opponent_status"] = after
    resource = {"party_hp": [50], "party_max_hp": [100]}
    return {"stop_reason": "party_defeated", "final_observation": final,
            "metrics": {"party_pp_spent": 1}, "decisions": [
                {"kind": "attack", "move_slot": 3, "observation": obs,
                 "state_before": resource, "state_after": resource,
                 "outcome": {"move_executed": executed},
                 "opponent_hp_before": 100, "opponent_hp_after": 100}]}


@pytest.mark.parametrize("move,status", [(79, "sleep"), (86, "paralysis"), (77, "poison")])
def test_measured_status_transition_and_no_change_have_different_targets(move, status):
    succeeds = episode(move, None, status)
    fails = episode(move, "paralysis", "paralysis")
    assert unchanged_status_turns(succeeds) == []
    assert unchanged_status_turns(fails) == [1]
    assert closed_loop_return(succeeds) - closed_loop_return(fails) == pytest.approx(.5)


def test_confusion_and_accuracy_changes_are_observed_not_assumed():
    e = episode(109)
    assert unchanged_status_turns(e) == [1]
    e["decisions"][0]["observation"]["features"]["battle"]["status_context"][
        "opponent_confused"] = False
    assert unchanged_status_turns(e) == []
    e = episode(28)
    assert unchanged_status_turns(e) == [1]
    e["final_observation"]["features"]["battle"]["status_context"]["opponent_stages"][4] = -1
    assert unchanged_status_turns(e) == []


@pytest.mark.parametrize("move", [105, 156, 50, 33])
def test_does_not_fabricate_ineffective_healing_disable_or_damage(move):
    assert unchanged_status_turns(episode(move)) == []


def test_suppression_and_unobserved_terminal_effect_are_not_fabricated():
    assert unchanged_status_turns(episode(executed=False)) == []
    e = episode()
    e["final_observation"]["features"]["battle"] = None
    assert unchanged_status_turns(e) == []


def test_repeated_turns_cost_more_and_finite_win_outweighs_quick_loss():
    e = episode(33)
    one = closed_loop_return(e)
    e["decisions"] *= 20
    assert closed_loop_return(e) == pytest.approx(one - 1.9)
    e["stop_reason"] = "battle_won"
    assert closed_loop_return(e) > one
    e["stop_reason"] = "unexpected_error"
    with pytest.raises(ValueError):
        closed_loop_return(e)


def test_pair_gate_rejects_loops_and_does_not_accept_an_attack_only_clone():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from run_red_closed_loop_status import gate

    base = [{"case": "one", "won": True, "decisions": 4, "return": 10., "status_choices": []}]
    good = [{**base[0], "return": 10.5, "status_choices": [{"concerns": []}]}]
    assert gate(good, base)["passed"]
    assert not gate(base, base)["passed"]
    assert not gate([{**good[0], "decisions": 20}], base)["passed"]
    assert not gate([{**good[0], "status_choices": [{"concerns": ["already_confused"]}]}], base)[
        "passed"]


def test_resume_refuses_overwrites_and_incomplete_episode_replays(tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from run_red_closed_loop_status import OFFSETS, play, write

    assert all(0 <= offset <= 12 for offset in OFFSETS)
    record = tmp_path / "retained.json"
    write(record, {"won": False})
    write(record, {"won": False})
    with pytest.raises(ValueError, match="refuse overwrite"):
        write(record, {"won": True})
    with pytest.raises(ValueError, match="cannot replay"):
        play(None, None, None, tmp_path, None)


def test_cost_sensitive_selector_preserves_objective_and_frozen_heads():
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import patch

    import numpy as np

    from pokemon_red_completion.red_balanced_status_features import (
        BALANCED_STATUS_NAMES,
        BALANCED_STATUS_SCHEMA,
        COMPACT_STATUS_NAMES,
    )
    from pokemon_red_completion.red_status_battle_features import STATUS_MOVE_NAMES
    from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import run_red_balanced_status_curriculum as balanced

    width = len(BALANCED_STATUS_NAMES)
    head = TrainerHeadModel(BALANCED_STATUS_SCHEMA, BALANCED_STATUS_NAMES,
                            np.zeros((width, 16)), np.zeros(16), np.ones(16), 1)
    frozen = SimpleNamespace(move=object(), train_capture_ids=("original",))
    initial = SimpleNamespace(move=head)
    damage = [0.] * width
    status = [0.] * width
    status[STATUS_MOVE_NAMES.index("move.category.status")] = 1.
    status[len(STATUS_MOVE_NAMES)] = 1.
    targets = [{"role": "train", "capture_id": "new", "vectors": [damage, status],
                "returns": [10., -10.]}]
    with patch.object(balanced, "replace", side_effect=lambda base, **kw: SimpleNamespace(**kw)):
        candidate, _ = balanced.fit_selector(targets, frozen, epochs=2, initial=initial,
                                              training_objective="expected_regret")
    assert candidate.move.training_objective == "expected_regret"
    assert candidate.damage_reference is frozen.move
    assert np.count_nonzero(candidate.move.weights1[:len(STATUS_MOVE_NAMES)]) == 0
    assert candidate.move.feature_names[-len(COMPACT_STATUS_NAMES):] == COMPACT_STATUS_NAMES
    assert candidate.move.predict_index((tuple(damage), tuple(status))) == 0
    with pytest.raises(ValueError, match="withheld"):
        balanced.fit_selector([{**targets[0], "role": "holdout"}], frozen, epochs=1)
