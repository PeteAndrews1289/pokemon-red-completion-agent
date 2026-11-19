"""Proposed group-v2/child-v3 reader regressions. No native inputs or fits.
Set POKEMON_PREP_STOP_CONSEQUENCE_FIXTURES to {"stop":"/abs/case","prepare":"/abs/case"}.
Fixture mutations affect in-memory file reads only. Copy to tests after root review.
"""
import json
import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from pokemon_red_completion import red_challenge_consequence as module
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_story_battle import StoryTrainerContract
from pokemon_red_completion.private_artifacts import open_private_root,gitless_fast_path_worktree_probe

def read(path):return json.loads(Path(path).read_bytes())
def contract(document):
    d=dict(document);d['trainer_identity']=tuple(d['trainer_identity']);d['victory_items']=tuple(tuple(x)for x in d['victory_items']);return StoryTrainerContract(**d)
class UnusedStore:
    def find_sealed_record(self,*a,**k):raise AssertionError('invalid identity join accessed sealed evidence')
def arguments_without_evidence():
    return dict(declaration_sha256='1'*64,result_sha256='2'*64,scoped_output=Path('/unused/child'),expected_scoped_declaration_sha256='3'*64,expected_native_plan_sha256='4'*64,expected_story_contract=StoryTrainerContract(objective_id='defeat_erika',battle_plan_id='defeat_erika',map_id=134,trainer_identity=(237,37,1),defeated_event=425,victory_money=2871,victory_badge_bits=8,victory_items=((221,1),)))
@pytest.mark.parametrize('extra',[
    dict(expected_work_order_sha256='5'*64),
    dict(expected_group_declaration_sha256='6'*64),
    dict(native_plan_path=Path('/unused/native-plan.json')),
    dict(expected_work_order_sha256='5'*64,expected_group_declaration_sha256='6'*64),
    dict(expected_work_order_sha256='bad',expected_group_declaration_sha256='6'*64,native_plan_path=Path('/unused/native-plan.json')),
    dict(expected_work_order_sha256='5'*64,expected_group_declaration_sha256='6'*64,native_plan_path='/unused/native-plan.json'),
])
def test_partial_or_untyped_group_join_rejects_before_store(extra):
    with pytest.raises(ValueError):module.load_scoped_train_challenge_consequence(UnusedStore(),**arguments_without_evidence(),**extra)

@pytest.fixture(params=['stop','prepare'])
def closed_case(request):
    raw=os.environ.get('POKEMON_PREP_STOP_CONSEQUENCE_FIXTURES')
    if raw is None:pytest.skip('explicit closed TRAIN arm fixtures not supplied')
    paths=json.loads(raw)
    assert set(paths)=={'stop','prepare'}
    case=Path(paths[request.param]);assert case.is_absolute()and case.is_dir()
    work=read(case/'PLAN.json');rcc=read(case/'native/consequence-plan.json');result=read(case/'native/consequence-result.json')
    root=case/'player/scoped-native-train';group=read(root/'declaration.json')
    children=[p for p in root.iterdir()if p.is_dir()];assert len(children)==1
    child=children[0];decl=read(child/'declaration.json')
    package=Path(work['package']['path']).parent
    store=open_private_root(case/'journal',repository_root=package/'checkout',allow_same_device=True,git_worktree_probe=gitless_fast_path_worktree_probe,native_input_storage='flat_sealed_v1')
    kwargs=dict(declaration_sha256=canonical_sha256(rcc),result_sha256=canonical_sha256(result),scoped_output=child,expected_scoped_declaration_sha256=canonical_sha256(decl),expected_native_plan_sha256=canonical_sha256(read(case/'native/native-plan.json')),expected_story_contract=contract(work['story_contract']),expected_work_order_sha256=rcc['source']['experiment_sha256'],expected_group_declaration_sha256=canonical_sha256(group),native_plan_path=case/'native/native-plan.json')
    return SimpleNamespace(case=case,root=root,child=child,group=group,decl=decl,store=store,kwargs=kwargs,rcc=rcc,result=result)

def load(f):return module.load_scoped_train_challenge_consequence(f.store,**f.kwargs)
def patch_documents(documents):
    original=Path.read_bytes
    def replacement(path):
        document=documents.get(path.resolve())
        return original(path)if document is None else json.dumps(document,sort_keys=True).encode()
    return patch.object(Path,'read_bytes',replacement)
def rehashed_child(f,change):
    child=deepcopy(f.decl);change(child)
    f.kwargs['expected_scoped_declaration_sha256']=canonical_sha256(child)
    group=deepcopy(f.group);key,=group['children'];group['children'][key]=canonical_sha256(child)
    f.kwargs['expected_group_declaration_sha256']=canonical_sha256(group)
    return {(f.child/'declaration.json').resolve():child,(f.root/'declaration.json').resolve():group}

def test_completed_native_attempt_loads_without_relabeling_worker(closed_case):
    f=closed_case;r=load(f)
    assert r.row.outcome is not None and r.row.outcome.attempted
    assert canonical_sha256(r.row.document())==canonical_sha256(f.result['row'])
    assert not hasattr(r,'native_worker_passed')

@pytest.mark.parametrize('change',[
    lambda g:g['source'].update(state_sha256='0'*64),
    lambda g:g.update(children={}),
    lambda g:g['source'].update(configuration_sha256='0'*64),
    lambda g:g['source'].update(unsupported_extra='not part of backend SourceSpec'),
    lambda g:g.update(training_eligible=True),
    lambda g:g.update(schema='pokemon.red.scoped-train-battler-group.v1'),
])
def test_rehashed_group_semantics_reject(closed_case,change):
    f=closed_case;group=deepcopy(f.group);change(group);f.kwargs['expected_group_declaration_sha256']=canonical_sha256(group)
    with patch_documents({(f.root/'declaration.json').resolve():group}),pytest.raises(ValueError):load(f)

