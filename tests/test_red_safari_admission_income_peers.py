import ast,sys,types
from pathlib import Path
from dataclasses import dataclass,replace
from enum import Enum

def test_safari_admission_income_demand_and_qualified_execution(monkeypatch):
    tree=ast.parse((Path(__file__).resolve().parents[1]/'runtime_helpers/red_whole_player_inventory_20261006.py').read_bytes());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='safari_admission_income_peers')
    class Kind(Enum):RESUPPLY='resupply';OTHER='other'
    class Battler:
     model_sha256='model';qualification_sha256='qualification'
     def run(self):raise AssertionError('inventory must not execute')
    @dataclass
    class Runtime:
     adapter:object;profile:object=None;trainer_battle_runner:object=None;trainer_battle_model_sha256:object=None;trainer_battle_qualification_sha256:object=None;trainer_funding_recovery:bool=False;trainer_funding_ledges:bool=False;trainer_funding_surf:bool=False;trainer_funding_indoor_departure:bool=False
    state=dict(cash=477,budget=types.SimpleNamespace(shortfall=23,target_cash=500),rows=[],calls=[],quote_calls=0,fly=False)
    def quote(*a):state['quote_calls']+=1;return state['budget']
    mod=types.ModuleType('pokemon_red_completion.red_autonomous_safari');mod.autonomous_safari_funding_quote=quote
    monkeypatch.setitem(sys.modules,'pokemon_red_completion.red_autonomous_safari',mod)
    def gate(*a,include_legal_fly=False):return 'fly'if include_legal_fly and state['fly']else None
    class Router:
     def __init__(self,rt,actions,world,**kw):
      assert rt.trainer_battle_runner.__self__.model_sha256=='model';state['calls'].append(kw)
     def enumerate_routed_kinds(self,*a):return types.SimpleNamespace(bindings=state['rows'])
    ns=dict(replace=replace,FrozenTrainerBattler=Battler,FROZEN_K_SHA256='model',K_QUALIFICATION_SHA256='qualification',supply_profile=lambda p,**k:p,bind_ordinary_trainer_funding_profile=lambda p:p,RedResourceGoalRouter=Router,bind_resupply_fly_profile=lambda p:p,GoalKind=Kind,_postgame_funding_gate_transit=gate)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'frozen_income_function','exec'),ns);f=ns[fn.name];rt=Runtime(types.SimpleNamespace(observe=lambda:types.SimpleNamespace(raw=types.SimpleNamespace(player_money=state['cash']))));b=Battler();checks=[]
    def run():return f(rt,None,None,battler=b)
    for cash in(None,500,8000):
     state['cash']=cash;assert run()==()and not state['calls']and state['quote_calls']==0;checks.append('no demand '+str(cash))
    state['cash']=477;state['budget']=None;assert run()==()and not state['calls'];checks.append('ineligible Safari')
    state['budget']=types.SimpleNamespace(shortfall=0,target_cash=500);assert run()==()and not state['calls'];checks.append('no shortfall')
    state['budget']=types.SimpleNamespace(shortfall=23,target_cash=500);b.model_sha256='wrong';assert run()==()and not state['calls'];checks.append('wrong model');b.model_sha256='model';b.qualification_sha256='wrong';assert run()==()and not state['calls'];checks.append('wrong qualification');b.qualification_sha256='qualification'
    def row(kind=Kind.RESUPPLY,income=1000,purchase=0):return types.SimpleNamespace(kind=kind,resource_quote=types.SimpleNamespace(expected_income=income,purchase_cost=purchase))
    good=row();state['rows']=[good,row(income=0),row(purchase=1),row(kind=Kind.OTHER)];assert run()==(good,);assert state['calls'][-1]['trainer_funding_target_cash']==500;checks.append('only legal positive pure income retained')
    state['rows']=[];state['calls']=[];state['fly']=True;assert run()==()and len(state['calls'])==2 and state['calls'][-1]['funding_gate_transit']=='fly';checks.append('existing legal Fly fallback')
