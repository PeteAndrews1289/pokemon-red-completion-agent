from copy import deepcopy

import numpy as np
import pytest
from audit_red_randomized_collection import validate_target
from red_randomized_value_learning import additive_basis, extend_randomized
from run_red_randomized_training_collection import SCHEMA
from scipy.special import expit
from test_red_outcome_value_learning import setup

from pokemon_red_completion.red_balanced_status_features import BALANCED_STATUS_NAMES as N
from pokemon_red_completion.red_balanced_status_features import COMPACT_STATUS_NAMES


def inputs():
    old, actor, targets, groups, initial = setup()
    target = targets[0]
    target.update(schema=SCHEMA, rng_seeds=list(range(32)), teacher_continuation="K_damage_only",
                  continuation_sha256="c"*64)
    target["rng_returns"] = {str(s): [target["returns"][i]]*32
                              for i, s in enumerate(target["slots"])}
    gap = target["returns"][1]-target["returns"][0]
    target.update(first_half_gap=gap, second_half_gap=gap, gap_standard_error_descriptive=0.)
    return old, actor, targets, groups, initial


def test_rng_extension_preserves_old_targets_constraints_and_gradients():
    old, actor, targets, _, _ = inputs()
    original = deepcopy(targets)
    p, labels = extend_randomized(old, actor, targets, seeds=list(range(32)),
                                 continuation_sha="c"*64)
    assert targets == original
    assert np.array_equal(p.constraints, old.constraints)
    assert np.array_equal(p.minimum, old.minimum)
    assert p.protected == old.protected
    assert np.array_equal(p.desired[:-1], old.desired)
    assert p.weights[:-1] == pytest.approx(.25*old.weights)
    target = targets[0]
    status = next(i for i, v in enumerate(target["vectors"]) if v[N.index("choice.status")])
    gap = target["returns"][status]-target["returns"][1-status]
    assert p.desired[-1] == pytest.approx(expit(gap-.05))
    assert labels[0]["status_gap"] == gap
    theta, eps = p.anchor+.1, 1e-6
    numerical = [(p.objective(theta+eps*e)[0]-p.objective(theta-eps*e)[0])/(2*eps)
                 for e in np.eye(len(theta))]
    assert p.objective(theta)[1] == pytest.approx(numerical, abs=1e-8)


@pytest.mark.parametrize("mutation", ["partition", "root", "continuation", "mean", "seed",
                                    "samples", "nonfinite", "split", "uncertainty", "schema"])
def test_invalid_rng_targets_fail_closed(mutation):
    _, actor, targets, _, _ = inputs()
    t = targets[0]
    if mutation == "partition":
        t["role"] = "holdout"
    elif mutation == "root":
        t["root"] = "evaluation-root"
    elif mutation == "continuation":
        t["teacher_continuation"] = "status_actor"
    elif mutation == "mean":
        t["returns"][0] += 1
    elif mutation == "seed":
        t["rng_seeds"][0] = 300
    elif mutation == "samples":
        t["rng_returns"][str(t["slots"][0])].pop()
    elif mutation == "nonfinite":
        t["rng_returns"][str(t["slots"][0])][0] = float("nan")
    elif mutation == "split":
        t["first_half_gap"] += .1
    elif mutation == "uncertainty":
        t["gap_standard_error_descriptive"] += .1
    else:
        t["schema"] = "timing-v1"
    with pytest.raises(ValueError):
        validate_target(t, actor.train_root_ids, list(range(32)), "c"*64)


def test_uncertain_same_mean_has_less_positive_status_target():
    old, actor, targets, _, _ = inputs()
    _, steady = extend_randomized(old, actor, targets, seeds=list(range(32)),
                                 continuation_sha="c"*64)
    t = targets[0]
    status = next(i for i, v in enumerate(t["vectors"]) if v[N.index("choice.status")])
    t["rng_returns"][str(t["slots"][status])] = [t["returns"][status]+v for v in [-5, 5]*16]
    t["gap_standard_error_descriptive"] = np.std([-5, 5]*16, ddof=1)/32**.5
    _, uncertain = extend_randomized(old, actor, targets, seeds=list(range(32)),
                                      continuation_sha="c"*64)
    assert uncertain[0]["status_gap"] == steady[0]["status_gap"]
    assert uncertain[0]["conservative_soft_target"] < steady[0]["conservative_soft_target"]


def test_duplicate_or_empty_rng_targets_rejected():
    old, actor, targets, _, _ = inputs()
    for inventory in ([], targets*2):
        with pytest.raises(ValueError):
            extend_randomized(old, actor, inventory, seeds=list(range(32)), continuation_sha="c"*64)


def test_additive_basis_has_fixed_semantic_channels_and_feasible_constant_start():
    from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
    _, actor, targets, _, _ = inputs()
    basis = additive_basis(actor)
    width = len(COMPACT_STATUS_NAMES)
    assert width == 28
    assert np.array_equal(basis.move.weights1[-width:], np.eye(width))
    assert not np.count_nonzero(basis.move.weights1[:-width])
    assert not np.count_nonzero(basis.move.bias1)
    assert basis.move.effect_weights == actor.move.effect_weights
    assert basis.control.to_dict() == actor.control.to_dict()
    assert basis.switch.to_dict() == actor.switch.to_dict()
    assert basis.damage_reference.to_dict() == actor.damage_reference.to_dict()
    t = targets[0]
    scores = basis.move.scores(t["vectors"])
    status = next(i for i, v in enumerate(t["vectors"]) if v[N.index("choice.status")])
    assert scores[status]-scores[1-status] == pytest.approx(-1.)
    reopened = TrainerPracticeThreeHeadModel.from_dict(basis.to_dict())
    assert np.array_equal(scores, reopened.move.scores(t["vectors"]))


def test_additive_outputs_can_learn_status_without_changing_the_basis():
    from dataclasses import replace

    from red_outcome_value_learning import fit_once
    from test_red_effect_selector import effect

    from pokemon_red_completion.red_effect_selector_learning import prepare_combination
    _, actor, targets, groups, initial = inputs()
    basis = additive_basis(actor)
    # Construct the original constraints in the new fixed representation.
    from test_red_status_readout_learning import problem_inputs
    frozen, _, originals = problem_inputs()
    old = prepare_combination(groups, initial, frozen, basis, originals, effect())
    old = replace(old, anchor=np.append(basis.move.weights2, basis.move.effect_readout))
    problem, _ = extend_randomized(old, basis, targets, seeds=list(range(32)),
                                   continuation_sha="c"*64)
    candidate, report = fit_once(problem, basis, targets, groups, initial, reference_actor=basis)
    assert report["passed"] and report["retention_regressions"] == 0
    assert np.array_equal(candidate.move.weights1, basis.move.weights1)
    status = next(i for i, v in enumerate(targets[0]["vectors"]) if v[N.index("choice.status")])
    assert candidate.move.predict_index(targets[0]["vectors"]) == status
