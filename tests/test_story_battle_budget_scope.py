from types import SimpleNamespace as N

import pytest
from test_red_story_battle import actor, contract
from test_red_trainer_battle_lifecycle import fixture
from pokemon_red_completion import red_story_battle as story
from pokemon_red_completion.red_player_story_battle import (
    StoryBattleDecisionBudgetReached, raise_if_story_battle_budget_reached,
)


@pytest.mark.parametrize("outcome", ["won", "lost", "unresolved"])
def test_larger_story_allowance_is_one_owned_episode(monkeypatch, tmp_path, outcome):
    _, reader, fake, actions = fixture(outcome)
    battler = actor(tmp_path)
    rival = story.StoryTrainerContract("story", "trainer-one", 61, (242, 42, 4), 8, 480)
    reader.read_active_trainer_identity = lambda: rival.trainer_identity
    original = fake.continue_battle
    seen = []
    def play(reader, executor, **kwargs):
        assert kwargs.pop("story_authority") is True
        seen.append(kwargs["maximum_decisions"])
        return original(reader, executor, **kwargs)
    battler.continue_battle = play
    monkeypatch.setattr(story, "advance_battle_to_policy_boundary", lambda *a, **k: None)
    controller = story.FrozenStoryBattleController(battler, (rival,), maximum_decisions=160)
    result = controller.run(reader, actions, objective_id="story", battle_plan_id="trainer-one", expected_map=61)
    assert result.outcome == outcome
    assert seen == [160]
    assert story.FrozenStoryBattleController(battler, (contract(),)).maximum_decisions == 80
    with pytest.raises(ValueError):
        story.FrozenStoryBattleController(battler, (rival,), maximum_decisions=161)


@pytest.mark.parametrize("fault", [None, "identity", "map", "count", "closed", "no_living_party"])
def test_typed_budget_requires_exact_retained_battle_and_never_issues_input(fault):
    raw = N(battle_state=2, map_id=33, party_hp=(64, 0))
    episode = N(stop_reason="decision_budget", battle_won=False, decisions=tuple(range(160)), final_battle_state=2)
    identity = (242, 42, 11)
    if fault == "identity": identity = (242, 42, 10)
    if fault == "map": raw.map_id = 19
    if fault == "count": episode.decisions = tuple(range(159))
    if fault == "closed": raw.battle_state = 0
    if fault == "no_living_party": raw.party_hp = (0, 0)
    runtime = N(reader=N(read=lambda: raw, read_active_trainer_identity=lambda: identity),
                emulator=N(save_state_bytes=lambda: b"exact retained state"))
    records = []
    actions = N(record_diagnostic_event=lambda *a: records.append(a))
    result = N(outcome="unresolved", field_ready=False, episode=episode)
    args = result, N(maximum_decisions=160), runtime, N(map_id=33, trainer_identity=(242, 42, 11)), actions
    if fault:
        assert raise_if_story_battle_budget_reached(*args) is None
        assert records == []
    else:
        with pytest.raises(StoryBattleDecisionBudgetReached):
            raise_if_story_battle_budget_reached(*args)
        assert len(records) == 1
        assert records[0][1]["decisions_consumed"] == 160
        assert records[0][1]["new_controller_inputs"] == 0


def test_larger_allowance_rejects_nonrival_story_and_funding(monkeypatch, tmp_path):
    from pokemon_red_completion.red_trainer_battle_lifecycle import continue_learned_trainer_battle
    from pokemon_red_completion.battle_runtime import BattleRuntimeTiming
    _, reader, fake, actions = fixture("unresolved")
    with pytest.raises(ValueError):
        story.FrozenStoryBattleController(actor(tmp_path), (contract(),), maximum_decisions=81)
    for story_authority in (False, True):
        with pytest.raises(ValueError, match="contract"):
            continue_learned_trainer_battle(fake, reader, actions,
                trainer_identity=(230, 30, 4), defeated_event=8,
                ordinary_victory_money=480, timing=BattleRuntimeTiming(),
                remaining_decisions=81, story_authority=story_authority)


def test_whole_rival_exhaustion_never_qualifies_for_automatic_handoff(monkeypatch):
    from hashlib import sha256
    import run_configured_red_player as script
    from run_fresh_red_player import model_handoff_verified
    from pokemon_red_completion.red_player_story_battle import RivalBattleDecisionBudgetReached
    episode=N(stop_reason="decision_budget", battle_won=False, decisions=tuple(range(160)),final_battle_state=2)
    raw=N(battle_state=2,map_id=33,party_hp=(64,))
    data=b"retained whole-battle terminal"
    runtime=N(reader=N(read=lambda:raw,read_active_trainer_identity=lambda:(242,42,11)),emulator=N(save_state_bytes=lambda:data,pressed_buttons=set(),frame_count=100))
    records=[]
    with pytest.raises(RivalBattleDecisionBudgetReached) as error:
        raise_if_story_battle_budget_reached(N(outcome="unresolved",field_ready=False,episode=episode),N(maximum_decisions=160),runtime,N(map_id=33,trainer_identity=(242,42,11)),N(record_diagnostic_event=lambda *a:records.append(a)),whole_battle_allowance=True)
    last=dict(selected_kind="advance_story",failure_phase="execution",safe_terminal=False,
              error_type=type(error.value).__name__,error=str(error.value),terminal_state_sha256=sha256(data).hexdigest(),
              error_chain=[dict(error_type=type(error.value).__name__,reason_code=error.value.reason_code)])
    result=dict(released=True,field_ready=False,state_sha256=sha256(data).hexdigest(),episode=dict(stop_reason="execution_failed",outcomes=[last]))
    assert script.qualified_native_control_handoff(result,runtime=runtime,inspect_bindings=lambda:pytest.fail("must not inspect a successor")) is None
    assert script.qualified_menu_control_handoff(result,runtime=runtime,menu=N(enumerate_base=lambda *a:pytest.fail("must not enumerate a successor"))) is None
    assert not model_handoff_verified([result["episode"]])
    assert records[0][1]["automatic_continuation_allowed"] is False
