import hashlib
import json
from types import SimpleNamespace

import pytest
from run_red_trainer_earned_switch import (
    MODEL_SHA,
    authenticated_endpoint,
    has_actual_switch,
    verify_story_outcome,
)

from pokemon_red_completion import red_trainer_practice_episode as runtime
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog


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


@pytest.mark.parametrize("corrupt", [None, "state", "outcome", "receipt", "model"])
def test_earned_endpoint_requires_bound_state_model_receipt_and_terminal(tmp_path, corrupt):
    state = b"earned battle endpoint"
    digest = hashlib.sha256(state).hexdigest()
    endpoint = {"episode_returned": True, "pressed_buttons": [], "state_sha256": digest}
    report = {
        "stop_reason": "battle_won",
        "battle_won": True,
        "outcome_model_sha256": MODEL_SHA["J"],
        "manifest_sha256": "a" * 64,
        "final_state_sha256": digest,
        "final_state_receipt_sha256": canonical_sha256(endpoint),
        "teacher_queries": 0,
        "memory_write_actions": 0,
    }
    log = TrainerPracticeEventLog(
        tmp_path / "events",
        run_identity={
            "outcome_model_sha256": MODEL_SHA["J"],
            "capture_manifest_sha256": "a" * 64,
        },
    )
    log.finish({"outcome_sha256": canonical_sha256(report)})
    if corrupt == "state":
        state = b"different state"
    elif corrupt == "outcome":
        report["battle_won"] = False
    elif corrupt == "receipt":
        endpoint["pressed_buttons"] = ["a"]
    elif corrupt == "model":
        report["outcome_model_sha256"] = "b" * 64
    (tmp_path / "final.state").write_bytes(state)
    (tmp_path / "outcome.json").write_text(json.dumps(report))
    (tmp_path / "final-state.json").write_text(json.dumps(endpoint))
    if corrupt is None:
        assert authenticated_endpoint(tmp_path) == (state, report)
    else:
        with pytest.raises(ValueError, match="authentication"):
            authenticated_endpoint(tmp_path)
