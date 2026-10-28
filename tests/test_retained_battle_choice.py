import pytest

from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)
from pokemon_red_completion.retained_battle_choice import read_pending_forced_switch


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "completed",
        "model",
        "hash",
        "attack",
        "index",
        "slot",
        "mode",
        "no_choice",
    ],
)
def test_pending_choice_is_preserved_or_refused(tmp_path, fault):
    log = TrainerPracticeEventLog(tmp_path / "events", run_identity={"model_sha256": "model"})
    log.emit(
        {
            "event": "decision_started",
            "decision_index": 4,
            "mode": "forced_switch",
            "legal_party_slots": [2, 3, 4],
        }
    )
    if fault != "no_choice":
        log.emit(
            {
                "event": "choice_recorded",
                "decision_index": 5 if fault == "index" else 4,
                "selected_action": "attack" if fault == "attack" else "switch",
                "party_slot": 1 if fault == "slot" else 3,
                "model_diagnostics": {
                    "decision_mode": "attack" if fault == "mode" else "forced_switch"
                },
            }
        )
    if fault == "completed":
        log.emit({"event": "decision_completed", "decision_index": 4})
    log.fail(RuntimeError("execution"))
    digest = verify_trainer_practice_event_log(log.directory)["last_record_sha256"]
    kwargs = {
        "expected_log_sha256": "bad" if fault == "hash" else digest,
        "model_sha256": "bad" if fault == "model" else "model",
    }
    if fault:
        with pytest.raises(ValueError):
            read_pending_forced_switch(log.directory, **kwargs)
    else:
        choice, started, _ = read_pending_forced_switch(log.directory, **kwargs)
        assert choice["party_slot"] == 3 and started["decision_index"] == 4
