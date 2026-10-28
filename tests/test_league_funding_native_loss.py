from types import SimpleNamespace as S
from copy import deepcopy
import pytest
from pokemon_red_completion.red_league_funding_execution import native_league_loss_certificate
from pokemon_red_completion.red_integrated_play import _settled_league_funding_loss
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from hashlib import sha256


def fixture():
    raw=S(player_money=100,party_species_ids=(28,64),badge_bits=255,battle_state=0)
    doc=dict(schema='pokemon.red.learned-trainer-completion.v1',outcome='lost',field_ready=True,money_delta=-100)
    completion=S(outcome='lost',field_ready=True,public_dict=lambda:doc)
    runtime=S(reader=S(read=lambda:raw,read_input_readiness=lambda:S(ready=True)),emulator=S(pressed_buttons=frozenset(),save_state_bytes=lambda:b'terminal'))
    before=S(player_money=200,party_species_ids=(28,64),badge_bits=255)
    return runtime,before,completion,doc,raw


def test_certificate_requires_native_balanced_loss():
    runtime,before,result,doc,raw=fixture()
    proof=native_league_loss_certificate(runtime,before,result,'defeat_champion')
    assert proof['completion'] is doc
    assert proof['money_before_battle']==200 and proof['ending_money']==100
    assert proof['terminal_sha256']==sha256(b'terminal').hexdigest()

@pytest.mark.parametrize('change',["won","unresolved","not_ready","money","delta","party","badge","battle","buttons","unknown"])
def test_false_or_unsettled_loss_is_never_certified(change):
    runtime,before,result,doc,raw=fixture()
    if change in ('won','unresolved'):result.outcome=change;doc['outcome']=change
    if change=='not_ready':result.field_ready=False
    if change=='money':raw.player_money=99
    if change=='delta':doc['money_delta']=0
    if change=='party':raw.party_species_ids=(28,)
    if change=='badge':raw.badge_bits=127
    if change=='battle':raw.battle_state=2
    if change=='buttons':runtime.emulator.pressed_buttons={'a'}
    if change=='unknown':result=None
    assert native_league_loss_certificate(runtime,before,result,'defeat_champion') is None


def test_loss_admission_is_bound_to_exact_terminal_and_no_income():
    runtime,before,result,doc,raw=fixture()
    proof=native_league_loss_certificate(runtime,before,result,'defeat_champion')
    terminal=S(sha256=proof['terminal_sha256'],facts=dict(cash=100))
    binding=S(kind=GoalKind.RESUPPLY,binding_ref='pokemon.red:funding:repeatable-league:bound')
    evidence=dict(status='lost',no_income_credit=True,native_league_funding_loss=proof)
    assert _settled_league_funding_loss(binding,terminal,GoalExecutionReport(4,240,evidence))
    for key,value in [('terminal_sha256','f'*64),('ending_money',99),('money_before_battle',300),('schema','unknown')]:
        changed=deepcopy(evidence);changed['native_league_funding_loss'][key]=value
        assert not _settled_league_funding_loss(binding,terminal,GoalExecutionReport(4,240,changed))
    for key,value in [('status','won'),('no_income_credit',False)]:
        changed=deepcopy(evidence);changed[key]=value
        assert not _settled_league_funding_loss(binding,terminal,GoalExecutionReport(4,240,changed))
    binding.binding_ref='unrelated'
    assert not _settled_league_funding_loss(binding,terminal,GoalExecutionReport(4,240,evidence))


def test_approved_medicine_composition_retains_real_loss_and_whole_cost():
    from pokemon_red_completion.red_autonomous_league_funding import compose_native_funding_loss
    from pokemon_red_completion.goal_manager import GoalFailureReason
    from pokemon_red_completion.goal_manager_runtime import GoalVerification
    report=GoalExecutionReport(100,900,dict(status='lost',no_income_credit=True,
        native_league_funding_loss=dict(ending_money=100)))
    verdict=GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
    result=compose_native_funding_loss(report,verdict,actions=130,frames=1200,
        cash_before=500,cash_after=100,purchase_cost=200,pre_entry_support=[{'actions':30}])
    assert result.actions_executed==130 and result.frames_executed==1200
    assert result.evidence['observed_total_net_income']==-400
    assert result.evidence['pre_entry_purchase_cost']==200
    assert result.evidence['gross_battle_income'] is None
    assert result.evidence['no_income_credit'] is True
    assert compose_native_funding_loss(report,GoalVerification.succeeded(),actions=130,
        frames=1200,cash_before=500,cash_after=100,purchase_cost=200,pre_entry_support=[]) is None
    with pytest.raises(ValueError,match='cost accounting'):
        compose_native_funding_loss(report,verdict,actions=99,frames=1200,
            cash_before=500,cash_after=100,purchase_cost=200,pre_entry_support=[])


