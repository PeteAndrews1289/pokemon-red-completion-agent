import json
from types import SimpleNamespace

import pytest

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.red_native_boxed_evolution import native_evolution_training_diagnostics


def test_no_recording_port_keeps_legacy_interface():
    assert native_evolution_training_diagnostics(object()) == {}


@pytest.mark.parametrize("kind", ["control", "candidates", "summary"])
def test_existing_training_sinks_are_observers_not_authorities(kind):
    rows = []
    actions = CountingExecutor(SimpleNamespace(
        record_diagnostic_event=lambda event, payload: rows.append((event, payload))))
    callbacks = native_evolution_training_diagnostics(actions)
    assert set(callbacks) == {
        "decision_sink", "candidate_decision_sink", "execution_summary_sink", "move_decision_sink"}
    name = {"control": "decision_sink", "candidates": "candidate_decision_sink",
            "summary": "execution_summary_sink"}[kind]
    record = {"selected_candidate_index": 1, "features": [0.2, 0.4]}
    assert callbacks[name](SimpleNamespace(public_dict=lambda: record)) is None
    assert record == {"selected_candidate_index": 1, "features": [0.2, 0.4]}
    assert rows == [("wild_training_" + kind, dict(
        actor="rule_based_support", source="native_level_evolution", **record))]
    assert actions.actions_executed == 0
    json.dumps(rows)


def test_move_log_retains_validated_choice_and_unknowns_without_claiming_execution():
    rows = []
    raw = SimpleNamespace(map_id=22, battle_state=1, enemy_hp=45, party_levels=(36, 24),
                          party_pp=((15, 20, 0, 0), (22, 10, 0, 0)))
    callbacks = native_evolution_training_diagnostics(SimpleNamespace(
        record_diagnostic_event=lambda event, payload: rows.append((event, payload))))
    assert callbacks["move_decision_sink"](raw, 2) is None
    event, payload = rows[0]
    assert event == "wild_training_move"
    assert payload["selected_move_slot"] == 2
    assert payload["selection_validated"] is True
    assert payload["execution_confirmed"] is False
    assert payload["actor"] == "rule_based_support"
    assert payload["observed"]["enemy_hp"] == 45
    assert payload["observed"]["enemy_status"] is None
    assert payload["observed"]["party_pp"] == raw.party_pp
    assert vars(raw) == dict(map_id=22, battle_state=1, enemy_hp=45, party_levels=(36, 24),
                            party_pp=((15, 20, 0, 0), (22, 10, 0, 0)))
    json.dumps(rows)


def test_recording_failure_is_not_swallowed_or_used_as_an_action():
    def fail(*args):
        raise OSError("journal unavailable")
    callbacks = native_evolution_training_diagnostics(
        SimpleNamespace(record_diagnostic_event=fail))
    with pytest.raises(OSError, match="journal unavailable"):
        callbacks["move_decision_sink"](SimpleNamespace(), 1)
