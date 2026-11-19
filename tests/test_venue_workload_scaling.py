"""ROM-free optimizer contracts; these synthetic rows are never fitting data."""

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
from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    VenueTrainingWorkload,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def example(partition=ScenarioPartition.TRAIN, same=False):
    menu = _project(
        venues=(
            VenueTrainingWorkload(1, 150, None, None),
            VenueTrainingWorkload(1, 150 if same else 50, None, None),
        )
    )
    column = menu.feature_names.index("venue.expected_recipient_xp_per_encounter")
    prefix = menu.candidates[0].features
    menu = replace(
        menu,
        candidates=tuple(
            replace(
                c,
                features=tuple(
                    c.features[i] if i == column else prefix[i] for i in range(len(prefix))
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
    row = adapt_party_development_outcomes_v2(
        menu,
        trials,
        scenario_id=binding.scenario_id,
        root_lineage_id=binding.root_lineage_id,
        initial_state_sha256=binding.initial_state_sha256,
        partition=partition,
        prospective_binding=binding,
        total_task_efficiency=True,
    )
    return menu, row


def test_workload_fit_conditions_tiny_yield_and_retains_entire_old_scorer():
    parent = upgrade_party_development_model_for_workload(_initialized_model())
    menu, row = example()
    before = parent.to_dict()
    update = adapt_party_development_model_from_outcomes(parent, (row,), restrict_workload=True)
    child = update.model
    n = len(PARTY_DEVELOPMENT_FEATURE_NAMES)
    yield_column = parent.feature_names.index("venue.expected_recipient_xp_per_encounter")
    assert child.feature_scale[yield_column] == pytest.approx(np.sqrt((0.0015**2 + 0.0005**2) / 2))
    assert child.predict(menu) == 0 and update.report.loss_after < update.report.loss_before
    assert parent.to_dict() == before
    for field in ("weights1", "feature_mean", "feature_scale"):
        np.testing.assert_array_equal(getattr(parent, field)[:n], getattr(child, field)[:n])
    for field in ("bias1", "weights2", "feature_mean"):
        np.testing.assert_array_equal(getattr(parent, field), getattr(child, field))
    old = replace(
        menu,
        candidates=tuple(
            replace(c, features=c.features[:n] + (0.0,) * (len(c.features) - n))
            for c in menu.candidates
        ),
    )
    assert parent.scores(old).tobytes() == child.scores(old).tobytes()
    assert update.report.public_dict()["workload_fit"]["retained_zero_workload_algebra"] is True


@pytest.mark.parametrize(
    "fault", ["development", "same_yield", "active_prior", "non_bool", "geometry"]
)
def test_workload_fit_rejects_ineligible_or_ambiguous_activation(fault):
    parent = upgrade_party_development_model_for_workload(_initialized_model())
    _, row = example(
        partition=ScenarioPartition.DEVELOPMENT
        if fault == "development"
        else ScenarioPartition.TRAIN,
        same=fault == "same_yield",
    )
    if fault == "active_prior":
        weights = parent.weights1.copy()
        weights[-1, 0] = 0.1
        parent = replace(parent, weights1=weights)
    with pytest.raises(PartyDevelopmentOutcomeLearningError):
        adapt_party_development_model_from_outcomes(
            parent,
            (row,),
            restrict_workload=1 if fault == "non_bool" else True,
            restrict_route_geometry=fault == "geometry",
        )


def test_conditioning_can_use_existing_full_update_without_claiming_retention():
    parent = upgrade_party_development_model_for_workload(_initialized_model())
    menu, row = example()
    update = adapt_party_development_model_from_outcomes(parent, (row,), condition_workload=True)
    assert update.model.predict(menu) == 0
    assert update.report.loss_after < update.report.loss_before
    assert update.report.public_dict()["workload_fit"]["retained_zero_workload_algebra"] is False
    assert not np.array_equal(parent.bias1, update.model.bias1)


@pytest.mark.parametrize(
    "fault", ["development", "same_yield", "active_prior", "non_bool", "restricted"]
)
def test_conditioning_preserves_admission_and_zero_prior_requirements(fault):
    parent = upgrade_party_development_model_for_workload(_initialized_model())
    _, row = example(
        partition=ScenarioPartition.DEVELOPMENT
        if fault == "development"
        else ScenarioPartition.TRAIN,
        same=fault == "same_yield",
    )
    if fault == "active_prior":
        weights = parent.weights1.copy()
        weights[-1, 0] = 0.1
        parent = replace(parent, weights1=weights)
    with pytest.raises(PartyDevelopmentOutcomeLearningError):
        adapt_party_development_model_from_outcomes(
            parent,
            (row,),
            condition_workload=1 if fault == "non_bool" else True,
            restrict_workload=fault == "restricted",
        )
