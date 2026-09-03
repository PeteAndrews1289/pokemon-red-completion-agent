from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_learning import (
    BattleOutcomeExample,
    BattleTurnOutcome,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.repeatable_battle_dataset import (
    repeatable_battle_outcome_record,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/evaluate_repeatable_battle_outcomes.py")


def _model(*, output_weight: float) -> MaskedMLPMoveRanker:
    effective_power = FEATURE_NAMES.index(
        "move.accuracy_weighted_effective_power_fraction"
    )
    input_weights = np.zeros((1, len(FEATURE_NAMES)), dtype=np.float64)
    input_weights[0, effective_power] = 1.0
    return MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=input_weights,
        hidden_bias=np.zeros(1, dtype=np.float64),
        output_weights=np.asarray((output_weight,), dtype=np.float64),
        output_bias=0.0,
        training_seed=7,
    )


def _example() -> BattleOutcomeExample:
    effective_power = FEATURE_NAMES.index(
        "move.accuracy_weighted_effective_power_fraction"
    )
    rows = [[0.0] * len(FEATURE_NAMES) for _ in range(2)]
    rows[0][effective_power] = 0.1
    rows[1][effective_power] = 0.8
    return BattleOutcomeExample(
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
        outcomes=(
            BattleTurnOutcome(True, 0.1, 0.0, False, False, False, 1, 3, 1),
            BattleTurnOutcome(True, 1.0, 0.0, True, False, False, 1, 3, 1),
        ),
    )


def test_evaluation_binds_inputs_and_scores_the_strong_fixed_baseline(
    tmp_path: Path,
) -> None:
    base_path = tmp_path / "base.json"
    challenger_path = tmp_path / "challenger.json"
    dataset_path = tmp_path / "development.jsonl"
    report_path = tmp_path / "report.json"
    base_path.write_text(_model(output_weight=-1.0).to_json() + "\n", encoding="ascii")
    challenger_path.write_text(
        _model(output_weight=1.0).to_json() + "\n",
        encoding="ascii",
    )
    dataset_path.write_text(
        json.dumps(
            repeatable_battle_outcome_record(
                _example(),
                capture_id="development-capture",
                manifest_sha256="2" * 64,
            ),
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="ascii",
    )

    report = SCRIPT["_run"](
        SimpleNamespace(
            base_model=base_path,
            challenger_model=challenger_path,
            dataset=[dataset_path],
            out_report=report_path,
        )
    )

    assert report["schema"].endswith("evaluation.v2")
    assert report["base"]["correct_preferences"] == 0
    assert report["challenger"]["correct_preferences"] == 1
    assert report["fixed_heuristic"]["correct_preferences"] == 1
    assert report["challenger_vs_fixed_heuristic"] == {
        "schema": "pokemon.core.battle.model-vs-fixed-heuristic.v1",
        "heuristic_id": "pokemon.core.battle.fixed-power-heuristic.v1",
        "example_count": 1,
        "challenger_wins": 0,
        "fixed_heuristic_wins": 0,
        "equivalent_choices": 1,
        "authority_promoted": False,
    }
    assert report["coverage"] == {
        "examples": 1,
        "unique_semantic_clusters": 1,
        "semantic_duplicate_examples": 0,
    }
    assert report["inputs"]["datasets"] == [
        {
            "ordinal": 1,
            "file_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            "record_count": 1,
        }
    ]
    assert json.loads(report_path.read_text("ascii")) == report


def test_evaluation_rejects_duplicate_capture_identity(tmp_path: Path) -> None:
    model_path = tmp_path / "model.json"
    dataset_path = tmp_path / "development.jsonl"
    report_path = tmp_path / "report.json"
    model_path.write_text(_model(output_weight=1.0).to_json(), encoding="ascii")
    record = repeatable_battle_outcome_record(
        _example(),
        capture_id="development-capture",
        manifest_sha256="2" * 64,
    )
    line = json.dumps(record, sort_keys=True, separators=(",", ":"))
    dataset_path.write_text(f"{line}\n{line}\n", encoding="ascii")

    try:
        SCRIPT["_run"](
            SimpleNamespace(
                base_model=model_path,
                challenger_model=model_path,
                dataset=[dataset_path],
                out_report=report_path,
            )
        )
    except ValueError as error:
        assert "capture identities" in str(error)
    else:  # pragma: no cover - assertion path
        raise AssertionError("duplicate capture identity was accepted")
