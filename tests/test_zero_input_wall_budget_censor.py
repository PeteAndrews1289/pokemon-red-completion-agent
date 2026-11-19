from copy import deepcopy
import pytest
import run_configured_red_player as driver


def receipt():
    before=dict(actions=5,completed_actions=5,frames=120,restoration_attempts=0,
                nested_restoration_attempts=0,training_healing_attempts=0,cash=300,
                battle_state=0,input_ready=True,buttons_released=True,player_lesson={"party":["unchanged"]})
    after={**before,"actions":6}
    chain=[dict(error_type="ControllerWallTimeBudgetExhausted",error="controller reached its hard monotonic wall-time admission deadline")]
    row=dict(error_type=chain[0]["error_type"],error=chain[0]["error"],error_chain=chain,
             failure_phase="execution",verification=None,ordinary_setback=False,safe_terminal=True,
             before_state_sha256="a"*64,terminal_state_sha256="a"*64,before=before,after=after,
             observed_cost=dict(actions=1,completed_actions=0,frames=0,cash_spent=0))
    meter=dict(schema="pokemon.red.native-player-costs.v1",automatic_fit=False,buttons_released=True,
        actions_attempted=6,actions_completed=5,frames=120,goal_attempts=1,restore_attempts=0,
        nested_restore_attempts=0,training_healing_attempts=0,observed_cash_debits=0,
        observed_cash_rewards=0,observed_cash_changes=0,control_recovery_cash_debits=0,seconds=30.1)
    return dict(passed=True,released=True,worker_stopped=True,field_ready=True,paired_context_authenticated=False,
                state_sha256="a"*64,context_sha256="b"*64,error_chain=deepcopy(chain),
                spent=dict(decisions=1,actions=6,frames=120,heals=0,cash_debits=0,seconds=30.1),
                chunk_costs=meter,episode=dict(stop_reason="execution_failed",executed_decisions=1,outcomes=[row]))


def limits():return driver.NativePlayerLimits(decisions=4,actions=100,frames=1000,seconds=30,heals=10,cash_debits=None)


def test_real_zero_input_cutoff_is_reported_without_erasing_error_or_inventing_context():
    value=receipt();before=deepcopy(value);status=driver.native_result_status(value,limits=limits())
    assert status["status"]=="zero_input_wall_budget_censor"and status["finite_censor"]
    assert status["native_outcome_error_count"]==status["unrecovered_native_error_count"]==1
    assert status["effective_unrecovered_native_error_count"]==0
    assert status["effective_nonordinary_verification_failures"]==0
    assert not status["independent_completion_verification"] and value==before
    assert value["paired_context_authenticated"]is False


@pytest.mark.parametrize("change",["wrong_type","wrong_text","chain","terminal","physical","frames",
    "completed","cash","seconds","nan","boolean","prior_error","prior_failure","root_error",
    "export_error","admission","unsafe","unready","held","unknown","unpaired_hash","cost","missing_meter"])
def test_unknown_or_state_changing_failure_stays_an_error(change):
    value=receipt();row=value["episode"]["outcomes"][-1]
    if change=="wrong_type":row["error_type"]="RuntimeError"
    elif change=="wrong_text":row["error"]="other"
    elif change=="chain":row["error_chain"]=[]
    elif change=="terminal":row["terminal_state_sha256"]="c"*64
    elif change=="physical":row["after"]["player_lesson"]={"party":["different"]}
    elif change=="frames":row["observed_cost"]["frames"]=1
    elif change=="completed":row["observed_cost"]["completed_actions"]=1
    elif change=="cash":row["after"]["cash"]-=1
    elif change=="seconds":value["chunk_costs"]["seconds"]=29.
    elif change=="nan":value["chunk_costs"]["seconds"]=float("nan")
    elif change=="boolean":row["before"]["frames"]=False;row["after"]["frames"]=False
    elif change=="prior_error":value["episode"]["outcomes"].insert(0,dict(error_type="ValueError"))
    elif change=="prior_failure":value["episode"]["outcomes"].insert(0,dict(verification="failed",ordinary_setback=False))
    elif change=="root_error":value["error_type"]="ValueError"
    elif change=="export_error":value["checkpoint_export_error"]={"error":"failed"}
    elif change=="admission":value["episode"]["admission_failure"]={"error":"scope"}
    elif change=="unsafe":row["safe_terminal"]=False
    elif change=="unready":value["field_ready"]=False
    elif change=="held":value["released"]=False
    elif change=="unknown":value["unknown_cost_fields"]=["seconds"]
    elif change=="unpaired_hash":value.pop("context_sha256")
    elif change=="cost":row["observed_cost"]["actions"]=0
    elif change=="missing_meter":value["chunk_costs"].pop("observed_cash_debits")
    assert not driver.qualified_zero_input_wall_budget_censor(value,limits=limits())
    assert driver.native_result_status(value,limits=limits())["effective_unrecovered_native_error_count"]>=1
