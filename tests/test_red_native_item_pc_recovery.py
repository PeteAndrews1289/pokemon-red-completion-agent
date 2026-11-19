"""Selected item evolution shares the existing bounded moving-PC recovery."""
from types import SimpleNamespace as NS
import pytest
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.route_executor import ReplanRequest, TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError
import pokemon_red_completion.red_native_boxed_evolution as level
import pokemon_red_completion.red_native_boxed_item_evolution as item


@pytest.mark.parametrize('vacates,unsafe,moving',[
    (True,False,True),(False,False,True),(True,True,True),(True,False,False)])
def test_stone_pc_transport_retains_bounded_native_recovery(monkeypatch,vacates,unsafe,moving):
    goal,other,standing=(4,13),(2,11),(5,10)
    waits,delegated=[],[]
    raw=NS(map_id=133,player_y=standing[0],player_x=standing[1],player_money=19920,
           bag_items=((34,1),),badge_bits=255,event_flags=b'',battle_state=0)
    def objects():
        return (NS(at=goal,moving=moving),)if not waits or not vacates else ()
    def observe():
        return NS(input_ready=not(unsafe and waits),raw=raw,party='party',collection_observation='dex')
    def live():
        return TraversalSnapshot(133,standing,True,mode='land',
            occupied=frozenset({goal,other}if not waits or not vacates else {other}))
    def delegate(request):
        delegated.append(request)
        if goal in request.blocked[133]:raise RoutePlanningError('PC remains occupied')
        return 'same PC route'
    world=NS(replanner=lambda:delegate,plan_feasible_to_map=lambda *a,**k:NS(segments=()))
    world.with_current_observation=lambda reader:world
    runtime=NS(reader=NS(read_current_map_objects=objects),adapter=NS(observe=observe),emulator=object())
    actions=NS(execute=lambda action:waits.append(action));traversal=NS(observe=live)
    monkeypatch.setattr(level,'Gen1TraversalObserver',lambda reader:NS(observe=live))
    monkeypatch.setattr(item,'Gen1WildFleeHandler',lambda *a,**k:object())
    request=ReplanRequest(live(),133,goal,{133:frozenset({goal,other})},1)
    def execute(plan,actual_actions,observer,**kw):
        assert actual_actions is actions and observer is traversal
        assert kw['replanner'](request)=='same PC route'
        return NS(passed=True)
    monkeypatch.setattr(item,'execute_route',execute)
    def run():return item._native_item_transport(runtime,world,actions,traversal,133,goal_at=goal)
    if not moving:
        with pytest.raises(RoutePlanningError,match='occupied'):run()
        assert not waits
    elif unsafe:
        with pytest.raises(level.context.RedGoalContextError,match='protected native'):run()
        assert len(waits)==1 and not delegated
    elif not vacates:
        with pytest.raises(level.context.RedGoalContextError,match='within its bound'):run()
        assert len(waits)==16 and not delegated
    else:
        assert run().passed and len(waits)==1
        assert delegated[0].goal_map==133 and delegated[0].goal_at==goal
        assert delegated[0].blocked[133]==frozenset({other})
        assert request.blocked[133]==frozenset({goal,other})
    assert all(a.kind is MacroActionKind.WAIT and a.repeat==120 for a in waits)
