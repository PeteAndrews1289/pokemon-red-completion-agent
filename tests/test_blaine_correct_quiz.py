"""Correct-answer opt-in must never reach the legacy battle controller."""

from types import SimpleNamespace

import pytest

from pokemon_red_completion import blaine


@pytest.mark.parametrize("index", range(1, 7))
def test_correct_answer_opens_gate_without_legacy_battle(monkeypatch, index):
    calls = []
    observed = iter((False, True))
    monkeypatch.setattr(blaine, "_event", lambda *args: next(observed))
    monkeypatch.setattr(blaine, "_face_and_interact", lambda *args: calls.append("interact"))
    monkeypatch.setattr(blaine, "_pulse", lambda *args, **kw: calls.append("pulse"))
    monkeypatch.setattr(
        blaine, "_await_trainer_battle", lambda *args: pytest.fail("teacher battle entered")
    )
    reader = SimpleNamespace(read_input_readiness=lambda: SimpleNamespace(ready=True))
    assert (
        blaine._answer_quiz(
            None,
            reader,
            None,
            index,
            blaine.QUIZ_CORRECT_ANSWERS[index - 1],
            blaine.QUIZ_TEXT_PULSES[index - 1],
            correct_only=True,
        )
        is None
    )
    assert calls[0] == "interact"


@pytest.mark.parametrize("index", range(1, 7))
def test_correct_only_rejects_wrong_answer_before_input(monkeypatch, index):
    monkeypatch.setattr(
        blaine, "_event", lambda *args: pytest.fail("must reject before observation")
    )
    with pytest.raises(ValueError, match="cannot authorize"):
        blaine._answer_quiz(
            None,
            None,
            None,
            index,
            not blaine.QUIZ_CORRECT_ANSWERS[index - 1],
            10,
            correct_only=True,
        )


def test_correct_quiz_retains_failed_native_gate(monkeypatch):
    monkeypatch.setattr(blaine, "_event", lambda *args: False)
    monkeypatch.setattr(blaine, "_face_and_interact", lambda *args: None)
    monkeypatch.setattr(blaine, "_pulse", lambda *args, **kw: None)
    with pytest.raises(blaine.BlaineChapterError, match="did not open"):
        blaine._answer_quiz(
            None,
            SimpleNamespace(read_input_readiness=lambda: SimpleNamespace(ready=True)),
            None,
            1,
            True,
            9,
            correct_only=True,
        )
