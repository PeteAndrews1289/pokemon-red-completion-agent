from copy import deepcopy

import pytest
from audit_red_selector_value_conflicts import paired_summary, reward_components
from test_red_status_closed_loop_returns import episode

from pokemon_red_completion.red_status_win_conditioned_returns import win_conditioned_return


@pytest.mark.parametrize("stop", ["battle_won", "party_defeated", "player_turn_budget"])
@pytest.mark.parametrize("move", [33, 79, 105, 156])
def test_components_reproduce_reward_without_changing_episode(stop, move):
    ep = episode(move, "paralysis", "paralysis")
    ep["stop_reason"] = stop
    original = deepcopy(ep)
    result = reward_components(ep)
    assert sum(result["terms"].values()) == pytest.approx(win_conditioned_return(ep))
    assert result["total"] == win_conditioned_return(ep)
    if stop != "battle_won":
        assert all(result["terms"][k] == 0 for k in
                   ("decision_cost", "pp_cost", "unchanged_status_cost"))
    assert original == ep


def test_positive_mean_does_not_hide_sign_changing_timing_results():
    report = paired_summary([-10., -9., 11.], [10., -10., -10.])
    assert report["mean_status_gap"] > 0
    assert report["preference_changes_sign"]
    assert report["minimum_gap"] == -20
    assert not report["statistical_confidence_claim"]
    assert not report["fit_label_created"]


def test_ties_and_small_damage_advantage_are_not_robust_negative_labels():
    report = paired_summary([1., .98, 1.], [1., 1., 1.])
    assert report["tied_samples"] == 2
    assert not report["damage_better_by_original_margin_every_sample"]
    assert not report["preference_changes_sign"]


def test_all_sample_negative_margin_is_descriptive_not_a_new_fit_label():
    report = paired_summary([0., .1, .2], [1., 1., 1.])
    assert report["damage_better_by_original_margin_every_sample"]
    assert not report["fit_label_created"]


@pytest.mark.parametrize("left,right", [([], []), ([1], []), ([float("nan")], [0]),
                                       ([0], [float("inf")]), ([True], [0])])
def test_invalid_pairs_rejected(left, right):
    with pytest.raises(ValueError):
        paired_summary(left, right)
