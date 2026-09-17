from __future__ import annotations

from copy import deepcopy

import pytest

from pokemon_red_completion.battle_scenario_capture import (
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_trainer_practice_admission import (
    TrainerPracticeAdmissionError,
    inspect_trainer_practice_choices,
)
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog
from pokemon_red_completion.scenario_lab import ScenarioPartition

_START = {
    "features": {
        "battle": {"active": True, "opponent_hp": 20, "opponent_max_hp": 20},
        "party": {
            "active_index": 0,
            "lead": {"moves": [{"slot_index": 0, "pp": 10}]},
            "members": [{"hp": 40, "max_hp": 50}, {"hp": 35, "max_hp": 50}],
        },
    }
}
_END = {
    "features": {
        "battle": {"active": True, "opponent_hp": 20, "opponent_max_hp": 20},
        "party": {"members": [{"hp": 35, "max_hp": 50}, {"hp": 35, "max_hp": 50}]},
    }
}
_CHOICES = ("pokemon.core:battle:move:1", "pokemon.core:battle:switch:2")


def _inspect(capture, document):
    return inspect_trainer_practice_choices(
        capture, document, expected_choice_refs=_CHOICES, continuation_policy_id="unit"
    )


def _capture(tmp_path):
    state = b"synthetic trainer state"
    path = tmp_path / "train.state"
    manifest = tmp_path / "train.state.json"
    path.write_bytes(state)
    manifest.write_bytes(
        build_battle_scenario_capture_payload(
            capture_id="train-unit",
            root_lineage_id="one-root",
            partition=ScenarioPartition.TRAIN,
            state_bytes=state,
            initial_observation_sha256=canonical_sha256(_START),
            source_commit="c" * 40,
            expected_map=120,
            expected_battle_state=2,
        )
    )
    return open_battle_scenario_capture(path, manifest)


def _document(capture):
    before = {
        "party_hp": [40, 35],
        "party_max_hp": [50, 50],
        "party_pp": [[10, 0, 0, 0], [10, 0, 0, 0]],
    }

    def branch(choice, kind, slot):
        after = deepcopy(before)
        after["party_hp"] = [35, 35]
        if kind == "attack":
            after["party_pp"][0][0] = 9
        decision = {
            "decision_index": 1,
            "kind": kind,
            "move_slot": slot if kind == "attack" else None,
            "party_slot": slot if kind == "voluntary_switch" else None,
            "observation": deepcopy(_START),
            "observation_sha256": canonical_sha256(_START),
            "after_observation_sha256": canonical_sha256(_END),
            "legal_move_slots": [1],
            "legal_party_slots": [2],
            "model_input": {
                "candidate_move_slots": [1],
                "legal_mask": [True],
                "supported_candidate_mask": [True],
            },
            "frames_executed": 100,
            "opponent_hp_before": 20,
            "opponent_hp_after": 20,
            "state_before": deepcopy(before),
            "state_after": after,
        }
        return {
            "first_choice_ref": choice,
            "episode": {
                "schema": "pokemon.red.trainer-practice-model-episode.v4",
                "capture_id": capture.manifest.capture_id,
                "manifest_sha256": capture.manifest_sha256,
                "policy_id": f"unit:first={choice}",
                "decisions": [decision],
                "decision_count": 1,
                "player_turn_count": 1,
                "stop_reason": "player_turn_budget",
                "battle_won": False,
                "final_battle_state": 2,
                "final_observation": deepcopy(_END),
                "final_observation_sha256": canonical_sha256(_END),
                "teacher_queries": 0,
                "memory_write_actions": 0,
                "authority_promotions": 0,
                "frames_executed": 100,
                "metrics": {
                    "opponent_faints": 0,
                    "party_faints": 0,
                    "party_hp_lost": 5,
                    "party_pp_spent": 1 if kind == "attack" else 0,
                    "teacher_interventions": 0,
                    "invalid_action_failures": 0,
                },
            },
        }

    return {
        "schema": "pokemon.red.trainer-practice-counterfactual-set.v1",
        "capture_id": capture.manifest.capture_id,
        "manifest_sha256": capture.manifest_sha256,
        "root_lineage_id": capture.manifest.root_lineage_id,
        "partition": "train",
        "player_turn_horizon": 1,
        "branch_count": 2,
        "branches": [
            branch("pokemon.core:battle:move:1", "attack", 1),
            branch("pokemon.core:battle:switch:2", "voluntary_switch", 2),
        ],
    }


def test_admits_only_executed_choices_with_one_upstream_root(tmp_path):
    capture = _capture(tmp_path)
    result = _inspect(capture, _document(capture))
    assert result["executed_choice_count"] == 2
    assert result["new_independent_upstream_roots"] == 0
    assert result["fit_targets"] == 0
    assert result["measured_choices"][1]["first_choice_ref"].endswith("switch:2")


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda d: d.update(root_lineage_id="fabricated-root"), "capture binding"),
        (
            lambda d: d["branches"][1].update(
                first_choice_ref=d["branches"][0]["first_choice_ref"]
            ),
            "repeated",
        ),
        (
            lambda d: d["branches"][0]["episode"]["decisions"][0].update(move_slot=2),
            "first executed",
        ),
        (
            lambda d: d["branches"][0]["episode"]["decisions"][0]["state_after"].update(
                party_hp=[65535, 35]
            ),
            "impossible HP",
        ),
        (lambda d: d["branches"][0]["episode"].update(player_turn_count=0), "player-turn"),
        (
            lambda d: d["branches"][0]["episode"].update(stop_reason="failed"),
            "unqualified terminal",
        ),
    ],
)
def test_rejects_unsafe_training_contrast(tmp_path, mutation, match):
    capture = _capture(tmp_path)
    document = deepcopy(_document(capture))
    mutation(document)
    with pytest.raises(TrainerPracticeAdmissionError, match=match):
        _inspect(capture, document)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["branches"][0]["episode"]["metrics"].update(opponent_faints=999),
        lambda d: d["branches"][0]["episode"]["decisions"][0]["observation"]["features"][
            "battle"
        ].update(opponent_hp=999),
        lambda d: (d.update(branches=d["branches"][-1:]), d.update(branch_count=1)),
        lambda d: d["branches"][0]["episode"].update(
            policy_id="wrong:first=pokemon.core:battle:move:1"
        ),
        lambda d: d["branches"][0]["episode"]["final_observation"]["features"]["battle"].update(
            opponent_hp=65535
        ),
        lambda d: d["branches"][0]["episode"]["decisions"][0].update(frames_executed=-100),
        lambda d: d["branches"][0]["episode"].update(stop_reason="battle_won", battle_won=True),
        lambda d: d["branches"][0]["episode"].pop("final_observation"),
    ],
)
def test_admission_rejects_mutated_outcome_evidence(tmp_path, mutation):
    capture = _capture(tmp_path)
    document = deepcopy(_document(capture))
    mutation(document)
    with pytest.raises(TrainerPracticeAdmissionError):
        _inspect(capture, document)


