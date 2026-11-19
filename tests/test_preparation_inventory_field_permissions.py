"""The actual inventory quote admits only the executor's legal water edge."""
import ast
from pathlib import Path
from types import SimpleNamespace as N
from dataclasses import replace
import pytest
from test_preparation_route_capability_parity import raw
from pokemon_red_completion.red_training_ground_route import ground_route_capability_projector
from pokemon_red_completion.gen1_traversal import SURF_CAPABILITY
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError

@pytest.mark.parametrize("surf,holder,badge,forced,admitted",[
 (True,True,True,False,True),(False,True,True,False,False),
 (True,False,True,False,False),(True,True,False,False,False),
 (True,True,True,True,False)])
def test_inventory_can_quote_supported_water_venue_without_bypassing_permissions(surf,holder,badge,forced,admitted):
 path=Path(__file__).parents[1]/"runtime_helpers/red_whole_player_inventory_20261006.py"
 tree=ast.parse(path.read_text())
 assembly=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=="assembly")
 preparation=next(n for n in assembly.body if isinstance(n,ast.FunctionDef)and n.name=="preparation")
 statement=next(n for n in preparation.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=="start"for t in n.targets))
 observed=replace(raw(),party_hp=(50,)if holder else(0,),badge_bits=255 if badge else 0)
 memory=N(read_u8=lambda _:1<<5 if forced else 0)
 reader=N(read=lambda:observed)
 hazard=object();calls=[]
 def observer(actual_reader,*,capability_projector,hazard_projector):
  assert actual_reader is reader and hazard_projector is hazard
  calls.append(1)
  return N(observe=lambda:TraversalSnapshot(observed.map_id,(observed.player_y,observed.player_x),True,capabilities=capability_projector(observed)))
 scope=dict(Gen1TraversalObserver=observer,ground_route_capability_projector=ground_route_capability_projector,
  Gen1TrainerSightProjector=lambda rom,r,**kw:hazard,rt=N(reader=reader,emulator=memory),route=N(allow_surf=surf),rom=b"fixture")
 exec(compile(ast.Module(body=[statement],type_ignores=[]),str(path),"exec"),scope)
 def quote_water_venue(snapshot):
  if SURF_CAPABILITY not in snapshot.capabilities:raise RoutePlanningError("water edge requires native Surf permission")
  return "existing stronger venue"
 if admitted:assert quote_water_venue(scope["start"])=="existing stronger venue"
 else:
  with pytest.raises(RoutePlanningError):quote_water_venue(scope["start"])
 assert calls==[1] and reader.read()==observed
