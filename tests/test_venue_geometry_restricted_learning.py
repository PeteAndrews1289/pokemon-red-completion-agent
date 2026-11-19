"""Synthetic optimizer checks, never real TRAIN records or native evidence."""

from dataclasses import replace

import numpy as np
import pytest
from test_party_development_outcome_learning import _initialized_model
from test_party_development_outcomes import _completion, _trial
from test_party_development_workload import _binding, _project

from pokemon_red_completion.party_development_outcome_learning import (
    PartyDevelopmentOutcomeLearningError,
    adapt_party_development_model_from_outcomes,
    upgrade_party_development_model_for_workload,
)
from pokemon_red_completion.party_development_outcomes import (
    PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE,
    adapt_party_development_outcomes_v2,
)
from pokemon_red_completion.party_development_rank import VenueTrainingWorkload
from pokemon_red_completion.scenario_lab import ScenarioPartition

NAMES = (
    "venue.travel_steps_known",
    "venue.travel_steps",
    "venue.recovery_steps_known",
    "venue.recovery_steps",
)


def example(*, same=False, unknown=False, partition=ScenarioPartition.TRAIN):
    work = (
        VenueTrainingWorkload(0.5, 50, None if unknown else 12, None if unknown else 24),
        VenueTrainingWorkload(
            0.5,
            50,
            None if unknown else (12 if same else 120),
            None if unknown else (24 if same else 240),
        ),
    )
    menu = _project(venues=work)
    cols = [menu.feature_names.index(n) for n in NAMES]
    # Hold all other candidate covariates fixed in this synthetic unit contrast.
    prefix = menu.candidates[0].features
    menu = replace(
        menu,
        candidates=tuple(
            replace(
                c,
                features=tuple(
                    c.features[i] if i in cols else prefix[i] for i in range(len(prefix))
                ),
            )
            for c in menu.candidates
        ),
    )
    binding = _binding(menu, PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE, tag="f", partition=partition)
    complete = _completion(registered=11, evolution_steps=0)
    trials = tuple(
        _trial(
            menu, i, gain=100, frames=frames, completion_after=complete, evolution_completed=True
        )
        for i, frames in enumerate((1000, 2000))
    )
    return menu, adapt_party_development_outcomes_v2(
        menu,
        trials,
        scenario_id=binding.scenario_id,
        root_lineage_id=binding.root_lineage_id,
        initial_state_sha256=binding.initial_state_sha256,
        partition=partition,
        prospective_binding=binding,
        total_task_efficiency=True,
    )


def test_restricted_fit_learns_cost_contrast_and_retains_unknown_geometry_exactly():
    parent = upgrade_party_development_model_for_workload(_initialized_model())
    before = parent.to_dict()
    menu, row = example()
    unknown = _project()
    old_scores = parent.scores(unknown)
    update = adapt_party_development_model_from_outcomes(
        parent, (row,), restrict_route_geometry=True
    )
    assert update.report.loss_after < update.report.loss_before
    assert update.model.predict(menu) in row.best_candidate_indices
    assert parent.to_dict() == before
    cols = [parent.feature_names.index(n) for n in NAMES]
    keep = [i for i in range(len(parent.feature_names)) if i not in cols]
    np.testing.assert_array_equal(update.model.weights1[keep], parent.weights1[keep])
    np.testing.assert_array_equal(update.model.bias1, parent.bias1)
    np.testing.assert_array_equal(update.model.weights2, parent.weights2)
    np.testing.assert_array_equal(update.model.feature_mean, parent.feature_mean)
    assert update.model.scores(unknown).tobytes() == old_scores.tobytes()
    assert update.report.public_dict()["route_geometry_fit"]["labels_used_for_scaling"] is False
    assert update.model.outcome_training_examples == parent.outcome_training_examples + 1
    assert row.root_lineage_id in update.model.outcome_training_root_lineage_ids


@pytest.mark.parametrize(
    "fault", ["development", "unknown", "no_variation", "active_parent", "not_bool"]
)
def test_restricted_geometry_rejects_uninformative_or_ineligible_inputs(fault):
    parent = upgrade_party_development_model_for_workload(_initialized_model())
    _, row = example(
        same=fault == "no_variation",
        unknown=fault == "unknown",
        partition=ScenarioPartition.DEVELOPMENT
        if fault == "development"
        else ScenarioPartition.TRAIN,
    )
    if fault == "active_parent":
        weights = parent.weights1.copy()
        weights[parent.feature_names.index("venue.travel_steps"), 0] = 0.1
        parent = replace(parent, weights1=weights)
    with pytest.raises(PartyDevelopmentOutcomeLearningError):
        adapt_party_development_model_from_outcomes(
            parent, (row,), restrict_route_geometry=1 if fault == "not_bool" else True
        )


def test_default_update_does_not_silently_enable_geometry_restriction():
    parent = upgrade_party_development_model_for_workload(_initialized_model())
    _, row = example()
    update = adapt_party_development_model_from_outcomes(parent, (row,))
    assert "route_geometry_fit" not in update.report.public_dict()
    assert update.report.public_dict()["schema"].endswith(".v2")
    np.testing.assert_array_equal(update.model.feature_scale, parent.feature_scale)
