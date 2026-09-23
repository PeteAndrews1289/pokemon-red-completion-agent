"""Exercise the actual live wrapper signature, not a permissive bridge mock."""

import pytest

from pokemon_red_completion import red_trainer_practice_episode as live


@pytest.mark.parametrize("status", [False, True])
def test_live_wrapper_forwards_status_opt_in_without_loading_or_closing(monkeypatch, status):
    seen = []
    session = object()
    capture, policy, executor, guard = object(), object(), object(), object()

    def inner(actual, **kwargs):
        assert actual is capture
        assert kwargs["policy"] is policy
        assert kwargs["action_executor"] is executor
        assert kwargs["decision_guard"] is guard
        assert kwargs["allow_status_moves"] is status
        assert kwargs["allow_stranded_accuracy_move"] is False
        with kwargs["session_factory"]() as borrowed:
            assert isinstance(borrowed, live.BorrowedLiveController)
        seen.append(True)
        return "retained"

    monkeypatch.setattr(live, "run_red_trainer_practice_episode", inner)
    assert live.run_live_red_trainer_practice_episode(capture, session=session, policy=policy,
        action_executor=executor, decision_guard=guard, allow_status_moves=status) == "retained"
    assert seen == [True]
