"""Prospective suitability inputs and legacy isolation, without a ROM or native input."""
from dataclasses import replace
import json
import numpy as np
import pytest
from test_party_development_workload import _project, _example, _binding
from test_party_development_outcome_learning import _initialized_model
from test_native_evolution_venue_model import build, select
import test_native_evolution_venue_model as fixtures

from pokemon_red_completion.party_development_rank import (
    VenueMatchupContext, VENUE_MATCHUP_FEATURE_NAMES, PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID,
    PartyDevelopmentCandidateSet, PartyDevelopmentFeatureError)
from pokemon_red_completion.party_development_outcome_learning import (
    upgrade_party_development_model_for_workload, upgrade_party_development_model_for_matchups,
    adapt_party_development_model_from_outcomes, PartyDevelopmentOutcomeLearningError,
    PartyDevelopmentOutcomeModel)
from pokemon_red_completion.party import PartyMemberObservation, MoveObservation
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.red_party_development_adapter import observe_red_venue_matchup_context


def extended(menu, contexts):
    return replace(menu, candidates=tuple(replace(c, features=(*c.features, *((0.0,)*len(VENUE_MATCHUP_FEATURE_NAMES)
        if v is None else v.vector())), feature_schema_id=PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID)
        for c,v in zip(menu.candidates, contexts, strict=True)))


def fresh_example(tag="b", partition=ScenarioPartition.TRAIN, observed=True):
    old = _example(tag=tag, partition=partition)
    menu = _project()
    a = VenueMatchupContext(.2, .5, .2, .5, 90, (60, 50, 70, 80))
    b = VenueMatchupContext(.03, 0, -.5, .25, 90, (60, 50, 70, 80))
    menu = extended(menu, (a,b) if observed else (None,None))
    binding = _binding(menu, old.objective, tag=tag, partition=partition)
    return menu, replace(old, feature_schema_id=menu.feature_schema_id, feature_names=menu.feature_names,
        candidates=tuple(replace(c, features=m.features) for c,m in zip(old.candidates,menu.candidates)),
        prospective_binding_sha256=binding.binding_sha256)


def test_upgrade_roundtrip_preserves_every_legacy_score_and_zero_influence():
    base = upgrade_party_development_model_for_workload(_initialized_model())
    model = upgrade_party_development_model_for_matchups(base)
    legacy = _project()
    known = extended(legacy, (VenueMatchupContext(.2,.5,.2,.5,90),)*2)
    for m in (legacy, extended(legacy,(None,None)), known):
        np.testing.assert_array_equal(base.scores(legacy), model.scores(m))
    np.testing.assert_array_equal(model.weights1[:len(base.feature_names)], base.weights1)
    assert not np.any(model.weights1[len(base.feature_names):])
    assert model.outcome_training_examples == base.outcome_training_examples
    restored = PartyDevelopmentOutcomeModel.from_dict(json.loads(json.dumps(model.to_dict())))
    np.testing.assert_array_equal(restored.scores(known), model.scores(known))
    assert PartyDevelopmentCandidateSet.from_public_dict(known.public_dict()) == known
    with pytest.raises(PartyDevelopmentOutcomeLearningError): base.scores(known)


def test_only_new_rows_learn_and_old_documents_keep_original_schema():
    base = upgrade_party_development_model_for_matchups(_initialized_model())
    menu, example = fresh_example()
    update = adapt_party_development_model_from_outcomes(base,(example,),refine_suitability=True)
    n = len(base.feature_names)-len(VENUE_MATCHUP_FEATURE_NAMES)
    np.testing.assert_array_equal(update.model.weights1[:n], base.weights1[:n])
    np.testing.assert_array_equal(update.model.weights2,base.weights2)
    np.testing.assert_array_equal(update.model.bias1,base.bias1)
    np.testing.assert_array_equal(update.model.scores(_project()),base.scores(_project()))
    assert np.any(update.model.weights1[n:] != 0)
    np.testing.assert_array_equal(update.model.weights1[n+6:], base.weights1[n+6:])
    assert update.report.loss_after < update.report.loss_before
    assert _project().feature_schema_id != menu.feature_schema_id
    assert not any(any(x in name for x in ("species","move_id","map_id","slot","identity")) for name in VENUE_MATCHUP_FEATURE_NAMES)


@pytest.mark.parametrize("fault",["development","unobserved","mixed","boolean","mean"])
def test_fit_fails_closed_without_fresh_observed_train_scope(fault):
    model=upgrade_party_development_model_for_matchups(_initialized_model())
    menu,e=fresh_example(partition=ScenarioPartition.DEVELOPMENT if fault=="development" else ScenarioPartition.TRAIN,
                         observed=fault!="unobserved")
    kw=dict(refine_suitability=True)
    if fault=="mixed":kw["refine_workload"]=True
    if fault=="boolean":kw["refine_suitability"]=1
    if fault=="mean":
        mean=model.feature_mean.copy();mean[-1]=.1;model=replace(model,feature_mean=mean)
    with pytest.raises(PartyDevelopmentOutcomeLearningError):
        adapt_party_development_model_from_outcomes(model,(e,),**kw)


