from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pokemon_red_completion.battle_expected_utility import (
    BattleExpectedUtilityExample,
    expected_utility_record,
)
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_batch import battle_outcome_model_sha256
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/evaluate_repeatable_battle_expected_utilities.py")
EvaluationError = SCRIPT["RepeatableBattleExpectedUtilityEvaluationError"]


def _model(*, output_weight: float) -> MaskedMLPMoveRanker:
    power = FEATURE_NAMES.index("move.accuracy_weighted_effective_power_fraction")
    weights = np.zeros((1, len(FEATURE_NAMES)), dtype=np.float64)
    weights[0, power] = 1.0
    return MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=weights,
        hidden_bias=np.zeros(1, dtype=np.float64),
        output_weights=np.asarray((output_weight,), dtype=np.float64),
        output_bias=0.0,
        training_seed=7,
    )


def _example() -> BattleExpectedUtilityExample:
    power = FEATURE_NAMES.index("move.accuracy_weighted_effective_power_fraction")
    rows = [[0.0] * len(FEATURE_NAMES) for _ in range(2)]
    rows[0][power] = 0.1
    rows[1][power] = 0.8
    return BattleExpectedUtilityExample(
        root_lineage_id="development-root",
        initial_state_sha256="1" * 64,
        partition=ScenarioPartition.DEVELOPMENT,
        features=BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=tuple(tuple(row) for row in rows),
            legal_mask=(True, True),
            current_pp=(10.0, 10.0),
            slot_indices=(0, 1),
        ),
        expected_utilities=(0.2, 1.5),
        utility_standard_deviations=(0.1, 0.8),
        trial_counts=(3, 3),
        pre_attack_frame_targets=(2_048, 2_059, 2_073),
    )


def _write_inputs(tmp_path: Path) -> SimpleNamespace:
    base = _model(output_weight=-1.0)
    challenger = _model(output_weight=1.0)
    base_path = tmp_path / "base.json"
    challenger_path = tmp_path / "challenger.json"
    dataset_path = tmp_path / "development.jsonl"
    commitment_path = tmp_path / "commitment.json"
    base_path.write_text(base.to_json() + "\n", encoding="ascii")
    challenger_path.write_text(challenger.to_json() + "\n", encoding="ascii")
    record = expected_utility_record(
        _example(),
        capture_id="development-capture",
        manifest_sha256="2" * 64,
    )
    dataset_path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    commitments = [
        {
            "ordinal": 1,
            "capture_id": "development-capture",
            "manifest_sha256": "2" * 64,
            "state_sha256": "1" * 64,
            "root_lineage_id": "development-root",
            "initial_observation_sha256": "3" * 64,
            "base_candidate_index": 0,
            "updated_candidate_index": 1,
            "fixed_heuristic_candidate_index": 1,
        }
    ]
    commitment = {
        "schema": "pokemon.core.battle.repeatable-development-predictions.v1",
        "collector_source_commit": "4" * 40,
        "rom_sha256": "5" * 64,
        "base_model_file_sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
        "base_model_sha256": battle_outcome_model_sha256(base),
        "updated_model_file_sha256": hashlib.sha256(
            challenger_path.read_bytes()
        ).hexdigest(),
        "updated_model_sha256": battle_outcome_model_sha256(challenger),
        "capture_count": 1,
        "commitments_sha256": canonical_sha256(commitments),
        "commitments": commitments,
        "development_outcomes_opened": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "authority_promoted": False,
        "sealed_evidence": False,
        "private_path_fields": 0,
    }
    commitment_path.write_text(
        json.dumps(commitment, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    return SimpleNamespace(
        base_model=base_path,
        challenger_model=challenger_path,
        prediction_commitment=commitment_path,
        dataset=[dataset_path],
        out_report=tmp_path / "report.json",
    )


def test_evaluation_requires_commitment_and_scores_mean_utility(
    tmp_path: Path,
) -> None:
    args = _write_inputs(tmp_path)

    report = SCRIPT["_run"](args)

    assert report["base"]["correct_preferences"] == 0
    assert report["challenger"]["correct_preferences"] == 1
    assert report["fixed_heuristic"]["correct_preferences"] == 1
    assert report["challenger_vs_fixed_heuristic"]["equivalent_choices"] == 1
    assert report["coverage"]["rng_trials_per_candidate"] == 3
    assert report["predictions_committed_before_outcomes"] is True
    assert report["authority_promoted"] is False
    assert json.loads(args.out_report.read_text("ascii")) == report


def test_evaluation_rejects_prediction_drift_before_writing(
    tmp_path: Path,
) -> None:
    args = _write_inputs(tmp_path)
    commitment = json.loads(args.prediction_commitment.read_text("ascii"))
    commitment["commitments"][0]["updated_candidate_index"] = 0
    commitment["commitments_sha256"] = canonical_sha256(commitment["commitments"])
    args.prediction_commitment.write_text(
        json.dumps(commitment, sort_keys=True),
        encoding="ascii",
    )

    with pytest.raises(EvaluationError, match="prediction differs"):
        SCRIPT["_run"](args)

    assert not args.out_report.exists()


def test_evaluation_accepts_preoutcome_commitment_superset_after_quarantine(
    tmp_path: Path,
) -> None:
    args = _write_inputs(tmp_path)
    commitment = json.loads(args.prediction_commitment.read_text("ascii"))
    omitted = dict(commitment["commitments"][0])
    omitted.update(
        {
            "ordinal": 2,
            "capture_id": "quarantined-development-capture",
            "manifest_sha256": "6" * 64,
            "state_sha256": "7" * 64,
            "initial_observation_sha256": "8" * 64,
        }
    )
    commitment["commitments"].append(omitted)
    commitment["capture_count"] = 2
    commitment["commitments_sha256"] = canonical_sha256(commitment["commitments"])
    args.prediction_commitment.write_text(
        json.dumps(commitment, sort_keys=True),
        encoding="ascii",
    )

    report = SCRIPT["_run"](args)

    assert report["coverage"]["examples"] == 1
    assert report["coverage"]["committed_captures"] == 2
    assert report["coverage"]["committed_captures_without_complete_schedule"] == 1


def test_evaluation_rejects_train_aggregates(tmp_path: Path) -> None:
    args = _write_inputs(tmp_path)
    record = json.loads(args.dataset[0].read_text("ascii"))
    record["partition"] = "train"
    args.dataset[0].write_text(json.dumps(record) + "\n", encoding="ascii")

    with pytest.raises(EvaluationError, match="development examples only"):
        SCRIPT["_run"](args)
