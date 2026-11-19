"""Native water arrival composes the existing guarded land passage."""
from dataclasses import replace
from types import SimpleNamespace as N
import pytest
from test_red_observed_preparation_corridor import setup_transport,preferred,HOME,TARGET
from pokemon_red_completion import gen1_route_runtime
from pokemon_red_completion.gen1_traversal import SURF_CAPABILITY
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError

def fixture(monkeypatch,*,allow=True,permission=True,land=True,return_ok=True,passage_ok=True):
 run,route,world,raw,calls,records,emulator=setup_transport(monkeypatch,off_map=True)
 raw.mode="land";original=world._quote
 def quote(start,goal_map,goal_at,blocked):
  if start.map_id==HOME and goal_map==TARGET and goal_at is None:
   return N(terminal_map=TARGET,terminal_at=(3,0),terminal_mode="water",steps=("native-water-map-arrival",))
  if start.mode=="water" and goal_map==TARGET:
   if not passage_ok:raise RoutePlanningError("land passage blocked")
   assert SURF_CAPABILITY in start.capabilities
   return N(terminal_map=TARGET,terminal_at=goal_at,terminal_mode="land",steps=("native-disembark-route",))
  if goal_map==HOME and not return_ok:raise RoutePlanningError("return blocked")
  return original(start,goal_map,goal_at,blocked)
 monkeypatch.setattr(world,"_quote",quote)
 original_call=type(route).__call__
 def native(self,actions,reader,em):
  original_call(self,actions,reader,em)
  raw.mode="water"if self.destination_map==TARGET and self.destination_at==(3,0)else("land"if land else"water")
 monkeypatch.setattr(type(route),"__call__",native)
 def observe():
  return TraversalSnapshot(raw.map_id,(raw.player_y,raw.player_x),True,mode=raw.mode,capabilities=frozenset({SURF_CAPABILITY})if permission else frozenset())
 monkeypatch.setattr(gen1_route_runtime,"Gen1TraversalObserver",lambda *a,**kw:N(observe=observe))
 return lambda:run(allow_surf=allow),calls,records,raw

def test_legal_water_arrival_proves_land_passage_and_recovery_before_search(monkeypatch):
 run,calls,records,raw=fixture(monkeypatch)
 corridor=run()
 assert corridor.source_id==preferred().source_id and corridor.map_id==TARGET
 assert raw.mode=="land" and calls==[(TARGET,(3,0)),(TARGET,preferred().origin_at),(TARGET,preferred().origin_at)]
 evidence=records[0][1]
 assert evidence["component_passage_used"] and evidence["native_map_entry_used"]
 assert evidence["recovery_map"]==HOME
 assert (corridor.maximum_legs,corridor.maximum_seek_steps,corridor.maximum_encounters)==(19,17,2)

@pytest.mark.parametrize("fault",["land_only","no_permission","unlanded","no_return","no_passage"])
def test_water_arrival_never_grants_permission_or_skips_land_and_return_checks(monkeypatch,fault):
 run,calls,records,_=fixture(monkeypatch,allow=fault!="land_only",permission=fault!="no_permission",land=fault!="unlanded",return_ok=fault!="no_return",passage_ok=fault!="no_passage")
 with pytest.raises((ValueError,RoutePlanningError)):run()
 assert len(calls)==(2 if fault=="unlanded"else 1)
 assert records==[]
