from dataclasses import dataclass, replace
from types import SimpleNamespace as NS
import pytest
import pokemon_red_completion.red_game_corner_goals as m
import pokemon_red_completion.gen1_field_moves as fields
import pokemon_red_completion.red_collection_fly as flights
import pokemon_red_completion.red_resource_goal_router as routes
from pokemon_red_completion.observation import Badge
from pokemon_red_completion.route_plan import RoutePlanningError
from test_red_game_corner_goals import environment, offers

@dataclass(frozen=True)
class Start:
    map_id: int = 1
    at: tuple = (26, 23)
    last_outside_map: int = 1
    occupied: frozenset = frozenset({(1, 1)})
    hazards: tuple = ('old-map-only',)
    capabilities: frozenset = frozenset()
    ready: bool = True
    interruption: object = None
    mode: str = 'land'

def quote_env(monkeypatch):
    raw=NS(map_id=1,battle_state=0,badge_bits=int(Badge.THUNDER))
    reader=NS(read=lambda:raw,read_bottom_dialogue_box_visible=lambda:False,
              read_fly_destinations=lambda:(1,6))
    rt=NS(reader=reader,emulator=NS(pressed_buttons=()))
    monkeypatch.setattr(fields,'fly_menu_indices',lambda r:(0,0))
    monkeypatch.setattr(flights,'red_fly_landings',lambda rom:((6,(17,23)),))
    monkeypatch.setattr(routes,'_supported_plan',lambda *a,**k:True)
    calls=[]
    def plan(start,target,**kw):
        calls.append((start,target,kw));return NS(steps=(1,2),terminal_mode='land')
    world=NS(rom=b'fixture',plan_feasible_to_map=plan)
    return rt,world,Start(),calls

def test_private_quote_never_executes_or_invents_current_position(monkeypatch):
    rt,w,start,calls=quote_env(monkeypatch)
    result=m._quote_corner_fly(rt,w,start,135,(8,5),allowed=True)
    assert result[1:]==(6,(17,23)) and rt.reader.read().map_id==1
    projected=calls[0][0]
    assert projected.map_id==6 and projected.at==(17,23)
    assert not projected.occupied and not projected.hazards and start.occupied

@pytest.mark.parametrize('bad',('disabled','indoor','same_town','not_ready','interruption','water','wrong_source','battle','dialogue','pressed','badge','destination','holder','unreachable','unsupported'))
def test_missing_permission_or_legal_geometry_is_unavailable(monkeypatch,bad):
    rt,w,start,calls=quote_env(monkeypatch);allowed=True
    if bad=='disabled':allowed=False
    elif bad=='indoor':start=replace(start,map_id=41)
    elif bad=='same_town':start=replace(start,map_id=6)
    elif bad=='not_ready':start=replace(start,ready=False)
    elif bad=='interruption':start=replace(start,interruption='trainer')
    elif bad=='water':start=replace(start,mode='water')
    elif bad=='wrong_source':rt.reader.read().map_id=2
    elif bad=='battle':rt.reader.read().battle_state=1
    elif bad=='dialogue':rt.reader.read_bottom_dialogue_box_visible=lambda:True
    elif bad=='pressed':rt.emulator.pressed_buttons=('a',)
    elif bad=='badge':rt.reader.read().badge_bits=0
    elif bad=='destination':rt.reader.read_fly_destinations=lambda:(1,)
    elif bad=='holder':
        def missing(raw):raise fields.Gen1FieldMoveError('no holder')
        monkeypatch.setattr(fields,'fly_menu_indices',missing)
    elif bad=='unreachable':
        def missing(*a,**k):raise RoutePlanningError('blocked')
        w.plan_feasible_to_map=missing
    elif bad=='unsupported':monkeypatch.setattr(routes,'_supported_plan',lambda *a,**k:False)
    assert m._quote_corner_fly(rt,w,start,135,(8,5),allowed=allowed) is None

def test_successful_original_ground_offers_are_exact_when_opted_in(monkeypatch):
    env=environment(monkeypatch,cash=200000)
    old=offers(env)
    def forbidden(*a,**k):raise AssertionError('direct path must be retained')
    monkeypatch.setattr(m,'_quote_corner_fly',forbidden)
    new=m.game_corner_options(*env[:4],situation=__import__('test_red_live_option_menu')._situation(safety=0),model_feature_version=4,maximum_actions=10000,maximum_frames=1000000,allow_fly_transport=True)
    assert [(r.binding.binding_ref,r.candidate,r.binding.maximum_cash_debit,r.binding.estimated_effort)for r in new]==[(r.binding.binding_ref,r.candidate,r.binding.maximum_cash_debit,r.binding.estimated_effort)for r in old]

@pytest.mark.parametrize('bad',(None,'wrong_landing','wrong_receipt','cash','party','dex','boxes','dialogue','pressed'))
def test_execution_requires_native_receipt_and_resource_conservation(monkeypatch,bad):
    before=NS(map_id=1,player_y=26,player_x=23,player_money=157716,bag_items=((69,1),),badge_bits=255,party_species_ids=(35,),party_levels=(71,),party_moves=((19,64,43,31),),party_hp=(200,),party_status=(0,))
    after=NS(**vars(before));after.map_id=6;after.player_y=17;after.player_x=23
    state=[before];dex=object();boxes=object();dexes=[dex];boxstates=[boxes]
    em=NS(pressed_buttons=());reader=NS(read=lambda:state[0],read_pokedex_state=lambda:dexes[0],read_all_box_states=lambda:boxstates[0],read_bottom_dialogue_box_visible=lambda:state[0]is after and bad=='dialogue');rt=NS(reader=reader,emulator=em)
    actions=[]
    def execute(action):
        actions.append(action);state[0]=after
        if bad=='wrong_landing':after.player_x+=1
        if bad=='cash':after.player_money-=1
        if bad=='party':after.party_levels=(72,)
        if bad=='dex':dexes[0]=object()
        if bad=='boxes':boxstates[0]=object()
        if bad=='pressed':em.pressed_buttons=('a',)
        return fields.Gen1FlyReceipt(1,7 if bad=='wrong_receipt'else 6,0,0,(6,))
    monkeypatch.setattr(fields,'Gen1FieldMovePort',lambda *a,**k:NS(execute=execute))
    observer=NS(observe=lambda:NS(ready=True,mode='land',interruption=None))
    if bad is None:
        proof=m._execute_corner_fly(rt,actions,observer,(None,6,(17,23)))
        assert proof['verified']and proof['resource_party_dex_boxes_preserved']and len(actions)==1
    else:
        with pytest.raises(RuntimeError,match='arrival/resources'):m._execute_corner_fly(rt,actions,observer,(None,6,(17,23)))
