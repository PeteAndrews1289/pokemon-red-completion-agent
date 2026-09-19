from dataclasses import replace

import numpy as np
import pytest
from audit_red_trainer_retention import contrast_audit

from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel
from pokemon_red_completion.red_trainer_retention import (
    batch_loss_gradient,
    bridge_control,
    fit_retained_head,
)


def test_conflicting_identical_observations_have_nonzero_floor():
    vectors = ((1.0, 0.0), (0.0, 1.0))
    groups = {
        "old": {
            "move": [TrainerHeadExample(vectors, (0,), mean_returns=(2.0, 0.0))],
            "control": [],
            "switch": [],
        },
        "new": {
            "move": [TrainerHeadExample(vectors, (1,), mean_returns=(0.0, 8.0))],
            "control": [],
            "switch": [],
        },
    }
    report = contrast_audit(groups)["move"]
    assert report["exact_input_mean_regret_floor"] == pytest.approx(1.0)
    assert report["conflicts"][0]["groups"] == ["old", "new"]
    assert report["scales"]["new"]["max_range"] == 8


def test_distinct_observations_do_not_create_false_conflicts():
    rows = [
        TrainerHeadExample(((1.0,), (0.0,)), (0,), mean_returns=(2.0, 0.0)),
        TrainerHeadExample(((0.0,), (1.0,)), (1,), mean_returns=(0.0, 8.0)),
    ]
    report = contrast_audit({"all": {"move": rows, "control": [], "switch": []}})
    assert report["move"]["exact_input_mean_regret_floor"] == 0
    assert report["move"]["conflicts"] == []


def test_bridge_preserves_scores_with_arbitrary_proposed_features():
    from pokemon_red_completion.red_trainer_practice_features import CONTROL_FEATURE_NAMES_V2
    from pokemon_red_completion.red_trainer_practice_fit import (
        CONTROL_ACTION_FEATURE_NAMES,
        CONTROL_ACTION_SCHEMA_ID,
        control_action_candidates,
    )
    from pokemon_red_completion.red_trainer_proposed_control import PROPOSED_STATE_NAMES

    rng = np.random.default_rng(19)
    head = TrainerHeadModel(
        CONTROL_ACTION_SCHEMA_ID,
        CONTROL_ACTION_FEATURE_NAMES,
        rng.normal(size=(len(CONTROL_ACTION_FEATURE_NAMES), 4)),
        rng.normal(size=4),
        rng.normal(size=4),
        19,
    )
    lifted = bridge_control(head)
    for _ in range(10):
        common = tuple(rng.uniform(-1, 1, len(CONTROL_FEATURE_NAMES_V2)))
        state = (*common, *rng.uniform(-1, 1, len(PROPOSED_STATE_NAMES) - len(common)))
        zeros = (0.0,) * len(state)
        rows = ((1.0, 0.0, *state, *zeros), (0.0, 1.0, *zeros, *state))
        np.testing.assert_allclose(
            lifted.scores(rows), head.scores(control_action_candidates(common)), atol=1e-12
        )


def unit_head():
    return TrainerHeadModel(
        "unit",
        ("x", "y"),
        np.array([[0.3, -0.2], [0.1, 0.2]]),
        np.array([0.0, 0.1]),
        np.array([0.2, -0.3]),
        1,
    )


def test_batched_gradient_matches_finite_difference_with_ragged_choices():
    model = unit_head()
    cases = (
        TrainerHeadExample(((1.0, 0.0), (0.0, 1.0)), (1,), mean_returns=(0.0, 2.0)),
        TrainerHeadExample(
            ((0.0, 0.0), (1.0, 1.0), (-1.0, 1.0)), (0,), mean_returns=(4.0, 1.0, 2.0)
        ),
    )
    _, gradient = batch_loss_gradient(model, cases)
    packed = np.concatenate((model.weights1.ravel(), model.bias1, model.weights2))

    def loss(p):
        return batch_loss_gradient(
            replace(model, weights1=p[:4].reshape(2, 2), bias1=p[4:6], weights2=p[6:]), cases
        )[0]

    numeric = []
    for i in range(len(packed)):
        delta = np.zeros_like(packed)
        delta[i] = 1e-6
        numeric.append((loss(packed + delta) - loss(packed - delta)) / 2e-6)
    np.testing.assert_allclose(gradient, numeric, atol=1e-8)


def test_fit_reduces_terminal_loss_and_never_changes_protected_choice():
    initial = unit_head()
    anchor = TrainerHeadExample(((1.0, 0.0), (0.0, 1.0)), (0,), mean_returns=(2.0, 0.0))
    terminal = TrainerHeadExample(((-1.0, 0.0), (0.0, -1.0)), (0,), mean_returns=(3.0, 0.0))
    fitted, receipt = fit_retained_head(initial, (terminal,), (anchor,), epochs=200)
    assert fitted.predict_index(anchor.candidate_vectors) == initial.predict_index(
        anchor.candidate_vectors
    )
    assert receipt["final_loss"] < receipt["initial_loss"]
    assert receipt["accepted_steps"] > 0
    assert all(
        b["loss"] < a["loss"]
        for a, b in zip(receipt["history"], receipt["history"][1:], strict=False)
    )


def test_direct_conflict_cannot_override_anchor_even_at_large_step():
    initial = unit_head()
    anchor = TrainerHeadExample(((1.0, 0.0), (0.0, 1.0)), (0,), mean_returns=(2.0, 0.0))
    chosen = initial.predict_index(anchor.candidate_vectors)
    terminal = replace(anchor, mean_returns=(0.0, 20.0) if chosen == 0 else (20.0, 0.0))
    fitted, _ = fit_retained_head(initial, (terminal,), (anchor,), epochs=50, learning_rate=100)
    assert fitted.predict_index(anchor.candidate_vectors) == chosen


def test_gates_require_learning_and_do_not_relax_retention():
    from copy import deepcopy

    from run_red_trainer_retention import gates

    before = {
        "original44": {"move": {"model_mean_train_regret": 0.01}},
        "retained52": {
            "move": {"model_mean_train_regret": 0.035},
            "composed_action": {"model_mean_train_regret": 0.098},
        },
        "terminal128": {"composed_action": {"model_mean_train_regret": 1.0}},
        "new80": {"composed_action": {"model_mean_train_regret": 1.2}},
    }
    assert not all(gates(before, before).values())
    after = deepcopy(before)
    after["terminal128"]["composed_action"]["model_mean_train_regret"] = 0.8
    assert all(gates(before, after).values())
    after["retained52"]["move"]["model_mean_train_regret"] = 0.06481
    assert not gates(before, after)["retained52_move"]


def test_cache_rejects_modified_target_bytes(tmp_path):
    import json

    from run_red_trainer_retention import admitted_cache

    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "counts": [52, 48, 80],
                "targets": {"path": str(tmp_path / "targets.json"), "sha256": "wrong"},
            }
        )
    )
    (tmp_path / "targets.json").write_text("[]")
    with pytest.raises(ValueError, match="cache differs"):
        admitted_cache(tmp_path)
