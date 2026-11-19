"""Budget exports keep only the authenticated completed preparation prefix."""
from dataclasses import asdict
from hashlib import sha256
import json
import pytest
from test_retained_story_preparation import story
from pokemon_red_completion.battle_scenario_capture import build_battle_scenario_capture_payload
from pokemon_red_completion.executor import ControllerActionBudgetExhausted,ControllerWallTimeBudgetExhausted,ControllerFrameBudgetError
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog
from pokemon_red_completion.red_player_preparation_history import StoryPreparationHistory,_observe_completed_preparation_history


def budget_failure(tmp_path,kind):
    b,h=story(tmp_path);b.calls+=1;d=b.output/f"battle-{b.calls:04d}";d.mkdir();payload=b"closed-budget-terminal";(d/"initial.state").write_bytes(b"initial")
    (d/"initial.state.json").write_bytes(build_battle_scenario_capture_payload(capture_id=f"player-trainer-{b.calls:04d}",root_lineage_id=b.root_lineage_id,partition=b.source_partition,state_bytes=b"initial",initial_observation_sha256="c"*64,source_commit=b.source_commit,expected_map=b.train_story_contract.map_id,expected_battle_state=2,source_state_sha256=b.source_state_sha256))
    (d/"final.state").write_bytes(payload);terminal=sha256(payload).hexdigest();endpoint=dict(final_state_sha256=terminal,outcome_sha256=None,model_sha256=b.model_sha256,qualification_sha256=b.qualification_sha256,actor_returned_win=False,outer_goal_verification_required=True);(d/"endpoint.json").write_text(json.dumps(endpoint))
    error=(ControllerActionBudgetExhausted(maximum_actions=1,attempted_actions=1)if kind=="action"else ControllerWallTimeBudgetExhausted(maximum_wall_seconds=1,elapsed_seconds=1.1)if kind=="wall"else ControllerFrameBudgetError("controller exhausted its hard frame budget"))
    log=TrainerPracticeEventLog(d/"events",run_identity=dict(model_sha256=b.model_sha256,qualification_sha256=b.qualification_sha256,source_commit=b.source_commit,root_lineage_id=b.root_lineage_id,parent_state_sha256=b.source_state_sha256,train_story_contract=asdict(b.train_story_contract)));log.fail(error)
    kwargs=dict(error=str(error))if kind=="frame"else{};_,censor=h.checkpoint_after_budget_stop(terminal_state_sha256=terminal,error_type=type(error).__name__,**kwargs)
    return b,h,d,censor


@pytest.mark.parametrize("kind",["action","wall"])
def test_budget_stop_retains_real_completed_loss_and_no_failed_battle_outcome(tmp_path,kind):
    b,h,d,censor=budget_failure(tmp_path,kind);before=(d/"final.state").read_bytes();m=StoryPreparationHistory();m.refresh(dict(scoped_actors={"s":(b,h)},censored_battle_checkpoint=censor))
    assert m.retained.directory.name=="battle-0001" and len(h.outcomes)==len(h.receipts)==1
    assert not(d/"outcome.json").exists()and(d/"final.state").read_bytes()==before
    with pytest.raises(FileNotFoundError):h()


@pytest.mark.parametrize("fault",["missing","terminal","ordinal","outcome","inference","identity","log","kind"])
def test_budget_export_rejects_foreign_missing_or_tampered_receipt(tmp_path,fault):
    b,h,d,censor=budget_failure(tmp_path,"action")
    if fault=="missing":censor=None
    elif fault=="terminal":censor["terminal_state_sha256"]="0"*64
    elif fault=="ordinal":censor["ordinal"]+=1
    elif fault=="outcome":censor["outcome"]={}
    elif fault=="inference":censor["fresh_inference"]=True
    elif fault=="identity":b.model_sha256="f"*64
    elif fault=="log":(d/"events/event-00002.json").write_text("{}")
    else:censor["error_type"]="RuntimeError"
    with pytest.raises((ValueError,FileNotFoundError,KeyError)):
        StoryPreparationHistory().refresh(dict(scoped_actors={"s":(b,h)},censored_battle_checkpoint=censor))


def test_ambiguous_legacy_frame_class_stays_refused_without_archived_message(tmp_path):
    b,h,d,censor=budget_failure(tmp_path,"frame")
    with pytest.raises((ValueError,FileNotFoundError,KeyError)):
        _observe_completed_preparation_history(h,censored_checkpoint=censor)
