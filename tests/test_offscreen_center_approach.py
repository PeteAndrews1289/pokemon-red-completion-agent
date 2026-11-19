"""An initial local return can approach its off-camera moving goal safely."""
from types import SimpleNamespace as N
from dataclasses import replace
import pytest
from pokemon_red_completion import red_native_boxed_evolution as module,red_player_party_loan as loan
from pokemon_red_completion.route_executor import ReplanRequest,TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError

@pytest.mark.parametrize("fault",[None,"no_route","cut","other_map","unsafe","no_optin"])
def test_initial_offscreen_approach_reuses_legal_same_map_walk_and_original_goal(monkeypatch,fault):
 raw=N(map_id=133,player_y=4,player_x=13,player_money=123,bag_items=((1,1),),badge_bits=255,event_flags=b"same",battle_state=0)
 moves=[];waits=[];delegates=[]
 def observed():return N(input_ready=True,raw=N(**vars(raw)),party="same party",collection_observation="same dex")
 def objects():return(N(at=(3,3),moving=True,visible=bool(moves)),)if not waits else()
 runtime=N(reader=N(read_current_map_objects=objects),adapter=N(observe=observed))
 def snapshot():return TraversalSnapshot(133,(raw.player_y,raw.player_x),True,mode="land",occupied=frozenset({(3,3)})if moves and not waits else frozenset())
 monkeypatch.setattr(module,"Gen1TraversalObserver",lambda _:N(observe=snapshot))
 def plan(start,destination,*,goal_at):
  assert start.at==(4,13)and destination==133 and goal_at!=(3,3)
  if fault=="no_route":raise RoutePlanningError("blocked")
  return N(cost=abs(goal_at[0]-4)+abs(goal_at[1]-13),macro_path=N(maps=(133,1,133)if fault=="other_map"else(133,)),terminal_at=goal_at,terminal_mode="land",walking=fault!="cut")
 def delegate(request):
  assert moves and waits and request.current.at==moves[-1]and request.goal_at==(3,3)
  delegates.append(request);return"same final nurse goal"
 world=N(replanner=lambda:delegate,with_current_observation=lambda _:world,plan_feasible_to_map=plan)
 monkeypatch.setattr(__import__('pokemon_red_completion.red_resource_goal_router',fromlist=['_walking_plan']),"_walking_plan",lambda p:p.walking)
 def walk(rt,actions,current,destination,at):
  assert rt is runtime and current is world and destination==133 and at!=(3,3)
  moves.append(at);raw.player_y,raw.player_x=at
  if fault=="unsafe":raw.player_money-=1
 monkeypatch.setattr(loan,"_walk",walk)
 actions=N(execute=lambda action:waits.append(action))
 request=ReplanRequest(snapshot(),133,(3,3),{133:frozenset()},1)
 if fault=="no_optin":
  # Preserve default: no movement inside an in-flight replan.
  with pytest.raises(AssertionError):module.native_evolution_pc_replanner(runtime,world,actions)(request)
  assert moves==[]
 elif fault:
  with pytest.raises(module.context.RedGoalContextError):module.native_evolution_pc_replanner(runtime,world,actions,allow_offscreen_approach=True)(request)
  assert not delegates and not waits
 else:
  assert module.native_evolution_pc_replanner(runtime,world,actions,allow_offscreen_approach=True)(request)=="same final nurse goal"
  assert moves==[(3,4)]and len(waits)==1 and len(delegates)==1
 assert request.current.at==(4,13)and request.goal_at==(3,3)
