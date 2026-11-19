from dataclasses import dataclass,replace
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion import red_story_item_storage as s,red_dig_recovery as dig
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport,GoalVerification
from pokemon_red_completion.observation import EventFlag,ItemId,RawGameState


@pytest.mark.parametrize('fault',[None,'stale','pc','bag','boxes','dex','no_fresh_offer','unverified'])
def test_legal_dig_rebinds_same_storage_goal_and_preserves_assets(monkeypatch,fault):
    ev=bytearray(320);i=int(EventFlag.GOT_MASTER_BALL);ev[i//8]|=1<<(i%8)
    bag=((int(ItemId.CARD_KEY),1),)+tuple((i,1)for i in range(80,98))
    raw=[RawGameState(True,165,20,18,2,0,event_flags=bytes(ev),bag_items=bag,player_money=127)]
    pc={};boxes=[('same_box',)];dex=[('same_dex',)];state=[b'origin'];calls=[]
    reader=N(read=lambda:raw[0],read_pc_items=lambda:tuple(pc.items()),
        read_all_box_states=lambda:boxes[0],read_pokedex_state=lambda:dex[0])
    actions=N(actions_executed=0);em=N(frame_count=0,save_state_bytes=lambda:state[0]);rt=N(reader=reader,emulator=em)
    @dataclass(frozen=True)
    class Start:
        map_id:int=165;at:tuple=(18,20);last_outside_map:int=8
        occupied:frozenset=frozenset();hazards:tuple=();mode:str='land'
    start=Start();escape=N(anchor=4,landing=(6,3))
    fresh=N()
    def quote(projected,center,*,goal_at):
        assert(projected.map_id,projected.at,projected.last_outside_map)==(4,(6,3),4)
        return N(cost=1,terminal_map=center,terminal_at=goal_at)
    def observe(r):
        assert r is reader and state[0]==b'escaped';calls.append('fresh_world');return fresh
    world=N(plan_feasible_to_map=quote,with_current_observation=observe)
    @dataclass
    class Route:
        route_world:object
    route=Route(world)
    def execute_escape(w,r,e,a,plan):
        assert(w,r,e,a,plan)==(world,reader,em,actions,escape)
        calls.append('dig');raw[0]=replace(raw[0],map_id=4,player_y=6,player_x=3)
        state[0]=b'escaped';actions.actions_executed+=3;em.frame_count+=30
        if fault=='pc':pc[99]=1
        if fault=='bag':raw[0]=replace(raw[0],bag_items=())
        if fault=='boxes':boxes[0]=('changed_box',)
        if fault=='dex':dex[0]=('changed_dex',)
        return dict(verified_escape=True,anchor_map=4,landing=[6,3])
    def bind(runtime,executor,**kw):
        assert runtime is rt and executor is actions and kw['route'].route_world is fresh
        assert kw['allow_dig_departure']is False;calls.append('rebind_storage')
        if fault=='no_fresh_offer':return None
        def execute():
            calls.append('deposit');raw[0]=replace(raw[0],map_id=141,player_y=4,player_x=13,
                bag_items=tuple(x for x in bag if x[0]!=int(ItemId.CARD_KEY)))
            pc[int(ItemId.CARD_KEY)]=1;state[0]=b'deposited';actions.actions_executed+=5;em.frame_count+=50
            return GoalExecutionReport(5,50,dict(items_conserved=True,stored_items=[int(ItemId.CARD_KEY)]))
        return N(execute=execute,verify=lambda report:GoalVerification.failed(s.GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if fault=='unverified' else GoalVerification.succeeded())
    monkeypatch.setattr(dig,'execute_dig_escape',execute_escape)
    monkeypatch.setattr(s,'completed_key_storage_binding',bind)
    monkeypatch.setattr(s,'_field_ready',lambda runtime:True)
    binding=s._completed_key_storage_via_dig(rt,actions,route=route,raw=raw[0],
        items=(int(ItemId.CARD_KEY),),pc={},start=start,escape=escape,reserved_slots=2,
        include_indigo_lobby=False,allow_spare_tm_storage=False)
    assert not calls and actions.actions_executed==em.frame_count==0
    assert binding.kind is s.GoalKind.MANAGE_STORAGE and binding.maximum_cash_debit==0
    if fault=='stale':
        state[0]=b'changed'
        with pytest.raises(ValueError,match='stale'):binding.execute()
        assert not calls
    elif fault:
        with pytest.raises(RuntimeError):binding.execute()
        assert calls[0]=='dig'
    else:
        report=binding.execute()
        assert calls==['dig','fresh_world','rebind_storage','deposit']
        assert(report.actions_executed,report.frames_executed)==(8,80)
        assert report.evidence['dig_departure']['verified_escape']and report.evidence['items_conserved']
        assert binding.verify(report).status.value=='succeeded'and raw[0].player_money==127
        with pytest.raises(ValueError,match='consumed'):binding.execute()
        state[0]=b'changed';assert binding.verify(report).status.value=='failed'


def test_storage_dig_requires_explicit_boolean():
    with pytest.raises(TypeError,match='Dig permission'):
        s.completed_key_storage_binding(None,None,route=None,allow_dig_departure=1)
