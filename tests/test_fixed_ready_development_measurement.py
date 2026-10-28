"""ROM-free opt-in measurement checks; no native corpus or optimizer runs.

Uses the existing artificial fixed-ready fixture. Each partition gets a fresh
prospective binding before adaptation; no admitted TRAIN row is relabeled.
"""
from dataclasses import asdict, replace

import pytest

import pokemon_red_completion.party_development_outcome_learning as learning
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.party_development_fixed_target_outcomes import (
    adapt_fixed_level_ready_outcomes,
    freeze_fixed_level_ready_binding,
    observed_party_sha256,
)
from pokemon_red_completion.party_development_rank import (
    VenueOperationalPrior, VenuePriorFeatureMode,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.scenario_outcomes import ScenarioOutcomeError

from test_party_development_fixed_target_outcomes import _fixture
from test_party_development_outcome_learning import _initialized_model


def _partition_fixture(partition):
    menu, contract, original_binding, trials, endpoints = _fixture()
    binding = freeze_fixed_level_ready_binding(
        menu, contract, original_semantic_snapshot_sha256="3" * 64,
        scenario_id=original_binding.scenario_id,
        root_lineage_id=original_binding.root_lineage_id,
        initial_state_sha256=original_binding.initial_state_sha256,
        partition=partition, source_commit=original_binding.source_commit,
        source_bundle_sha256=original_binding.source_bundle_sha256,
        venue_priors=(VenueOperationalPrior(),) * len(menu.candidates),
        venue_prior_registry_sha256=original_binding.venue_prior_registry_sha256,
        venue_prior_feature_mode=VenuePriorFeatureMode.MASKED_UNCALIBRATED,
    )
    return menu, contract, binding, trials, endpoints


def _adapt(fixture, **kwargs):
    menu, contract, binding, trials, endpoints = fixture
    return adapt_fixed_level_ready_outcomes(
        menu, trials, endpoints, contract=contract,
        prospective_binding=binding,
        original_semantic_snapshot_sha256="3" * 64, **kwargs,
    )


def test_existing_train_default_and_explicit_train_keep_exact_legacy_identity():
    fixture = _fixture()
    default = _adapt(fixture)
    explicit = _adapt(fixture, measurement_partition=ScenarioPartition.TRAIN)
    assert asdict(default) == asdict(explicit)
    assert canonical_sha256(asdict(default)) == (
        "5581f1928e82baac3230a84cd903bf9ef348f1e3222e73d2aaad5e092ee459d6"
    )
    assert canonical_sha256(default.public_dict()) == (
        "568810a3a2ba0f3358a46db24ddd1d2368a44ccd08214203bc56abd7278b6cc8"
    )


def test_development_requires_explicit_measurement_opt_in():
    fixture = _partition_fixture(ScenarioPartition.DEVELOPMENT)
    with pytest.raises(ScenarioOutcomeError, match="measurement partition"):
        _adapt(fixture)
    with pytest.raises(ScenarioOutcomeError, match="measurement partition"):
        _adapt(fixture, measurement_partition=ScenarioPartition.TRAIN)
    example = _adapt(fixture, measurement_partition=ScenarioPartition.DEVELOPMENT)
    assert example.partition is ScenarioPartition.DEVELOPMENT
    assert example.prospective_binding_sha256 == fixture[2].binding_sha256
    assert example.fully_measured
    fixture[2].require_matches(example)


def test_train_source_binding_cannot_be_admitted_as_development():
    with pytest.raises(ScenarioOutcomeError, match="measurement partition"):
        _adapt(_fixture(), measurement_partition=ScenarioPartition.DEVELOPMENT)


@pytest.mark.parametrize("partition", [
    ScenarioPartition.TEST, "train", "development", "test", None, True, 1,
])
def test_only_typed_train_or_development_measurement_is_permitted(partition):
    with pytest.raises(ScenarioOutcomeError, match="measurement partition"):
        _adapt(_fixture(), measurement_partition=partition)


@pytest.mark.parametrize("permission", [
    ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT, ScenarioPartition.TEST,
])
def test_test_binding_cannot_enter_through_any_measurement_permission(permission):
    with pytest.raises(ScenarioOutcomeError, match="measurement partition"):
        _adapt(_partition_fixture(ScenarioPartition.TEST),
               measurement_partition=permission)


def test_opt_in_changes_only_partition_and_prospective_identity_not_raw_outcomes():
    train = _adapt(_fixture())
    development = _adapt(_partition_fixture(ScenarioPartition.DEVELOPMENT),
                         measurement_partition=ScenarioPartition.DEVELOPMENT)
    a, b = asdict(train), asdict(development)
    differences = {key for key in a if a[key] != b[key]}
    assert differences == {"partition", "prospective_binding_sha256"}
    assert train.candidates == development.candidates
    assert train.outcomes == development.outcomes
    assert train.objective == development.objective


@pytest.mark.parametrize("fault", [
    "source", "recipient", "home", "field_return", "frames", "hp", "evolution",
])
def test_development_permission_preserves_source_and_completed_endpoint_guards(fault):
    menu, contract, binding, trials, endpoints = _partition_fixture(
        ScenarioPartition.DEVELOPMENT
    )
    trial, endpoint = trials[0], endpoints[0]
    if fault == "source":
        endpoint = replace(endpoint, source_state_sha256="b" * 64)
    elif fault == "recipient":
        endpoint = replace(endpoint, recipient_binding_sha256="b" * 64)
    elif fault == "home":
        endpoint = replace(endpoint, home_binding_sha256="b" * 64)
    elif fault == "field_return":
        endpoint = replace(endpoint, field_return_verified=False)
    elif fault == "frames":
        endpoint = replace(endpoint, frames_executed=999)
    elif fault == "hp":
        target = trial.after_party.members[0]
        changed = replace(target, hp=target.max_hp - 1)
        trial = replace(trial, after_party=PartyObservation(
            members=(changed, *trial.after_party.members[1:])
        ))
        endpoint = replace(endpoint,
                           terminal_party_sha256=observed_party_sha256(trial.after_party))
    elif fault == "evolution":
        trial = replace(trial, evolution_completed=True)
    with pytest.raises(ScenarioOutcomeError):
        _adapt((menu, contract, binding, (trial, trials[1]), (endpoint, endpoints[1])),
               measurement_partition=ScenarioPartition.DEVELOPMENT)


def test_development_measurement_is_rejected_by_existing_train_learner_before_optimizer(monkeypatch):
    row = _adapt(_partition_fixture(ScenarioPartition.DEVELOPMENT),
                 measurement_partition=ScenarioPartition.DEVELOPMENT)
    # Deterministic synthetic constructor and zero extension only; no fitting.
    model = learning.upgrade_party_development_model_for_workload(_initialized_model())
    before = model.to_dict()
    reached_after_partition_guard = []

    def forbidden(*args, **kwargs):
        reached_after_partition_guard.append(True)
        raise AssertionError("partition rejection must precede optimizer setup")

    monkeypatch.setattr(learning, "_require_hyperparameters", forbidden)
    monkeypatch.setattr(learning, "_outcome_loss", forbidden)
    with pytest.raises(learning.PartyDevelopmentOutcomeLearningError, match="partition"):
        learning.adapt_party_development_model_from_outcomes(model, (row,), epochs=1)
    assert not reached_after_partition_guard
    assert model.to_dict() == before
