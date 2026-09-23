from copy import deepcopy

import numpy as np
import pytest
from probe_red_status_effect_observation import (
    balanced_weights,
    objective,
    probe,
)

from pokemon_red_completion.red_balanced_status_features import COMPACT_STATUS_NAMES


def rows():
    return [{"root": root, "capture_id": f"{root}-{label}", "offset": timing,
             "features": [float(label), *([0.] * (len(COMPACT_STATUS_NAMES) - 1))],
             "evidence": {"kind": "observed", "family": "sleep", "reason": "test",
                          "net_change": label}}
            for root in ("a", "b", "c", "d") for label in (0, 1) for timing in (0, 11, 12)]


def test_weights_balance_roots_contexts_and_timings():
    data = rows() + [{**rows()[0], "capture_id": "extra"}]
    weights = balanced_weights(data)
    assert weights.sum() == pytest.approx(1.)
    for root in "abcd":
        assert weights[[r["root"] == root for r in data]].sum() == pytest.approx(.25)
    for context in ("a-0", "a-1", "extra"):
        assert weights[[r["capture_id"] == context for r in data]].sum() == pytest.approx(1/12)


def test_gradient_matches_finite_difference_and_intercept_is_unpenalized():
    rng = np.random.default_rng(7)
    x = np.column_stack((np.ones(10), rng.normal(size=(10, 3))))
    y = np.arange(10) % 2
    w = np.ones(10) / 10
    theta = rng.normal(size=4)
    _, analytic = objective(theta, x, y, w)
    epsilon = 1e-6
    for i in range(4):
        delta = np.eye(4)[i] * epsilon
        numerical = (objective(theta+delta, x, y, w)[0] -
                     objective(theta-delta, x, y, w)[0]) / (2*epsilon)
        assert analytic[i] == pytest.approx(numerical, abs=1e-8)


def test_whole_root_split_never_fits_held_labels_and_cannot_promote():
    data = rows()
    original = deepcopy(data)
    result = probe(data)
    assert data == original
    assert result["diagnostic_pass"] and result["fits"] == 1
    assert result["held_train_root"] == "d" and result["train_roots"] == ["a", "b", "c"]
    assert result["actor_promotions"] == 0
    for row in data:
        if row["root"] == "d":
            row["evidence"]["net_change"] = 1 - row["evidence"]["net_change"]
    reversed_result = probe(data)
    assert reversed_result["diagnostic_weights"] == result["diagnostic_weights"]
    assert not reversed_result["diagnostic_pass"]


def test_missing_classes_do_not_fit_or_impute_unknown():
    data = rows()
    for row in data:
        if row["root"] == "d" and row["evidence"]["net_change"] == 1:
            row["evidence"].update(kind="unknown", net_change=None)
    result = probe(data)
    assert result["fits"] == 0 and result["stop"] == "insufficient_observed_classes"
    assert result["coverage"]["sleep:unknown"] == 3


def test_duplicates_cross_root_contexts_and_nonfinite_features_fail():
    data = rows()
    with pytest.raises(ValueError, match="duplicate"):
        probe([*data, data[0]])
    data[0]["capture_id"] = "d-0"
    with pytest.raises(ValueError, match="crosses roots"):
        probe(data)
    data = rows()
    data[0]["features"][0] = float("nan")
    with pytest.raises(ValueError, match="invalid observable"):
        probe(data)
