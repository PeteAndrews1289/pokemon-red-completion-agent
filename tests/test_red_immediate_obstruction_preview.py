"""ROM-free contract regression tests for the isolated immediate-obstruction proposal."""
import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_gym as gym
from pokemon_red_completion import red_player_story_obstruction as obstacle
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalVerification
from pokemon_red_completion.red_gym_reward import KOGA_REWARD
from pokemon_red_completion.red_story_battle import StoryTrainerContract


def binding(name='exact'):
    return ExecutableGoalBinding(name, GoalKind.ADVANCE_STORY, .1, .1,
        lambda: pytest.fail('inventory must not execute input'),
        lambda _: GoalVerification.succeeded())


def contract(map_id=157):
    return StoryTrainerContract('defeat_koga', 'observed-story-obstruction',
        map_id, (202, 2, 3), 321, 500)


@pytest.mark.parametrize('admitted', [False, True])
def test_obstruction_witness_only_follows_admitted_exact_binding(monkeypatch, admitted):
    raw = N(map_id=157)
    runtime = N(reader=N(read=lambda:raw, read_current_map_objects=lambda:()))
    exact, result, actor = contract(), binding(), object()
    order=[]
    monkeypatch.setattr(obstacle, '_field_ready', lambda _:True)
    monkeypatch.setattr(obstacle, 'Gen1TraversalObserver', lambda *a,**k:N(observe=lambda:object()))
    monkeypatch.setattr(obstacle, 'Gen1TrainerSightProjector', lambda *a,**k:None)
    monkeypatch.setattr(obstacle, 'trainer_headers', lambda *a,**k:())
    monkeypatch.setattr(obstacle, 'map_object_events', lambda *a:())
    monkeypatch.setattr(obstacle, 'trainer_sight_zones', lambda *a:())
    monkeypatch.setattr(obstacle, 'blocking_story_trainers', lambda *a,**k:
        (N(trainer=N(event_flag=321), approach=N(cost=1)),))
    monkeypatch.setattr(obstacle.StoryTrainerContract, 'from_cartridge', lambda *a,**k:exact)
    def resolve(c):
        assert c is exact
        order.append('actor')
        return actor
    def bind(*args, **kwargs):
        assert kwargs['contract'] is exact and kwargs['battler'] is actor
        assert kwargs['completes_objective'] is False
        order.append('bind')
        return result if admitted else None
    def observe(c,b):
        assert c is exact and b is result and order==['actor','bind']
        order.append('observe')
    monkeypatch.setattr(obstacle, 'story_battle_binding', bind)
    actions=N(actions_executed=0)
    got=obstacle.obstructing_story_battle_binding(runtime,actions,
        objective_id='defeat_koga',route=N(rom=b'rom',route_world=object()),
        battler=object(),trainer_battler_for_contract=resolve,observe_binding=observe)
    assert got is (result if admitted else None)
    assert order == ['actor','bind']+(['observe'] if admitted else [])
    assert actions.actions_executed==0


@pytest.mark.parametrize('module,method,keyword', [
    (obstacle,'obstructing_story_battle_binding','observe_binding'),
    (gym,'gym_story_option','observe_leader_binding'),
])
def test_invalid_observer_rejected_before_runtime_observation(module, method, keyword):
    kwargs=dict(route=None,battler=None,**{keyword:object()})
    kwargs.update(dict(objective_id='defeat_koga') if module is obstacle else
                  dict(reward=KOGA_REWARD,preparation_plan=None))
    with pytest.raises(TypeError,match='observer must be callable'):
        getattr(module,method)(None,None,**kwargs)


def gym_setup(monkeypatch, *, frontier=False, no_combat=False):
    raw=N(map_id=15 if frontier else 157,event_flags=bytes(256),bag_items=())
    rt=N(reader=N(read=lambda:raw),emulator=object(),adapter=N(
        observe=lambda:N(game_state=object()),
        graph=N(available_objectives=lambda _:(N(id='defeat_koga'),))))
    monkeypatch.setattr(gym,'_field_ready',lambda _:True)
    monkeypatch.setattr(gym.GymReward,'contract',lambda *a:object())
    monkeypatch.setattr(gym,'story_battle_binding',lambda *a,**k:None)
    monkeypatch.setattr(gym,'story_travel_binding',lambda *a,**k:None)
    monkeypatch.setattr(gym,'map_object_events',lambda *a:(N(object_index=1,y=10,x=4),))
    members=(N(purpose=gym.PreparationPurpose.FIELD_UTILITY,observation=N(level=1)),
             N(purpose=gym.PreparationPurpose.UNDECIDED,observation=N(level=99)))
    if not no_combat:
        members += tuple(N(purpose=gym.PreparationPurpose.COMBAT,observation=N(level=x))
                         for x in (40,44))
    monkeypatch.setattr(gym,'observe_preparation_members',lambda *a:members)
    quotes=[]
    def quote(rom,klass,index):
        assert rom==b'rom' and (klass,index)==(202,3), 'must not quote Koga for obstruction'
        quotes.append((klass,index))
        return N(party=(N(level=18),N(level=19)))
    monkeypatch.setattr(gym,'trainer_party_quote',quote)
    return rt,raw,quotes


