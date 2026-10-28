"""ROM-free live-geometry and shared-transport contracts; no emulator/model."""
from dataclasses import dataclass,field,replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge,LocalGraph,find_local_path,without_coordinates
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
from pokemon_red_completion.red_living_dex_wild_corridor import (
    RedLivingDexWildCorridor,RedLivingDexWildCorridorError,derive_red_living_dex_wild_corridor,
)
from pokemon_red_completion.route_executor import TraversalSnapshot,TraversalHazard
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion import red_wild_preparation as w
from pokemon_red_completion import gen1_route_runtime,gen1_trainer_sight

TARGET=int(MapId.ROUTE_2)
HOME=int(MapId.PEWTER_POKECENTER)
SOURCE='wild:Route2:grass'

def terrain():
    grass=tuple(tuple((y,x)in{(2,1),(3,1),(2,4),(3,4)}for x in range(6))for y in range(6))
    return Terrain(map_id=TARGET,tileset=0,walkable=tuple((True,)*6 for _ in range(6)),
                   grass=grass,water=tuple((False,)*6 for _ in range(6)),tiles=tuple((0,)*6 for _ in range(6)))

def graph(*,connected=False):
    edges={}
    for y in range(6):
        for x in range(6):
            outgoing=[]
            for dy,dx,action in ((-1,0,'up'),(1,0,'down'),(0,-1,'left'),(0,1,'right')):
                ny,nx=y+dy,x+dx
                if 0<=ny<6 and 0<=nx<6 and(connected or(x<3)==(nx<3)):
                    outgoing.append(LocalEdge((ny,nx),action))
            edges[(y,x)]=tuple(outgoing)
    return LocalGraph(edges)

def preferred():
    return RedLivingDexWildCorridor(SOURCE,TARGET,(3,4),(2,4),maximum_legs=19,maximum_seek_steps=17,maximum_encounters=2)

def test_preferred_valid_pair_keeps_exact_object_and_caps_over_other_ranked_pair():
    selected=preferred();g=graph(connected=True);t=terrain();target=RedEncounterSourceTarget(SOURCE)
    default=derive_red_living_dex_wild_corridor(target,t,g,reachable_from=(3,0))
    assert default.origin_at==(3,1)
    actual=derive_red_living_dex_wild_corridor(target,t,g,reachable_from=(3,0),preferred_corridor=selected)
    assert actual is selected

def test_preferred_stale_pair_is_not_kept_across_disconnected_observed_component():
    selected=preferred()
    actual=derive_red_living_dex_wild_corridor(RedEncounterSourceTarget(SOURCE),terrain(),graph(),reachable_from=(3,0),preferred_corridor=selected)
    assert actual.origin_at==(3,1) and selected.origin_at==(3,4)

@pytest.mark.parametrize('fault',['occupied','hazard','missing_reverse_edge','not_encounter_tile'])
def test_preferred_pair_must_pass_every_existing_geometry_constraint(fault):
    selected=preferred();g=graph(connected=True);t=terrain();blocked=()
    if fault in {'occupied','hazard'}:blocked=(selected.origin_at,)
    if fault=='missing_reverse_edge':
        g=LocalGraph({at:tuple(e for e in es if not(at==selected.terminal_at and e.target==selected.origin_at))for at,es in g.edges.items()})
    if fault=='not_encounter_tile':
        t=replace(t,grass=tuple(tuple(False if(y,x)==selected.origin_at else v for x,v in enumerate(row))for y,row in enumerate(t.grass)))
    actual=derive_red_living_dex_wild_corridor(RedEncounterSourceTarget(SOURCE),t,g,reachable_from=(3,0),excluded=blocked,preferred_corridor=selected)
    assert actual.origin_at==(3,1)

def test_wrong_preferred_source_or_type_fails_without_retargeting():
    wrong=replace(preferred(),source_id='wild:Route11:grass',map_id=int(MapId.ROUTE_11))
    for selected in (wrong,object()):
        with pytest.raises(RedLivingDexWildCorridorError,match='preferred corridor source'):
            derive_red_living_dex_wild_corridor(RedEncounterSourceTarget(SOURCE),terrain(),graph(),preferred_corridor=selected)