def test_projector_filters_executor_unsupported_charge_and_preserves_unknown_stats():
    mon=PartyMemberObservation(slot=1,species_id=59,level=30,hp=46,max_hp=46,
        moves=(MoveObservation(10,35,35),MoveObservation(91,10,10)))
    a=observe_red_venue_matchup_context(mon,encounter_slots=((15,59),),weights=(256,))
    b=observe_red_venue_matchup_context(replace(mon,moves=(MoveObservation(10,35,35),)),encounter_slots=((15,59),),weights=(256,))
    assert a==b and a.usable_attack_fraction==.25 and a.vector()[6]==0 and a.vector()[7:]==(0,0,0,0)
    escape=observe_red_venue_matchup_context(mon,encounter_slots=((15,59),),weights=(256,),escaped_species={59})
    assert escape.attack_power==escape.attack_type_margin==escape.usable_attack_fraction==0
    assert observe_red_venue_matchup_context(replace(mon,hp=0),encounter_slots=((15,59),),weights=(256,)) is None
    with pytest.raises(PartyDevelopmentFeatureError):
        observe_red_venue_matchup_context(mon,encounter_slots=((15,59),),weights=(256,),raw_stats=(1,2))


@pytest.fixture
def menu_case(monkeypatch):
    return fixtures.menu_case.__wrapped__(monkeypatch)


def test_production_menu_optin_binds_observations_and_permutation(menu_case):
    old=build(menu_case);new=build(menu_case,include_matchup_context=True)
    for a,b in zip(old.candidate_set.candidates,new.candidate_set.candidates):
        assert b.features[:len(a.features)]==a.features
        assert b.features[len(a.features)]==1
    assert new.candidate_set.feature_schema_id==PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID
    rev=build(menu_case,venues=menu_case.venues[::-1],include_matchup_context=True)
    assert [c.features for c in new.candidate_set.candidates]==[c.features for c in rev.candidate_set.candidates][::-1]
    model=upgrade_party_development_model_for_matchups(_initialized_model());events=[]
    chosen=select(menu_case,model,{},events)
    assert chosen in menu_case.venues
    assert events[-1][1]["candidate_set"]["schema"]=="pokemon-party-development-candidate-set-v4"


def test_teacher_recorder_opts_into_shared_builder_before_prospective_binding():
    import ast
    import inspect
    from pokemon_red_completion import red_teacher_venue
    from pokemon_red_completion.party_development_catalog import PartyDevelopmentProspectiveBinding
    tree = ast.parse(inspect.getsource(red_teacher_venue))
    builders = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == "build_native_evolution_venue_menu"]
    assert len(builders) == 1
    assert "include_matchup_context" in {k.arg for k in builders[0].keywords}
    bindings = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "build"
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "PartyDevelopmentProspectiveBinding"]
    assert len(bindings) == 1
    allowed = inspect.signature(PartyDevelopmentProspectiveBinding.build).parameters
    assert all(k.arg in allowed for k in bindings[0].keywords)


def test_explicit_observed_stats_refinement_preserves_legacy_unknown_scores():
    base = upgrade_party_development_model_for_matchups(_initialized_model())
    menu, example = fresh_example()
    update = adapt_party_development_model_from_outcomes(
        base, (example,), refine_suitability=True, include_observed_stats=True
    )
    n = len(base.feature_names) - len(VENUE_MATCHUP_FEATURE_NAMES)
    np.testing.assert_array_equal(update.model.weights1[:n], base.weights1[:n])
    np.testing.assert_array_equal(update.model.bias1, base.bias1)
    np.testing.assert_array_equal(update.model.weights2, base.weights2)
    np.testing.assert_array_equal(update.model.scores(_project()), base.scores(_project()))
    np.testing.assert_array_equal(
        update.model.scores(extended(_project(), (None, None))), base.scores(_project())
    )
    assert np.any(update.model.weights1[n+6:] != base.weights1[n+6:])
    assert update.report.workload_fit["diagnostic_stat_rows_frozen"] == []
    assert update.report.loss_after < update.report.loss_before
    assert update.model.outcome_training_examples == base.outcome_training_examples + 1


@pytest.mark.parametrize("fault", ["implicit", "integer", "unknown_stats", "development"])
def test_observed_stats_refinement_needs_explicit_native_train_facts(fault):
    base = upgrade_party_development_model_for_matchups(_initialized_model())
    menu, example = fresh_example(partition=ScenarioPartition.DEVELOPMENT if fault == "development" else ScenarioPartition.TRAIN)
    if fault == "unknown_stats":
        a = VenueMatchupContext(.2, .5, .2, .5, 90)
        b = VenueMatchupContext(.03, 0, -.5, .25, 90)
        menu = extended(_project(), (a, b))
        binding = _binding(menu, example.objective, tag="b", partition=ScenarioPartition.TRAIN)
        example = replace(example, candidates=tuple(replace(c, features=m.features) for c, m in zip(example.candidates, menu.candidates)), prospective_binding_sha256=binding.binding_sha256)
    with pytest.raises(PartyDevelopmentOutcomeLearningError):
        adapt_party_development_model_from_outcomes(
            base, (example,), refine_suitability=fault != "implicit",
            include_observed_stats=1 if fault == "integer" else True,
        )
