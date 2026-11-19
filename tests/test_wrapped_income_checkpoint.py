"""Wrapped finite income cutoff retains its real censored battle and raw error."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
import pytest
import run_configured_red_player as driver
from test_retained_story_preparation import story
from pokemon_red_completion.battle_scenario_capture import build_battle_scenario_capture_payload
from pokemon_red_completion.executor import ControllerWallTimeBudgetExhausted
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog


def wrapped_chain():
    return [dict(error_type="RedLeagueFundingExecutionError",error="defeat_agatha failed",reason_code="defeat_agatha failed"),dict(error_type="ControllerWallTimeBudgetExhausted",error="controller reached its hard monotonic wall-time admission deadline")]


def closed_wall_history(tmp_path):
    b,h=story(tmp_path);b.calls+=1;d=b.output/f"battle-{b.calls:04d}";d.mkdir()
    payload=b"exact-cutoff-terminal";(d/"initial.state").write_bytes(b"initial")
    (d/"initial.state.json").write_bytes(build_battle_scenario_capture_payload(capture_id=f"player-trainer-{b.calls:04d}",root_lineage_id=b.root_lineage_id,partition=b.source_partition,state_bytes=b"initial",initial_observation_sha256="c"*64,source_commit=b.source_commit,expected_map=b.train_story_contract.map_id,expected_battle_state=2,source_state_sha256=b.source_state_sha256))
    (d/"final.state").write_bytes(payload);terminal=sha256(payload).hexdigest()
    endpoint=dict(final_state_sha256=terminal,outcome_sha256=None,model_sha256=b.model_sha256,qualification_sha256=b.qualification_sha256,actor_returned_win=False,outer_goal_verification_required=True)
    (d/"endpoint.json").write_text(json.dumps(endpoint))
    log=TrainerPracticeEventLog(d/"events",run_identity=dict(model_sha256=b.model_sha256,qualification_sha256=b.qualification_sha256,source_commit=b.source_commit,root_lineage_id=b.root_lineage_id,parent_state_sha256=b.source_state_sha256,train_story_contract=asdict(b.train_story_contract)))
    log.fail(ControllerWallTimeBudgetExhausted(maximum_wall_seconds=1,elapsed_seconds=1.1))
    return b,h,payload,terminal,d


def test_wrapped_budget_exports_only_authenticated_closed_prefix(tmp_path):
    chain=wrapped_chain();original=deepcopy(chain)
    kind,message=driver.checkpoint_error_for_export(chain[0]["error_type"],chain[0]["error"],chain)
    assert kind=="ControllerWallTimeBudgetExhausted" and chain==original
    b,h,payload,terminal,d=closed_wall_history(tmp_path)
    latest,censor=h.checkpoint_after_budget_stop(terminal_state_sha256=terminal,error_type=kind)
    assert len(h.outcomes)==len(h.receipts)==1 and latest==h.outcomes[-1]
    assert censor["outcome"] is None and censor["fresh_inference"] is False
    assert censor["terminal_state_sha256"]==terminal and not(d/"outcome.json").exists()
    with pytest.raises(FileNotFoundError):h()
    with pytest.raises(ValueError):h.checkpoint_after_budget_stop(terminal_state_sha256="0"*64,error_type=kind)


@pytest.mark.parametrize("fault",["outer","message","unknown_cause","missing","extra","malformed","frame_text"])
def test_unsupported_or_inconsistent_wrapper_is_not_a_checkpoint(fault):
    chain=wrapped_chain();kind=chain[0]["error_type"];message=chain[0]["error"]
    if fault=="outer":kind="ValueError"
    elif fault=="message":message="different wrapper"
    elif fault=="unknown_cause":chain[1]["error_type"]="FileNotFoundError"
    elif fault=="missing":chain=None
    elif fault=="extra":chain.append(dict(error_type="ValueError",error="hidden cause"))
    elif fault=="malformed":chain[1]=None
    else:chain[1]=dict(error_type="ControllerFrameBudgetError",error="unknown frame failure")
    assert driver.checkpoint_error_for_export(kind,message,chain)==(None,None)


@pytest.mark.parametrize("kind",sorted(driver.CHECKPOINT_ERRORS-{"ControllerFrameBudgetError"}))
def test_old_unwrapped_export_types_stay_exact(kind):
    assert driver.checkpoint_error_for_export(kind,"original",None)==(kind,"original")


def test_configured_export_projects_wrapped_cause_without_erasing_primary(tmp_path,monkeypatch):
    from types import SimpleNamespace as N
    (tmp_path/"battles").mkdir()
    b,h,payload,terminal,d=closed_wall_history(tmp_path/"battles")
    output=tmp_path/"chunk";native=output/"native";native.mkdir(parents=True)
    meter=dict(goal_attempts=1,actions_attempted=7,actions_completed=6,frames=120,seconds=1.1,restore_attempts=0,observed_cash_debits=0,observed_cash_rewards=0)
    (native/"native-costs.json").write_text(json.dumps(meter))
    previous=dict(decisions=0,actions=0,frames=0,seconds=0.,heals=0,cash_debits=0)
    raw=N(player_money=8,map_id=1,player_y=2,player_x=3,party_levels=(54,))
    emulator=N(frame_count=120,pressed_buttons=(),save_state_bytes=lambda:payload)
    holder=dict(plan=N(roster=()),prior_spent=previous,runtime=N(reader=N(read=lambda:raw)))
    class RedLeagueFundingExecutionError(RuntimeError):pass
    def fail_native(**kwargs):
        try:raise ControllerWallTimeBudgetExhausted(maximum_wall_seconds=1,elapsed_seconds=1.1)
        except ControllerWallTimeBudgetExhausted as error:raise RedLeagueFundingExecutionError("defeat_agatha failed")from error
    def observe_history(*,checkpoint_error_type=None,**kwargs):
        assert checkpoint_error_type=="ControllerWallTimeBudgetExhausted"
        latest,censor=h.checkpoint_after_budget_stop(terminal_state_sha256=terminal,error_type=checkpoint_error_type)
        holder["censored_battle_checkpoint"]=censor
        return latest
    def capture(runtime,**kwargs):
        assert kwargs["battle"]is None and holder["censored_battle_checkpoint"]["outcome"]is None
        return dict(schema=driver.PLAYER_CONTINUATION_SCHEMA,state_sha256=terminal,lesson=dict(completed_objectives=[]),cash=8,bag=[],preparation=None,battle=None,spent=kwargs["spent"],grants_new_budget=False,fit_allowed=False)
    holder["observe_history"]=observe_history
    monkeypatch.setattr(driver,"run_native_continuous_player",fail_native)
    monkeypatch.setattr(driver,"native_player_options",lambda *a:dict(greedy_selection=True,resume_branch_refinement_after_settlement=False))
    monkeypatch.setattr(driver,"player_wiring_declaration",lambda *a:{})
    monkeypatch.setattr(driver,"_field_ready",lambda *a:False)
    monkeypatch.setattr(driver,"native_checkpoint_facts",lambda *a:dict(badges=8,registrations=98))
    monkeypatch.setattr(driver,"capture_player_continuation",capture)
    result,exported=driver.execute_player_chunk(plan=dict(seed=1),configuration=N(sha256="c"*64),c=N(digest=lambda path:sha256(path.read_bytes()).hexdigest()),emulator=emulator,factory=None,menu=None,holder=holder,source=None,output=output,model=N(model_sha256="m"*64),limits=driver.NativePlayerLimits(),memory=None,store=None,ordinal=1)
    assert result["error_type"]=="RedLeagueFundingExecutionError"and result["error"]=="defeat_agatha failed"
    assert result["error_chain"][-1]["error_type"]=="ControllerWallTimeBudgetExhausted"
    assert "checkpoint_export_error"not in result and result["paired_context_authenticated"]
    assert result["passed"]is False and result["spent"]["actions"]==7 and result["chunk_costs"]==meter
    assert exported["grants_new_budget"]is False and exported["fit_allowed"]is False
    assert result["censored_battle_checkpoint"]["fresh_inference"]is False
    assert not(d/"outcome.json").exists()
