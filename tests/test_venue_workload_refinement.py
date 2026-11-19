"""Conditional optimizer refinement preserves the zero-workload prior exactly."""

from dataclasses import replace

import numpy as np
import pytest
from test_party_development_workload import _example, _project
from test_venue_workload_rehearsal import trained

from pokemon_red_completion.party_development_outcome_learning import (
    PartyDevelopmentOutcomeLearningError,
)
from pokemon_red_completion.party_development_outcome_learning import (
    adapt_party_development_model_from_outcomes as fit,
)
from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_WORKLOAD_FEATURE_NAMES,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def test_refinement_preserves_legacy_predictions_and_frozen_parameters():
    base, old = trained()
    new = _example(tag="b")
    from pokemon_red_completion.party_development_rank import VenueTrainingWorkload

    legacy = _project(venues=(VenueTrainingWorkload(0.9, 50), VenueTrainingWorkload(0.2, 5)))
    legacy = replace(
        legacy,
        candidates=tuple(
            replace(
                c,
                features=tuple(
                    0.0 if name.startswith("level_workload.") else value
                    for name, value in zip(legacy.feature_names, c.features, strict=True)
                ),
            )
            for c in legacy.candidates
        ),
    )
    update = fit(
        base,
        (new,),
        refine_workload=True,
        rehearsal_examples=(old,),
        rehearsal_attestation_sha256="d" * 64,
    )
    names = tuple(
        n for n in PARTY_DEVELOPMENT_WORKLOAD_FEATURE_NAMES if n.startswith("level_workload.")
    )
    columns = [base.feature_names.index(n) for n in names]
    frozen = np.ones(base.weights1.shape[0], dtype=bool)
    frozen[columns] = False
    np.testing.assert_array_equal(update.model.weights1[frozen], base.weights1[frozen])
    np.testing.assert_array_equal(update.model.weights2, base.weights2)
    np.testing.assert_array_equal(update.model.bias1, base.bias1)
    np.testing.assert_array_equal(update.model.feature_scale, base.feature_scale)
    np.testing.assert_array_equal(update.model.feature_mean, base.feature_mean)
    np.testing.assert_array_equal(update.model.scores(legacy), base.scores(legacy))
    assert np.any(update.model.weights1[columns] != base.weights1[columns])
    assert update.model.outcome_training_examples == base.outcome_training_examples + 1
    assert update.report.training_example_count == 1
    assert update.report.loss_after < update.report.loss_before
    assert update.report.public_dict()["rehearsal_training"]["replay_counted_as_new"] is False


@pytest.mark.parametrize("fault", ["seen", "development", "not_boolean", "means", "mixed_mode"])
def test_refinement_retains_source_and_scope_guards(fault):
    base, old = trained()
    new = _example(tag="b")
    kwargs = dict(refine_workload=True)
    if fault == "seen":
        new = old
    if fault == "development":
        new = _example(tag="b", partition=ScenarioPartition.DEVELOPMENT)
    if fault == "not_boolean":
        kwargs["refine_workload"] = 1
    if fault == "mixed_mode":
        kwargs["restrict_workload"] = True
    if fault == "means":
        means = base.feature_mean.copy()
        means[base.feature_names.index("level_workload.present")] = 1
        base = replace(base, feature_mean=means)
    with pytest.raises(PartyDevelopmentOutcomeLearningError):
        fit(base, (new,), **kwargs)


def test_explicit_false_preserves_existing_unrestricted_update():
    base, _ = trained()
    new = _example(tag="b")
    a = fit(base, (new,))
    b = fit(base, (new,), refine_workload=False)
    np.testing.assert_array_equal(a.model.weights1, b.model.weights1)
    np.testing.assert_array_equal(a.model.weights2, b.model.weights2)
    np.testing.assert_array_equal(a.model.bias1, b.model.bias1)
