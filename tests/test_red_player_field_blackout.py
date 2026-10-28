from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_field_blackout as b
from pokemon_red_completion.goal_manager import GoalDecisionOutcome


@pytest.mark.parametrize("fault", [None, "xp", "story", "stale", "living"])
@pytest.mark.parametrize("battle_state", [0, 1, 2])
def test_only_existing_native_loss_can_settle_without_changing_progress(monkeypatch, fault, battle_state):
    raw = N(battle_state=battle_state, party_hp=(0,), player_money=1690)
    ready = [False]
    lesson = dict(
        completed_objectives=["dex"],
        party=[dict(specimen_ref="s", species_id=177, level=7, experience=250, moves=[(33, 20)])],
    )
    rt = N(
        emulator=N(pressed_buttons=(), frame_count=0, save_state_bytes=lambda: b"state"),
        reader=N(
            read=lambda: raw,
            read_input_readiness=lambda: N(ready=ready[0]),
            read_bottom_dialogue_box_visible=lambda: not ready[0],
        ),
    )
    monkeypatch.setattr(
        b,
        "capture_player_lesson_snapshot",
        lambda _: (
            N(raw=raw),
            {
                "completed_objectives": list(lesson["completed_objectives"]),
                "party": [dict(m) for m in lesson["party"]],
            },
        ),
    )
    monkeypatch.setattr(b, "_field_ready", lambda _: ready[0])
    monkeypatch.setattr(b, "_raw_party_fully_restored", lambda _: ready[0])
    actions = N(actions_executed=0)

    def settle(*args, **kwargs):
        assert kwargs["allow_field_loss"] is True
        actions.actions_executed += 2
        rt.emulator.frame_count += 140
        ready[0] = True
        raw.player_money = 845
        if fault == "xp":
            lesson["party"][0]["experience"] = 251
        if fault == "story":
            lesson["completed_objectives"].append("unearned")
        return dict(cash_lost=845)

    monkeypatch.setattr(b, "settle_red_blackout", settle)
    if fault == "living":
        raw.party_hp = (1,)
        assert b.field_blackout_binding(rt, actions) is None
        return
    binding = b.field_blackout_binding(rt, actions)
    assert actions.actions_executed == 0
    if fault == "stale":
        rt.emulator.save_state_bytes = lambda: b"changed"
        with pytest.raises(ValueError, match="stale"):
            binding.execute()
        assert actions.actions_executed == 0
    elif fault:
        with pytest.raises(ValueError, match="preserve"):
            binding.execute()
    else:
        report = binding.execute()
        assert not report.evidence["learned_recovery"]
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert raw.player_money == 845
