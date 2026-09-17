from __future__ import annotations

from copy import deepcopy

import pytest

from pokemon_red_completion.battle_scenario_capture import OBSERVATION_SCHEMA_V2
from pokemon_red_completion.red_trainer_practice_returns import RETURN_SCHEMA_ID
from pokemon_red_completion.red_trainer_practice_targets import (
    TrainerPracticeTargetError,
    aggregate_trainer_timing_targets,
    extract_trainer_practice_targets,
)


def _contrast():
    refs = (
        "pokemon.core:battle:move:1",
        "pokemon.core:battle:move:2",
        "pokemon.core:battle:switch:2",
        "pokemon.core:battle:switch:3",
    )
    returns = (1.0, 0.8, 0.9, 0.5)
    observation = {"features": {"battle": {"kind": "trainer"}}}
    admission = {
        "schema": "pokemon.red.trainer-practice-admission.v1",
        "partition": "train",
        "execution_proof_complete": True,
        "return_proof_complete": True,
        "observation_schema": OBSERVATION_SCHEMA_V2,
        "capture_id": "unit",
        "manifest_sha256": "a" * 64,
        "root_lineage_id": "one-root",
        "source_commit": "c" * 40,
        "opening_idle_frames": 0,
        "measured_choices": [
            {
                "first_choice_ref": ref,
                "whole_party_return": {
                    "schema": RETURN_SCHEMA_ID,
                    "value": value,
                },
            }
            for ref, value in zip(refs, returns, strict=True)
        ],
    }
    document = {
        "capture_id": "unit",
        "manifest_sha256": "a" * 64,
        "branches": [
            {
                "first_choice_ref": ref,
                "episode": {
                    "decisions": [
                        {
                            "kind": "attack" if ":move:" in ref else "voluntary_switch",
                            "observation": observation,
                        }
                    ]
                },
            }
            for ref in refs
        ],
    }
    return admission, document


def test_three_head_targets_share_executed_whole_party_returns():
    admission, document = _contrast()
    result = extract_trainer_practice_targets(admission, document)
    assert result["scenario_count"] == 1
    assert result["root_lineage_id"] == "one-root"
    assert result["decision_context"] == "main"
    assert result["attack_depleted"] is False
    assert result["heads"]["move"]["best_indices"] == [0]
    assert result["heads"]["switch"]["best_indices"] == [0]
    assert result["heads"]["control"]["best_indices"] == [0]


def test_depleted_main_context_trains_switch_target_without_fake_attack_target():
    admission, document = _contrast()
    admission["measured_choices"] = admission["measured_choices"][2:]
    document["branches"] = document["branches"][2:]
    for branch in document["branches"]:
        branch["episode"]["decisions"][0]["model_input"] = {
            "supported_candidate_mask": [False, False]
        }
    result = extract_trainer_practice_targets(admission, document)
    assert result["attack_depleted"] is True
    assert result["decision_context"] == "main"
    assert set(result["heads"]) == {"switch"}
    assert result["heads"]["switch"]["best_indices"] == [0]


def test_target_extraction_refuses_unproven_or_different_start():
    admission, document = _contrast()
    admission["execution_proof_complete"] = False
    with pytest.raises(TrainerPracticeTargetError, match="execution-proven"):
        extract_trainer_practice_targets(admission, document)
    admission["execution_proof_complete"] = True
    document["branches"][1]["episode"]["decisions"][0]["observation"] = {"different": True}
    with pytest.raises(TrainerPracticeTargetError, match="different observations"):
        extract_trainer_practice_targets(admission, document)


def test_five_declared_timings_average_one_scenario_not_five_roots():
    admission, document = _contrast()
    base = extract_trainer_practice_targets(admission, document)
    offsets = (0, 2, 4, 6, 8)
    targets = []
    for offset in offsets:
        item = deepcopy(base)
        item["timing_offset_frames"] = offset
        item["heads"]["switch"]["returns"][0] += offset / 100
        targets.append(item)
    result = aggregate_trainer_timing_targets(tuple(targets), expected_offsets=offsets)
    assert result["scenario_count"] == 1
    assert result["timing_count"] == 5
    assert result["root_lineage_id"] == "one-root"
    assert result["heads"]["switch"]["returns"][0] == 0.94
    targets[1]["decision_context"] = "prompt"
    with pytest.raises(TrainerPracticeTargetError, match="comparable scenario"):
        aggregate_trainer_timing_targets(tuple(targets), expected_offsets=offsets)
    targets[1]["decision_context"] = "main"
    with pytest.raises(TrainerPracticeTargetError, match="timing schedule"):
        aggregate_trainer_timing_targets(tuple(targets), expected_offsets=(0, 2, 4, 6, 10))
