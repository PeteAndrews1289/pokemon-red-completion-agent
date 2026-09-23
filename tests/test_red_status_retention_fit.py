from dataclasses import replace

import numpy as np
import pytest
from test_red_trainer_practice_fit import _target

from pokemon_red_completion.red_balanced_status_features import (
    BALANCED_STATUS_NAMES,
    BALANCED_STATUS_SCHEMA,
)
from pokemon_red_completion.red_status_battle_features import STATUS_MOVE_NAMES
from pokemon_red_completion.red_status_closed_loop_returns import RETURN_SCHEMA
from pokemon_red_completion.red_status_retention_fit import fit_retaining_negatives
from pokemon_red_completion.red_trainer_practice_fit import (
    TrainerPracticeThreeHeadModel,
    fit_trainer_practice_three_heads,
)
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel


def inputs():
    frozen = fit_trainer_practice_three_heads([_target()], seed=3, epochs=1,
                                             require_corpus_floor=False)
    w = np.zeros((len(BALANCED_STATUS_NAMES), 2))
    w[BALANCED_STATUS_NAMES.index("choice.status")] = -.2
    head = TrainerHeadModel(BALANCED_STATUS_SCHEMA, BALANCED_STATUS_NAMES,
                            w, np.zeros(2), np.ones(2), 3)
    initial = replace(frozen, move=head, damage_reference=frozen.move)
    damage = [0.] * len(BALANCED_STATUS_NAMES)
    status = damage.copy()
    status[BALANCED_STATUS_NAMES.index("choice.status")] = 1.
    row = {"role": "train", "root": "unit-root", "capture_id": "new-capture",
           "return_schema": RETURN_SCHEMA, "slots": [1, 2], "vectors": [damage, status],
           "returns": [0., -1.], "timing_returns": {"1": [0., 0., 0.], "2": [-1., -1., -1.]}}
    return frozen, initial, row


def test_retention_rejects_optimizer_updates_that_forget_measured_negative():
    frozen, initial, negative = inputs()
    positive = {**negative, "returns": [0., 10.],
                "timing_returns": {"1": [0., 0., 0.], "2": [10., 10., 10.]}}
    candidate, report = fit_retaining_negatives(
        [[negative], [positive]], initial, frozen, epochs=500)
    assert report["protected_preferences"] == 1
    assert report["retention_regressions"] == 0
    assert report["backtracked_steps"] > 0
    assert candidate.move.predict_index(negative["vectors"]) == 0
    assert candidate.control.to_dict() == frozen.control.to_dict()
    assert candidate.switch.to_dict() == frozen.switch.to_dict()
    assert candidate.damage_reference.to_dict() == frozen.move.to_dict()
    assert np.count_nonzero(candidate.move.weights1[:len(STATUS_MOVE_NAMES)]) == 0
    restored = TrainerPracticeThreeHeadModel.from_dict(candidate.to_dict())
    assert restored.to_dict() == candidate.to_dict()


def test_uncertain_negative_is_not_silently_treated_as_robust():
    frozen, initial, row = inputs()
    row["timing_returns"]["2"] = [-2., -2., 1.]
    _, report = fit_retaining_negatives([[row]], initial, frozen, epochs=1)
    assert report["protected_preferences"] == 0


def test_constrained_solver_can_learn_new_choice_without_forgetting_negative():
    frozen, initial, negative = inputs()
    vectors = [list(v) for v in negative["vectors"]]
    vectors[1][BALANCED_STATUS_NAMES.index("choice.player_hp")] = 1.
    positive = {**negative, "vectors": vectors, "returns": [0., 2.],
                "timing_returns": {"1": [0., 0., 0.], "2": [2., 2., 2.]}}
    candidate, report = fit_retaining_negatives(
        [[negative], [positive]], initial, frozen, solver="slsqp")
    assert report["solver_result"]["success"]
    assert report["solver_result"]["minimum_constraint_slack"] >= -1e-8
    assert candidate.move.predict_index(negative["vectors"]) == 0
    assert candidate.move.predict_index(positive["vectors"]) == 1
    continued, diagnostics = fit_retaining_negatives(
        [[negative], [positive]], initial, frozen, solver="slsqp", continuation=candidate)
    assert diagnostics["protected_preferences"] == report["protected_preferences"] == 1
    assert diagnostics["retention_regressions"] == 0
    assert continued.move.predict_index(positive["vectors"]) == 1


@pytest.mark.parametrize("changes", [{"role": "holdout"}, {"root": "other-root"},
                                     {"return_schema": "different"}])
def test_fit_rejects_unqualified_training_inputs(changes):
    frozen, initial, row = inputs()
    with pytest.raises(ValueError, match="TRAIN"):
        fit_retaining_negatives([[{**row, **changes}]], initial, frozen, epochs=1)


def test_read_only_audit_detects_lost_preference_and_recomputes_regret():
    from audit_red_status_retention_fit import metrics, preference_check

    _, initial, row = inputs()
    bad = replace(initial, move=replace(initial.move, weights2=-initial.move.weights2))
    check = preference_check([row], initial, bad)
    assert check["protected_preferences"] == 1
    assert check["retention_regressions"] == 1
    assert check["minimum_constraint_slack"] < 0
    assert metrics([row], bad) == {
        "contexts": 1, "regret": 1., "errors": 1, "high_cost_errors": 1}


def test_read_only_audit_does_not_protect_uncertain_timing():
    from audit_red_status_retention_fit import preference_check

    _, initial, row = inputs()
    row["timing_returns"]["2"] = [-2., -2., 1.]
    assert preference_check([row], initial, initial) == {
        "protected_preferences": 0, "retention_regressions": 0, "minimum_constraint_slack": 0.}