def test_branch_logs_bind_prospectively_declared_executions(tmp_path):
    capture = _capture(tmp_path)
    document = _document(capture)
    plan_sha = "a" * 64
    logs = {}
    for index, branch in enumerate(document["branches"]):
        choice = branch["first_choice_ref"]
        episode = branch["episode"]
        directory = tmp_path / f"branch-{index}-events"
        log = TrainerPracticeEventLog(
            directory,
            run_identity={
                "capture_id": capture.manifest.capture_id,
                "root_lineage_id": capture.manifest.root_lineage_id,
                "capture_manifest_sha256": capture.manifest_sha256,
                "source_commit": capture.manifest.source_commit,
                "partition": "train",
                "policy_id": "unit",
                "first_choice_ref": choice,
                "player_turn_horizon": 1,
                "plan_sha256": plan_sha,
                "model_sha256": "b" * 64,
                "max_decisions": 8,
                "opening_idle_frames": 0,
            },
        )
        log.emit(
            {
                "event": "episode_started",
                "manifest_sha256": capture.manifest_sha256,
                "policy_id": f"unit:first={choice}",
                "max_player_turns": 1,
                "max_decisions": 8,
                "opening_idle_frames": 0,
            }
        )
        log.emit({"event": "decision_started"})
        log.emit(
            {
                "event": "choice_recorded",
                "decision_index": 1,
                "selected_action": {
                    "kind": "select_move",
                    "move_slot": 1,
                }
                if index == 0
                else {"kind": "switch", "party_slot": 2},
            }
        )
        log.emit({"event": "decision_completed", "decision": episode["decisions"][0]})
        log.finish(
            {
                "first_choice_ref": choice,
                "episode_sha256": canonical_sha256(episode),
                "stop_reason": episode["stop_reason"],
            }
        )
        logs[choice] = directory
    admitted = inspect_trainer_practice_choices(
        capture,
        document,
        expected_choice_refs=_CHOICES,
        continuation_policy_id="unit",
        branch_event_logs=logs,
        plan_sha256=plan_sha,
        model_sha256="b" * 64,
        max_decisions=8,
    )
    assert admitted["execution_proof_complete"] is True
    altered = deepcopy(document)
    altered["branches"][1]["episode"]["decisions"][0]["frames_executed"] = 101
    altered["branches"][1]["episode"]["frames_executed"] = 101
    with pytest.raises(TrainerPracticeAdmissionError, match="execution log"):
        inspect_trainer_practice_choices(
            capture,
            altered,
            expected_choice_refs=_CHOICES,
            continuation_policy_id="unit",
            branch_event_logs=logs,
            plan_sha256=plan_sha,
            model_sha256="b" * 64,
            max_decisions=8,
        )
