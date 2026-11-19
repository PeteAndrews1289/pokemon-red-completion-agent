"""Dojo native win/faint retention is a failed gift and fresh model choice."""
import ast
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion.goal_manager import GoalKind,GoalFailureReason,GoalDecisionOutcome
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding,GoalExecutionReport,GoalVerification
from pokemon_red_completion.red_player_engaged_story import SettledNativeTrainerRecovery
from pokemon_red_completion.red_integrated_play import ordinary_player_setback


def setup(*,opt_in=True,fault=None,error=None):
    source=Path(__file__).resolve().parents[1]/'runtime_helpers/red_mixed_postgame_delivery_20261009.py'
    tree=ast.parse(source.read_text());fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='native_goal_binding')
    ns=dict(sha256=sha256,GoalKind=GoalKind,GoalFailureReason=GoalFailureReason,GoalVerification=GoalVerification,GoalExecutionReport=GoalExecutionReport,ExecutableGoalBinding=ExecutableGoalBinding,_field_ready=lambda rt:rt.ready)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns)
    em=N(state=b'source',frame_count=0);em.save_state_bytes=lambda:em.state
    raw=N(player_money=100,party_hp=(0,20));actions=N(actions_executed=0)
    rt=N(emulator=em,reader=N(read=lambda:raw),adapter=N(observe=lambda: N(raw=N(player_money=100))),ready=True)
    calls=[];saved=[]
    def run():
        calls.append('execute');em.state=b'terminal';em.frame_count=120;actions.actions_executed=5;raw.player_money=110
        if error:raise error
        report=GoalExecutionReport(2,60,dict(support='already_engaged_native_trainer',source_sha256='b'*64,terminal_sha256=sha256(em.state).hexdigest(),battle=dict(schema='pokemon.red.learned-trainer-completion.v1',outcome='won',field_ready=True,money_delta=10)))
        stop=SettledNativeTrainerRecovery(report,cash_before=100,cash_after=110,party_hp=(0,20));saved.append(stop)
        if fault:fault(stop,raw,em,actions)
        raise stop
    def verify():calls.append('verify gift');return True
    binding=ns['native_goal_binding'](rt,actions,GoalKind.ACQUIRE_SPECIES,'dojo-gift',run,verify,retain_trainer_recovery=opt_in)
    return binding,rt,actions,calls,saved


def test_native_recovery_retains_win_and_cost_without_gift_success():
    b,rt,a,calls,_=setup();r=b.execute();v=b.verify(r)
    assert v==GoalVerification.failed(GoalFailureReason.RECOVERY_REQUIRED)
    assert calls==['execute'] and r.actions_executed==5 and r.frames_executed==120
    assert r.evidence['objective_completed']is False and r.evidence['reward']is None
    assert 'route_setback'not in r.evidence and 'route_verified'not in r.evidence
    assert rt.emulator.state==b'terminal' and rt.reader.read().party_hp==(0,20)
    with pytest.raises(ValueError,match='stale or consumed'):b.execute()


def test_default_still_propagates_the_typed_stop():
    b,_,_,_,saved=setup(opt_in=False)
    with pytest.raises(SettledNativeTrainerRecovery)as e:b.execute()
    assert e.value is saved[0]


def test_unknown_exception_is_never_swallowed():
    error=RuntimeError('unknown');b,*_=setup(error=error)
    with pytest.raises(RuntimeError)as e:b.execute()
    assert e.value is error


FAULTS=[
 lambda s,r,e,a:s.evidence.update(verified=False),
 lambda s,r,e,a:s.evidence.update(schema='unknown'),
 lambda s,r,e,a:s.evidence.update(terminal_sha256='c'*64),
 lambda s,r,e,a:s.evidence.update(cash_after=111),
 lambda s,r,e,a:s.evidence['battle'].update(outcome='lost'),
 lambda s,r,e,a:s.evidence['battle'].update(field_ready=False),
 lambda s,r,e,a:s.evidence['battle'].update(money_delta=11),
 lambda s,r,e,a:s.evidence.update(party_hp=[0,0]),
 lambda s,r,e,a:s.evidence.update(party_hp=[20,20]),
 lambda s,r,e,a:setattr(r,'party_hp',(0,19)),
 lambda s,r,e,a:setattr(r,'player_money',True),
 lambda s,r,e,a:setattr(a,'actions_executed',1),
 lambda s,r,e,a:setattr(e,'frame_count',59),
]
@pytest.mark.parametrize('fault',FAULTS)
def test_invalid_native_certificate_propagates_original_stop(fault):
    b,_,_,_,saved=setup(fault=fault)
    with pytest.raises(SettledNativeTrainerRecovery)as e:b.execute()
    assert e.value is saved[0]


