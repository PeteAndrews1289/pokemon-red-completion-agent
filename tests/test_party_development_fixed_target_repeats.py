"""Repeated native tasks retain all declared costs and original single labels."""

from dataclasses import replace

import pytest
from test_party_development_fixed_target_outcomes import _fixture, _adapt

from pokemon_red_completion.party_development_fixed_target_repeats import (
    FIXED_LEVEL_READY_REPEATED_OBJECTIVE, RepeatedReadyContract,
    adapt_repeated_ready_outcomes, freeze_repeated_ready_binding,
)
from pokemon_red_completion.party_development_rank import VenueOperationalPrior, VenuePriorFeatureMode
from pokemon_red_completion.party_development_catalog import PartyDevelopmentCatalogError
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.scenario_outcomes import ScenarioOutcomeError


def fixture():
    menu, fixed, single, trials, endpoints = _fixture()
    contract = RepeatedReadyContract(fixed, (0, 31, 97), "c" * 64)
    binding = freeze_repeated_ready_binding(
        menu, contract, original_semantic_snapshot_sha256="3" * 64,
        scenario_id="unit-ready-repeated", root_lineage_id=single.root_lineage_id,
        initial_state_sha256=single.initial_state_sha256, partition=ScenarioPartition.TRAIN,
        source_commit="1" * 40, source_bundle_sha256="2" * 64,
        venue_priors=(VenueOperationalPrior(),) * 2, venue_prior_registry_sha256="4" * 64,
        venue_prior_feature_mode=VenuePriorFeatureMode.MASKED_UNCALIBRATED,
    )
    examples = []
    for timing, costs in ((0, (1000, 2000)), (31, (4000, 2000)), (97, (4000, 2000))):
        tt = tuple(replace(t, frames_executed=costs[i]) for i, t in enumerate(trials))
        ee = tuple(replace(e, frames_executed=costs[i],
            native_receipt_sha256=canonical_sha256([timing, i])) for i, e in enumerate(endpoints))
        examples.append((timing, _adapt((menu, fixed, single, tt, ee))))
    return menu, contract, binding, single, tuple(examples)


def adapt(f):
    menu, contract, binding, single, examples = f
    return adapt_repeated_ready_outcomes(menu, examples, contract=contract,
        prospective_binding=binding, single_task_binding=single,
        original_semantic_snapshot_sha256="3" * 64)


def test_sum_all_physical_costs_overrules_one_lucky_return_and_caps_target_xp():
    f = fixture()
    old = tuple(e.public_dict() for _, e in f[-1])
    result = adapt(f)
    assert result.objective == FIXED_LEVEL_READY_REPEATED_OBJECTIVE
    assert result.best_candidate_indices == (1,)
    assert [o.frames_executed for o in result.outcomes] == [9000, 6000]
    assert [o.actions_executed for o in result.outcomes] == [60, 63]
    assert all(o.criterion_values[-1] == 1500 for o in result.outcomes)
    assert tuple(e.public_dict() for _, e in f[-1]) == old


@pytest.mark.parametrize("timings", [(0,), (0, 31, 31), (True, 31, 97), (-1, 31, 97), (31, 0, 97)])
def test_timing_contract_rejects_ambiguous_conditions(timings):
    with pytest.raises(ScenarioOutcomeError):
        replace(fixture()[1], timing_frames=timings)


