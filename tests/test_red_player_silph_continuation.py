from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_silph as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason


def setup(monkeypatch, which="third", status="complete"):
    index = [p[0] for p in s._CONTINUATION_EVENTS].index(which)
    flags = {int(p[1]) for p in s._CONTINUATION_EVENTS[:index]}
    flags.add(int(s._CONTINUATION_EVENTS[index][2]))
    raw = N(
        map_id=int(s.MapId.SAFFRON_POKECENTER),
        player_y=3,
        player_x=3,
        bag_items=((int(s.ItemId.CARD_KEY), 1),),
        event_flags=flags,
        full=True,
    )
    state, lesson, checked, invoked = (
        [b"source"],
        {"completed_objectives": ["defeat_blaine"]},
        [],
        [],
    )
    rt = N(
        emulator=N(save_state_bytes=lambda: state[0], frame_count=0),
        reader=N(read=lambda: raw, read_rival_starter=lambda: 153),
        adapter=N(graph=N(available_objectives=lambda _: (N(id="liberate_silph"),))),
    )
    actions, route = N(actions_executed=0), N(rom=b"rom", allow_surf=True)
    contract = N(trainer_identity=(230, 30, 25))
    actor = N(require_story_contract=checked.append, development_story_scope=object())
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "_raw_party_fully_restored", lambda r: r.full)
    monkeypatch.setattr(s, "event_flag_is_set", lambda flags, event: event in flags)
    monkeypatch.setattr(
        s,
        "capture_player_lesson_snapshot",
        lambda _: (
            N(raw=raw, game_state=None),
            {"completed_objectives": list(lesson["completed_objectives"])},
        ),
    )
    monkeypatch.setattr(s, "silph_continuation_contract", lambda *a, **kw: contract)
    monkeypatch.setattr(s, "trainer_party_quote", lambda *a: N(party=(N(level=28), N(level=28))))
    monkeypatch.setattr(
        s, "FrozenStoryBattleController", lambda a, c, **kw: N(actor=a, contracts=c)
    )

    def phase(*args, **kw):
        assert kw["controller"].actor is actor and kw["controller"].contracts == (contract,)
        invoked.append(kw)
        state[0], actions.actions_executed, rt.emulator.frame_count = b"terminal", 2, 8
        if status == "complete":
            flags.add(int(s._CONTINUATION_EVENTS[index][1]))
            if which == "third":
                flags.add(int(s.EventFlag.SILPH_CO_3_UNLOCKED_DOOR_2))
            if which == "giovanni":
                lesson["completed_objectives"].append("liberate_silph")
        return dict(status=status)

    def reward(*args, **kw):
        assert which == "giovanni" and status == "complete"
        raw.bag_items += ((int(s.ItemId.MASTER_BALL), 1),)
        flags.add(int(s.EventFlag.GOT_MASTER_BALL))
        return dict(status="complete", master_balls_received=1)

    monkeypatch.setattr(s, "run_learned_silph_continuation", phase)
    monkeypatch.setattr(s, "collect_silph_reward", reward)
    return rt, actions, route, actor, raw, state, lesson, checked, invoked


@pytest.mark.parametrize("map_id", [19, 23, int(s.MapId.SAFFRON_POKECENTER)])
@pytest.mark.parametrize("which", ["rival", "giovanni"])
def test_unrestored_continuation_does_not_advertise_an_unusable_story_return(
    monkeypatch, map_id, which,
):
    rt, actions, route, actor, raw, state, _, checked, calls = setup(monkeypatch, which)
    raw.map_id, raw.player_y, raw.full = map_id, 7, False
    monkeypatch.setattr(s, "story_travel_binding", lambda *a, **k: pytest.fail("unusable travel"))
    assert s.silph_continuation_story_option(
        rt, actions, None, route=route, battler=actor, combat_levels=(40,), continuous_travel=True,
    ) is None
    assert actions.actions_executed == 0 and not checked and not calls and state[0] == b"source"


