from types import SimpleNamespace as N
from dataclasses import asdict
import pytest
from pokemon_red_completion.red_native_player import _ordinary_retained_capture_loss
from pokemon_red_completion.red_static_capture import RedStaticCaptureTarget
from pokemon_red_completion.observation import EventFlag
from pokemon_red_completion.goal_manager import GoalDecisionOutcome,GoalFailureReason

@pytest.mark.parametrize("fault",[None,"not_capture","success","wrong_failure","captured","no_target","wrong_map","wrong_flag","unconsumed","other_event","cash","bag","unknown_stock","owned","specimens","position","unsettled"])
def test_preface_accepts_only_exact_exhausted_route12_loss_as_a_setback(fault):
    target=RedStaticCaptureTarget(143,132,30,23,1,67,(62,10),int(EventFlag.BEAT_ROUTE12_SNORLAX))
    events=bytes(320);changed=bytearray(events);changed[target.event_flag//8]|=1<<(target.event_flag%8)
    before_raw=N(battle_state=1,map_id=23,player_x=10,player_y=61,player_money=3325,badge_bits=15,event_flags=events,bag_items=((4,4),))
    after_raw=N(**vars(before_raw));after_raw.battle_state=0;after_raw.bag_items=();after_raw.event_flags=bytes(changed)
    facts=dict(cash=3325,owned_species=[1,2],specimen_counts={"one":1})
    before=N(facts=facts);after=N(facts=dict(facts));loss=asdict(target)
    report=N(evidence=dict(captured=False,lost_static_target=loss))
    verdict=N(status=GoalDecisionOutcome.FAILED,failure_reason=GoalFailureReason.RESOURCE_LOST)
    if fault=="success":verdict.status=GoalDecisionOutcome.SUCCEEDED
    if fault=="wrong_failure":verdict.failure_reason=GoalFailureReason.OUTCOME_NOT_VERIFIED
    if fault=="captured":report.evidence["captured"]=True
    if fault=="no_target":report.evidence.pop("lost_static_target")
    if fault=="wrong_map":loss["map_id"]=27
    if fault=="wrong_flag":loss["event_flag"]+=1
    if fault=="unconsumed":after_raw.event_flags=events
    if fault=="other_event":changed[0]|=1;after_raw.event_flags=bytes(changed)
    if fault=="cash":after.facts["cash"]-=1
    if fault=="bag":after_raw.bag_items=((3,1),)
    if fault=="unknown_stock":after_raw.bag_items=None
    if fault=="owned":after.facts["owned_species"]=[1,2,143]
    if fault=="specimens":after.facts["specimen_counts"]={"one":2}
    if fault=="position":after_raw.player_y+=1
    if fault=="unsettled":after_raw.battle_state=1
    assert _ordinary_retained_capture_loss(fault!="not_capture",before,after,report,verdict,before_raw,after_raw) is (fault is None)
