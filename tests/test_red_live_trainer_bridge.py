from types import SimpleNamespace

import pytest
from run_red_trainer_earned_switch import has_actual_switch, verify_story_outcome

from pokemon_red_completion import red_trainer_practice_episode as runtime


@pytest.mark.parametrize("fail", [False, True])
def test_live_bridge_never_resets_or_closes_and_retains_actual_state(monkeypatch, fail):
    calls = []
    session = SimpleNamespace(
        state=b"captured",
        frame_count=0,
        save_state_bytes=lambda: session.state,
        load_state_bytes=lambda _p: calls.append("reset"),
        close=lambda: calls.append("close"),
        press=lambda b: calls.append(b),
        release=lambda b: calls.append("release-" + b),
        read_u8=lambda _a: 7,
    )

    def tick(frames):
        session.frame_count += frames
        session.state = b"earned"

    session.tick = tick

    def episode(_capture, *, session_factory, **_kwargs):
        with session_factory() as live:
            live.load_state_bytes(b"captured")
            live.press("a")
            live.tick(10)
            live.release("a")
            assert live.frame_count == 10 and live.read_u8(1) == 7
            if fail:
                raise RuntimeError("battle interrupted")
            return "completed"

    monkeypatch.setattr(runtime, "run_red_trainer_practice_episode", episode)
    if fail:
        with pytest.raises(RuntimeError, match="interrupted"):
            runtime.run_live_red_trainer_practice_episode(None, session=session, policy=None)
    else:
        assert (
            runtime.run_live_red_trainer_practice_episode(None, session=session, policy=None)
            == "completed"
        )
    assert calls == ["a", "release-a"]
    assert session.state == b"earned"


def test_live_bridge_rejects_stale_capture_and_second_initialization():
    session = SimpleNamespace(save_state_bytes=lambda: b"current")
    live = runtime._BorrowedTrainerSession(session)
    with pytest.raises(runtime.RedTrainerPracticeEpisodeError, match="differs"):
        live.load_state_bytes(b"stale")
    live.load_state_bytes(b"current")
    with pytest.raises(runtime.RedTrainerPracticeEpisodeError, match="reset"):
        live.load_state_bytes(b"current")


def test_story_verifier_requires_new_event_and_preserved_actual_ledger():
    before = {
        "registered": [7, 8, 41],
        "party_national_ids": [8, 41],
        "next_trainer_defeated": False,
    }
    after = {
        **before,
        "party_national_ids": [41, 8],
        "next_trainer_defeated": True,
        "battle_state": 0,
    }
    episode = SimpleNamespace(battle_won=True)
    assert verify_story_outcome(before, after, episode)["status"] == "succeeded"
    for broken in (
        {**after, "registered": [8, 41]},
        {**after, "party_national_ids": [8]},
        {**after, "battle_state": 2},
        {**after, "next_trainer_defeated": False},
    ):
        assert verify_story_outcome(before, broken, episode)["status"] == "failed"
    assert verify_story_outcome(before, after, None)["status"] == "failed"
    assert (
        verify_story_outcome({**before, "next_trainer_defeated": True}, after, episode)["status"]
        == "failed"
    )


def test_prompt_decline_does_not_count_as_real_switch():
    assert not has_actual_switch(
        SimpleNamespace(decisions=[{"kind": "switch_prompt", "party_slot": None}])
    )
    for kind in ("voluntary_switch", "forced_switch", "switch_prompt"):
        assert has_actual_switch(SimpleNamespace(decisions=[{"kind": kind, "party_slot": 2}]))