@pytest.mark.parametrize('damage',[None,'wrong_terminal','wrong_money','generic_cause'])
def test_real_funding_binding_bridges_only_exact_native_loss(monkeypatch,damage):
    from pokemon_red_completion import red_autonomous_league_funding as f
    from pokemon_red_completion.red_league_funding_execution import RedLeagueFundingExecutionError,RedLeagueFundingBattleLoss
    from pokemon_red_completion.red_lorelei_story import LoreleiStoryBattleStopped
    from pokemon_red_completion.goal_manager import GoalFailureReason
    from pokemon_red_completion.goal_manager_runtime import GoalVerification
    raw=S(player_money=100,battle_state=0)
    actions=S(actions_executed=0);emulator=S(frame_count=0,pressed_buttons=frozenset(),save_state_bytes=lambda:b'terminal')
    runtime=S(adapter=S(observe=lambda:S(raw=raw,input_ready=True)),emulator=emulator)
    league=S(origin=S(raw=S(player_money=500)),qualification=S(expected_net_income=1000,public_dict=lambda:{'schema':'qualification'}))
    monkeypatch.setattr(f,'bind_red_league_funding_execution',lambda *a:league)
    def fail(*a,**k):
        actions.actions_executed=40;emulator.frame_count=500
        proof=dict(schema='pokemon.red.league-funding-native-loss.v1',objective_id='defeat_champion',ending_money=100,money_before_battle=200,
            terminal_sha256=sha256(b'terminal').hexdigest(),completion=dict(schema='pokemon.red.learned-trainer-completion.v1',outcome='lost',field_ready=True,money_delta=-100))
        if damage=='wrong_terminal':proof['terminal_sha256']='f'*64
        if damage=='wrong_money':proof['ending_money']=99
        native=LoreleiStoryBattleStopped('retained defeat_champion outcome: lost')
        cause=RedLeagueFundingBattleLoss(proof);cause.__cause__=native
        if damage=='generic_cause':cause=native
        raise RedLeagueFundingExecutionError('defeat_champion failed',progress=S(phase='battle:defeat_champion',public_dict=lambda:{'phase':'battle:defeat_champion'})) from cause
    monkeypatch.setattr(f,'execute_red_league_funding',fail)
    binding=f.bind_autonomous_league_funding(runtime,actions,object(),maximum_actions=30000,maximum_frames=3000000,
        postgame_return=lambda:pytest.fail('loss must not invoke postgame victory return'))
    if damage:
        with pytest.raises(RedLeagueFundingExecutionError):binding.execute()
        return
    report=binding.execute()
    assert report.actions_executed==40 and report.frames_executed==500
    assert report.evidence['no_income_credit'] is True
    assert len(report.evidence['native_error_chain'])==3
    assert binding.verify(report)==GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
    assert _settled_league_funding_loss(binding,S(sha256=sha256(b'terminal').hexdigest(),facts={'cash':100}),report)
    emulator.save_state_bytes=lambda:b'changed'
    assert binding.verify(report)==GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)


def test_shared_native_gate_preserves_success_without_consulting_loss_owner():
    from pokemon_red_completion.red_league_funding_execution import run_retained_league_battle
    runtime,before,completion,doc,raw=fixture()
    value=object()
    assert run_retained_league_battle(runtime,lambda:value,battle_owner=None,objective_id='defeat_champion')is value

def test_shared_native_gate_preserves_original_native_error_chain():
    from pokemon_red_completion.red_league_funding_execution import run_retained_league_battle,RedLeagueFundingBattleLoss
    from pokemon_red_completion.red_lorelei_story import LoreleiStoryBattleStopped
    runtime,before,completion,doc,raw=fixture()
    runtime.reader.read=lambda:before
    original=LoreleiStoryBattleStopped('retained defeat_champion outcome: lost')
    def execute():
        runtime.reader.read=lambda:raw
        raise original
    with pytest.raises(RedLeagueFundingBattleLoss)as raised:
        run_retained_league_battle(runtime,execute,battle_owner=S(last_completion=completion),objective_id='defeat_champion')
    assert raised.value.__cause__ is original
    assert raised.value.certificate['money_before_battle']==200
    assert raised.value.certificate['ending_money']==100

@pytest.mark.parametrize('damage',['missing_owner','missing_completion','unresolved','unreleased','unsettled','wrong_cash'])
def test_shared_native_gate_never_converts_unverified_stop(damage):
    from pokemon_red_completion.red_league_funding_execution import run_retained_league_battle
    from pokemon_red_completion.red_lorelei_story import LoreleiStoryBattleStopped
    runtime,before,completion,doc,raw=fixture();runtime.reader.read=lambda:before
    owner=S(last_completion=completion)
    if damage=='missing_owner':owner=None
    if damage=='missing_completion':owner.last_completion=None
    if damage=='unresolved':completion.outcome='unresolved'
    if damage=='unreleased':runtime.emulator.pressed_buttons={'a'}
    if damage=='unsettled':raw.battle_state=2
    if damage=='wrong_cash':raw.player_money=99
    original=LoreleiStoryBattleStopped('native stop')
    def execute():
        runtime.reader.read=lambda:raw
        raise original
    with pytest.raises(LoreleiStoryBattleStopped)as raised:
        run_retained_league_battle(runtime,execute,battle_owner=owner,objective_id='defeat_champion')
    assert raised.value is original

def test_shared_native_gate_does_not_convert_unrelated_runtime_error():
    from pokemon_red_completion.red_league_funding_execution import run_retained_league_battle
    runtime,before,completion,doc,raw=fixture();original=RuntimeError('native input failure')
    def execute():raise original
    with pytest.raises(RuntimeError)as raised:
        run_retained_league_battle(runtime,execute,battle_owner=S(last_completion=completion),objective_id='defeat_champion')
    assert raised.value is original
