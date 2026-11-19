"""Return transport must use the carrier's observed Cut without granting other moves."""
from types import SimpleNamespace as N
import pytest
import pokemon_red_completion.red_player_party_loan as loan
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import Badge, MapId, RawGameState
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError

def route(action='cut:down',kind=MacroActionKind.FIELD_MOVE,source_mode='land',expected_mode='land'):
    return N(cost=12,steps=(N(action=action,action_kind=kind,source_mode=source_mode,expected_mode=expected_mode),))

@pytest.mark.parametrize('has_badge,has_holder,allowed',[(True,True,True),(False,True,False),(True,False,False)])
def test_pending_return_quotes_only_the_actual_observed_cut(monkeypatch,has_badge,has_holder,allowed):
    from pokemon_red_completion.gen1_traversal import CUT_CAPABILITY
    center=int(MapId.VERMILION_POKECENTER)
    raw=RawGameState(game_started=True,map_id=92,player_y=2,player_x=5,
        badge_bits=int(Badge.CASCADE)if has_badge else 0,party_count=1,party_hp=(20,),
        party_moves=((15 if has_holder else 33,0,0,0),),battle_state=0)
    runtime=N(reader=N(read=lambda:raw))
    def observer(reader,**kw):
        project=kw.get('capability_projector',lambda _:frozenset())
        return N(observe=lambda:N(capabilities=project(raw)))
    def plan(start,dest,*,goal_at):
        if dest==center and CUT_CAPABILITY in start.capabilities:return route()
        raise RoutePlanningError('No observed Cut route')
    world=N(with_current_observation=lambda _:world,plan_feasible_to_map=plan)
    calls=[]
    monkeypatch.setattr(loan,'Gen1TraversalObserver',observer)
    monkeypatch.setattr(loan,'_walk',lambda *a,**kw:calls.append((a[-2:],kw)))
    # Ordinary loans retain the legacy walking-only boundary.
    with pytest.raises(ValueError,match='no executable'):loan._reach_center(runtime,None,world)
    if allowed:
        loan._reach_center(runtime,None,world,allow_cut=True)
        assert calls==[((center,(3,3)),dict(venue_return=True,allow_cut=True))]
    else:
        with pytest.raises(ValueError,match='no executable'):loan._reach_center(runtime,None,world,allow_cut=True)
        assert not calls

@pytest.mark.parametrize('action,kind,source_mode,expected_mode',[
    ('surf:right',MacroActionKind.FIELD_MOVE,'land','water'),
    ('fly:vermilion_city',MacroActionKind.FIELD_MOVE,'land','land'),
    ('strength:activate',MacroActionKind.FIELD_MOVE,'land','land'),
    ('right',MacroActionKind.MOVE,'water','water'),
])
def test_cut_return_never_admits_other_transport(monkeypatch,action,kind,source_mode,expected_mode):
    center=int(MapId.VERMILION_POKECENTER)
    runtime=N(reader=N(read=lambda:N(map_id=92)))
    monkeypatch.setattr(loan,'Gen1TraversalObserver',lambda *a,**k:N(observe=lambda:object()))
    world=N(with_current_observation=lambda _:world,plan_feasible_to_map=lambda *a,**k:route(action,kind,source_mode,expected_mode))
    monkeypatch.setattr(loan,'_walk',lambda *a,**k:pytest.fail('Unsupported route cannot execute'))
    with pytest.raises(ValueError,match='no executable'):loan._reach_center(runtime,None,world,allow_cut=True)

def test_selected_cut_transport_uses_metered_field_port_and_rejects_surf_replan(monkeypatch):
    import pokemon_red_completion.gen1_field_moves as moves
    import pokemon_red_completion.red_native_boxed_evolution as evolution
    import pokemon_red_completion.red_training_ground_route as ground
    center=int(MapId.VERMILION_POKECENTER);position=[(92,(2,5))];port=object();actions=object()
    reader=N(read_bottom_dialogue_box_visible=lambda:False)
    runtime=N(reader=reader,emulator=object())
    current=N(observe=lambda:TraversalSnapshot(position[0][0],position[0][1],True))
    monkeypatch.setattr(loan,'Gen1TraversalObserver',lambda *a,**k:current)
    world=N(rules=N(cut_block_swaps=(N(before=1,after=2),)))
    world.with_current_observation=lambda _:world
    original=route();world.plan_feasible_to_map=lambda *a,**k:original
    def field_port(delegate,actual_reader,memory,*,cut_block_swaps):
        assert(delegate,actual_reader,memory)==(actions,reader,runtime.emulator)
        assert cut_block_swaps=={1:2}
        return port
    monkeypatch.setattr(moves,'Gen1FieldMovePort',field_port)
    monkeypatch.setattr(loan,'prepare_center_departure',lambda *a:None)
    monkeypatch.setattr(evolution,'native_evolution_pc_replanner',lambda *a:lambda request:route('surf:right'))
    recorded=[]
    monkeypatch.setattr(ground,'record_verified_field_cuts',lambda a,p:recorded.append((a,p)))
    def execute(plan,actual_port,observer,**kw):
        assert plan is original and actual_port is port and observer is current
        with pytest.raises(ValueError,match='supported walking-only'):
            kw['replanner'](object())
        position[0]=(center,(3,3))
        return N(passed=True)
    monkeypatch.setattr(loan,'execute_route',execute)
    loan._walk(runtime,actions,world,center,(3,3),allow_cut=True)
    assert recorded==[(actions,port)]

