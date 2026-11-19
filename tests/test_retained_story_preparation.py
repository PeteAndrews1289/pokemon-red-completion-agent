from dataclasses import asdict, replace
from types import SimpleNamespace as N
import json
import pytest
from test_red_player_battle_history import battler,publish
from pokemon_red_completion.red_player_battle_history import NativeBattlerHistory
from pokemon_red_completion.red_player_preparation_history import RetainedStoryDefeat,StoryPreparationHistory
from pokemon_red_completion.red_story_battle import StoryTrainerContract
from pokemon_red_completion.red_learned_trainer import FROZEN_K_SHA256,K_QUALIFICATION_SHA256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.post_battle_strategy import BattleResult


def story(tmp_path):
    b=battler(tmp_path);b.source_partition=ScenarioPartition.TRAIN
    b.model_sha256,b.qualification_sha256=FROZEN_K_SHA256,K_QUALIFICATION_SHA256
    b.train_story_contract=StoryTrainerContract("defeat_misty","misty",65,(235,35,1),191,2079)
    h=NativeBattlerHistory(b);publish(b)
    return b,h


def world(*,legal=("defeat_misty",),completed=(),defeated=False):
    flags=bytearray(320)
    if defeated:flags[191//8]|=1<<(191%8)
    graph=N(available_objectives=lambda s:tuple(N(id=x)for x in legal),completed_ids=lambda s:completed)
    return N(adapter=N(graph=graph),reader=N(read=lambda:N(event_flags=bytes(flags)))),N(game_state=None)


def test_story_loss_survives_wild_win_and_restoration_without_relabeling_latest(tmp_path):
    b,h=story(tmp_path);holder={"scoped_actors":{"story":(b,h)}};memory=StoryPreparationHistory()
    loss=h();rt,obs=world();assert memory.preparation_loss(rt,obs,loss,holder)==loss
    latest=replace(loss,result=BattleResult.WON,opponents_defeated=loss.opponent_count,
                   terminal_fainted_count=0,terminal_hp_fraction=1.)
    assert memory.preparation_loss(rt,obs,latest,holder)==loss
    assert latest.result is BattleResult.WON
    restored=StoryPreparationHistory.from_document(json.loads(json.dumps(memory.private_dict())))
    assert restored.preparation_loss(rt,obs,latest,{"scoped_actors":{}})==loss


@pytest.mark.parametrize("completed,defeated",[(True,False),(False,True)])
def test_completed_objective_or_exact_defeated_event_clears_retained_loss(tmp_path,completed,defeated):
    b,h=story(tmp_path);retained=RetainedStoryDefeat.from_history(h,1);memory=StoryPreparationHistory(retained)
    rt,obs=world(legal=(),completed=("defeat_misty",)if completed else(),defeated=defeated)
    assert memory.preparation_loss(rt,obs,None,{})is None and memory.retained is None


def test_temporarily_unavailable_story_does_not_supply_or_erase_preparation(tmp_path):
    b,h=story(tmp_path);memory=StoryPreparationHistory(RetainedStoryDefeat.from_history(h,1))
    rt,obs=world(legal=());assert memory.preparation_loss(rt,obs,None,{})is None
    rt,obs=world();assert memory.preparation_loss(rt,obs,None,{}).result is BattleResult.LOST


def test_unbound_latest_loss_stays_latest_but_is_not_invented_as_story_memory(tmp_path):
    b,h=story(tmp_path);memory=StoryPreparationHistory();rt,obs=world()
    assert memory.preparation_loss(rt,obs,h(),{})==h()
    assert memory.private_dict()is None


@pytest.mark.parametrize("key",["outcome_sha256","manifest_sha256","endpoint_sha256","battle_receipt_sha256"])
def test_carried_native_evidence_rejects_changed_hash(tmp_path,key):
    b,h=story(tmp_path);doc=RetainedStoryDefeat.from_history(h,1).private_dict();doc[key]="f"*64
    with pytest.raises(ValueError):RetainedStoryDefeat.from_document(doc)


@pytest.mark.parametrize("change",["contract","outcome","terminal","event"])
def test_carried_native_evidence_rejects_actual_tampering(tmp_path,change):
    b,h=story(tmp_path);doc=RetainedStoryDefeat.from_history(h,1).private_dict();d=b.output/"battle-0001"
    if change=="contract":doc["contract"]["objective_id"]="defeat_erika"
    elif change=="outcome":(d/"outcome.json").write_text("{}")
    elif change=="terminal":(d/"final.state").write_bytes(b"tampered")
    else:(d/"events/event-00001.json").write_text("{}")
    with pytest.raises((ValueError,KeyError)):RetainedStoryDefeat.from_document(doc)


def test_new_incomplete_story_battle_is_not_silently_reused(tmp_path):
    b,h=story(tmp_path);memory=StoryPreparationHistory();memory.refresh({"scoped_actors":{"s":(b,h)}})
    b.calls+=1
    with pytest.raises((ValueError,FileNotFoundError)):memory.refresh({"scoped_actors":{"s":(b,h)}})


def test_ordinary_actor_cannot_create_story_memory(tmp_path):
    b=battler(tmp_path);h=NativeBattlerHistory(b);publish(b)
    with pytest.raises(ValueError,match="story defeat"):RetainedStoryDefeat.from_history(h,1)


def test_wild_history_does_not_clear_a_retained_story_defeat(tmp_path):
    d=tmp_path/"story";d.mkdir();b,h=story(d);memory=StoryPreparationHistory();memory.refresh({"scoped_actors":{"story":(b,h)}})
    wild=battler(tmp_path/"wild");wild.output.mkdir();wh=NativeBattlerHistory(wild);publish(wild,wild=True)
    old=memory.private_dict();memory.refresh({"scoped_actors":{"story":(b,h),"wild":(wild,wh)}})
    assert memory.private_dict()==old


@pytest.mark.parametrize("change",["root","partition"])
def test_carried_story_evidence_cannot_cross_native_lineage_or_partition(tmp_path,change):
    b,h=story(tmp_path);memory=StoryPreparationHistory(RetainedStoryDefeat.from_history(h,1))
    if change=="root":b.root_lineage_id="foreign-root"
    else:b.source_partition=ScenarioPartition.DEVELOPMENT
    with pytest.raises(ValueError,match="lineage or partition"):
        memory.refresh({"actor":b})


def test_one_completed_trainer_preserves_another_unfinished_contract(tmp_path,monkeypatch):
    a=tmp_path/"leader";a.mkdir();leader,lh=story(a)
    b=tmp_path/"obstruction";b.mkdir();trainer,th=story(b)
    trainer.train_story_contract=replace(trainer.train_story_contract,battle_plan_id="observed-story-obstruction",defeated_event=192,trainer_identity=(235,35,2))
    # Republish the second fixture under its actual distinct contract.
    import shutil
    shutil.rmtree(b/"battle-0001");trainer.calls=0;th=NativeBattlerHistory(trainer);publish(trainer)
    memory=StoryPreparationHistory();memory.refresh({"scoped_actors":{"leader":(leader,lh)}})
    memory.refresh({"scoped_actors":{"leader":(leader,lh),"trainer":(trainer,th)}})
    assert memory.retained.contract==trainer.train_story_contract
    # Actual fixture publisher's next outcome is a complete trainer win.
    import test_red_player_battle_history as fixtures
    original=fixtures.episode
    def won():
        ep=original();ep.update(battle_won=True,stop_reason="battle_won")
        row=ep["decisions"][0];row["state_after"]["party_hp"]=[90]
        row["observation"]["features"]["battle"].update(opponent_party_count=1,opponent_remaining_count=1)
        row["outcome"]["opponent_fainted"]=True;ep["metrics"]["opponent_faints"]=1
        return ep
    monkeypatch.setattr(fixtures,"episode",won);directory=publish(trainer)
    # Publisher's actor_returned_win follows the fixed old loss fixture;rebind
    # the independent event log to this actual synthetic win fixture.
    from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog
    import hashlib
    endpoint=json.loads((directory/"endpoint.json").read_bytes());endpoint["actor_returned_win"]=True
    (directory/"endpoint.json").write_text(json.dumps(endpoint))
    first=json.loads((directory/"events/event-00001.json").read_bytes())["payload"]["identity"]
    shutil.rmtree(directory/"events");log=TrainerPracticeEventLog(directory/"events",run_identity=first);log.finish(endpoint)
    memory.refresh({"scoped_actors":{"leader":(leader,lh),"trainer":(trainer,th)}})
    assert memory.retained.contract==leader.train_story_contract
    restored=StoryPreparationHistory.from_document(memory.private_dict(),expected_lineage=leader.root_lineage_id,expected_partition="train")
    rt,obs=world();assert restored.preparation_loss(rt,obs,None,{})==lh()


def test_expected_source_rejects_foreign_record_even_without_any_live_actor(tmp_path):
    b,h=story(tmp_path);doc=RetainedStoryDefeat.from_history(h,1).private_dict()
    with pytest.raises(ValueError,match="lineage or partition"):
        StoryPreparationHistory.from_document(doc,expected_lineage="foreign-root",expected_partition="train")


def test_normal_require_win_party_wipe_is_retained_despite_run_failed(tmp_path):
    b,h=story(tmp_path);publish(b,failed=True)
    # NativeBattlerHistory explicitly permits a closed require-win failure that
    # contains an authenticated ordinary LOST outcome;technical failures still refuse.
    assert RetainedStoryDefeat.from_history(h,2).aftermath().result is BattleResult.LOST


@pytest.mark.parametrize("declared",[None,False])
def test_assembly_refuses_silent_removal_of_carried_preparation_flag(tmp_path,declared):
    from test_red_player_configuration import config
    from pokemon_red_completion.red_player_configuration import assemble_configured_player
    from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    parent=tmp_path/"parent";parent.mkdir();(parent/"CONTEXT.json").write_text(json.dumps({"preparation_story_loss":{"schema":"carried"}}))
    work=tmp_path/"WORK.json";work.write_text(json.dumps({}if declared is None else{"retain_story_preparation_opposition":declared}))
    menu=NativeStoryBranchInventory(lambda *a:GoalBindingSet((),()),lambda *a:())
    backend=N(assembly=lambda *a,**k:(b"unchanged",None,menu,{},dict(partition="development")))
    with pytest.raises(ValueError,match="silently disable"):
        assemble_configured_player(backend,config(),parent,tmp_path/"out",plan_path=work)


def test_assembly_binds_carried_record_to_current_origin_before_actor_construction(tmp_path):
    from test_red_player_configuration import config
    from pokemon_red_completion.red_player_configuration import assemble_configured_player
    from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    capture=tmp_path/"capture";capture.mkdir();b,h=story(capture)
    parent=tmp_path/"parent";parent.mkdir();(parent/"CONTEXT.json").write_text(json.dumps({"preparation_story_loss":RetainedStoryDefeat.from_history(h,1).private_dict()}))
    work=tmp_path/"WORK.json";work.write_text(json.dumps({"retain_story_preparation_opposition":True}))
    menu=NativeStoryBranchInventory(lambda *a:GoalBindingSet((),()),lambda *a:())
    backend=N(PREPARATION_LOSS_OBSERVER_SUPPORTED=True,assembly=lambda *a,**k:(b"unchanged",None,menu,{},dict(partition="train")))
    with pytest.raises(ValueError,match="lineage or partition"):
        assemble_configured_player(backend,config(),parent,tmp_path/"out",plan_path=work)
