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

SCRIPT = runpy.run_path("scripts/fit_repeatable_battle_outcomes.py")


def _model() -> MaskedMLPMoveRanker:
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
        output_weights=np.asarray((-1.0,), dtype=np.float64),
        output_bias=0.0,
        training_seed=7,
    )


def _example(
    partition: ScenarioPartition,
    *,
    player_hp: float,
    root: str,
    state_character: str,
) -> BattleOutcomeExample:
    effective_power = FEATURE_NAMES.index(
        "move.accuracy_weighted_effective_power_fraction"
    )
    player_hp_index = FEATURE_NAMES.index("state.player_hp_ratio")
    rows = [[0.0] * len(FEATURE_NAMES) for _ in range(2)]
    for row in rows:
        row[player_hp_index] = player_hp
    rows[0][effective_power] = 0.1
    rows[1][effective_power] = 0.8
    return BattleOutcomeExample(
        root_lineage_id=root,
        initial_state_sha256=state_character * 64,
        partition=partition,
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


def test_fit_binds_inputs_scores_heuristic_and_recovers_orphan_model(
    tmp_path: Path,
) -> None:
    base_path = tmp_path / "base.json"
    dataset_path = tmp_path / "dataset.jsonl"
    out_model = tmp_path / "adapted.json"
    out_report = tmp_path / "report.json"
    base_path.write_text(_model().to_json() + "\n", encoding="ascii")
    examples = (
        (
            "train-capture",
            _example(
                ScenarioPartition.TRAIN,
                player_hp=1.0,
                root="train-root",
                state_character="1",
            ),
        ),
        (
            "development-capture",
            _example(
                ScenarioPartition.DEVELOPMENT,
                player_hp=0.5,
                root="development-root",
                state_character="2",
            ),
        ),
    )
    dataset_path.write_text(
        "".join(
            json.dumps(
                repeatable_battle_outcome_record(
                    example,
                    capture_id=capture_id,
                    manifest_sha256=character * 64,
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
            for character, (capture_id, example) in zip("34", examples, strict=True)
        ),
        encoding="ascii",
    )
    args = SimpleNamespace(
        base_model=base_path,
        dataset=[dataset_path],
        out_model=out_model,
        out_report=out_report,
        epochs=100,
        learning_rate=0.1,
        prior_l2=0.0,
    )

    report = SCRIPT["_run"](args)

    assert report["schema"].endswith("fit.v2")
    assert report["fixed_heuristic_development"]["correct_preferences"] == 1
    assert report["inputs"]["base_model_file_sha256"] == hashlib.sha256(
        base_path.read_bytes()
    ).hexdigest()
    assert report["inputs"]["datasets"][0]["file_sha256"] == hashlib.sha256(
        dataset_path.read_bytes()
    ).hexdigest()
    assert out_model.exists()
    assert out_report.exists()

    out_report.unlink()
    recovered = SCRIPT["_run"](args)
    assert recovered == report
    assert json.loads(out_report.read_text("ascii")) == report
