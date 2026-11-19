"""Collection-route purification is independent of field-faint dialogue authority."""
from dataclasses import replace
from types import SimpleNamespace as N
import pytest
from test_purified_wild_escape import encounter, flags
from test_purified_wild_healing import pair
from pokemon_red_completion import wild_party_flee as wild
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import BattleMenuPhase,EventFlag
from pokemon_red_completion.red_routed_recovery import guarded_collection_route_handler
from pokemon_red_completion.route_executor import RouteExecutionError,TraversalSnapshot

def fixture(monkeypatch,*,healing=False,fault=None):
    before,after=pair()if healing else(encounter(),None)
    if after is None:after=replace(before,battle_state=0,battle_result=2,event_flags=flags(EventFlag.IN_PURIFIED_ZONE))
    if fault=='other_event':after=replace(after,event_flags=flags(EventFlag.IN_PURIFIED_ZONE,271))
    elif fault=='map':before,after=replace(before,map_id=145),replace(after,map_id=145)
    elif fault=='tile':before,after=replace(before,player_x=12),replace(after,player_x=12)
    elif fault=='cash':after=replace(after,player_money=after.player_money+1)
    elif fault=='bag':after=replace(after,bag_items=((1,1),))
    elif fault=='badge':after=replace(after,badge_bits=after.badge_bits+1)
    elif fault=='level':after=replace(after,party_levels=(26,45,25,26))
    elif fault=='native_poison':after=replace(after,event_flags=before.event_flags,party_status=(8,0,0,0))
    current=[before];inputs=[];events=[]
    def custody(*_):
        data=['individual',100,'box','dex']
        if current[0].battle_state==0 and fault in('individual','xp','box','dex'):data[{'individual':0,'xp':1,'box':2,'dex':3}[fault]]='changed'
        return tuple(data)
    monkeypatch.setattr(wild,'_purified_party_custody',custody)
    def execute(action):
        inputs.append(action.kind)
        if action.kind is MacroActionKind.CONFIRM:current[0]=after
    actions=N(execute=execute,record_diagnostic_event=lambda k,v:events.append((k,v)))
    reader=N(read=lambda:current[0],read_input_readiness=lambda:N(ready=True),read_battle_menu_state=lambda _:N(phase=BattleMenuPhase.MAIN,selected_main_command=3),trainer_engagement_active=lambda:False)
    handler=guarded_collection_route_handler(actions,reader,route_name='guarded collection purification test',maximum_flees=1,allow_wild_faints=True,emulator=object())
    return handler,TraversalSnapshot(before.map_id,(before.player_y,before.player_x),False,'wild_battle'),inputs,events

@pytest.mark.parametrize('healing',[False,True])
def test_collection_transport_certifies_purification_without_field_faint_authority(monkeypatch,healing):
    handler,boundary,inputs,events=fixture(monkeypatch,healing=healing)
    assert not handler.allow_field_faints and 'scripted_dialogue'not in handler.handled_interruption_kinds
    result=handler.handle(boundary)
    proof=result.details['native_field_event']
    assert result.details['verified']and proof['after']and proof['event']=='IN_PURIFIED_ZONE'
    assert proof.get('resources_restored',False)is healing
    if healing:assert proof['individual_xp_box_dex_custody_verified']
    assert len(events)==1 and events[0][0]=='native_purified_zone_escape'
    assert inputs==[MacroActionKind.CONFIRM,MacroActionKind.WAIT,MacroActionKind.WAIT]
    with pytest.raises(RouteExecutionError,match='flee budget'):handler.handle(boundary)

@pytest.mark.parametrize('fault',['other_event','map','tile','cash','bag','badge','level'])
def test_collection_purification_does_not_waive_unrelated_changes(monkeypatch,fault):
    handler,boundary,_,events=fixture(monkeypatch,fault=fault)
    with pytest.raises(RouteExecutionError):handler.handle(boundary)
    assert not events and not handler.inner.wild_evidence

@pytest.mark.parametrize('fault',['individual','xp','box','dex'])
def test_collection_healing_still_requires_native_individual_and_storage_custody(monkeypatch,fault):
    handler,boundary,_,events=fixture(monkeypatch,healing=True,fault=fault)
    with pytest.raises(RouteExecutionError,match='custody'):handler.handle(boundary)
    assert not events and not handler.inner.wild_evidence

def test_uncertified_native_poison_still_requires_recovery(monkeypatch):
    from pokemon_red_completion.goal_manager_runtime import GoalRecoveryRequired
    handler,boundary,_,events=fixture(monkeypatch,fault='native_poison')
    with pytest.raises(GoalRecoveryRequired,match='status recovery'):handler.handle(boundary)
    assert not events

@pytest.mark.parametrize('value',[1,None,'yes'])
def test_purification_capability_requires_a_boolean(value):
    from pokemon_red_completion.gen1_route_runtime import Gen1WildFleeHandler
    with pytest.raises(TypeError,match='purification opt-in'):
        Gen1WildFleeHandler(N(),N(),maximum_flees=1,stabilization_frames=24,allow_native_purification=value)

@pytest.mark.parametrize('party,emulator',[(False,None),(True,None),(False,object())])
def test_purification_capability_requires_its_guarded_native_owner(party,emulator):
    from pokemon_red_completion.gen1_route_runtime import Gen1WildFleeHandler
    with pytest.raises(ValueError,match='guarded party escape'):
        Gen1WildFleeHandler(N(),N(),maximum_flees=1,stabilization_frames=24,allow_party_faints=party,emulator=emulator,allow_native_purification=True)
