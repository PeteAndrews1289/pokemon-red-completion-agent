from copy import deepcopy
import pytest
import run_fresh_red_player as fresh
from pokemon_red_completion.provenance import canonical_sha256
from test_run_fresh_red_player import plan


def official_plan():
    p=plan()
    p.update(official_acceptance=True,maximum_state_loads=0,maximum_emulators=1,
        runtime_llm_calls=0,training_admission=False,source_and_models_frozen_during_attempt=True,
        no_midrun_repair_or_rollback=True,all_attempts_count=True,
        required_species=[f'pokemon:national:{i:03d}'for i in range(1,125)],
        configuration_template={'goal_model_sha256':'b'*64})
    p['acceptance_declaration']=dict(schema=fresh.FRESH_ACCEPTANCE_SCHEMA,lane='learned_hybrid',
        teacher_oracle_fallback=False,cross_run_memory=False,freeze_until_exit=True,
        champion_and_concurrent_hall_of_fame=True,required_registrations=124,
        required_species_sha256=canonical_sha256(p['required_species']),
        configuration_template_sha256=canonical_sha256(p['configuration_template']),
        allowed_support=sorted(fresh.FRESH_ACCEPTANCE_SUPPORT))
    return p


def test_legacy_development_is_not_retroactively_promoted():
    p=plan();before=deepcopy(p)
    assert fresh.declared_fresh_acceptance(p) is False
    assert fresh.validate_fresh_plan(p) is p and p==before
    p['official_acceptance']=False
    assert fresh.declared_fresh_acceptance(p) is False
    p['acceptance_declaration']=official_plan()['acceptance_declaration']
    with pytest.raises(ValueError,match='prospective authority'):
        fresh.declared_fresh_acceptance(p)


def test_explicit_frozen_attempt_is_admitted_without_mutation():
    p=official_plan();before=deepcopy(p)
    assert fresh.declared_fresh_acceptance(p) is True
    assert fresh.validate_fresh_plan(p) is p and p==before


@pytest.mark.parametrize('key,value',[
    ('official_acceptance',1),('official_acceptance',None),
    ('maximum_state_loads',1),('maximum_state_loads',False),
    ('maximum_emulators',2),('maximum_emulators',True),
    ('runtime_llm_calls',1),('runtime_llm_calls',False),
    ('fit_allowed',True),('training_admission',True),('copy_back',True),('resume_allowed',True),
    ('source_and_models_frozen_during_attempt',False),('no_midrun_repair_or_rollback',False),
    ('all_attempts_count',False),
])
def test_unsafe_or_coerced_attempt_never_reaches_gameplay(key,value):
    p=official_plan();p[key]=value
    with pytest.raises(ValueError):fresh.validate_fresh_plan(p)


@pytest.mark.parametrize('fault',['teacher','memory','freeze','story_only','denominator','duplicate_species',
    'species_changed','configuration_changed','unknown_support','duplicate_support','extra_field','missing_field'])
def test_no_hidden_support_or_changed_curriculum(fault):
    p=official_plan();d=p['acceptance_declaration']
    if fault=='teacher':d['teacher_oracle_fallback']=True
    elif fault=='memory':d['cross_run_memory']=True
    elif fault=='freeze':d['freeze_until_exit']=False
    elif fault=='story_only':d['champion_and_concurrent_hall_of_fame']=False
    elif fault=='denominator':d['required_registrations']=123
    elif fault=='duplicate_species':p['required_species'][0]=p['required_species'][1]
    elif fault=='species_changed':p['required_species'][0]='pokemon:national:151'
    elif fault=='configuration_changed':p['configuration_template']['goal_model_sha256']='c'*64
    elif fault=='unknown_support':d['allowed_support'][0]='teacher_route_fallback'
    elif fault=='duplicate_support':d['allowed_support'][0]=d['allowed_support'][1]
    elif fault=='extra_field':d['oracle_override']=False
    else:d.pop('freeze_until_exit')
    with pytest.raises(ValueError):fresh.declared_fresh_acceptance(p)


def completed():
    return dict(passed=True,state_loads=0,training=0,fits=0,runtime_llm_calls=0)


def test_full_runtime_candidate_still_requires_separate_native_acceptance_audit():
    p=official_plan();r=completed()
    assert fresh.fresh_official_completion_candidate(p,r,'curriculum_complete') is True
    assert fresh.fresh_official_completion_candidate(plan(),r,'curriculum_complete') is False
    assert fresh.fresh_official_completion_candidate(p,r,'budget_exhausted') is False
    assert fresh.fresh_official_completion_candidate(p,r,'champion_room_reached') is False


@pytest.mark.parametrize('key,value',[
    ('passed',False),('state_loads',1),('training',1),('fits',1),('runtime_llm_calls',1),
    ('state_loads',False),('error_type','NativeError'),('pending_automatic_control_recoveries',[{'unresolved':True}]),
])
def test_partial_tainted_or_unresolved_runtime_is_not_a_completion_candidate(key,value):
    r=completed();r[key]=value
    assert fresh.fresh_official_completion_candidate(official_plan(),r,'curriculum_complete') is False


def test_missing_zero_load_evidence_is_not_inferred():
    r=completed();r.pop('state_loads')
    assert fresh.fresh_official_completion_candidate(official_plan(),r,'curriculum_complete') is False
