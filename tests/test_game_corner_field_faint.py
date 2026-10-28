"""Coin purchases retain ordinary native faint losses through guarded travel."""
from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from test_red_game_corner_goals import environment,coin_offers,offers
from test_gen1_route_runtime import FakeReader,reader_as_real
from test_red_routed_recovery import make_test_raw
from pokemon_red_completion import red_game_corner_goals as module
from pokemon_red_completion import red_game_corner_resources as resources
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_route_runtime import Gen1WildFleeHandler
from pokemon_red_completion.route_executor import TraversalSnapshot,RouteExecutionError

@pytest.mark.parametrize("fault",[None,"cash","unknown_dialogue"])
def test_coin_trip_settles_only_native_poison_faint_before_exact_purchase(monkeypatch,fault):
    env=environment(monkeypatch,cash=5029,coins=20,owned=(7,63))
    runtime,_,actions,_,payload=env
    runtime.emulator.frame_count=0;runtime.emulator.pressed_buttons=()
    monkeypatch.setattr(module,"authenticate_coin_vendor",resources.authenticate_coin_vendor)
    native=make_test_raw(map_id=197,x=12,y=26,hp=(1,100),status=(8,0))
    fake=FakeReader(native,moving_direction=0)
    fake.read_all_box_states=lambda:();fake.read_pokedex_state=lambda:()
    presses=[];receipts=[]
    class Port:
        def execute(self,action):
            presses.append(action);actions.actions_executed+=1
            runtime.emulator.frame_count+=max(1,action.repeat)
            if action.kind is MacroActionKind.CANCEL:
                fake.dialogue_visible=False;fake.moving_direction=0
                if fault=="cash":fake.raw=replace(fake.raw,player_money=999)
    def transition(**options):
        def execute(*_):
            handler=Gen1WildFleeHandler(Port(),reader_as_real(fake),maximum_flees=options["maximum_flees"],allow_party_faints=options.get("allow_wild_faints",False),allow_field_faint_dialogue=options.get("allow_field_faint_dialogue",False),stabilization_frames=24)
            fake.raw=replace(native,party_hp=(1 if fault=="unknown_dialogue"else 0,100),party_status=(0,0));fake.dialogue_visible=True
            receipts.append(handler.handle(TraversalSnapshot(197,(26,12),False,"scripted_dialogue")))
            payload[0]+=b"native faint retained"
        return execute
    monkeypatch.setattr(module,"RedVermilionGroundTransition",transition)
    monkeypatch.setattr(module,"face_pc_boundary",lambda *_:None)
    purchases=[]
    def buy(*_,**__):
        purchases.append(True)
        runtime.reader.state=replace(runtime.reader.state,player_money=runtime.reader.state.player_money-1000)
        runtime.reader.coins+=50;actions.actions_executed+=8;runtime.emulator.frame_count+=80;payload[0]+=b"lot"
    monkeypatch.setattr(module,"buy_coin_lot",buy)
    binding=coin_offers(env)[0].binding
    if fault:
        with pytest.raises(RouteExecutionError):binding.execute()
        assert not purchases and runtime.reader.coins==20
        if fault=="unknown_dialogue":assert not presses
    else:
        report=binding.execute()
        assert binding.verify(report).status.value=="succeeded"
        assert len(purchases)==5 and runtime.reader.state.player_money==29 and runtime.reader.coins==270
        assert fake.raw.party_hp==(0,100) and receipts[0].details["native_field_faint"]
        assert report.evidence["registration_credit"]is False
        assert report.actions_executed==42 and len(presses)==2

@pytest.mark.parametrize("kind",["coin_case","prize"])
def test_other_game_corner_transport_uses_same_guarded_faint_contract(monkeypatch,kind):
    env=environment(monkeypatch,case=kind!="coin_case")
    seen=[]
    def capture(**options):seen.append(options);return NS()
    monkeypatch.setattr(module,"RedVermilionGroundTransition",capture)
    assert offers(env)
    assert len(seen)==1 and seen[0]["allow_wild_faints"]is True and seen[0]["allow_field_faint_dialogue"]is True
    assert not seen[0].get("maximum_scripted_dialogues",0)