@dataclass
class World:
    terrain:dict
    local_graphs:dict
    macro_graph:object=field(default_factory=lambda:MacroGraph({HOME:(),TARGET:()}))
    observed_maps:list=field(default_factory=list)
    quotes:list=field(default_factory=list)
    fallback_calls:list=field(default_factory=list)
    fail_bounded:bool=False
    wrong_entry_map:bool=False
    fail_return:bool=False

    def with_current_observation(self,reader):
        self.observed_maps.append(reader.read().map_id)
        return self

    def _quote(self,start,goal_map,goal_at,blocked):
        if goal_map!=start.map_id:
            if goal_at is None:
                return NS(terminal_map=HOME if self.wrong_entry_map else goal_map,terminal_at=(3,0),terminal_mode='land',steps=('native-map-passage',))
            assert goal_map==HOME
            if self.fail_return:raise RoutePlanningError('synthetic return route unavailable')
            return NS(terminal_map=goal_map,terminal_at=goal_at,terminal_mode='land',steps=('native-return-passage',))
        try:
            path=find_local_path(without_coordinates(self.local_graphs[goal_map],blocked),start.at,goal_at,capabilities=start.capabilities,start_mode='land',goal_mode='land')
        except Exception as exc:
            raise RoutePlanningError('synthetic local route unavailable')from exc
        return NS(terminal_map=goal_map,terminal_at=goal_at,terminal_mode='land',steps=path.edges)

    def plan_feasible_to_map(self,start,goal_map,*,goal_at=None):
        self.quotes.append((start.map_id,goal_map,goal_at))
        if self.fail_bounded:raise RoutePlanningError('bounded quote fixture failed')
        return self._quote(start,goal_map,goal_at,start.occupied|frozenset(h.at for h in start.hazards))

    def _plan_candidate(self,start,goal_map,*,goal_at=None,blocked=None):
        self.fallback_calls.append(blocked)
        return self._quote(start,goal_map,goal_at,blocked[start.map_id])

@dataclass
class Route:
    route_world:World
    raw:object
    calls:list
    observe_terrain:bool=True
    full_event_offsets:bool=True
    excluded_maps:frozenset=frozenset()
    allow_complete_cut_search:bool=False
    trainer_binding_factory:object=None
    allow_surf:bool=False
    rom:bytes=b'synthetic-non-indoor'
    destination_map:int=TARGET
    destination_at:tuple=(3,4)
    fail_call:object=None

    def __call__(self,actions,reader,emulator):
        self.calls.append((self.destination_map,self.destination_at))
        if self.fail_call is not None:raise self.fail_call
        self.raw.map_id=self.destination_map
        self.raw.player_y,self.raw.player_x=self.destination_at

def setup_transport(monkeypatch,*,off_map=False,connected=False,ready=True,interruption=None,hazards=(),occupied=frozenset()):
    raw=NS(map_id=HOME if off_map else TARGET,player_y=3,player_x=0,battle_state=0)
    reader=NS(read=lambda:raw);emulator=NS(pressed_buttons=frozenset());calls=[];records=[]
    world=World({TARGET:terrain()},{TARGET:graph(connected=connected)})
    route=Route(world,raw,calls)
    def observe():
        return TraversalSnapshot(map_id=raw.map_id,at=(raw.player_y,raw.player_x),ready=ready,
                                 interruption=interruption,mode='land',occupied=occupied,hazards=hazards)
    monkeypatch.setattr(gen1_route_runtime,'Gen1TraversalObserver',lambda *a,**kw:NS(observe=observe))
    monkeypatch.setattr(gen1_trainer_sight,'Gen1TrainerSightProjector',lambda *a,**kw:NS(full_event_offsets=kw['full_event_offsets']))
    def run(**changes):
        return w.transport_to_observed_preparation_corridor(NS(),reader,emulator,route=replace(route,**changes),corridor=preferred(),record=lambda k,v:records.append((k,v)),recovery_map=HOME,recovery_at=(3,3))
    return run,route,world,raw,calls,records,emulator

def test_off_map_transport_uses_ordinary_entry_then_live_component_and_original_caps(monkeypatch):
    run,route,world,raw,calls,records,_=setup_transport(monkeypatch,off_map=True)
    actual=run()
    assert calls==[(TARGET,(3,0)),(TARGET,(3,1))]
    assert world.quotes==[(HOME,TARGET,None),(TARGET,TARGET,(3,1)),(TARGET,HOME,(3,3))]
    assert world.observed_maps==[HOME,TARGET]
    assert actual.source_id==SOURCE and actual.map_id==TARGET
    assert(actual.maximum_legs,actual.maximum_seek_steps,actual.maximum_encounters)==(19,17,2)
    assert records[0][1]['planned_corridor']==preferred().private_dict()
    assert records[0][1]['corridor_rebound']and records[0][1]['native_map_entry_used']

