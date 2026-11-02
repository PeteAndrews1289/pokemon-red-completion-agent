"""ROM-free tests for the frozen full-battle runner and independent decision gate."""

import copy
import json
from types import SimpleNamespace

import audit_red_damage_composition as audit
import pytest
import run_red_damage_composition as packet


def episode(stop="battle_won"):
    before = {
        "party_hp": [10, 10, 10],
        "party_max_hp": [10, 10, 10],
        "party_pp": [[5, 5], [5, 5], [5, 5]],
        "opponent_hp": 10,
    }
    return {
        "decisions": [
            {"state_before": before, "state_after": before, "kind": "attack", "move_slot": 1}
        ],
        "teacher_queries": 0,
        "memory_write_actions": 0,
        "metrics": {
            "teacher_interventions": 0,
            "opponent_faints": 1,
            "party_faints": 0,
            "party_pp_spent": 1,
            "move_suppressed_or_failed": 0,
            "invalid_action_failures": 0,
        },
        "stop_reason": stop,
        "decision_count": 1,
        "player_turn_count": 1,
        "frames_executed": 2,
        "elapsed_ns": 100,
        "action_counts": {"voluntary_switch": 0, "forced_switch": 0},
        "failed_move_executions": 0,
    }


def terminal():
    return {
        "completed_actions": 1,
        "attempted_actions": 1,
        "frame_delta": 2,
        "state_sha256": "state",
    }


def test_nested_pp_and_switch_identity_in_repeat_counter(tmp_path):
    ep = episode()
    ep["decisions"] *= 2
    packet.old.write_once(tmp_path / "episode.json", ep)
    assert packet.old._composition_metrics(ep, tmp_path)["repeat_state_action_loops"] == 1
    ep["decisions"][1] = copy.deepcopy(ep["decisions"][1])
    ep["decisions"][1]["party_slot"] = 2
    assert packet.old._composition_metrics(ep, tmp_path)["repeat_state_action_loops"] == 0


@pytest.mark.parametrize("stop", sorted(packet.CENSORED_STOPS))
def test_only_complete_declared_censors_are_retained(tmp_path, monkeypatch, stop):
    path = tmp_path / "arm"

    def play(*args, **kwargs):
        packet.old.write_once(path / "episode.json", episode(stop))
        packet.old.write_once(path / "final-state.json", terminal())
        raise ValueError(f"unsupported stop {stop}")

    monkeypatch.setattr(packet.old.lab, "play", play)
    import audit_red_interaction_damage_successor as shared

    monkeypatch.setattr(shared, "_audit_events", lambda *args: 1)
    result = packet.play_arm(None, None, None, path, None, 0)
    assert result["censored"] and not result["win"] and not result["loss"]
    with pytest.raises(ValueError, match="consumed"):
        packet.play_arm(None, None, None, path, None, 0)


@pytest.mark.parametrize("error", [RuntimeError("broken executor"), ValueError("broken source")])
def test_unexpected_failure_never_becomes_censor(tmp_path, monkeypatch, error):
    path = tmp_path / "arm"

    def play(*args, **kwargs):
        packet.old.write_once(path / "episode.json", episode("decision_budget"))
        raise error

    monkeypatch.setattr(packet.old.lab, "play", play)
    with pytest.raises(type(error), match=str(error)):
        packet.play_arm(None, None, None, path, None, 0)


def test_non_damage_metadata_must_be_identical():
    baseline = {"damage_reference": "old", "metadata": [1], "move": 3}
    candidate = {**baseline, "damage_reference": "new"}
    packet.assert_models(
        SimpleNamespace(to_dict=lambda: baseline), SimpleNamespace(to_dict=lambda: candidate)
    )
    candidate["metadata"] = [2]
    with pytest.raises(ValueError, match="metadata"):
        packet.assert_models(
            SimpleNamespace(to_dict=lambda: baseline), SimpleNamespace(to_dict=lambda: candidate)
        )


def pairs():
    metric = {
        "win": True,
        "loss": False,
        "censored": False,
        "opponents_defeated": 3,
        "normalized_terminal_hp": 0.5,
        "turns": 10,
        "pp_spent": 10,
        "invalid_action_failures": 0,
        "decision_trace_path": "trace",
    }
    return [
        {
            "team_id": f"team-{i:02d}",
            "offset": offset,
            "roster": "3v3",
            "admitted": copy.deepcopy(metric),
            "candidate": {**copy.deepcopy(metric), "normalized_terminal_hp": 0.55},
        }
        for i in range(24)
        for offset in packet.OFFSETS
    ]


def test_paired_gate_independently_agrees_without_reading_old_outputs():
    rows = pairs()
    result = packet.old.score_composition(rows, {}, bindings={"synthetic": True})
    assert result["provisional_review_gate_passed"]
    assert audit.independent_gate(rows) == []


@pytest.mark.parametrize(
    "key,value,failure",
    [
        ("censored", True, "censored_increase"),
        ("loss", True, "loss_increase"),
        ("win", False, "win_decrease"),
        ("invalid_action_failures", 1, "illegal_action"),
        ("turns", 1000, "common_win_efficiency_regression"),
        ("pp_spent", 1000, "common_win_efficiency_regression"),
    ],
)
def test_frozen_gates_reject_regressions(key, value, failure):
    rows = pairs()
    rows[0]["candidate"][key] = value
    result = packet.old.score_composition(rows, {}, bindings={})
    assert failure in result["gate_failures"]
    assert audit.independent_gate(rows) == result["gate_failures"]


def test_no_common_win_is_unassessed_not_success():
    rows = pairs()
    for p in rows:
        p["admitted"]["win"] = p["candidate"]["win"] = False
    assert "common_win_efficiency_unassessed" in audit.independent_gate(rows)


def test_invalid_timing_rejected_before_protected_inputs(monkeypatch):
    monkeypatch.setattr(packet, "OFFSETS", (0, 16, 12))
    monkeypatch.setattr(packet.old, "inputs", lambda: pytest.fail("opened inputs"))
    with pytest.raises(packet.damage.RedTrainerPracticeEpisodeError, match="timing"):
        packet.preflight()


def test_expired_packet_does_not_launch(monkeypatch):
    monkeypatch.setattr(packet.time, "monotonic", lambda: packet.MAX_SECONDS)
    with pytest.raises(TimeoutError):
        packet.deadline(0)


def test_claim_and_recipe_are_json_serializable():
    assert json.loads(json.dumps(packet.OFFSETS)) == [0, 6, 12]


def test_final_knockout_has_no_live_roster_but_requires_exit_evidence():
    decision = {
        "kind": "attack",
        "state_before": {"opponent_hp": 82},
        "state_after": {"opponent_hp": 0},
        "outcome": {"battle_exited": True, "opponent_fainted": True},
    }
    assert audit.opponent_faints(decision) == 1
    decision["outcome"]["battle_exited"] = False
    with pytest.raises(ValueError, match="final knockout"):
        audit.opponent_faints(decision)


def test_roster_delta_counts_knockout_not_sendout():
    assert (
        audit.opponent_faints(
            {
                "referee_opponent_roster_hp_before": [0, 20, 30],
                "referee_opponent_roster_hp_after": [0, 0, 30],
            }
        )
        == 1
    )


def test_audit_projects_real_public_move_slot_indices():
    from test_red_trainer_practice_fit import _target

    from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog

    observation = _target()["observation"]
    prepared = audit.prepared_from_observation(observation, PokemonRedBattleCatalog())
    assert prepared.features.slot_indices == (0, 1)
    assert any(prepared.supported_candidate_mask)
