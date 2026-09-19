from run_red_trainer_terminal_curriculum import late_capture_reasons


def test_late_capture_covers_progress_without_outcome_selection():
    event = {
        "event": "decision_started",
        "decision_index": 8,
        "mode": "forced_switch",
        "state_before": {"party_hp": [0, 0, 50], "opponent_party_position": 2},
    }
    expected = {"forced_switch", "last_ally", "last_opponent"}
    assert late_capture_reasons(event, set()) == expected
    assert late_capture_reasons(event, expected) == set()
    assert late_capture_reasons(event, {"last_ally"}) == expected - {"last_ally"}
    event["mode"] = "switch_prompt"
    assert late_capture_reasons(event, expected) == {"switch_prompt"}


def test_late_attack_capture_waits_past_singleton_replacement():
    event = {
        "event": "decision_started",
        "decision_index": 9,
        "mode": "forced_switch",
        "state_before": {"party_hp": [0, 0, 50], "opponent_party_position": 2},
    }
    seen = set()
    assert late_capture_reasons(event, seen, main_only=True) == set()
    event["mode"] = "main"
    assert late_capture_reasons(event, seen, main_only=True) == {"last_ally", "last_opponent"}


def test_late_capture_skips_initial_and_early_main_and_nondecision_events():
    assert late_capture_reasons({"event": "run_completed"}, set()) == set()
    event = {
        "event": "decision_started",
        "decision_index": 1,
        "mode": "main",
        "state_before": {"party_hp": [50, 50, 50], "opponent_party_position": 0},
    }
    assert late_capture_reasons(event, set()) == set()
    event["decision_index"] = 4
    assert late_capture_reasons(event, set()) == set()
