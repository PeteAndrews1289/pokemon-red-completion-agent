"""Off-camera does not mean the moving nurse-stance blocker has vacated."""
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion import red_native_boxed_evolution as module
from pokemon_red_completion.route_executor import ReplanRequest,TraversalSnapshot

@pytest.mark.parametrize("vacates_after",[1,3,None])
def test_waiter_checks_map_wide_objects_when_goal_is_outside_camera(monkeypatch,vacates_after):
 goal=(3,3);other=(5,12);waits=[];calls=[]
 raw=N(map_id=133,player_y=4,player_x=13,player_money=100,bag_items=((1,1),),badge_bits=255,event_flags=b"same",battle_state=0)
 def objects():
  return (N(at=goal,moving=True),N(at=other,moving=False))if vacates_after is None or len(waits)<vacates_after else(N(at=other,moving=False),)
 rt=N(reader=N(read_current_map_objects=objects),adapter=N(observe=lambda:N(input_ready=True,raw=raw,party="same party",collection_observation="same dex")))
 snapshot=TraversalSnapshot(133,(4,13),True,mode="land",occupied=frozenset({other}))
 monkeypatch.setattr(module,"Gen1TraversalObserver",lambda _:N(observe=lambda:snapshot))
 def delegate(request):
  assert not any(o.at==goal for o in objects()),"offscreen NPC was still there"
  assert request.goal_at==goal and request.current.at==(4,13)
  assert (6,10)in request.blocked[133]and other in request.blocked[133]and goal not in request.blocked[133]
  calls.append(request);return "same legal walking route"
 world=N(replanner=lambda:delegate,with_current_observation=lambda _:world)
 actions=N(execute=lambda a:waits.append(a))
 request=ReplanRequest(snapshot,133,goal,{133:frozenset({goal,other,(6,10)})},1)
 if vacates_after is None:
  with pytest.raises(module.context.RedGoalContextError,match="within its bound"):module.native_evolution_pc_replanner(rt,world,actions)(request)
  assert len(waits)==16 and calls==[]
 else:
  assert module.native_evolution_pc_replanner(rt,world,actions)(request)=="same legal walking route"
  assert len(waits)==vacates_after and len(calls)==1
 assert all(a.kind.value=="wait"and a.repeat==120 for a in waits)
 assert request.blocked[133]==frozenset({goal,other,(6,10)})