@pytest.mark.parametrize('fault',['state','hp','cash','field','report','certificate'])
def test_verifier_rechecks_exact_live_terminal_and_original_report(fault):
    b,rt,_,_,_=setup();r=b.execute()
    if fault=='state':rt.emulator.state=b'other'
    elif fault=='hp':rt.reader.read().party_hp=(0,21)
    elif fault=='cash':rt.reader.read().player_money=111
    elif fault=='field':rt.ready=False
    elif fault=='report':r=replace(r)
    else:r.evidence['native_trainer_recovery']['verified']=False
    assert b.verify(r)==GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)


def native_referee_fixture(monkeypatch):
    from test_red_route_loss_recovery import route_loss
    _,before,after,report,binding=route_loss(monkeypatch)
    bf=deepcopy(dict(before.facts));bf['cash']=935;before=replace(before,facts=bf)
    af=deepcopy(dict(after.facts));af.setdefault('diagnostics',{})['party_hp']=[0,25];after=replace(after,facts=af)
    stop=deepcopy(dict(report.evidence['route_setback']));stop.pop('cash_lost')
    from pokemon_red_completion.red_player_engaged_story import SETTLED_ROUTE_TRAINER_RECOVERY_SCHEMA
    stop.update(schema=SETTLED_ROUTE_TRAINER_RECOVERY_SCHEMA,cash_before=935,cash_after=945,party_hp=[0,25],battle=dict(schema='pokemon.red.learned-trainer-completion.v1',outcome='won',field_ready=True,money_delta=10))
    evidence=dict(schema='pokemon.red.native-delivery-recovery.v1',delivery='dojo-gift',selected_kind=binding.kind.value,source_sha256=before.sha256,terminal_sha256=after.sha256,source_cash=935,native_trainer_recovery=stop,objective_completed=False,reward=None)
    binding=replace(binding,binding_ref='red-native-delivery:dojo-gift:'+before.sha256)
    return before,after,replace(report,evidence=evidence),binding


@pytest.mark.parametrize('fault',[None,'kind','binding','source','terminal','payout','hp','gift','reward','registration','census','unsafe','unready','reason','exception','meter','source_cash','prior_loss','fake_route'])
def test_ordinary_loop_admits_only_measured_conserved_native_gift_recovery(monkeypatch,fault):
    before,after,report,binding=native_referee_fixture(monkeypatch);e=deepcopy(dict(report.evidence));reason=GoalFailureReason.RECOVERY_REQUIRED;error=None
    if fault=='kind':binding=replace(binding,kind=GoalKind.RESUPPLY)
    elif fault=='binding':binding=replace(binding,binding_ref='unrelated')
    elif fault=='source':e['source_sha256']='invalid';binding=replace(binding,binding_ref='red-native-delivery:dojo-gift:invalid')
    elif fault=='terminal':e['terminal_sha256']='b'*64
    elif fault=='payout':e['native_trainer_recovery']['cash_after']=946
    elif fault=='hp':after.facts['diagnostics']['party_hp']=[0,20]
    elif fault=='gift':e['objective_completed']=True
    elif fault=='reward':e['reward']=1
    elif fault=='registration':after.facts['owned_species']=[]
    elif fault=='census':after.facts['specimen_counts']={}
    elif fault=='unsafe':after=replace(after,safe=False)
    elif fault=='unready':after.facts['input_ready']=False
    elif fault=='reason':reason=GoalFailureReason.RESOURCE_LOST
    elif fault=='exception':error=RuntimeError('unknown')
    elif fault=='meter':report=replace(report,actions_executed=0)
    elif fault=='source_cash':e['source_cash']=1
    elif fault=='prior_loss':e['native_trainer_recovery']['cash_before']=934;e['native_trainer_recovery']['battle']['money_delta']=11
    elif fault=='fake_route':e['route_setback']={}
    report=replace(report,evidence=e)
    assert ordinary_player_setback(binding,before,after,report,GoalVerification.failed(reason),error)is(fault is None)
