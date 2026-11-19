"""PROPOSAL: ROM-free prepared-Master transport quote tests.
Root sets MASTER_HELPER_UNDER_TEST to the applied helper (or reviewed proposal).
Only the real prepared_master_binding AST is loaded; no legacy module bootstraps,
emulator, model, ROM, executable closure or native method is run by these tests.
"""
import ast
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType, SimpleNamespace as N
from unittest.mock import patch
import pytest

DEFAULT = Path(__file__).resolve().parents[1] / 'scripts/runtime_helpers/red_mixed_static_options_20261009.py'

@dataclass(frozen=True)
class Start:
    map_id: int
    at: tuple = (3,5)
    last_outside_map: int = 9
    occupied: frozenset = frozenset({(7,7)})
    hazards: tuple = ('native-hazard',)
    ready: bool = True
    interruption: object = None
    mode: str = 'land'

class RoutePlanningError(ValueError): pass
class FlyError(ValueError): pass


def fixture_quote(start, *, target_map=200, departure=None, same_cave=False,
                  fly=True, route_error=False, supported=True):
    calls=[];landings=[];planned=[]
    raw=N(fly=fly)
    reader=N(read_fly_destinations=lambda:(3,),read=lambda:raw)
    runtime=N(reader=reader)
    fresh=N(rom=object())
    def plan(origin,map_id,*,goal_at):
        calls.append('plan');planned.append(origin)
        if route_error:raise RoutePlanningError('unsupported destination')
        return N(terminal_mode='land',steps=(1,),cost=1,terminal_at=goal_at)
    fresh.plan_feasible_to_map=plan
    def current(got):
        assert got is reader;calls.append('fresh');return fresh
    world=N(rom=fresh.rom,with_current_observation=current)
    def depart(origin,got_world,got_raw):
        assert origin is start and got_world is fresh and got_raw is raw
        calls.append('departure');return departure
    def menu_indices(got):
        assert got is raw;calls.append('fly-menu')
        if not fly:raise FlyError('no living Fly holder')
        return 0,0
    def landing(rom):
        assert rom is fresh.rom;calls.append('landing');landings.append(rom)
        return ((3,(8,9)),)
    parent=ModuleType('pokemon_red_completion');parent.__path__=[]
    modules={'pokemon_red_completion':parent}
    def module(name,**attrs):
        m=ModuleType(name);m.__dict__.update(attrs);modules[name]=m
    module('pokemon_red_completion.red_collection_fly',red_fly_landings=landing)
    module('pokemon_red_completion.red_routed_static_capture',prepared_static_acquisition_binding=lambda *a,**kw:N(**kw))
    module('pokemon_red_completion.red_resource_goal_router',_supported_plan=lambda *a,**kw:supported)
    module('pokemon_red_completion.gen1_field_moves',fly_menu_indices=menu_indices,Gen1FieldMoveError=FlyError)
    module('pokemon_red_completion.observation',MapId=N(CERULEAN_POKECENTER=64))
    module('red_current_source_preparation_20261004',source_departure=depart,same_cave_transit=lambda a,b:same_cave)
    source=Path(os.environ.get('MASTER_HELPER_UNDER_TEST',str(DEFAULT)))
    parsed=ast.parse(source.read_text());fn=next(x for x in parsed.body if isinstance(x,ast.FunctionDef)and x.name=='prepared_master_binding')
    isolated=ast.Module(body=[fn],type_ignores=[]);ast.fix_missing_locations(isolated)
    namespace=dict(replace=replace,RoutePlanningError=RoutePlanningError)
    # No source module is imported; only this dependency-injected function runs.
    exec(compile(isolated,str(source),'exec'),namespace)
    with patch.dict(sys.modules,modules):
        value=namespace['prepared_master_binding'](runtime,N(raw=raw),N(),world,N(map_id=target_map,at=(4,4)),Path('/not-created'),N(observe=lambda:start))
    return value,calls,planned,landings


def test_oneway_agatha_does_not_quote_a_fictitious_fly_landing():
    result,calls,planned,landings=fixture_quote(Start(245),departure=None)
    assert result is None and calls==['fresh','departure']
    assert not planned and not landings


def test_supported_indoor_departure_precedes_unchanged_virtual_fly_geometry():
    departure=N(terminal_map=1,terminal_at=(2,3),terminal_mode='land')
    result,calls,planned,_=fixture_quote(Start(245),departure=departure)
    assert result is not None and calls[:4]==['fresh','departure','fly-menu','landing']
    assert planned and all(x.map_id==3 and x.at==(8,9)for x in planned)
    assert all(not x.occupied and not x.hazards for x in planned)


def test_ordinary_outdoor_quote_keeps_prior_cerulean_landing():
    result,calls,planned,_=fixture_quote(Start(1))
    assert result is not None and calls[:3]==['fresh','fly-menu','landing']
    assert all(x.map_id==3 and x.at==(8,9)for x in planned)
    assert 'departure'not in calls


def test_foreign_outdoor_missing_fly_remains_conservatively_unavailable():
    result,calls,planned,landings=fixture_quote(Start(1),fly=False)
    assert result is None and calls==['fresh','fly-menu']and not planned and not landings


def test_same_town_needs_no_fly_or_departure():
    start=Start(3)
    result,calls,planned,landings=fixture_quote(start,fly=False)
    assert result is not None and calls[0]=='fresh'and set(calls)=={'fresh','plan'}
    assert not landings and all(x is start for x in planned)


def test_same_target_indoor_map_stays_local_without_departure_or_fly():
    start=Start(200)
    result,calls,planned,landings=fixture_quote(start,fly=False)
    assert result is not None and set(calls)=={'fresh','plan'}
    assert not landings and all(x is start for x in planned)


def test_existing_same_cave_branch_does_not_invent_departure_or_flight():
    start=Start(194)
    result,calls,planned,landings=fixture_quote(start,target_map=198,same_cave=True,fly=False)
    assert result is not None and set(calls)=={'fresh','plan'}
    assert not landings and all(x is start for x in planned)


def test_departure_already_at_fly_town_uses_real_terminal_without_flight():
    departure=N(terminal_map=3,terminal_at=(1,2),terminal_mode=None)
    result,calls,planned,landings=fixture_quote(Start(245),departure=departure,fly=False)
    assert result is not None and calls[:2]==['fresh','departure']and not landings
    assert all(x.map_id==3 and x.at==(1,2)and x.mode=='land'for x in planned)


@pytest.mark.parametrize('fault',['unreachable','unsupported'])
def test_existing_destination_and_supported_plan_rejections_are_retained(fault):
    result,_,_,_=fixture_quote(Start(1),route_error=fault=='unreachable',supported=fault!='unsupported')
    assert result is None