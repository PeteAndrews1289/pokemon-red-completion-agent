"""Real scaling invariants; synthetic fixtures are never TRAIN evidence."""

from dataclasses import replace

import numpy as np
import pytest
from test_party_development_outcome_learning import _initialized_model
from test_venue_workload_scaling import example

from pokemon_red_completion.party_development_outcome_learning import (
    PartyDevelopmentOutcomeLearningError,
    recondition_party_development_workload,
    upgrade_party_development_model_for_workload,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def active_parent():
    model = upgrade_party_development_model_for_workload(_initialized_model())
    rng = np.random.default_rng(53)
    weights = model.weights1.copy()
    weights[-12:] = rng.normal(0, 0.3, weights[-12:].shape)
    means = model.feature_mean.copy()
    means[-12:] = rng.normal(0, 0.1, 12)
    return replace(model, weights1=weights, feature_mean=means)


def test_reconditioning_preserves_active_function_for_observed_and_unseen_inputs():
    parent = active_parent()
    menu, row = example()
    before = parent.to_dict()
    child, report = recondition_party_development_workload(parent, (row,))
    rng = np.random.default_rng(71)
    values = np.concatenate(
        (
            np.zeros((1, len(parent.feature_names))),
            rng.normal(size=(100, len(parent.feature_names))),
        )
    )
    old = (
        np.tanh(
            ((values - parent.feature_mean) / parent.feature_scale) @ parent.weights1 + parent.bias1
        )
        @ parent.weights2
    )
    new = (
        np.tanh(
            ((values - child.feature_mean) / child.feature_scale) @ child.weights1 + child.bias1
        )
        @ child.weights2
    )
    np.testing.assert_allclose(old, new, atol=1e-13, rtol=1e-13)
    np.testing.assert_allclose(parent.scores(menu), child.scores(menu), atol=1e-13, rtol=1e-13)
    assert parent.predict(menu) == child.predict(menu)
    assert before == parent.to_dict()
    assert child.outcome_training_root_lineage_ids == parent.outcome_training_root_lineage_ids
    assert child.outcome_training_examples == parent.outcome_training_examples
    assert report["optimizer_calls"] == 0 and report["ancestry_consumed"] is False


@pytest.mark.parametrize("fault", ["development", "same_yield", "consumed_root", "consumed_state"])
def test_reconditioning_cannot_use_dev_or_consumed_evidence(fault):
    parent = active_parent()
    _, row = example(
        partition=ScenarioPartition.DEVELOPMENT
        if fault == "development"
        else ScenarioPartition.TRAIN,
        same=fault == "same_yield",
    )
    if fault == "consumed_root":
        parent = replace(
            parent,
            outcome_training_examples=1,
            outcome_training_root_lineage_ids=(row.root_lineage_id,),
            outcome_training_state_sha256=("f" * 64,),
        )
    if fault == "consumed_state":
        parent = replace(
            parent,
            outcome_training_examples=1,
            outcome_training_root_lineage_ids=("different-root",),
            outcome_training_state_sha256=(row.initial_state_sha256,),
        )
    with pytest.raises(PartyDevelopmentOutcomeLearningError):
        recondition_party_development_workload(parent, (row,))