@pytest.mark.parametrize('change',[
    lambda d:d.update(schema='pokemon.red.scoped-train-battlers.v1'),
    lambda d:d.update(scoped_train_pp_reentry=False),
    lambda d:d.update(pp_depleted_switch_screen=False),
    lambda d:d.update(experiment_sha256='0'*64),
    lambda d:d['actors'][1].update(train_risk_story_scope={'unsupported':True}),
    lambda d:d['actors'][1].update(model_sha256='0'*64),
    lambda d:d['actors'][1].update(contract={'unsupported':True}),
])
def test_rehashed_child_semantics_reject(closed_case,change):
    f=closed_case
    with patch_documents(rehashed_child(f,change)),pytest.raises(ValueError):load(f)

def test_native_plan_consequence_join_rejects_rehashed_change(closed_case):
    f=closed_case;p=f.kwargs['native_plan_path'];d=read(p);d['consequence_spec']['maximum_phases']=3
    f.kwargs['expected_native_plan_sha256']=canonical_sha256(d)
    with patch_documents({p.resolve():d}),pytest.raises(ValueError):load(f)

def test_extra_sibling_directory_rejects(closed_case):
    f=closed_case;original=Path.iterdir
    # Use a genuine existing directory outside the one-child root as the sibling.
    def replacement(path):
        values=list(original(path))
        if path==f.root:values.append(f.case/'native')
        return iter(values)
    with patch.object(Path,'iterdir',replacement),pytest.raises(ValueError):load(f)

def test_call_outside_recorded_phase_costs_rejects(closed_case):
    f=closed_case;start=next(iter(sorted(f.child.glob('battle-*-start.json'))));end=start.with_name(start.name.replace('-start','-end'))
    a,b=read(start),read(end);delta=10**12;a['before_frame']+=delta;b['before_frame']+=delta;b['after_frame']+=delta
    with patch_documents({start.resolve():a,end.resolve():b}),pytest.raises(ValueError):load(f)
def test_floating_native_plan_rejects_even_if_source_and_spec_match(closed_case):
    f=closed_case;p=f.kwargs['native_plan_path'];d=read(p);d['unbound_test_field']=True
    f.kwargs['expected_native_plan_sha256']=canonical_sha256(d)
    with patch_documents({p.resolve():d}),pytest.raises(ValueError,match='sealed native execution plan differs'):load(f)

def test_undeclared_actor_directory_rejects(closed_case):
    f=closed_case;original=Path.iterdir
    def replacement(path):
        values=list(original(path))
        if path==f.child:values.append(f.case/'native')
        return iter(values)
    with patch.object(Path,'iterdir',replacement),pytest.raises(ValueError,match='undeclared actor artifact directory'):load(f)

def test_unregistered_wild_battle_artifact_rejects(closed_case):
    f=closed_case;original=Path.glob;wild=f.child/'actor-001'
    def replacement(path,pattern):
        values=list(original(path,pattern))
        if path==wild and pattern=='battle-*':values.append(f.case/'native')
        return iter(values)
    with patch.object(Path,'glob',replacement),pytest.raises(ValueError,match='actor battle artifact census differs'):load(f)

def test_missing_registered_wild_battle_artifact_rejects(closed_case):
    f=closed_case;wild=f.child/'actor-001'
    if not list(wild.glob('battle-*')):pytest.skip('direct arm has no registered wild battle')
    original=Path.glob
    def replacement(path,pattern):
        if path==wild and pattern=='battle-*':return iter(())
        return original(path,pattern)
    with patch.object(Path,'glob',replacement),pytest.raises(ValueError,match='actor battle artifact census differs'):load(f)

def test_story_native_identity_requires_repaired_pp_flag(closed_case):
    from pokemon_red_completion import red_trainer_practice_log as logs
    f=closed_case;directory=f.child/'actor-000/battle-0001';events=directory/'events'
    summary=logs.verify_trainer_practice_event_log(events)
    p=events/'event-00001.json';d=read(p);d['payload']['identity']['pp_depleted_switch_screen']=False
    # Bypass only the independently tested event hash check, so this test reaches
    # the new identity semantic rather than succeeding on generic hash rejection.
    with patch_documents({p.resolve():d}),patch.object(logs,'verify_trainer_practice_event_log',return_value=summary),pytest.raises(ValueError,match='native event identity differs'):load(f)
@pytest.mark.parametrize('change,reason',[
    (lambda s:s.update(unsupported_extra=True),'configured source fields differ'),
    (lambda s:s.pop('configuration_sha256'),'configured source fields differ'),
    (lambda s:s.update(configuration_sha256='malformed'),None),
    (lambda s:s.update(state_sha256='0'*64),'one-child group/source membership differs'),
])
def test_configured_source_projection_rejects_unknown_missing_malformed_or_changed(closed_case,change,reason):
    f=closed_case;row=load(f).row;plan=deepcopy(f.rcc);change(plan['source'])
    original_store=f.store;record_id='rcc-plan-'+f.kwargs['declaration_sha256']
    class ChangedRecord:
        def read(self):return deepcopy(plan)
    class ChangedStore:
        def find_sealed_record(self,key,**kwargs):
            if key==record_id:return ChangedRecord()
            return original_store.find_sealed_record(key,**kwargs)
    f.store=ChangedStore()
    # Isolate this new projection guard from the separately tested upstream row
    # hash/source checks. Native execution store/file and other artifacts stay real.
    expected=pytest.raises(ValueError)if reason is None else pytest.raises(ValueError,match=reason)
    with patch.object(module,'load_challenge_consequence',return_value=row),expected:load(f)