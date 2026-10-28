"""ROM-free checks of actual configured integration and extracted gym closure."""
import ast
import copy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace as N
import pytest
from test_player_option_matchup import fixture
from pokemon_red_completion.red_player_matchup import project_current_trainer_matchups
import pokemon_red_completion.red_player_configuration as config_module


def helper_tree():
    root=Path(config_module.__file__).resolve().parents[2]
    path=root/'runtime_helpers/red_whole_player_inventory_20261006.py'
    if not path.is_file():path=root.parent/'helpers/red_whole_player_inventory_20261006.py'
    return ast.parse(path.read_text()),str(path)


def actual_gym(namespace):
    tree,path=helper_tree()
    assembly=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='assembly')
    branches=next(n for n in assembly.body if isinstance(n,ast.FunctionDef)and n.name=='branches')
    gym=next(n for n in branches.body if isinstance(n,ast.FunctionDef)and n.name=='gym')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(gym)],type_ignores=[])),path,'exec'),namespace)
    return namespace['gym']


def current():
    raw,members,w=fixture();state=b'current synthetic boundary'
    w=replace(w,source_sha256=sha256(state).hexdigest())
    boundary=N(state=state,observation=N(raw=raw))
    bindings=N(bindings=(N(binding_ref=w.binding_ref),))
    return dict(boundary=boundary,bindings=bindings,supplements=(),members=members,witnesses=(w,))


def test_current_main_and_supplement_bindings_have_same_exact_measurement():
    args=current();descriptors,proofs=project_current_trainer_matchups(**args)
    w=args['witnesses'][0]
    assert set(descriptors)==set(proofs)=={w.binding_ref}
    assert proofs[w.binding_ref]['source_sha256']==sha256(args['boundary'].state).hexdigest()
    args['supplements']=(N(binding=args['bindings'].bindings[0]),);args['bindings']=N(bindings=())
    again,_=project_current_trainer_matchups(**args);assert again==descriptors
    args['witnesses']=();assert project_current_trainer_matchups(**args)==({}, {})


@pytest.mark.parametrize('fault',['stale','unoffered','duplicate','untyped','roles'])
def test_current_join_rejects_bad_witness_or_roles(fault):
    args=current();w=args['witnesses'][0]
    if fault=='stale':args['witnesses']=(replace(w,source_sha256='f'*64),)
    elif fault=='unoffered':args['bindings']=N(bindings=())
    elif fault=='duplicate':args['witnesses']=(w,w)
    elif fault=='untyped':args['witnesses']=(N(source_sha256=w.source_sha256,binding_ref=w.binding_ref),)
    else:args['members']=args['members'][:1]
    with pytest.raises((TypeError,ValueError)):project_current_trainer_matchups(**args)


@pytest.mark.parametrize('leader,enabled',[(False,False),(False,True),(True,False),(True,True)])
def test_actual_nested_gym_keeps_only_returned_binding_witness(leader,enabled):
    calls=[];pre=N(binding_ref='preliminary');final=N(binding_ref='final')
    old_actor=object();new_actor=object();holder={'actor':old_actor,'plan':object()}
    if enabled:holder['current_matchup_witnesses']=[]
    def gym_story_option(runtime,executor,**kw):
        calls.append(kw);first=len(calls)==1;binding=pre if first else final
        if leader and first:kw['observe_leader_binding'](object(),binding)
        callback=kw.get('observe_matchup_binding')
        if callback:callback(N(binding_ref=binding.binding_ref))
        return binding,'challenge'
    ns=dict(include_rewards=False,include_matchup_observation=enabled,holder=holder,route=object(),continuous_travel=False,
        gym_trainer_actor=object(),gym_story_option=gym_story_option,leader_actor=lambda *_:new_actor)
    gym=actual_gym(ns);result=gym(N(objective_id='defeat_misty'),object(),object(),None)
    assert result[0]is(final if leader else pre)
    assert len(calls)==(2 if leader else 1)
    assert calls[0]['battler']is old_actor
    if leader:assert calls[1]['battler']is new_actor
    if enabled:assert [w.binding_ref for w in holder['current_matchup_witnesses']]==[result[0].binding_ref]
    else:assert 'current_matchup_witnesses'not in holder and all('observe_matchup_binding'not in k for k in calls)


def test_actual_nested_gym_rejects_lost_leader_identity_before_second_actor():
    def provider(*a,**kw):
        kw['observe_leader_binding'](object(),N(binding_ref='same-text'))
        return N(binding_ref='same-text'),'challenge'
    ns=dict(include_rewards=False,include_matchup_observation=True,holder={'actor':object(),'plan':object(),'current_matchup_witnesses':[]},
        route=object(),continuous_travel=False,gym_trainer_actor=object(),gym_story_option=provider,
        leader_actor=lambda *_:pytest.fail('lost first witness reached final actor'))
    with pytest.raises(ValueError,match='exact binding witness'):actual_gym(ns)(N(objective_id='defeat_misty'),None,None,None)


def test_actual_assembly_default_boolean_guard_executes_before_any_construction():
    tree,path=helper_tree();assembly=copy.deepcopy(next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='assembly'))
    # Execute actual signature and first guard; replace subsequent heavy assembly with its flag result.
    assembly.body=[assembly.body[0],ast.Return(ast.Name(id='include_matchup_observation',ctx=ast.Load()))]
    ns={};exec(compile(ast.fix_missing_locations(ast.Module(body=[assembly],type_ignores=[])),path,'exec'),ns)
    f=ns['assembly'];assert f(None,None)is False and f(None,None,include_matchup_observation=True)is True
    for invalid in (None,1,'yes'):
        with pytest.raises(ValueError,match='explicit boolean'):f(None,None,include_matchup_observation=invalid)


@pytest.mark.parametrize('version',[7,9,14,15])
def test_actual_configured_player_passes_only_V15_matchup_flag_and_keeps_config(tmp_path,monkeypatch,version):
    from test_red_player_configuration import config
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory
    import pokemon_red_completion.red_player_owned_machines as machines
    calls=[];machine_calls=[]
    monkeypatch.setattr(machines,'connect_move_change_inventory',lambda *a,**kw:machine_calls.append(kw))
    def assembly(*a,**kw):
        calls.append(kw)
        return b'unchanged',None,NativeStoryBranchInventory(lambda *_:GoalBindingSet((),()),lambda *_:()),{},dict(partition='development')
    path=tmp_path/'rom';path.write_bytes(b'not a ROM')
    cfg=config();before=cfg.to_dict()
    out=config_module.assemble_configured_player(N(assembly=assembly,c=N(ROM=path)),cfg,tmp_path,tmp_path,plan_path=tmp_path/'plan',model_feature_version=version)
    assert out[0]==b'unchanged' and cfg.to_dict()==before
    if version==15:assert calls[0]['include_matchup_observation']is True
    else:assert 'include_matchup_observation'not in calls[0]
    assert calls[0].get('include_capture_invocation',False)is(version>=13)
    assert bool(machine_calls)is(version>=10)
