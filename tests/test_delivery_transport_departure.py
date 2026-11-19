"""ROM-free shared delivery transport quote/executor departure parity."""
import ast
from dataclasses import dataclass,replace
from functools import partial
from pathlib import Path
from types import SimpleNamespace as N
import sys
import pytest
from pokemon_red_completion.route_plan import RoutePlanningError


@dataclass(frozen=True)
class Start:
    map_id:int
    at:tuple=(3,5)
    last_outside_map:int=9
    ready:bool=True
    interruption:object=None
    mode:str='land'
    occupied:frozenset=frozenset({(5,5)})
    hazards:tuple=('current-observation',)


def load_quote(monkeypatch,start,*,departure=None,fly=True,town=2,target=59,cave=False,supported=True,arrival_failure=False):
    source=Path(__file__).resolve().parents[1]/'runtime_helpers/red_mixed_postgame_delivery_20261009.py'
    tree=ast.parse(source.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='quoted_native_arrival')
    calls=[];raw=object();reader=N(read=lambda:raw,read_fly_destinations=lambda:(town,))
    class World:
        rom=b'no-native-ROM'
        def with_current_observation(self,r):
            assert r is reader;calls.append(('observe',));return self
        def plan_feasible_to_map(self,origin,destination,*,goal_at):
            calls.append(('arrival',origin,destination,goal_at))
            if arrival_failure:raise RoutePlanningError('fixture route unavailable')
            return N(terminal_mode='land',steps=(object(),),terminal_map=destination,terminal_at=goal_at)
    world=World()
    def preview(origin,w,r):
        assert origin==start and w is world and r is raw;calls.append(('departure',));return departure
    prep=N(source_field_capabilities=lambda *a:frozenset(),same_cave_transit=lambda a,b:cave,native_fly_usable=lambda r:fly,source_departure=preview)
    monkeypatch.setitem(sys.modules,'red_current_source_preparation_20261004',prep)
    import pokemon_red_completion.red_collection_fly as fly_module
    import pokemon_red_completion.red_resource_goal_router as router_module
    monkeypatch.setattr(fly_module,'red_fly_landings',lambda rom:((town,(9,10)),))
    monkeypatch.setattr(router_module,'_supported_plan',lambda plan,**kw:supported)
    env=dict(Gen1TraversalObserver=lambda r,**kw:N(observe=lambda:start),partial=partial,replace=replace,RoutePlanningError=RoutePlanningError)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),env)
    runtime=N(reader=reader,emulator=object())
    return lambda:env['quoted_native_arrival'](runtime,world,town=town,map_id=target,at=(2,4)),calls


@pytest.mark.parametrize('source_map',[60,177,245,246,247,248,249])
def test_unsupported_indoor_remote_offer_fails_closed_before_arrival_projection(monkeypatch,source_map):
    quote,calls=load_quote(monkeypatch,Start(source_map),departure=None,fly=True)
    assert quote()is None
    assert calls==[('observe',),('departure',)]


def test_no_special_League_blacklist_when_existing_departure_is_supported(monkeypatch):
    dep=N(terminal_map=9,terminal_at=(7,8),terminal_mode='land')
    quote,calls=load_quote(monkeypatch,Start(245),departure=dep,town=2,fly=True)
    assert quote()is not None
    origin=calls[-1][1];assert origin.map_id==2 and origin.at==(9,10)


def test_same_town_indoor_source_quotes_actual_exit_and_does_not_require_Fly(monkeypatch):
    dep=N(terminal_map=2,terminal_at=(4,6),terminal_mode='land')
    quote,calls=load_quote(monkeypatch,Start(60),departure=dep,town=2,target=59,fly=False)
    assert quote()is not None
    origin=calls[-1][1];assert origin.map_id==2 and origin.at==(4,6)and origin.last_outside_map==2
    assert origin.occupied==frozenset()and origin.hazards==()


def test_supported_indoor_foreign_town_uses_existing_Fly_branch(monkeypatch):
    dep=N(terminal_map=3,terminal_at=(4,6),terminal_mode=None)
    quote,calls=load_quote(monkeypatch,Start(60),departure=dep,town=2,target=59,fly=True)
    assert quote()is not None
    origin=calls[-1][1];assert origin.map_id==2 and origin.at==(9,10)and origin.mode=='land'


def test_same_cave_transit_neither_departs_nor_projects_Fly(monkeypatch):
    start=Start(194)
    quote,calls=load_quote(monkeypatch,start,departure=None,fly=False,town=9,target=198,cave=True)
    assert quote()is not None
    assert calls==[('observe',),('arrival',start,198,(2,4))]


def test_local_indoor_target_does_not_require_departure_or_Fly(monkeypatch):
    start=Start(59)
    quote,calls=load_quote(monkeypatch,start,departure=None,fly=False,target=59)
    assert quote()is not None
    assert calls==[('observe',),('arrival',start,59,(2,4))]


def test_ordinary_outdoor_town_keeps_existing_quote(monkeypatch):
    start=Start(2)
    quote,calls=load_quote(monkeypatch,start,departure=None,fly=False,town=2,target=59)
    assert quote()is not None
    assert calls==[('observe',),('arrival',start,59,(2,4))]


def test_ordinary_foreign_outdoor_source_keeps_existing_Fly_projection(monkeypatch):
    quote,calls=load_quote(monkeypatch,Start(3),town=2,target=59,fly=True)
    assert quote()is not None
    assert calls[-1][1].map_id==2 and calls[-1][1].at==(9,10)
    assert not any(c[0]=='departure'for c in calls)


@pytest.mark.parametrize('fault',['unready','interrupted','water'])
def test_existing_control_restrictions_fail_closed(monkeypatch,fault):
    start=Start(245,ready=fault!='unready',interruption='scene'if fault=='interrupted'else None,mode='water'if fault=='water'else'land')
    quote,calls=load_quote(monkeypatch,start,fly=True)
    assert quote()is None and calls==[]


@pytest.mark.parametrize('failure',[False,True])
def test_arrival_still_requires_existing_supported_plan(monkeypatch,failure):
    quote,calls=load_quote(monkeypatch,Start(2),supported=False,arrival_failure=failure)
    assert quote()is None and calls[-1][0]=='arrival'

def test_foreign_outdoor_without_Fly_keeps_existing_conservative_rejection(monkeypatch):
    quote,calls=load_quote(monkeypatch,Start(3),town=2,target=59,fly=False)
    assert quote()is None and calls==[('observe',)]


def test_foreign_indoor_without_Fly_is_not_turned_into_new_walking_offer(monkeypatch):
    dep=N(terminal_map=3,terminal_at=(4,6),terminal_mode='land')
    quote,calls=load_quote(monkeypatch,Start(60),departure=dep,town=2,target=59,fly=False)
    assert quote()is None and calls==[('observe',),('departure',)]