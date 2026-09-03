#!/usr/bin/env python3
"""Evaluate committed model choices on multi-RNG development outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_expected_utility_evaluation import (  # noqa: E402
    BattleExpectedUtilityDatasetRow,
    compare_expected_utility_choices,
    evaluate_expected_utility_fixed_heuristic,
    evaluate_expected_utility_model,
    load_expected_utility_datasets,
)
from pokemon_red_completion.provenance import canonical_sha256  # noqa: E402
from pokemon_red_completion.repeatable_battle_evaluation import (  # noqa: E402
    load_repeatable_battle_model,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


class RepeatableBattleExpectedUtilityEvaluationError(RuntimeError):
    """Raised when prospective choices do not bind to development outcomes."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--challenger-model", type=Path, required=True)
    parser.add_argument("--prediction-commitment", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, action="append", required=True)
    parser.add_argument("--out-report", type=Path, required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    _require_output(args.out_report)
    base, base_file_sha256 = load_repeatable_battle_model(args.base_model)
    challenger, challenger_file_sha256 = load_repeatable_battle_model(
        args.challenger_model
    )
    rows, dataset_inputs = load_expected_utility_datasets(
        args.dataset,
        subject="expected-utility evaluation",
    )
    examples = tuple(row.example for row in rows)
    if any(
        example.partition is not ScenarioPartition.DEVELOPMENT
        for example in examples
    ):
        raise RepeatableBattleExpectedUtilityEvaluationError(
            "expected-utility evaluation requires development examples only"
        )
    schedules = {example.pre_attack_frame_targets for example in examples}
    if len(schedules) != 1:
        raise RepeatableBattleExpectedUtilityEvaluationError(
            "development examples use different RNG schedules"
        )

    base_evaluation, base_choices = evaluate_expected_utility_model(base, examples)
    challenger_evaluation, challenger_choices = evaluate_expected_utility_model(
        challenger,
        examples,
    )
    fixed_evaluation, fixed_choices = evaluate_expected_utility_fixed_heuristic(
        examples
    )
    commitment_payload = args.prediction_commitment.read_bytes()
    commitment = _load_commitment(commitment_payload)
    omitted_commitments = _verify_commitment(
        commitment,
        rows=rows,
        base_file_sha256=base_file_sha256,
        challenger_file_sha256=challenger_file_sha256,
        base_choices=base_choices,
        challenger_choices=challenger_choices,
        fixed_choices=fixed_choices,
    )
    semantic_clusters = {
        example.semantic_cluster_sha256 for example in examples
    }
    report = {
        "schema": "pokemon.core.battle.expected-utility-development-evaluation.v1",
        "inputs": {
            "base_model_file_sha256": base_file_sha256,
            "challenger_model_file_sha256": challenger_file_sha256,
            "prediction_commitment_file_sha256": hashlib.sha256(
                commitment_payload
            ).hexdigest(),
            "prediction_commitments_sha256": commitment["commitments_sha256"],
            "datasets": list(dataset_inputs),
        },
        "coverage": {
            "examples": len(examples),
            "committed_captures": len(examples) + omitted_commitments,
            "committed_captures_without_complete_schedule": omitted_commitments,
            "root_lineages": len(
                {example.root_lineage_id for example in examples}
            ),
            "unique_semantic_clusters": len(semantic_clusters),
            "semantic_duplicate_examples": len(examples) - len(semantic_clusters),
            "rng_trials_per_candidate": len(next(iter(schedules))),
            "pre_attack_frame_targets": list(next(iter(schedules))),
        },
        "base": base_evaluation,
        "challenger": challenger_evaluation,
        "fixed_heuristic": fixed_evaluation,
        "challenger_vs_base": compare_expected_utility_choices(
            examples,
            challenger_choices,
            base_choices,
        ),
        "challenger_vs_fixed_heuristic": compare_expected_utility_choices(
            examples,
            challenger_choices,
            fixed_choices,
        ),
        "predictions_committed_before_outcomes": True,
        "learner_updates": 0,
        "teacher_queries": 0,
        "authority_promoted": False,
        "development_artifact": True,
        "sealed_evidence": False,
    }
    _write_exclusive(
        args.out_report,
        (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("ascii"),
    )
    return report


def _load_commitment(payload: bytes) -> dict[str, object]:
    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise RepeatableBattleExpectedUtilityEvaluationError(
            "prediction commitment is not strict JSON"
        ) from None
    if not isinstance(value, dict):
        raise RepeatableBattleExpectedUtilityEvaluationError(
            "prediction commitment is invalid"
        )
    return value


def _verify_commitment(
    value: dict[str, object],
    *,
    rows: tuple[BattleExpectedUtilityDatasetRow, ...],
    base_file_sha256: str,
    challenger_file_sha256: str,
    base_choices: tuple[int, ...],
    challenger_choices: tuple[int, ...],
    fixed_choices: tuple[int, ...],
) -> int:
    if (
        value.get("schema")
        != "pokemon.core.battle.repeatable-development-predictions.v1"
        or value.get("base_model_file_sha256") != base_file_sha256
        or value.get("updated_model_file_sha256") != challenger_file_sha256
        or value.get("development_outcomes_opened") != 0
        or value.get("controller_actions") != 0
        or value.get("teacher_queries") != 0
        or value.get("authority_promoted") is not False
        or value.get("sealed_evidence") is not False
        or value.get("private_path_fields") != 0
    ):
        raise RepeatableBattleExpectedUtilityEvaluationError(
            "prediction commitment contract or model binding differs"
        )
    commitments = value.get("commitments")
    if (
        not isinstance(commitments, list)
        or len(commitments) < len(rows)
        or value.get("capture_count") != len(commitments)
        or value.get("commitments_sha256") != canonical_sha256(commitments)
    ):
        raise RepeatableBattleExpectedUtilityEvaluationError(
            "prediction commitment collection binding differs"
        )
    expected_fields = {
        "ordinal",
        "capture_id",
        "manifest_sha256",
        "state_sha256",
        "root_lineage_id",
        "initial_observation_sha256",
        "base_candidate_index",
        "updated_candidate_index",
        "fixed_heuristic_candidate_index",
    }
    by_capture: dict[str, Mapping[str, object]] = {}
    committed_states: set[str] = set()
    for ordinal, raw in enumerate(commitments, start=1):
        capture_id = raw.get("capture_id") if isinstance(raw, Mapping) else None
        state_id = raw.get("state_sha256") if isinstance(raw, Mapping) else None
        indices = (
            raw.get("base_candidate_index") if isinstance(raw, Mapping) else None,
            raw.get("updated_candidate_index") if isinstance(raw, Mapping) else None,
            raw.get("fixed_heuristic_candidate_index")
            if isinstance(raw, Mapping)
            else None,
        )
        if (
            not isinstance(raw, Mapping)
            or set(raw) != expected_fields
            or raw.get("ordinal") != ordinal
            or not isinstance(capture_id, str)
            or capture_id in by_capture
            or not isinstance(state_id, str)
            or state_id in committed_states
            or any(type(index) is not int or index < 0 for index in indices)  # noqa: E721
        ):
            raise RepeatableBattleExpectedUtilityEvaluationError(
                "one committed development prediction is invalid or duplicated"
            )
        by_capture[capture_id] = raw
        committed_states.add(state_id)

    for row, base, challenger, fixed in zip(
        rows,
        base_choices,
        challenger_choices,
        fixed_choices,
        strict=True,
    ):
        raw = by_capture.get(row.capture_id)
        if raw is None or (
            raw.get("manifest_sha256") != row.manifest_sha256
            or raw.get("state_sha256") != row.example.initial_state_sha256
            or raw.get("root_lineage_id") != row.example.root_lineage_id
            or raw.get("base_candidate_index") != base
            or raw.get("updated_candidate_index") != challenger
            or raw.get("fixed_heuristic_candidate_index") != fixed
        ):
            raise RepeatableBattleExpectedUtilityEvaluationError(
                "one committed development prediction differs from its outcome"
            )
    return len(commitments) - len(rows)


def _require_output(path: Path) -> None:
    if path.exists() or not path.parent.is_dir():
        raise RepeatableBattleExpectedUtilityEvaluationError(
            "evaluation output is unavailable or already exists"
        )
    if path.resolve().is_relative_to(PROJECT_ROOT.resolve()):
        raise RepeatableBattleExpectedUtilityEvaluationError(
            "evaluation output must remain outside the repository"
        )


def _write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = item
    return result


def main() -> int:
    try:
        result = _run(_parser().parse_args())
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"expected-utility evaluation failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
