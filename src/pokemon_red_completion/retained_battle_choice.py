"""Read-only authentication of an interrupted, already-selected forced switch."""

import json

from .red_trainer_practice_log import verify_trainer_practice_event_log


def read_pending_forced_switch(directory, *, expected_log_sha256, model_sha256):
    """Return the existing choice, never call a policy or infer a replacement."""
    verified = verify_trainer_practice_event_log(directory)
    if (
        verified["last_record_sha256"] != expected_log_sha256
        or verified["terminal_event"] != "run_failed"
        or verified["incomplete_decisions"] != 1
    ):
        raise ValueError("retained choice requires exact failed incomplete log")
    events = [json.loads(p.read_bytes())["payload"] for p in sorted(directory.glob("event-*.json"))]
    if events[0].get("identity", {}).get("model_sha256") != model_sha256:
        raise ValueError("retained choice model differs")
    if len(events) < 4:
        raise ValueError("retained choice missing")
    started, choice, failed = events[-3:]
    slot = choice.get("party_slot")
    if (
        started.get("event") != "decision_started"
        or started.get("mode") != "forced_switch"
        or choice.get("event") != "choice_recorded"
        or choice.get("selected_action") != "switch"
        or choice.get("model_diagnostics", {}).get("decision_mode") != "forced_switch"
        or type(started.get("decision_index")) is not int
        or choice.get("decision_index") != started["decision_index"]
        or type(slot) is not int
        or slot not in started.get("legal_party_slots", [])
        or failed.get("failure_after_event") != "choice_recorded"
    ):
        raise ValueError("retained forced choice is not an owned legal boundary")
    return dict(choice), dict(started), verified
