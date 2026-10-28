from copy import deepcopy

import pytest
from test_red_status_retention_fit import inputs

from pokemon_red_completion.red_balanced_status_features import BALANCED_STATUS_NAMES
from pokemon_red_completion.red_status_execution_learning import eligible_target, split_targets
from pokemon_red_completion.red_status_retention_fit import fit_retaining_negatives


def test_sleep_exclusion_is_predecision_only_and_does_not_modify_targets():
    _, _, awake = inputs()
    sleeping = deepcopy(awake)
    sleeping["vectors"][1][BALANCED_STATUS_NAMES.index("choice.player_asleep")] = 1.
    original = deepcopy(sleeping)
    good, report = split_targets([awake, sleeping])
    assert good == [awake] and sleeping == original
    assert report["eligible_count"] == 1
    assert report["excluded"][0]["reason"] == "predecision_sleep"
    awake["move_executed"] = False
    assert eligible_target(awake)  # No retrospective success-only filtering.
    awake["role"] = "holdout"
    with pytest.raises(ValueError, match="evaluation"):
        eligible_target(awake)


def test_regularized_fit_retains_negative_and_reports_parameter_distance():
    frozen, initial, target = inputs()
    candidate, report = fit_retaining_negatives(
        [[target]], initial, frozen, solver="slsqp", anchor_l2=.001)
    assert report["solver_result"]["success"]
    assert report["solver_result"]["anchor_l2"] == .001
    assert report["solver_result"]["parameter_distance"] < 20
    assert candidate.move.predict_index(target["vectors"]) == 0
    assert report["retention_regressions"] == 0


@pytest.mark.parametrize("coefficient", [-1., float("inf"), float("nan")])
def test_bad_regularization_is_rejected(coefficient):
    frozen, initial, target = inputs()
    with pytest.raises(ValueError, match="regularization"):
        fit_retaining_negatives([[target]], initial, frozen, solver="slsqp",
                               anchor_l2=coefficient)
