"""Native healing is an exact resource transition, separate from flag-only entry."""
from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_purified_wild_escape import encounter, flags

from pokemon_red_completion import wild_party_flee as w
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_route_runtime import Gen1WildFleeHandler
from pokemon_red_completion.observation import BattleMenuPhase, EventFlag
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


def pair(ups=0):
    source = encounter()
    source = replace(source, party_hp=(39, 130, 65, 70), first_party_hp=39, active_party_hp=39,
                     party_status=(0, 64, 0, 0),
                     party_pp=(((ups << 6) | 1, 0, 0, 0),) * 4)
    result = replace(source, battle_state=0, battle_result=2,
                     event_flags=flags(EventFlag.IN_PURIFIED_ZONE),
                     party_hp=source.party_max_hp, first_party_hp=40, active_party_hp=40,
                     party_status=(0,) * 4,
                     party_pp=(((ups << 6) | (35 + 7 * ups), 0, 0, 0),) * 4)
    return source, result


@pytest.mark.parametrize('ups', range(4))
def test_exact_native_heal_preserves_earned_pp_up_capacity_and_default_refusal(ups):
    before, after = pair(ups)
    assert w.purified_zone_escape_event(before, after) is None
    with pytest.raises(ValueError):
        w.validate_flee_party(before, after, allow_native_purified_transition=True)
    w.validate_flee_party(before, after, allow_native_purified_transition=True,
                         allow_native_purified_healing=True)
    proof = w.purified_zone_escape_event(before, after, allow_healing=True)
    assert proof['resources_restored'] and proof['after']
    assert proof['healing_performed_by_handler'] is False
    assert before.party_hp != after.party_hp and before.party_pp != after.party_pp


@pytest.mark.parametrize('fault', ['map', 'tile', 'drift', 'flag', 'extra_event', 'still_battle',
    'wrong_result', 'enemy', 'stats', 'species', 'level', 'moves', 'cash', 'bag', 'badge',
    'partial_hp', 'partial_pp', 'status', 'pp_ups', 'bad_source_pp', 'bad_source_status',
    'bad_source_hp', 'blackout'])
def test_native_heal_never_admits_other_changes(fault):
    before, after = pair()
    if fault == 'map':before, after = replace(before,map_id=145),replace(after,map_id=145)
    elif fault == 'tile':before, after = replace(before,player_x=9),replace(after,player_x=9)
    elif fault == 'drift':after = replace(after,player_x=10)
    elif fault == 'flag':after = replace(after,event_flags=flags())
    elif fault == 'extra_event':after = replace(after,event_flags=flags(EventFlag.IN_PURIFIED_ZONE,271))
    elif fault == 'still_battle':after = replace(after,battle_state=1)
    elif fault == 'wrong_result':after = replace(after,battle_result=1)
    elif fault == 'enemy':after = replace(after,enemy_species_id=25)
    elif fault == 'stats':after = replace(after,party_stats=((41,40,40,40),)*4)
    elif fault == 'species':after = replace(after,party_species_ids=(25,)*4)
    elif fault == 'level':after = replace(after,party_levels=(99,)*4)
    elif fault == 'moves':after = replace(after,party_moves=((1,0,0,0),)*4)
    elif fault == 'cash':after = replace(after,player_money=after.player_money+1)
    elif fault == 'bag':after = replace(after,bag_items=((1,1),))
    elif fault == 'badge':after = replace(after,badge_bits=after.badge_bits+1)
    elif fault == 'partial_hp':after = replace(after,party_hp=(39,140,66,71))
    elif fault == 'partial_pp':after = replace(after,party_pp=((34,0,0,0),)*4)
    elif fault == 'status':after = replace(after,party_status=(0,64,0,0))
    elif fault == 'pp_ups':after = replace(after,party_pp=((64+42,0,0,0),)*4)
    elif fault == 'bad_source_pp':before = replace(before,party_pp=((63,0,0,0),)*4)
    elif fault == 'bad_source_status':before = replace(before,party_status=(128,)*4)
    elif fault == 'bad_source_hp':before = replace(before,party_hp=(41,130,65,70))
    elif fault == 'blackout':before = replace(before,party_hp=(0,)*4)
    with pytest.raises(ValueError):
        w.validate_flee_party(before, after, allow_native_purified_transition=True,
                             allow_native_purified_healing=True)


