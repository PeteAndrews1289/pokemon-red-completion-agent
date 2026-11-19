"""Explicit same-origin task rehearsal keeps the origin and default guards."""
from dataclasses import replace
import json

import numpy as np
import pytest
from test_mixed_completed_task_venue_learning import lesson, model, EVO, READY
from test_party_development_workload import _project

from pokemon_red_completion.party_development_catalog import PartyDevelopmentProspectiveBinding
from pokemon_red_completion.party_development_outcome_learning import (
    adapt_party_development_model_from_outcomes as fit,
    PartyDevelopmentOutcomeLearningError, PartyDevelopmentOutcomeModel,
    _outcome_loss, _hidden_activations,
)
from pokemon_red_completion.party_development_rank import VenueOperationalPrior, VenuePriorFeatureMode, VENUE_MATCHUP_FEATURE_NAMES
from pokemon_red_completion.scenario_lab import ScenarioPartition


def tasks():
    menu, a = lesson("b", READY)
    _, b = lesson("c", EVO)
    index = menu.feature_names.index("trainee.max_hp")
    related_menu = replace(menu, candidates=tuple(replace(c, features=tuple(
        value + .1 if i == index else value for i, value in enumerate(c.features)
    )) for c in menu.candidates))
    binding = PartyDevelopmentProspectiveBinding.build(
        scenario_id="related-different-trainee", root_lineage_id=a.root_lineage_id,
        initial_state_sha256=a.initial_state_sha256, partition=ScenarioPartition.TRAIN,
        source_commit="1" * 40, source_bundle_sha256="2" * 64,
        semantic_snapshot_sha256="8" * 64, candidate_set=related_menu,
        venue_priors=(VenueOperationalPrior(),) * 2, venue_prior_registry_sha256="4" * 64,
        venue_prior_feature_mode=VenuePriorFeatureMode.MASKED_UNCALIBRATED,
        outcome_objective_sha256=READY.objective_sha256,
    )
    related = replace(a, scenario_id=binding.scenario_id,
        candidates=tuple(replace(c, features=m.features)for c,m in zip(a.candidates,related_menu.candidates)),
        prospective_binding_sha256=binding.binding_sha256)
    binding.require_matches(related)
    return (a, b), related


def options(related):
    return dict(refine_suitability=True, include_observed_stats=True,
        mix_completed_task_costs=True, related_task_rehearsal=True,
        rehearsal_examples=(related,), rehearsal_attestation_sha256="d" * 64)


def test_related_tasks_share_one_origin_vote_and_keep_model_format_and_legacy_scores():
    primary, related = tasks()
    base = model()
    before = [x.public_dict() for x in (*primary,related)]
    update = fit(base, primary, epochs=20, **options(related))
    report = update.report.rehearsal_training
    assert report["task_loss_weights"] == [.25,.5,.25]
    assert report["primary_origin_count"] == 2 and report["total_task_questions"] == 3
    assert report["independent_origins_added"] == 0
    assert update.report.training_example_count == 2
    assert update.model.outcome_training_examples == base.outcome_training_examples + 2
    assert set(update.model.outcome_training_root_lineage_ids) == {x.root_lineage_id for x in primary}
    assert len(update.model.outcome_training_state_sha256) == 2
    np.testing.assert_array_equal(update.model.weights1[:78], base.weights1[:78])
    np.testing.assert_array_equal(update.model.bias1, base.bias1)
    np.testing.assert_array_equal(update.model.weights2, base.weights2)
    np.testing.assert_array_equal(update.model.scores(_project()), base.scores(_project()))
    known = base.feature_names.index("trainee.max_hp")
    expected = np.sqrt(sum(w*np.mean([c.features[known]**2 for c in e.candidates])
        for w,e in zip((.25,.5,.25),(*primary,related))))
    assert update.model.feature_scale[known] == pytest.approx(expected)
    restored = PartyDevelopmentOutcomeModel.from_dict(json.loads(json.dumps(update.model.to_dict())))
    np.testing.assert_array_equal(restored.weights1, update.model.weights1)
    assert before == [x.public_dict() for x in (*primary,related)]