def test_same_map_transport_skips_entry_and_preserves_valid_old_pair(monkeypatch):
    run,_,world,_,calls,records,_=setup_transport(monkeypatch,connected=True)
    actual=run()
    assert calls==[(TARGET,preferred().origin_at)]and actual==preferred()
    assert world.quotes==[(TARGET,TARGET,preferred().origin_at),(TARGET,HOME,(3,3))]
    assert not records[0][1]['native_map_entry_used']and not records[0][1]['corridor_rebound']

@pytest.mark.parametrize('fault',['not_ready','interrupted','pressed','battle'])
def test_unsafe_boundary_is_rejected_before_any_transport(monkeypatch,fault):
    run,_,_,raw,calls,_,emulator=setup_transport(monkeypatch,ready=fault!='not_ready',interruption='wild_battle'if fault=='interrupted'else None)
    if fault=='pressed':emulator.pressed_buttons=frozenset({'down'})
    if fault=='battle':raw.battle_state=1
    with pytest.raises(ValueError,match='settled land|observation changed'):run()
    assert calls==[]

def test_occupied_or_hazardous_only_current_pair_fails_without_source_escape(monkeypatch):
    run,_,world,_,calls,_,_=setup_transport(monkeypatch,hazards=(TraversalHazard(at=(3,1),kind='trainer_sight'),))
    with pytest.raises(RedLivingDexWildCorridorError,match='no unobstructed'):run()
    assert calls==[]and not world.fallback_calls

def test_failed_transport_exception_is_not_caught_or_retried(monkeypatch):
    run,_,_,_,calls,records,_=setup_transport(monkeypatch,off_map=True);error=RuntimeError('native travel failed with paid partial progress')
    with pytest.raises(RuntimeError)as caught:run(fail_call=error)
    assert caught.value is error and len(calls)==1 and records==[]

def test_wrong_macro_arrival_quote_is_rejected_before_input(monkeypatch):
    run,_,world,_,calls,_,_=setup_transport(monkeypatch,off_map=True);world.wrong_entry_map=True
    with pytest.raises(ValueError,match='entry quote differs'):run()
    assert calls==[]

@pytest.mark.parametrize('allow_complete',[False,True])
def test_existing_complete_cut_opt_in_is_preserved_for_arrival_and_local_quote(monkeypatch,allow_complete):
    run,_,world,_,calls,_,_=setup_transport(monkeypatch,off_map=True);world.fail_bounded=True
    if allow_complete:
        actual=run(allow_complete_cut_search=True)
        assert actual.origin_at==(3,1)and len(world.fallback_calls)==3 and len(calls)==2
    else:
        with pytest.raises(RoutePlanningError,match='bounded quote'):run()
        assert not world.fallback_calls and not calls

def test_complete_cut_fallback_keeps_existing_learned_trainer_hazard_policy(monkeypatch):
    trainer=TraversalHazard(at=(5,5),kind='trainer_sight');other=TraversalHazard(at=(4,5),kind='rock')
    run,_,world,_,_,_,_=setup_transport(monkeypatch,off_map=True,hazards=(trainer,other));world.fail_bounded=True
    run(allow_complete_cut_search=True,trainer_binding_factory=lambda:None)
    assert all((5,5)not in blocked[next(iter(blocked))]and(4,5)in blocked[next(iter(blocked))]for blocked in world.fallback_calls)

def test_excluded_venue_is_rejected_before_transport(monkeypatch):
    run,_,_,_,calls,_,_=setup_transport(monkeypatch,off_map=True)
    with pytest.raises(ValueError,match='destination excluded'):run(excluded_maps=frozenset({TARGET}))
    assert calls==[]


def test_missing_return_route_rejects_refreshed_lane_before_any_local_input(monkeypatch):
    run,_,world,_,calls,records,_=setup_transport(monkeypatch)
    world.fail_return=True
    with pytest.raises(RoutePlanningError,match='return route unavailable'):run()
    assert calls==[]and records==[]

def test_observed_transport_retains_exact_existing_recovery_destination(monkeypatch):
    run,_,world,_,calls,records,_=setup_transport(monkeypatch,off_map=True)
    run()
    assert world.quotes[-1]==(TARGET,HOME,(3,3))
    event=records[0][1]
    assert event['recovery_map']==HOME and event['recovery_at']==(3,3)
    assert event['return_quote_steps']==1 and len(calls)==2
