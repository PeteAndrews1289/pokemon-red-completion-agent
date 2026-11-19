"""A selected decoded connection may finish its pending poison-faint text."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_gen1_route_runtime import FakeReader, raw, reader_as_real
from test_red_training_ground_route import _world

from pokemon_red_completion import red_training_ground_route as ground
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


@pytest.mark.parametrize("exit_at", [(11,89),(0,0)])
@pytest.mark.parametrize("direction,offset", [("up",(-1,0)),("down",(1,0)),
                                              ("left",(0,-1)),("right",(0,1))])
@pytest.mark.parametrize("fault", [None,"wrong_landing","wrong_departure","unplanned",
                                  "cash","pp","status","disabled"])
def test_selected_connection_faint_keeps_exact_native_endpoints(monkeypatch,direction,offset,fault,exit_at):
    arrival = (19,0)
    pending = ((exit_at[0]+offset[0]) % 256,(exit_at[1]+offset[1]) % 256)
    initial=replace(raw(),map_id=15,player_y=exit_at[0],player_x=exit_at[1],
                    party_count=2,party_species_ids=(28,5),party_hp=(54,1),
                    party_status=(0,8),party_pp=((20,),(10,)),player_money=1053)
    fake=FakeReader(initial);fake.read_all_box_states=lambda:();fake.read_pokedex_state=lambda:()
    actions=[]
    class Port:
        def execute(self,action):
            actions.append(action)
            if action.kind is MacroActionKind.CANCEL:
                fake.ready,fake.dialogue_visible,fake.moving_direction=True,False,0
                changes=dict(map_id=3,player_y=arrival[0],player_x=arrival[1])
                if fault=="wrong_landing":changes['player_x']=1
                elif fault=="cash":changes['player_money']=1054
                elif fault=="pp":changes['party_pp']=((19,),(10,))
                elif fault=="status":changes['party_status']=(8,0)
                fake.raw=replace(fake.raw,**changes)
            return action
    def observe():
        value=fake.read();return TraversalSnapshot(value.map_id,(value.player_y,value.player_x),True)
    observer=SimpleNamespace(observe=observe)
    monkeypatch.setattr(ground,"Gen1TraversalObserver",lambda *a,**k:observer)
    monkeypatch.setattr(ground,"Gen1TrainerSightProjector",lambda *a,**k:None)
    monkeypatch.setattr(ground,"Gen1FieldMovePort",lambda port,*a,**k:port)
    edge=SimpleNamespace(source_map=15,target_map=4 if fault=="unplanned" else 3,
                         passage_kind="connection",transition=SimpleNamespace(
                             exit_at=exit_at,arrival_at=arrival,action=direction))
    plan=SimpleNamespace(segments=(edge,))
    monkeypatch.setattr(StrategicScenarioRouteWorld,"plan_feasible_to_map",lambda *a,**k:plan)
    monkeypatch.setattr(StrategicScenarioRouteWorld,"replanner",lambda *a:lambda r:plan)
    receipts=[]
    def execute(selected,port,traversal,*,interruption_handler,**kwargs):
        assert selected is plan
        fake.dialogue_visible,fake.moving_direction=True,4
        source=(pending[0],pending[1]+1) if fault=="wrong_departure" else pending
        fake.raw=replace(initial,player_y=source[0],player_x=source[1],
                         party_hp=(54,0),party_status=(0,0))
        receipts.append(interruption_handler.handle(
            TraversalSnapshot(15,source,False,"scripted_dialogue")))
    monkeypatch.setattr(ground,"execute_route",execute)
    transition=ground.RedVermilionGroundTransition(b"rom",_world(),destination_map=3,
        destination_at=arrival,allow_wild_faints=True,allow_field_faint_dialogue=fault!="disabled")
    if fault:
        with pytest.raises(RouteExecutionError):transition(Port(),reader_as_real(fake),SimpleNamespace(pressed_buttons=()))
        assert not receipts
    else:
        transition(Port(),reader_as_real(fake),SimpleNamespace(pressed_buttons=()))
        assert len(receipts)==1
        receipt=receipts[0]
        assert(receipt.resumed_map,receipt.resumed_at)==(3,arrival)
        assert receipt.details['new_fainted_slots']==[2]
        assert receipt.details['model_queries']==0
        assert receipt.allows_map_transition and receipt.allows_relocation
        assert[action.kind for action in actions]==[MacroActionKind.CANCEL,MacroActionKind.WAIT]