@pytest.mark.parametrize("fault", ["missing_attestation", "other_root", "other_state", "same_input",
    "same_scenario", "same_binding", "development", "unmeasured", "unknown_stats", "unobserved",
    "extra_task_same_root", "flag_not_bool", "without_mixed_scope", "no_tasks", "duplicate_primary"])
def test_related_mode_never_grants_new_source_or_task_authority(fault):
    primary, related = tasks()
    kwargs = options(related)
    if fault == "missing_attestation": kwargs['rehearsal_attestation_sha256'] = None
    elif fault == "other_root": related=replace(related,root_lineage_id="unrelated")
    elif fault == "other_state": related=replace(related,initial_state_sha256="f"*64)
    elif fault == "same_input": related=replace(related,candidates=primary[0].candidates)
    elif fault == "same_scenario": related=replace(related,scenario_id=primary[0].scenario_id)
    elif fault == "same_binding": related=replace(related,prospective_binding_sha256=primary[0].prospective_binding_sha256)
    elif fault == "development": related=replace(related,partition=ScenarioPartition.DEVELOPMENT)
    elif fault == "unmeasured": related=replace(related,outcomes=(None,related.outcomes[1]))
    elif fault in ("unknown_stats","unobserved"):
        name="trainee.stats_known" if fault=="unknown_stats" else VENUE_MATCHUP_FEATURE_NAMES[0]
        # These are the two existing public knownness inputs, not admission flags.
        index=related.feature_names.index(name)
        related=replace(related,candidates=tuple(replace(c,features=tuple(0. if i==index else v for i,v in enumerate(c.features)))for c in related.candidates))
    elif fault == "flag_not_bool": kwargs['related_task_rehearsal']=1
    elif fault == "without_mixed_scope": kwargs['mix_completed_task_costs']=False
    elif fault == "duplicate_primary": primary=(primary[0],primary[0])
    kwargs['rehearsal_examples']=(related,related)if fault=="extra_task_same_root" else ()if fault=="no_tasks" else (related,)
    with pytest.raises(PartyDevelopmentOutcomeLearningError):
        fit(model(),primary,epochs=1,**kwargs)


def test_default_mixed_rehearsal_and_default_duplicate_primary_still_reject():
    primary, related = tasks()
    kwargs=options(related);kwargs.pop('related_task_rehearsal')
    with pytest.raises(PartyDevelopmentOutcomeLearningError,match="no rehearsal scope"):
        fit(model(),primary,**kwargs)
    with pytest.raises(PartyDevelopmentOutcomeLearningError,match="repeats inside"):
        fit(model(),(*primary,related),refine_suitability=True,include_observed_stats=True,mix_completed_task_costs=True)


def test_weighted_loss_and_gradient_match_origin_mean_and_numerical_derivative():
    primary, related = tasks();examples=(*primary,related);weights=(.25,.5,.25)
    base=model()
    losses=tuple(_outcome_loss(base,(e,))for e in examples)
    assert _outcome_loss(base,examples,weights)==pytest.approx((losses[0]+losses[2])/4+losses[1]/2)
    row,column=base.feature_names.index('trainee.max_hp'),0
    gradient=0.
    for w,e in zip(weights,examples):
        x=(np.asarray([c.features for c in e.candidates])-base.feature_mean)/base.feature_scale
        h=_hidden_activations(x,base.weights1,base.bias1,base.feature_schema_id)
        scores=h@base.weights2;p=np.exp(scores-scores.max());p/=p.sum()
        delta=(p-e.target_distribution)[:,None]*base.weights2[None,:]*(1-h*h)
        gradient+=w*(x.T@delta)[row,column]
    epsilon=1e-6;plus=base.weights1.copy();minus=base.weights1.copy();plus[row,column]+=epsilon;minus[row,column]-=epsilon
    numerical=(_outcome_loss(replace(base,weights1=plus),examples,weights)-_outcome_loss(replace(base,weights1=minus),examples,weights))/(2*epsilon)
    assert gradient==pytest.approx(numerical,rel=1e-5,abs=1e-8)
