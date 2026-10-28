from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as NS

import pytest

from test_settled_wild_route_recovery import certificate
from test_red_routed_recovery import make_test_raw
from pokemon_red_completion import red_routed_static_capture as module
from pokemon_red_completion.red_routed_recovery import SettledNativeWildRecovery
from pokemon_red_completion.goal_manager import GoalFailureReason
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.red_static_capture import RedStaticCaptureTarget
from pokemon_red_completion.route_executor import RouteExecutionFailureReport,RouteExecutionFailureReason
from pokemon_red_completion.route_plan import RoutePlan
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.local_router import LocalPath


def scenario(monkeypatch,fault=None):
    target=RedStaticCaptureTarget(150,131,70,227,1,67,(2,9),2522)
    initial=make_test_raw(map_id=227,x=9,y=2,hp=(30,30))
    state=dict(raw=initial,version=0,owned=frozenset(),consumed=False)
    em=NS(frame_count=0,pressed_buttons=(),save_state_bytes=lambda:bytes([state['version']]))
    actions=NS(actions_executed=0)
    runtime=NS(emulator=em,adapter=NS(observe=lambda:NS(raw=state['raw'],input_ready=True)),
               reader=NS(read_pokedex_state=lambda:NS(owned_species=state['owned'])))
    monkeypatch.setattr(module,'red_static_capture_targets',lambda _:(target,))
    monkeypatch.setattr(module,'observe_static_capture',lambda *_:NS(registered=150 in state['owned'],consumed=state['consumed']))
    route=RoutePlan(MacroPath((227,),()),(2,9),None,(),LocalPath(((2,9),),(),(None,)),(2,9),None)
    def execute(_):
        actions.actions_executed=10;em.frame_count=400;state['version']=1
        state['raw']=replace(initial,party_hp=(0,30))
        proof=certificate();proof['terminal_sha256']=sha256(em.save_state_bytes()).hexdigest()
        if fault=='proof':proof['wild_escape']['pp_preserved']=False
        if fault=='terminal':proof['terminal_sha256']='a'*64
        if fault=='hp':state['raw']=replace(state['raw'],party_hp=(0,29))
        if fault=='cash':state['raw']=replace(state['raw'],player_money=208)
        if fault=='buttons':em.pressed_buttons=('a',)
        if fault=='battle':state['raw']=replace(state['raw'],battle_state=1)
        if fault=='capture':state['owned']=frozenset({150})
        if fault=='consumed':state['consumed']=True
        if fault=='cost':actions.actions_executed=2
        if fault=='unknown':raise RuntimeError('unknown prepared recipe error')
        stop=SettledNativeWildRecovery(GoalExecutionReport(3,240,proof))
        if fault!='missing_failure':stop.attach_failure(RouteExecutionFailureReport(route,RouteExecutionFailureReason.INTERRUPTION_UNRECOVERED,None,(),(),(),2,1))
        raise stop
    binding=module.prepared_static_acquisition_binding(runtime,actions,rom=b'',target=target,
        execute_prepared=execute,verify_return=lambda:True,estimated_effort=.4,estimated_risk=.25)
    return binding,state,em,actions


def test_prepared_static_capture_retains_real_failed_route_and_full_costs(monkeypatch):
    binding,state,em,actions=scenario(monkeypatch)
    report=binding.execute()
    assert report.actions_executed==10 and report.frames_executed==400
    assert report.evidence['destination_executed'] is False
    assert report.evidence['prepared_static_capture_not_executed'] is True
    assert binding.verify(report).failure_reason is GoalFailureReason.RECOVERY_REQUIRED
    assert state['owned']==frozenset() and state['raw'].party_hp==(0,30)
    with pytest.raises(RuntimeError,match='already attempted'):binding.execute()


@pytest.mark.parametrize('fault',['proof','terminal','hp','cash','buttons','battle','capture',
    'consumed','cost','missing_failure','unknown'])
def test_wrapper_does_not_waive_unknown_or_mismatched_route_failure(monkeypatch,fault):
    binding,*_=scenario(monkeypatch,fault)
    with pytest.raises((SettledNativeWildRecovery,RuntimeError)):binding.execute()


@pytest.mark.parametrize('fault',['terminal','report','hp','money','registration','consumed'])
def test_recovery_verdict_requires_unchanged_exact_terminal(monkeypatch,fault):
    binding,state,em,_=scenario(monkeypatch);report=binding.execute()
    if fault=='terminal':state['version']=2
    elif fault=='report':report=replace(report)
    elif fault=='hp':state['raw']=replace(state['raw'],party_hp=(1,30))
    elif fault=='money':state['raw']=replace(state['raw'],player_money=210)
    elif fault=='registration':state['owned']=frozenset({150})
    elif fault=='consumed':state['consumed']=True
    assert binding.verify(report).failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED
