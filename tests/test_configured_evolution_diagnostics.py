import ast
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace as NS
import json
import pytest
import run_configured_red_player as driver


def plan():
    return dict(partition='development',diagnostic_only=True,
        actual_gameplay_resume_authorized=False,copy_back=False,fit_allowed=False,
        cutoff_utc=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),
        owned_stock_income_bootstrap=True,conserved_owned_medicine_income=True,
        goal_model_record={'path':'model-record','content_sha256':'a'*64},
        evolution_copy_experiment=dict(venue='cave',maximum_quanta=4,maximum_wall_seconds=60))


@pytest.mark.parametrize('venue',['cave','mansion'])
def test_bounded_copy_venue_measurement_is_explicit(venue):
    p=plan();p['evolution_copy_experiment']['venue']=venue
    value=driver.declared_evolution_copy_experiment(p)
    assert value==p['evolution_copy_experiment'] and value is not p['evolution_copy_experiment']
    assert driver.declared_evolution_copy_experiment({}) is None


@pytest.mark.parametrize('change',[
    {'partition':'train'},{'partition':'sealed'},{'diagnostic_only':False},
    {'actual_gameplay_resume_authorized':True},{'actual_gameplay_resume_authorized':None},
    {'copy_back':True},{'fit_allowed':True},
])
def test_actual_or_fitting_scope_cannot_use_the_venue_override(change):
    p=plan();p.update(change)
    with pytest.raises(ValueError,match='DEVELOPMENT'):driver.declared_evolution_copy_experiment(p)


@pytest.mark.parametrize('field,value',[
    ('venue','unknown'),('venue',None),('venue',[]),
    ('maximum_quanta',True),('maximum_quanta',0),('maximum_quanta',129),
    ('maximum_wall_seconds',True),('maximum_wall_seconds',0),('maximum_wall_seconds',601),
])
def test_probe_limits_and_names_fail_closed(field,value):
    p=plan();p['evolution_copy_experiment'][field]=value
    with pytest.raises(ValueError,match='bounded'):driver.declared_evolution_copy_experiment(p)


@pytest.mark.parametrize('spec',[{},[],True,{'venue':'cave','maximum_quanta':1},
    dict(venue='cave',maximum_quanta=1,maximum_wall_seconds=1,source_species='operator-target')])
def test_no_missing_or_extra_diagnostic_authority(spec):
    p=plan();p['evolution_copy_experiment']=spec
    with pytest.raises(ValueError):driver.declared_evolution_copy_experiment(p)


def test_postgame_evolution_assembly_receives_validated_model_and_support(tmp_path,monkeypatch):
    class BeforeEmulator(Exception):pass
    p=plan();seen={}
    def assemble(*args,plan_path,**kwargs):
        seen.update(json.loads(plan_path.read_text()))
        raise BeforeEmulator
    monkeypatch.setattr(driver,'assemble_configured_player',assemble)
    c=NS(digest=lambda _: 'd'*64)
    backend=NS(c=c)
    with pytest.raises(BeforeEmulator):
        driver.verify_evolution_copy(NS(seconds=90),p,tmp_path,backend,
            NS(sha256='c'*64,to_dict=lambda:dict(goal_model_sha256='e'*64)),tmp_path/'parent',
            dict(state_sha256='b'*64,spent={}),
            dict(seconds=90,actions=20000,frames=2000000,heals=128,decisions=1))
    assert seen['goal_model_record']==p['goal_model_record']
    assert seen['configuration']==dict(goal_model_sha256='e'*64)
    assert seen['configuration_sha256']=='c'*64
    assert seen['owned_stock_income_bootstrap'] is True
    assert seen['conserved_owned_medicine_income'] is True
    assert seen['evolution_copy_experiment']==p['evolution_copy_experiment']
    assert seen['diagnostic_only'] and seen['copy_back'] is False and seen['fit_allowed'] is False


@pytest.mark.parametrize('name',['verify_loan_copy','verify_evolution_copy'])
def test_each_diagnostic_assembly_uses_common_permission_projection(name):
    module=ast.parse(Path(driver.__file__).read_text())
    fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name==name)
    declaration=next(n for n in ast.walk(fn) if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='declaration' for t in n.targets))
    assert any(k.arg is None and isinstance(k.value,ast.Call)
        and isinstance(k.value.func,ast.Name) and k.value.func.id=='player_wiring_declaration'
        for k in declaration.value.keywords)


def test_explicit_evolution_measurement_clips_all_requested_limits_to_remaining():
    args=NS(actions=50000,frames=6000000)
    left=dict(actions=35000,frames=4000000,seconds=450,decisions=1,heals=12)
    limits=driver.evolution_copy_limits(args,left,450,experiment={'declared':True})
    assert (limits.actions,limits.frames,limits.seconds,limits.decisions,limits.heals)==(35000,4000000,450,1,12)


def test_legacy_evolution_diagnostic_keeps_its_original_caps():
    left=dict(actions=50000,frames=6000000,seconds=600,decisions=8,heals=12)
    limits=driver.evolution_copy_limits(NS(actions=50000,frames=6000000),left,600,experiment=None)
    assert (limits.actions,limits.frames,limits.decisions)==(20000,2000000,1)


@pytest.mark.parametrize('field,value',[('actions',True),('actions',0),('frames',-1),('frames',2.5)])
def test_explicit_diagnostic_limits_cannot_disable_native_guards(field,value):
    args=NS(actions=50000,frames=6000000);setattr(args,field,value)
    with pytest.raises(ValueError,match='positive integer'):
        driver.evolution_copy_limits(args,dict(actions=50000,frames=6000000,seconds=600,decisions=1,heals=12),600,experiment={'declared':True})
