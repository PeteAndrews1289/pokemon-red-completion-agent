"""Proposed ROM-free checks; root must install/run against the proposed source."""
from types import SimpleNamespace as N
import inspect
import pytest
from test_red_story_battle import actor, contract
from test_red_trainer_battle_lifecycle import fixture
from pokemon_red_completion import red_story_battle as story
from pokemon_red_completion.red_learned_trainer import story_whole_battle_decision_limit
from pokemon_red_completion.red_player_league_options import bind_live_league_runtime
from pokemon_red_completion.red_lorelei_story import FrozenLoreleiStoryController
from pokemon_red_completion.red_trainer_battle_lifecycle import continue_learned_trainer_battle
from pokemon_red_completion.battle_runtime import BattleRuntimeTiming

LEAGUE = [(244,44,1),(233,33,1),(246,46,1),(247,47,1),(243,43,1),(243,43,2),(243,43,3)]

@pytest.mark.parametrize("identity", LEAGUE)
@pytest.mark.parametrize("outcome", ["won","lost","unresolved"])
def test_explicit_league_allowance_is_one_owned_episode(monkeypatch,tmp_path,identity,outcome):
    _,reader,fake,actions=fixture(outcome)
    battler=actor(tmp_path)
    exact=story.StoryTrainerContract("story","trainer-one",61,identity,8,480)
    reader.read_active_trainer_identity=lambda:identity
    original=fake.continue_battle
    seen=[]
    def play(reader,executor,**kwargs):
        assert kwargs.pop("story_authority") is True
        seen.append(kwargs["maximum_decisions"])
        return original(reader,executor,**kwargs)
    battler.continue_battle=play
    monkeypatch.setattr(story,"advance_battle_to_policy_boundary",lambda *a,**k:None)
    controller=story.FrozenStoryBattleController(battler,(exact,),maximum_decisions=160)
    result=controller.run(reader,actions,objective_id="story",battle_plan_id="trainer-one",expected_map=61)
    assert result.outcome==outcome
    assert seen==[160]  # no second80 call and no replay/renewal
    if outcome=="unresolved":
        assert not result.field_ready
    with pytest.raises(ValueError):
        story.FrozenStoryBattleController(battler,(exact,),maximum_decisions=161)

@pytest.mark.parametrize("identity",[(244,44,2),(247,47,2),(243,43,4),(230,30,4),(225,25,0)])
def test_unknown_or_unadmitted_league_sets_do_not_get_league_allowance(identity):
    # Rival's existing class permission is intentionally retained; not a League expansion.
    if identity[0] not in {225,242}:
        assert story_whole_battle_decision_limit(identity)==80

@pytest.mark.parametrize("identity",LEAGUE)
def test_ordinary_funding_cannot_borrow_league_budget(identity):
    _,reader,fake,actions=fixture("unresolved")
    with pytest.raises(ValueError,match="contract"):
        continue_learned_trainer_battle(fake,reader,actions,trainer_identity=identity,
            defeated_event=8,ordinary_victory_money=480,timing=BattleRuntimeTiming(),
            remaining_decisions=81,story_authority=False)


def test_old_defaults_and_nonleague_story_remain80(tmp_path):
    assert inspect.signature(bind_live_league_runtime).parameters["maximum_decisions"].default==80
    assert FrozenLoreleiStoryController.__dataclass_fields__["maximum_decisions"].default==80
    assert story.FrozenStoryBattleController(actor(tmp_path),(contract(),)).maximum_decisions==80
    with pytest.raises(ValueError):
        story.FrozenStoryBattleController(actor(tmp_path),(contract(),),maximum_decisions=81)


def test_unresolved_episode_still_cannot_be_claimed_as_lorelei_victory():
    # The patch must not alter the observed failure's final verdict/settlement.
    # Existing actual-controller tests must additionally replay won/lost/unresolved;
    # this file leaves the original refusal branch in production unchanged.
    source=inspect.getsource(FrozenLoreleiStoryController.run)
    assert 'result.outcome != "won" or not result.field_ready' in source
    assert "raise LoreleiStoryBattleStopped" in source
@pytest.mark.parametrize("objective",["defeat_lorelei","defeat_bruno","defeat_agatha","defeat_lance"])
def test_actual_scoped_retry_accepts_explicit160_and_rejects161(tmp_path,objective):
    import test_red_scoped_league_retry as retry
    ctl=retry.controller(tmp_path,objective)
    assert ctl.maximum_decisions==80
    ctl.maximum_decisions=160
    ctl.require_identity()
    ctl.maximum_decisions=161
    with pytest.raises(ValueError):ctl.require_identity()

@pytest.mark.parametrize("variant",[1,2,3])
def test_actual_scoped_champion_accepts160_and_rejects161(tmp_path,variant):
    import test_red_scoped_champion as champion
    ctl=champion.controller(tmp_path,variant)
    ctl.maximum_decisions=160
    ctl.require_identity()
    ctl.maximum_decisions=161
    with pytest.raises(ValueError):ctl.require_identity()


def test_actual_legacy_first_lorelei_does_not_inherit160(tmp_path):
    import test_red_scoped_lorelei as lorelei
    ctl=lorelei.controller(tmp_path)
    ctl.maximum_decisions=81
    with pytest.raises(ValueError):ctl.require_identity()

@pytest.mark.parametrize("won",[0,1,2,3])
def test_real_live_composition_explicit160_does_not_call_actor_or_change_default(tmp_path,monkeypatch,won):
    import test_red_player_league_options as existing
    rt,battler,current,_,_,arguments=existing.composition_fixture(tmp_path,monkeypatch,won=won)
    assert battler.calls==7
    arguments["maximum_decisions"]=160
    configured,actor,_=existing.module.bind_live_league_runtime(rt,**arguments)
    assert configured.league_story_battle_controller.maximum_decisions==160
    assert actor.calls==0 and battler.calls==7
    assert not tuple(tmp_path.iterdir())
@pytest.mark.parametrize("fault",["source","model","work","assistance","contract","partition"])
def test_explicit160_keeps_actual_retry_source_model_work_and_scope_guards(tmp_path,monkeypatch,fault):
    import test_red_scoped_league_retry as retry
    import test_red_scoped_lorelei as lorelei
    ctl=retry.controller(tmp_path)
    ctl.maximum_decisions=160
    ctl.require_identity()
    monkeypatch.setattr(lorelei,"controller",lambda _:ctl)
    lorelei.test_scoped_lorelei_rejects_changed_authority(tmp_path,fault)