from __future__ import annotations

import json

import pytest

from pokemon_red_completion.battle_runtime_diagnostics import BattleRuntimeDiagnostic
from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)


def test_log_retains_complete_ordered_trace(tmp_path):
    log = TrainerPracticeEventLog(tmp_path / "trace", run_identity={"partition": "train"})
    log.emit({"event": "decision_started", "decision_index": 1})
    log.emit({"event": "choice_recorded", "selected_action": "attack"})
    log.finish({"battle_won": False, "stop_reason": "party_defeated"})
    verified = verify_trainer_practice_event_log(log.directory)
    assert verified["complete"] is True
    assert verified["terminal_event"] == "run_finished"
    assert verified["event_count"] == 4
    assert verified["started_decisions"] == 1
    assert verified["incomplete_decisions"] == 1
    with pytest.raises(RuntimeError, match="closed"):
        log.emit({"event": "decision_started"})


def test_log_retains_failure_after_selected_action(tmp_path):
    log = TrainerPracticeEventLog(tmp_path / "failure", run_identity={"partition": "train"})
    log.emit({"event": "decision_started", "decision_index": 1})
    log.emit({"event": "choice_recorded", "selected_action": "switch"})
    error = ValueError("private path /do/not/retain")
    error.battle_runtime_diagnostic = BattleRuntimeDiagnostic(
        phase="settle", total_events=1, recording_failures=0,
        selection={"slot": 2}, events=({"kind": "selection"},), exception_chain=(),
    )
    log.fail(error)
    assert verify_trainer_practice_event_log(log.directory)["terminal_event"] == "run_failed"
    text = (log.directory / "event-00004.json").read_text()
    assert "ValueError" in text
    assert "choice_recorded" in text
    assert "battle_runtime_diagnostic" in text
    assert '"phase":"settle"' in text
    assert "/do/not/retain" not in text


def test_log_rejects_modified_event(tmp_path):
    log = TrainerPracticeEventLog(tmp_path / "tamper", run_identity={"partition": "train"})
    log.finish({"battle_won": True})
    path = log.directory / "event-00001.json"
    record = json.loads(path.read_bytes())
    record["payload"]["identity"]["partition"] = "development"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="chain differs"):
        verify_trainer_practice_event_log(log.directory)


def test_log_rejects_sequence_gap(tmp_path):
    log = TrainerPracticeEventLog(tmp_path / "gap", run_identity={"partition": "train"})
    log.finish({"battle_won": True})
    (log.directory / "event-00001.json").rename(log.directory / "event-00003.json")
    with pytest.raises(ValueError, match="sequence has a gap"):
        verify_trainer_practice_event_log(log.directory)
