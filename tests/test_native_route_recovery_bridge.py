from copy import deepcopy
import json
import pytest
from run_configured_red_player import native_result_status, chunk_continuation_reason, qualified_route_setback_receipt


def retained_failure():
    boundary=dict(map_id=214,at=[5,8],ready=True,interruption=None,mode="land")
    facts=dict(party_guard_verified=True,input_ready=True,buttons_released=True,battle_state=0,
        player_lesson={"party":[{"specimen_ref":"kept"}]},owned_species=["kept"],specimen_counts={"kept":1},
        completed_objectives=["kept"],bag_items=[[1,1]],coins=0,cash=21590,route_boundary=boundary)
    cost=dict(actions=38,completed_actions=38,frames=1068,cash_spent=0)
    row=dict(error_type="RouteExecutionError",error="route step right at (5, 8) exceeded 8 attempts",
        error_chain=[dict(error_type="RouteExecutionError",reason_code="step_acknowledgement_exhausted")],
        before=deepcopy(facts),after=deepcopy(facts),safe_terminal=True,verification=None,ordinary_setback=False,
        observed_cost=cost,recoverable_route_setback=dict(reason="step_acknowledgement_exhausted",cost=cost,
            route_terminal=boundary,failed_walk=dict(source_map=214,source_at=[5,8],expected_map=214,expected_at=[5,9],action="right")))
    return row


def result(row):
    return dict(passed=True,released=True,field_ready=True,state_sha256="b"*64,
        chunk_costs=dict(actions_attempted=38,frames=1068),
        episode=dict(stop_reason="decision_budget",outcomes=[row]))


def test_certified_route_failure_keeps_raw_error_and_cost_but_allows_next_chunk():
    value=result(retained_failure());old=deepcopy(value)
    status=native_result_status(value)
    assert status["native_outcome_error_count"]==status["recovered_route_error_count"]==1
    assert status["unrecovered_native_error_count"]==0 and status["status"]=="recovered_route_setback"
    assert chunk_continuation_reason(value,source_sha256="a"*64)=="automatic_chunk_renewal"
    assert value==old


@pytest.mark.parametrize("fault",["missing","type","chain","unsafe","verified","cost","cash",
    "party","items","coins","readiness","buttons","battle","guard","location","transition","direction"])
def test_unknown_or_changed_failure_still_stops(fault):
    row=retained_failure()
    if fault=="missing":row.pop("recoverable_route_setback")
    elif fault=="type":row["error_type"]="ValueError"
    elif fault=="chain":row["error_chain"].append({"error_type":"RuntimeError"})
    elif fault=="unsafe":row["safe_terminal"]=False
    elif fault=="verified":row["verification"]="succeeded"
    elif fault=="cost":row["observed_cost"]={**row["observed_cost"],"completed_actions":37}
    elif fault in {"cash","coins"}:row["after"][fault]+=1
    elif fault=="party":row["after"]["player_lesson"]={"party":[]}
    elif fault=="items":row["after"]["bag_items"]=[]
    elif fault in {"readiness","buttons","guard"}:row["after"][{"readiness":"input_ready","buttons":"buttons_released","guard":"party_guard_verified"}[fault]]=False
    elif fault=="battle":row["after"]["battle_state"]=2
    elif fault=="location":row["after"]["route_boundary"]={}
    elif fault=="transition":row["recoverable_route_setback"]["failed_walk"]["expected_map"]=215
    else:row["recoverable_route_setback"]["failed_walk"]["action"]="surf"
    assert not qualified_route_setback_receipt(row)
    value=result(row)
    assert native_result_status(value)["status"]=="execution_error"
    assert chunk_continuation_reason(value,source_sha256="a"*64)=="native_execution_error"


def test_native_development_declares_recovery_but_train_does_not(tmp_path,monkeypatch):
    from test_red_native_player import setup
    from pokemon_red_completion import red_native_player as native
    for partition in ["development","train"]:
        args,_=setup(tmp_path/partition,monkeypatch)
        args["source"]={**args["source"],"partition":partition}
        native.run_native_continuous_player(**args)
        plan=json.loads((args["output"]/"native-plan.json").read_text())
        assert plan.get("continue_safe_route_failures",False)==(partition=="development")