@pytest.mark.parametrize('value', [1, None, 'yes'])
def test_healing_is_explicit_and_not_truthy(value):
    before, after = pair()
    with pytest.raises(TypeError,match='healing allowance'):
        w.validate_flee_party(before,after,allow_native_purified_healing=value)


@pytest.mark.parametrize('fault', [None, 'individual', 'xp', 'box', 'dex'])
def test_executor_verifies_deep_native_custody_before_admitting_healing(monkeypatch,fault):
    before, after = pair();current=[before];inputs=[];events=[];reads=[]
    def custody(*_):
        data=['individual',100,'box','dex']
        if current[0].battle_state==0 and fault is not None:
            data[{'individual':0,'xp':1,'box':2,'dex':3}[fault]]='changed'
        reads.append(tuple(data));return tuple(data)
    monkeypatch.setattr(w,'_purified_party_custody',custody)
    def execute(action):
        inputs.append(action.kind)
        if action.kind is MacroActionKind.CONFIRM:current[0]=after
    reader=N(read=lambda:current[0],read_input_readiness=lambda:N(ready=True),
        read_battle_menu_state=lambda _:N(phase=BattleMenuPhase.MAIN,selected_main_command=3),
        trainer_engagement_active=lambda:False)
    actions=N(execute=execute,record_diagnostic_event=lambda kind,row:events.append((kind,row)))
    handler=Gen1WildFleeHandler(actions,reader,maximum_flees=1,stabilization_frames=24,
        allow_party_faints=True,allow_field_faint_dialogue=True,emulator=object())
    boundary=TraversalSnapshot(146,(9,11),False,'wild_battle')
    if fault is not None:
        with pytest.raises(RouteExecutionError,match='custody'):handler.handle(boundary)
        assert not events and not handler.evidence
    else:
        result=handler.handle(boundary)
        proof=result.details['native_field_event']
        assert proof['resources_restored'] and proof['individual_xp_box_dex_custody_verified']
        assert len(reads)>=2 and len(events)==1 and len(handler.evidence)==1
        assert inputs==[MacroActionKind.CONFIRM,MacroActionKind.WAIT,MacroActionKind.WAIT]


def test_healing_requires_the_exact_transition_permission():
    before,after=pair()
    with pytest.raises(ValueError,match='location transition'):
        w.validate_flee_party(before,after,allow_native_purified_healing=True)


@pytest.mark.parametrize('fault',[None,'missing_custody','wrong_map','wrong_tile','wrong_event',
    'no_entry','injected_heal','wrong_hp','wrong_pp','capacity','wrong_receipt_map','ko_exit'])
def test_receipt_requires_the_complete_matching_heal_certificate(fault):
    from pokemon_red_completion.route_1_wild import Route1WildFleeEvidence
    before,after=pair();proof=w.purified_zone_escape_event(before,after,allow_healing=True)
    proof['individual_xp_box_dex_custody_verified']=True
    if fault=='missing_custody':proof.pop('individual_xp_box_dex_custody_verified')
    elif fault=='wrong_map':proof['map_id']=145
    elif fault=='wrong_tile':proof['at']=[9,12]
    elif fault=='wrong_event':proof['event_flag']+=1
    elif fault=='no_entry':proof['before']=True
    elif fault=='injected_heal':proof['healing_performed_by_handler']=True
    elif fault=='wrong_hp':proof['hp_after'][0]-=1
    elif fault=='wrong_pp':proof['pp_after'][0][0]-=1
    elif fault=='capacity':proof['pp_after'][0][0]=64+42
    receipt=Route1WildFleeEvidence(1,0,0 if fault=='ko_exit'else 2,
        145 if fault=='wrong_receipt_map'else 146,146,11,9,17,22,
        sum(before.party_hp),sum(after.party_hp),True,True,True,False,False,True,1,24,
        hp_scope='whole_party',native_purified_healing=proof)
    assert receipt.verified is (fault is None)
    if fault is None:
        assert not receipt.pp_preserved and receipt.final_hp>receipt.initial_hp
        assert receipt.public_dict()['native_purified_healing']==proof