@pytest.mark.parametrize("which", ["third", "rival", "eleventh", "giovanni"])
def test_native_prerequisite_phase_has_real_preview_and_exact_actor(monkeypatch, which):
    rt, actions, route, actor, raw, state, lesson, checked, calls = setup(monkeypatch, which)
    binding, challenge = s.silph_continuation_story_option(
        rt, actions, None, route=route, battler=actor, combat_levels=(26, 35, 33)
    )
    assert actions.actions_executed == 0 and challenge.opposition_known
    assert challenge.maximum_level_deficit == -0.05
    report = binding.execute()
    assert calls[0]["phase"] == which
    assert calls[0]["rival_from_center"] is (which == "rival")
    assert calls[0]["recovered_from_center"] is (which != "rival")
    assert calls[0]["ordinary_game_economy"] is True
    assert "opening_item_support" not in calls[0]
    assert report.evidence["chapter_complete"] is (which == "giovanni")
    assert report.evidence["phase"]["embedded_restoration"] is False
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert checked and state[0] == b"terminal"
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


@pytest.mark.parametrize(
    "fault", ["card", "flags", "prerequisite", "unrestored", "unavailable", "full_bag"]
)
def test_no_execution_or_actor_for_unearned_or_unready_phase(monkeypatch, fault):
    rt, actions, route, actor, raw, _, _, checked, calls = setup(monkeypatch, "giovanni")
    if fault == "card":
        raw.bag_items = ()
    elif fault == "flags":
        raw.event_flags = None
    elif fault == "prerequisite":
        raw.event_flags = set()
    elif fault == "unrestored":
        raw.full = False
    elif fault == "unavailable":
        rt.adapter.graph.available_objectives = lambda _: ()
    else:
        raw.bag_items = ((int(s.ItemId.CARD_KEY), 1),) + tuple((n + 100, 1) for n in range(19))
    assert (
        s.silph_continuation_story_option(
            rt, actions, None, route=route, battler=actor, combat_levels=(26,)
        )
        is None
    )
    assert actions.actions_executed == 0 and not checked and not calls


@pytest.mark.parametrize("tamper", ["defeated", "door", "chapter", "state", "card"])
def test_partial_phase_cannot_fabricate_liberation(monkeypatch, tamper):
    rt, actions, route, actor, raw, state, lesson, *_ = setup(monkeypatch)
    binding, _ = s.silph_continuation_story_option(
        rt, actions, None, route=route, battler=actor, combat_levels=(26,)
    )
    report = binding.execute()
    if tamper == "defeated":
        raw.event_flags.remove(int(s.EventFlag.BEAT_SILPH_CO_3F_TRAINER_0))
    elif tamper == "door":
        raw.event_flags.remove(int(s.EventFlag.SILPH_CO_3_UNLOCKED_DOOR_2))
    elif tamper == "chapter":
        lesson["completed_objectives"].append("liberate_silph")
    elif tamper == "card":
        raw.bag_items = ()
    else:
        state[0] = b"tampered"
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("tamper", ["reward_event", "reward_stock"])
def test_giovanni_requires_actual_master_ball_reward(monkeypatch, tamper):
    rt, actions, route, actor, raw, *_ = setup(monkeypatch, "giovanni")
    binding, _ = s.silph_continuation_story_option(
        rt, actions, None, route=route, battler=actor, combat_levels=(26,)
    )
    report = binding.execute()
    if tamper == "reward_event":
        raw.event_flags.remove(int(s.EventFlag.GOT_MASTER_BALL))
    else:
        raw.bag_items = ((int(s.ItemId.CARD_KEY), 1),)
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


def test_loss_is_charged_failure_without_reward_or_fallback(monkeypatch):
    rt, actions, route, actor, _, _, _, _, calls = setup(monkeypatch, "giovanni", "lost")
    binding, _ = s.silph_continuation_story_option(
        rt, actions, None, route=route, battler=actor, combat_levels=(26,)
    )
    report = binding.execute()
    assert binding.verify(report).failure_reason is GoalFailureReason.RESOURCE_LOST
    assert len(calls) == 1 and "reward" not in report.evidence["phase"]


def test_stale_actor_and_state_refused_before_input(monkeypatch):
    rt, actions, route, actor, _, state, _, _, calls = setup(monkeypatch)
    chosen = [actor]
    binding, _ = s.silph_continuation_story_option(
        rt,
        actions,
        None,
        route=route,
        battler=None,
        combat_levels=(26,),
        battler_for_contract=lambda _: chosen[0],
    )
    chosen[0] = object()
    with pytest.raises(ValueError, match="actor changed"):
        binding.execute()
    state[0] = b"stale"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert actions.actions_executed == 0 and not calls
