import json
from hashlib import sha256
from types import SimpleNamespace as N
import pytest
from test_red_player_story_battle import setup
from pokemon_red_completion import red_player_engaged_story as s


@pytest.mark.parametrize("fault", [None, "early_stop", "other_stop", "won", "field_ready",
    "battle_exited", "wrong_map", "wrong_trainer", "party_defeated"])
def test_retained_censor_preserves_failed_battle_and_full_decisions_without_inputs(monkeypatch, fault):
    rt,actions,route,raw,lesson,inputs,_,contract,_=setup(monkeypatch)
    rt.adapter.observe=lambda:N(game_state=object())
    rt.adapter.graph.available_objectives=lambda _:(N(id=contract.objective_id),)
    raw.map_id=contract.map_id
    raw.battle_state=2
    rt.reader.read_active_trainer_identity=lambda:((0,0,0)if fault=="wrong_trainer"else contract.trainer_identity)
    monkeypatch.setattr(s,"engaged_story_contract",lambda *a,**k:contract)
    monkeypatch.setattr(s,"_field_ready",lambda _:False)
    events,counts=[],[]
    def record(k,p):
        assert len(json.dumps(p).encode())<1024*1024
        events.append((k,p))
    actions.record_diagnostic_event=record
    public=dict(outcome="unresolved",episode=dict(decisions=[dict(kind="attack",model_vectors=[0.125]*3000)]*80))
    def exhausted(*a,**kw):
        counts.append((len(inputs),actions.actions_executed,rt.emulator.frame_count))
        raw.battle_state=0 if fault=="battle_exited"else 2
        if fault=="wrong_map":raw.map_id+=1
        if fault=="party_defeated":raw.party_hp=tuple(0 for _ in raw.party_hp)
        return N(outcome="unresolved",field_ready=fault=="field_ready",public_dict=lambda:public,
            episode=N(stop_reason="other"if fault=="other_stop"else"decision_budget",
                battle_won=fault=="won",final_battle_state=raw.battle_state,
                decisions=(None,)*(79 if fault=="early_stop"else 80)))
    monkeypatch.setattr(s,"FrozenStoryBattleController",lambda *a,**k:N(run=exhausted,maximum_decisions=80))
    binding=s.engaged_story_binding(rt,actions,rom=route.rom,battler=object(),objective_id=contract.objective_id)
    expected=s.RetainedTrainerBattleDecisionBudgetReached if fault is None else RuntimeError
    with pytest.raises(expected)as caught:binding.execute()
    assert (len(inputs),actions.actions_executed,rt.emulator.frame_count)==counts[0]
    assert contract.objective_id not in lesson["completed_objectives"]
    if fault is None:
        assert caught.value.reason_code=="retained_trainer_battle_decision_budget"
        assert events[-1][0]=="retained_trainer_battle_decision_budget"
        footer=events[-1][1]
        restored=dict(footer["battle"],episode=dict(footer["battle"]["episode"]))
        restored["episode"]["decisions"]=[p["decision"]for k,p in events[:-1]]
        assert restored==public
        from pokemon_red_completion.provenance import canonical_sha256
        assert footer["battle_sha256"]==canonical_sha256(restored)
        assert [p["ordinal"]for k,p in events[:-1]]==list(range(80))
        assert footer["maximum_decisions"]==80 and footer["decision_records_written"]==80
        assert footer["new_controller_inputs"]==0
    else:
        assert type(caught.value)is RuntimeError and not events
    with pytest.raises(ValueError,match="consumed"):binding.execute()


@pytest.mark.parametrize("fault", [None,"unknown","missing_reason","pressed","stale","field_ready",
    "wild","party_defeated","wrong_ref","extra_choice","inspection_mutation","row_not_preface"])
def test_compulsory_preface_handoff_keeps_raw_error_and_requires_exact_one_recovery(monkeypatch,fault):
    import run_configured_red_player as script
    from pokemon_red_completion.goal_manager import GoalKind,GoalAvailability,GoalOpportunity,GoalUnavailableReason
    from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding,GoalBindingSet,GoalVerification
    payload=[b"exact retained bounded trainer"]
    digest=sha256(payload[0]).hexdigest()
    em=N(pressed_buttons=set(),frame_count=80,save_state_bytes=lambda:payload[0])
    raw=N(battle_state=1 if fault=="wild"else 2,party_hp=(0,)if fault=="party_defeated"else(1,))
    rt=N(emulator=em,reader=N(read=lambda:raw))
    result=dict(error_type="RetainedTrainerBattleDecisionBudgetReached",
        error="retained trainer battle reached its bounded decision limit",released=True,field_ready=False,
        state_sha256=digest,error_chain=[dict(error_type="RetainedTrainerBattleDecisionBudgetReached",
        reason_code="retained_trainer_battle_decision_budget")])
    if fault=="unknown":result["error_type"]="RuntimeError"
    if fault=="missing_reason":result["error_chain"]=[]
    if fault=="pressed":em.pressed_buttons.add("a")
    if fault=="stale":payload[0]=b"changed"
    if fault=="field_ready":result["field_ready"]=True
    if fault=="row_not_preface":result["episode"]=dict(outcomes=[dict(error_type=result["error_type"])])
    monkeypatch.setattr(script,"_field_ready",lambda _:False)
    def inventory():
        if fault=="inspection_mutation":em.frame_count+=1
        b=ExecutableGoalBinding("pokemon.red:retained-engagement:"+("0"*64 if fault=="wrong_ref"else digest),
            GoalKind.RECOVER_CONTROL,0.,0.,lambda:pytest.fail("no inputs during handoff"),lambda _:GoalVerification.succeeded())
        extra=ExecutableGoalBinding("other",GoalKind.EXPLORE,0.,0.,lambda:pytest.fail("no execute"),lambda _:GoalVerification.succeeded())
        bs=(b,extra)if fault=="extra_choice"else(b,)
        blocked=GoalOpportunity("blocked",GoalKind.EXPLORE,GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
        return GoalBindingSet((*tuple(x.opportunity for x in bs),blocked),bs)
    original=json.dumps(result,sort_keys=True)
    if fault=="inspection_mutation":
        with pytest.raises(ValueError,match="changed state"):
            script.qualified_native_control_handoff(result,runtime=rt,inspect_bindings=inventory)
    else:
        receipt=script.qualified_native_control_handoff(result,runtime=rt,inspect_bindings=inventory)
        if fault is None:
            assert receipt["qualified"]and receipt["compulsory_preface_censor"]
            assert receipt["local_decision_limit_unchanged"]and not receipt["aggregate_budget_reset"]
            assert receipt["inputs"]==receipt["frames"]==receipt["model_queries"]==0
        else:assert receipt is None
    assert json.dumps(result,sort_keys=True)==original
