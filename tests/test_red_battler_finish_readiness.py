from copy import deepcopy

import pytest
from audit_red_timing_selector_preparation import readiness
from test_red_timing_selector_preparation import qualification


def inputs():
    later = qualification()
    later.update(observed_awake=8, brier=.04)
    later["rows"].extend(deepcopy(later["rows"][:3]))
    fit = {"solver_success": True, "protected_preferences": 182, "minimum_slack": 0.,
           "retention_regressions": 0, "groups": [
               {"candidate": {"regret": c}, "initial": {"regret": i}}
               for c, i in ((.1, .2), (.1, .2), (.1, .2))]}
    screen = {"wins": {"candidate": 33, "frozen": 32},
              "decisions": {"candidate": 190, "frozen": 154},
              "concerning_selections": 0, "improved_won_status_cases": 1}
    return later, fit, screen


def test_even_passing_training_screen_is_not_live_battler_completion():
    report = readiness(*inputs())
    assert report["ready_to_prepare_reserved_comparison"]
    assert report["first_unpassed_gate"] is None
    assert not report["natural_party_qualified"]
    assert not report["live_story_ready"] and not report["full_battler_complete"]


@pytest.mark.parametrize("change", ["count", "cell", "brier", "nonfinite"])
def test_error_score_alone_cannot_admit_missing_effect_support(change):
    later, _, _ = inputs()
    if change == "count":
        later["observed_awake"] = 7
    elif change == "cell":
        later["rows"] = [r for r in later["rows"] if r["family"] != "confusion"]
    elif change == "brier":
        later["brier"] = .126
    else:
        later["brier"] = float("nan")
    report = readiness(later, None, None)
    assert not report["ready_to_prepare_reserved_comparison"]
    assert report["first_unpassed_gate"] == "later_effect_qualification"


@pytest.mark.parametrize("change", ["solver", "preferences", "slack", "regression", "regret"])
def test_fit_failure_cannot_open_screen_or_reserved_comparison(change):
    later, fit, _ = inputs()
    if change == "solver":
        fit["solver_success"] = False
    elif change == "preferences":
        fit["protected_preferences"] = 181
    elif change == "slack":
        fit["minimum_slack"] = -.01
    elif change == "regression":
        fit["retention_regressions"] = 1
    else:
        fit["groups"][1]["candidate"]["regret"] = 1.
    report = readiness(later, fit, None)
    assert report["first_unpassed_gate"] == "retained_selector_fit"
    assert not report["ready_to_prepare_reserved_comparison"]


@pytest.mark.parametrize("change", ["wins", "concerns", "useful", "decisions"])
def test_native_behavior_thresholds_are_not_weakened(change):
    later, fit, screen = inputs()
    if change == "wins":
        screen["wins"]["candidate"] = 31
    elif change == "concerns":
        screen["concerning_selections"] = 1
    elif change == "useful":
        screen["improved_won_status_cases"] = 0
    else:
        screen["decisions"]["candidate"] = 193
    result = readiness(later, fit, screen)
    assert result["first_unpassed_gate"] == "native_train_screen"
    assert not result["ready_to_prepare_reserved_comparison"]


def test_running_downstream_through_failed_prerequisite_is_an_integrity_error():
    later, fit, screen = inputs()
    later["observed_awake"] = 7
    with pytest.raises(ValueError, match="prerequisite"):
        readiness(later, fit, None)
    later["observed_awake"] = 8
    fit["solver_success"] = False
    with pytest.raises(ValueError, match="prerequisite"):
        readiness(later, fit, screen)