@pytest.mark.parametrize("fault", ["missing", "reordered", "duplicate", "root", "state", "partition", "binding", "partial", "cost", "xp", "same_evidence"])
def test_any_missing_or_substituted_trial_blocks_aggregation(fault):
    menu, contract, binding, single, examples = fixture()
    if fault == "missing":
        examples = examples[:2]
    elif fault == "reordered":
        examples = tuple(reversed(examples))
    elif fault == "duplicate":
        examples = (examples[0], examples[0], examples[2])
    else:
        e = examples[1][1]
        if fault in ("root", "state", "partition", "binding"):
            changes = {"root": {"root_lineage_id": "wrong"}, "state": {"initial_state_sha256": "f" * 64},
                "partition": {"partition": ScenarioPartition.DEVELOPMENT},
                "binding": {"prospective_binding_sha256": "f" * 64}}
            e = replace(e, **changes[fault])
        else:
            o = e.outcomes[0]
            if fault == "partial":
                values = list(o.criterion_values); values[2] = 0.0
                o = replace(o, criterion_values=tuple(values))
            elif fault == "cost":
                o = replace(o, frames_executed=o.frames_executed + 1)
            elif fault == "xp":
                values = list(o.criterion_values); values[-1] += 100
                o = replace(o, criterion_values=tuple(values))
            else:
                o = replace(o, evidence_sha256=examples[0][1].outcomes[0].evidence_sha256)
            e = replace(e, outcomes=(o, e.outcomes[1]))
        examples = (examples[0], (31, e), examples[2])
    with pytest.raises((ScenarioOutcomeError, PartyDevelopmentCatalogError)):
        adapt((menu, contract, binding, single, examples))


def test_old_single_task_binding_cannot_attest_a_different_recipient():
    menu, contract, _, single, examples = fixture()
    changed = replace(contract, fixed_task=replace(contract.fixed_task, recipient_binding_sha256="d" * 64))
    binding = freeze_repeated_ready_binding(menu, changed, original_semantic_snapshot_sha256="3" * 64,
        scenario_id="changed", root_lineage_id=single.root_lineage_id,
        initial_state_sha256=single.initial_state_sha256, partition=ScenarioPartition.TRAIN,
        source_commit="1" * 40, source_bundle_sha256="2" * 64,
        venue_priors=(VenueOperationalPrior(),) * 2, venue_prior_registry_sha256="4" * 64,
        venue_prior_feature_mode=VenuePriorFeatureMode.MASKED_UNCALIBRATED)
    with pytest.raises(ScenarioOutcomeError):
        adapt((menu, changed, binding, single, examples))


def test_repeated_task_uses_existing_optin_loss_and_freezes_legacy_parameters():
    import numpy as np
    from test_mixed_completed_task_venue_learning import lesson, model, EVO, READY
    from test_party_development_workload import _binding, _project
    from pokemon_red_completion.party_development_outcome_learning import (
        adapt_party_development_model_from_outcomes, PartyDevelopmentOutcomeLearningError,
    )
    _, evolution = lesson("b", EVO)
    menu, ready = lesson("c", READY)
    binding = _binding(menu, FIXED_LEVEL_READY_REPEATED_OBJECTIVE, tag="c")
    repeated = replace(ready, objective=FIXED_LEVEL_READY_REPEATED_OBJECTIVE,
        prospective_binding_sha256=binding.binding_sha256)
    binding.require_matches(repeated)
    base = model()
    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="objectives differ"):
        adapt_party_development_model_from_outcomes(base, (evolution, repeated),
            refine_suitability=True, include_observed_stats=True)
    update = adapt_party_development_model_from_outcomes(base, (evolution, repeated),
        refine_suitability=True, include_observed_stats=True, mix_completed_task_costs=True, epochs=2)
    np.testing.assert_array_equal(update.model.weights1[:78], base.weights1[:78])
    np.testing.assert_array_equal(update.model.bias1, base.bias1)
    np.testing.assert_array_equal(update.model.weights2, base.weights2)
    np.testing.assert_array_equal(update.model.scores(_project()), base.scores(_project()))
    forged = replace(repeated, objective=replace(FIXED_LEVEL_READY_REPEATED_OBJECTIVE,
        objective_id="party-development.forged-repeat.v1"))
    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="not canonical"):
        adapt_party_development_model_from_outcomes(base, (evolution, forged),
            refine_suitability=True, include_observed_stats=True, mix_completed_task_costs=True)
