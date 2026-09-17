from __future__ import annotations

from copy import deepcopy

import pytest

from pokemon_red_completion.battle_scenario_capture import (
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.red_trainer_practice_admission import (
    TrainerPracticeAdmissionError,
    inspect_trainer_practice_choices,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _capture(tmp_path):
    state = b"synthetic trainer state"
    path = tmp_path / "train.state"
    manifest = tmp_path / "train.state.json"
    path.write_bytes(state)
    manifest.write_bytes(build_battle_scenario_capture_payload(
        capture_id="train-unit", root_lineage_id="one-root", partition=ScenarioPartition.TRAIN,
        state_bytes=state, initial_observation_sha256="b" * 64, source_commit="c" * 40,
        expected_map=120, expected_battle_state=2,
    ))
    return open_battle_scenario_capture(path, manifest)


def _document(capture):
    resource = {"party_hp": [40, 35], "party_max_hp": [50, 50]}

    def branch(choice, kind, slot):
        decision = {
            "kind": kind,
            "move_slot": slot if kind == "attack" else None,
            "party_slot": slot if kind == "voluntary_switch" else None,
            "observation_sha256": "b" * 64,
            "state_before": resource,
            "state_after": resource,
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
                "teacher_queries": 0,
                "memory_write_actions": 0,
                "authority_promotions": 0,
                "frames_executed": 100,
                "metrics": {
                    "opponent_faints": 0, "party_faints": 0, "party_hp_lost": 5,
                    "party_pp_spent": 1, "teacher_interventions": 0,
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
    result = inspect_trainer_practice_choices(capture, _document(capture))
    assert result["executed_choice_count"] == 2
    assert result["new_independent_upstream_roots"] == 0
    assert result["fit_targets"] == 0
    assert result["measured_choices"][1]["first_choice_ref"].endswith("switch:2")


@pytest.mark.parametrize("mutation,match", [
    (lambda d: d.update(root_lineage_id="fabricated-root"), "capture binding"),
    (lambda d: d["branches"][1].update(first_choice_ref=d["branches"][0]["first_choice_ref"]),
     "repeated"),
    (lambda d: d["branches"][0]["episode"]["decisions"][0].update(move_slot=2),
     "first executed"),
    (lambda d: d["branches"][0]["episode"]["decisions"][0]["state_after"].update(
        party_hp=[65535, 35]), "impossible HP"),
    (lambda d: d["branches"][0]["episode"].update(player_turn_count=0), "equal-turn"),
    (lambda d: d["branches"][0]["episode"].update(stop_reason="failed"),
     "unqualified terminal"),
])
def test_rejects_unsafe_training_contrast(tmp_path, mutation, match):
    capture = _capture(tmp_path)
    document = deepcopy(_document(capture))
    mutation(document)
    with pytest.raises(TrainerPracticeAdmissionError, match=match):
        inspect_trainer_practice_choices(capture, document)
