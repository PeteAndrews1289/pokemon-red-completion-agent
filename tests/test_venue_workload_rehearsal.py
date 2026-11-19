"""Synthetic replay is explicit, TRAIN-only and never counted as new roots."""

from dataclasses import replace

import numpy as np
import pytest
from test_party_development_outcome_learning import _initialized_model
from test_party_development_workload import _example

from pokemon_red_completion.party_development_outcome_learning import (
    PartyDevelopmentOutcomeLearningError,
    upgrade_party_development_model_for_workload,
)
from pokemon_red_completion.party_development_outcome_learning import (
    adapt_party_development_model_from_outcomes as fit,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def trained():
    old = _example(tag="a")
    base = upgrade_party_development_model_for_workload(_initialized_model())
    return fit(base, (old,)).model, old


def test_rehearsal_retains_real_counts_and_keeps_geometry_frozen():
    base, old = trained()
    new = _example(tag="b")
    update = fit(
        base,
        (new,),
        rehearsal_examples=(old,),
        rehearsal_attestation_sha256="d" * 64,
        freeze_route_geometry=True,
    )
    assert update.report.training_example_count == 1
    assert update.model.outcome_training_examples == base.outcome_training_examples + 1
    assert set(update.model.outcome_training_root_lineage_ids) == {
        old.root_lineage_id,
        new.root_lineage_id,
    }
    report = update.report.public_dict()["rehearsal_training"]
    assert report["replay_example_count"] == 1 and report["replay_counted_as_new"] is False
    assert report["geometry_frozen"] is True
    cols = [
        i
        for i, n in enumerate(base.feature_names)
        if n.startswith("venue.travel_steps") or n.startswith("venue.recovery_steps")
    ]
    np.testing.assert_array_equal(update.model.weights1[cols], base.weights1[cols])
    np.testing.assert_array_equal(update.model.feature_scale, base.feature_scale)


@pytest.mark.parametrize(
    "fault",
    ["no_attestation", "unseen_replay", "development", "new_already_seen", "active_geometry"],
)
def test_rehearsal_does_not_erase_existing_admission_guards(fault):
    base, old = trained()
    new = _example(tag="b")
    replay = old
    if fault == "unseen_replay":
        replay = _example(tag="c")
    if fault == "development":
        replay = _example(tag="a", partition=ScenarioPartition.DEVELOPMENT)
    if fault == "new_already_seen":
        new = old
    if fault == "active_geometry":
        w = base.weights1.copy()
        w[base.feature_names.index("venue.travel_steps"), 0] = 0.1
        base = replace(base, weights1=w)
    with pytest.raises(PartyDevelopmentOutcomeLearningError):
        fit(
            base,
            (new,),
            rehearsal_examples=(replay,),
            rehearsal_attestation_sha256=None if fault == "no_attestation" else "d" * 64,
            freeze_route_geometry=True,
        )


def test_rehearsal_is_rejected_as_an_implicit_fresh_example():
    base, old = trained()
    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="already consumed"):
        fit(base, (old,))
