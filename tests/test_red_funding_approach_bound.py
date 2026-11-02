from dataclasses import replace
from types import SimpleNamespace as N
import pytest
from test_red_routed_trainer_funding import fixture
from pokemon_red_completion import red_routed_trainer_funding as funding
from pokemon_red_completion.red_funding_approach import BoundedFundingApproach, FundingApproachLimit
from pokemon_red_completion.route_executor import InterruptionReceipt, RouteExecutionError
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.red_integrated_play import ordinary_player_setback
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot


@pytest.mark.parametrize("fault", [None,"seventh","arrived","unverified","battle","map","input",
    "dialogue","pending","engaged","buttons","delegate_error"])
def test_eighth_escape_stops_only_after_proven_free_control(fault):
    raw=N(map_id=22,player_y=9,player_x=19,battle_state=0)
    last=N(verified=fault!="unverified")
    d=N(evidence=[last]*(7 if fault=="seventh" else 8),maximum_flees=8)
    receipt=InterruptionReceipt("wild_battle",22,(9,19),{"verified":True})
    def handle(_):
        if fault=="delegate_error":raise RouteExecutionError("real divergence")
        return receipt
    d.handle=handle
    r=N(read=lambda:raw,read_input_readiness=lambda:N(ready=fault!="input"),
        read_bottom_dialogue_box_visible=lambda:fault=="dialogue",
        read_pending_trainer_battle_identity=lambda:object() if fault=="pending" else None,
        trainer_engagement_active=lambda:fault=="engaged")
    em=N(pressed_buttons=("A",) if fault=="buttons" else ())
    if fault=="battle":raw.battle_state=1
    if fault=="map":raw.map_id=23
    bound=BoundedFundingApproach(d,r,em,(22,9,19) if fault=="arrived" else (22,10,36))
    if fault in {"seventh","arrived"}:
        assert bound.handle(object()) is receipt
    elif fault is None:
        with pytest.raises(FundingApproachLimit) as caught:bound.handle(object())
        assert caught.value.handler is bound and caught.value.receipt is receipt
    else:
        with pytest.raises(RouteExecutionError):bound.handle(object())


@pytest.mark.parametrize("fault", [None,"cash","bag","events","buttons","pending","engaged","unready","wrong_exception"])
def test_funding_binding_returns_only_exact_failed_approach(monkeypatch,fault):
    router,state,target,bindings,calls=fixture(monkeypatch)
    runtime=router.runtime
    runtime.emulator.pressed_buttons=()
    runtime.emulator.save_state_bytes=lambda:repr(state.raw).encode()
    runtime.reader.trainer_engagement_active=lambda:False
    runtime.reader.read_input_readiness=lambda:N(ready=True)
    def route(*args,interruption_handler,**kwargs):
        router.actions.actions_executed+=8;runtime.emulator.frame_count+=80
        state.raw=replace(state.raw,player_x=19)
        receipt=InterruptionReceipt("wild_battle",22,(9,19),{"verified":True})
        if fault=="wrong_exception":raise RouteExecutionError("unrelated failure")
        interruption_handler.delegate=N(maximum_flees=8,evidence=[N(verified=True)]*8,handle=lambda _:receipt)
        interruption_handler.handle(object())
    monkeypatch.setattr(funding,"execute_route",route)
    result=funding.bind_local_trainer_funding(router,bindings,state)
    binding=next(b for b in result.bindings if b.kind is GoalKind.RESUPPLY)
    if fault=="wrong_exception":
        with pytest.raises(RouteExecutionError):binding.execute()
        return
    report=binding.execute()
    assert calls==["escort"]
    assert report.evidence["funding_approach_partial"]["income_earned"]==0
    assert report.actions_executed==9 and report.frames_executed==90
    assert binding.verify(report).failure_reason is GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
    if fault=="cash":state.raw=replace(state.raw,player_money=10)
    if fault=="bag":state.raw=replace(state.raw,bag_items=())
    if fault=="events":state.raw=replace(state.raw,event_flags=bytes([1])+bytes(319))
    if fault=="buttons":runtime.emulator.pressed_buttons=("A",)
    if fault=="pending":runtime.reader.read_pending_trainer_battle_identity=lambda:(200,1)
    if fault=="engaged":runtime.reader.trainer_engagement_active=lambda:True
    if fault=="unready":state.input_ready=False
    assert binding.verify(report).failure_reason is (
        GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED if fault is None else GoalFailureReason.OUTCOME_NOT_VERIFIED)


@pytest.mark.parametrize("fault",[None,"count","terminal","earned","attempted","kind","ref","reason","error","cash","unsafe","unready","partial_cost","ledger"])
def test_only_typed_settled_failed_funding_dose_allows_new_choice(fault):
    facts=dict(actions=0,completed_actions=0,frames=0,cash=100,battle_state=0,
        buttons_released=True,input_ready=True,owned_species=["one"],completed_objectives=["begin"],specimen_counts={"one":1})
    before=AutonomousSnapshot(b"before",facts,True)
    after_facts=dict(facts,actions=8,completed_actions=8,frames=80)
    after=AutonomousSnapshot(b"after",after_facts,fault!="unsafe")
    binding=N(binding_ref="red-trainer-funding:test",kind=GoalKind.RESUPPLY)
    e=dict(schema="pokemon.red.funding-approach-partial.v1",stop_reason="verified_flee_limit",
        maximum_flees=8,completed_flees=8,trainer_attempted=False,target_reached=False,income_earned=0,
        terminal_sha256=after.sha256)
    if fault=="count":e["completed_flees"]=9
    if fault=="terminal":e["terminal_sha256"]="0"*64
    if fault=="earned":e["income_earned"]=1
    if fault=="attempted":e["trainer_attempted"]=True
    if fault=="kind":binding.kind=GoalKind.ACQUIRE_SPECIES
    if fault=="ref":binding.binding_ref="other"
    if fault=="cash":after_facts["cash"]=101
    if fault=="unready":after_facts["input_ready"]=False
    if fault=="partial_cost":after_facts["completed_actions"]=7
    if fault=="ledger":after_facts["specimen_counts"]={"other":1}
    report=GoalExecutionReport(8,80,{"funding_approach_partial":e})
    verdict=GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED if fault=="reason" else GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED)
    assert ordinary_player_setback(binding,before,after,report,verdict,RuntimeError() if fault=="error" else None) is (fault is None)