@pytest.mark.parametrize('frontier',[False,True])
@pytest.mark.parametrize('no_combat',[False,True])
def test_exact_local_or_frontier_obstruction_has_only_its_own_semantic_roster(
        monkeypatch,frontier,no_combat):
    rt,raw,quotes=gym_setup(monkeypatch,frontier=frontier,no_combat=no_combat)
    exact,result=contract(raw.map_id),binding()
    resolver=object(); attempts=[];leaders=[]
    def obstacle_quote(*a,**kw):
        assert kw['trainer_battler_for_contract'] is resolver
        attempts.append(kw)
        kw['observe_binding'](exact,result)
        return result
    # A callable marker whose identity is preserved, never invoked by the gym.
    def resolver(_):
        pytest.fail('gym must not resolve the obstruction actor itself')
    monkeypatch.setattr(gym,'obstructing_story_battle_binding',obstacle_quote)
    row=gym.gym_story_option(rt,object(),reward=KOGA_REWARD,
        route=N(rom=b'rom'),battler=object(),preparation_plan=object(),
        trainer_battler_for_contract=resolver,
        observe_leader_binding=lambda *x:leaders.append(x))
    selected,challenge=row
    assert selected.execute is result.execute
    assert selected.story_objective_ref=='defeat_koga'
    assert challenge.combat_required
    assert challenge.opposition_known is (not no_combat)
    assert not leaders
    if no_combat:
        assert not quotes
        assert challenge.opponent_fraction==challenge.maximum_level_deficit==0
    else:
        assert quotes==[(202,3)]
        assert challenge.opponent_fraction==2/6
        assert challenge.maximum_level_deficit==pytest.approx(-.23)
        assert challenge.median_level_deficit==pytest.approx(-.235)
        assert set(vars(challenge)) == {'combat_required','opposition_known','opponent_fraction',
                                      'maximum_level_deficit','median_level_deficit'}
    assert len(attempts)==1
    assert attempts[0].get('frontier',False) is frontier


@pytest.mark.parametrize('fault',['wrong_map','wrong_objective','leader_substitution','defeated','wrong_binding'])
def test_obstruction_preview_cannot_borrow_wrong_or_stale_witness(monkeypatch,fault):
    rt,raw,quotes=gym_setup(monkeypatch)
    exact=contract(); result=binding()
    if fault=='wrong_map': exact=replace(exact,map_id=156)
    if fault=='wrong_objective': exact=replace(exact,objective_id='defeat_blaine')
    if fault=='leader_substitution': exact=replace(exact,battle_plan_id='koga-leader')
    if fault=='defeated':
        events=bytearray(256);events[321//8]|=1<<(321%8);raw.event_flags=bytes(events)
    def obstacle_quote(*a,**kw):
        kw['observe_binding'](exact,result if fault!='wrong_binding' else binding('other'))
        return result
    monkeypatch.setattr(gym,'obstructing_story_battle_binding',obstacle_quote)
    with pytest.raises(ValueError,match='obstruction witness'):
        gym.gym_story_option(rt,object(),reward=KOGA_REWARD,route=N(rom=b'rom'),
            battler=object(),preparation_plan=object())
    assert not quotes


def test_failed_direction_probe_does_not_hide_next_exact_obstruction(monkeypatch):
    rt,raw,quotes=gym_setup(monkeypatch)
    result=binding();attempts=[]
    def obstruction(*a,**kw):
        attempts.append(kw['destination_at'])
        if len(attempts)==1:return None
        kw['observe_binding'](contract(),result)
        return result
    monkeypatch.setattr(gym,'obstructing_story_battle_binding',obstruction)
    row=gym.gym_story_option(rt,object(),reward=KOGA_REWARD,route=N(rom=b'rom'),
        battler=object(),preparation_plan=object())
    assert row[1].opposition_known and len(attempts)==2 and quotes==[(202,3)]


def production_gym():
    """Execute actual nested provider body with mocked services, not a copied algorithm."""
    path=Path(gym.__file__).resolve().parents[2]/'runtime_helpers/red_whole_player_inventory_20261006.py'
    if not path.is_file():
        path=Path(gym.__file__).resolve().parents[3]/'helpers/red_whole_player_inventory_20261006.py'
    tree=ast.parse(path.read_text())
    funcs=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='gym']
    assert len(funcs)==1
    return ast.Module(body=[funcs[0]],type_ignores=[])


@pytest.mark.parametrize('component,known',[('obstruction',True),('leader',True),('leader',False),('travel',False)])
def test_production_provider_uses_direct_leader_witness_not_opposition_known(component,known):
    ordinary,leader,plan,resolver=object(),object(),object(),object()
    first,second=binding('first'),binding('second')
    calls=[];qualified=[];runtime=object();route=object()
    def option(rt,executor,**kw):
        assert rt is runtime and kw['route'] is route
        assert kw['trainer_battler_for_contract'] is resolver
        calls.append(kw['battler'])
        out=first if len(calls)==1 else second
        if component=='leader' and 'observe_leader_binding' in kw:
            kw['observe_leader_binding'](object(),out)
        return out,N(opposition_known=known)
    def leader_actor(reward,rt):
        assert rt is runtime
        qualified.append(reward)
        return leader
    env=dict(include_rewards=False,include_matchup_observation=False,gym_story_option=option,route=route,
        holder={'actor':ordinary,'plan':plan},continuous_travel=False,
        gym_trainer_actor=resolver,leader_actor=leader_actor)
    exec(compile(production_gym(),'<production gym provider>','exec'),env)
    result=env['gym'](KOGA_REWARD,runtime,object(),None)
    assert calls==([ordinary,leader] if component=='leader' else [ordinary])
    assert qualified==([KOGA_REWARD] if component=='leader' else [])
    assert result[0] is (second if component=='leader' else first)


