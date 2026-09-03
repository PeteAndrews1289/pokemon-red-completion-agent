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
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/fit_repeatable_battle_expected_utilities.py")
FitError = SCRIPT["RepeatableBattleExpectedUtilityFitError"]


def _model() -> MaskedMLPMoveRanker:
    power = FEATURE_NAMES.index("move.accuracy_weighted_effective_power_fraction")
    input_weights = np.zeros((1, len(FEATURE_NAMES)), dtype=np.float64)
    input_weights[0, power] = 1.0
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
    root: str,
    character: str,
    *,
    partition: ScenarioPartition = ScenarioPartition.TRAIN,
    frames: tuple[int, ...] = (2_048, 2_059, 2_073),
) -> BattleExpectedUtilityExample:
    power = FEATURE_NAMES.index("move.accuracy_weighted_effective_power_fraction")
    rows = [[0.0] * len(FEATURE_NAMES) for _ in range(2)]
    rows[0][power] = 0.1
    rows[1][power] = 0.8
    return BattleExpectedUtilityExample(
        root_lineage_id=root,
        initial_state_sha256=character * 64,
        partition=partition,
        features=BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=tuple(tuple(row) for row in rows),
            legal_mask=(True, True),
            current_pp=(10.0, 10.0),
            slot_indices=(0, 1),
        ),
        expected_utilities=(0.25, 1.25),
        utility_standard_deviations=(0.1, 1.0),
        trial_counts=(len(frames), len(frames)),
        pre_attack_frame_targets=frames,
    )


def _write_dataset(
    path: Path,
    examples: tuple[BattleExpectedUtilityExample, ...],
) -> None:
    path.write_text(
        "".join(
            json.dumps(
                expected_utility_record(
                    example,
                    capture_id=f"capture-{index}",
                    manifest_sha256=f"{index:x}" * 64,
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
            for index, example in enumerate(examples, start=1)
        ),
        encoding="ascii",
    )


def _args(tmp_path: Path, dataset: Path) -> SimpleNamespace:
    base = tmp_path / "base.json"
    base.write_text(_model().to_json() + "\n", encoding="ascii")
    return SimpleNamespace(
        base_model=base,
        dataset=[dataset],
        out_model=tmp_path / "updated.json",
        out_report=tmp_path / "report.json",
        minimum_root_lineages=2,
        minimum_examples_per_lineage=2,
        epochs=100,
        learning_rate=0.1,
        prior_l2=0.0,
    )


def test_expected_utility_fit_balances_roots_and_records_rng_schedule(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "train.jsonl"
    _write_dataset(
        dataset,
        (
            _example("root-a", "1"),
            _example("root-b", "2"),
            _example("root-a", "3"),
            _example("root-b", "4"),
            _example("root-a", "5"),
        ),
    )
    args = _args(tmp_path, dataset)

    report = SCRIPT["_run"](args)

    assert report["coverage"]["input_examples"] == 5
    assert report["coverage"]["balanced_examples_per_lineage"] == 2
    assert report["coverage"]["balanced_training_examples"] == 4
    assert report["coverage"]["excluded_for_lineage_balance"] == 1
    assert report["coverage"]["rng_trials_per_candidate"] == 3
    assert report["coverage"]["pre_attack_frame_targets"] == [2_048, 2_059, 2_073]
    assert report["target"] == "mean_cartridge_utility_across_hidden_rng_trajectories"
    assert report["development_outcomes_opened"] == 0
    assert report["test_outcomes_opened"] == 0
    assert report["authority_promoted"] is False
    assert report["inputs"]["base_model_file_sha256"] == hashlib.sha256(
        args.base_model.read_bytes()
    ).hexdigest()
    assert args.out_model.stat().st_mode & 0o777 == 0o600
    assert json.loads(args.out_report.read_text("ascii")) == report


def test_expected_utility_fit_rejects_development_before_writing(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "mixed.jsonl"
    _write_dataset(
        dataset,
        (
            _example("root-a", "1"),
            _example("root-b", "2"),
            _example("root-a", "3"),
            _example("root-development", "4", partition=ScenarioPartition.DEVELOPMENT),
        ),
    )
    args = _args(tmp_path, dataset)

    with pytest.raises(FitError, match="rejects development"):
        SCRIPT["_run"](args)

    assert not args.out_model.exists()
    assert not args.out_report.exists()


def test_expected_utility_fit_rejects_mixed_rng_schedules(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "mixed-schedule.jsonl"
    _write_dataset(
        dataset,
        (
            _example("root-a", "1"),
            _example("root-b", "2"),
            _example("root-a", "3"),
            _example("root-b", "4", frames=(2_048, 2_061, 2_079)),
        ),
    )
    args = _args(tmp_path, dataset)

    with pytest.raises(FitError, match="different RNG schedules"):
        SCRIPT["_run"](args)


def test_expected_utility_fit_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    dataset = tmp_path / "duplicates.jsonl"
    record = expected_utility_record(
        _example("root-a", "1"),
        capture_id="capture-1",
        manifest_sha256="1" * 64,
    )
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"))
    dataset.write_text(payload[:-1] + ',"schema":"duplicate"}\n', encoding="ascii")
    args = _args(tmp_path, dataset)

    with pytest.raises(ValueError, match="not strict JSON lines"):
        SCRIPT["_run"](args)
