#!/usr/bin/env python3
"""Fit a lineage-balanced battle ranker from multi-RNG expected utilities."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_expected_utility import (  # noqa: E402
    BattleExpectedUtilityExample,
    adapt_mlp_last_layer_from_expected_utilities,
)
from pokemon_red_completion.battle_expected_utility_evaluation import (  # noqa: E402
    load_expected_utility_datasets,
)
from pokemon_red_completion.repeatable_battle_evaluation import (  # noqa: E402
    load_repeatable_battle_model,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


class RepeatableBattleExpectedUtilityFitError(RuntimeError):
    """Raised when an expected-utility fit would cross its data boundary."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, action="append", required=True)
    parser.add_argument("--out-model", type=Path, required=True)
    parser.add_argument("--out-report", type=Path, required=True)
    parser.add_argument("--minimum-root-lineages", type=int, default=4)
    parser.add_argument("--minimum-examples-per-lineage", type=int, default=4)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--prior-l2", type=float, default=0.1)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    if type(args.minimum_root_lineages) is not int or args.minimum_root_lineages < 2:  # noqa: E721
        raise RepeatableBattleExpectedUtilityFitError(
            "minimum root lineages must be at least two"
        )
    if (
        type(args.minimum_examples_per_lineage) is not int  # noqa: E721
        or args.minimum_examples_per_lineage < 1
    ):
        raise RepeatableBattleExpectedUtilityFitError(
            "minimum examples per lineage must be positive"
        )
    _require_output(args.out_model, subject="updated model")
    _require_output(args.out_report, subject="fit report")
    if args.out_model.resolve() == args.out_report.resolve():
        raise RepeatableBattleExpectedUtilityFitError(
            "model and report outputs must differ"
        )
    model, base_file_sha256 = load_repeatable_battle_model(args.base_model)
    rows, dataset_inputs = load_expected_utility_datasets(
        args.dataset,
        subject="expected-utility fit",
    )
    examples = tuple(row.example for row in rows)
    if any(example.partition is not ScenarioPartition.TRAIN for example in examples):
        raise RepeatableBattleExpectedUtilityFitError(
            "expected-utility fit rejects development and test records"
        )
    schedules = {example.pre_attack_frame_targets for example in examples}
    if len(schedules) != 1:
        raise RepeatableBattleExpectedUtilityFitError(
            "expected-utility examples use different RNG schedules"
        )
    balanced, root_counts, quota = _lineage_balanced(examples)
    if len(root_counts) < args.minimum_root_lineages:
        raise RepeatableBattleExpectedUtilityFitError(
            "expected-utility fit has too few root lineages"
        )
    if quota < args.minimum_examples_per_lineage:
        raise RepeatableBattleExpectedUtilityFitError(
            "expected-utility fit has too few examples per lineage"
        )
    update = adapt_mlp_last_layer_from_expected_utilities(
        model,
        balanced,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        prior_l2=args.prior_l2,
    )
    model_payload = update.model.to_json().encode("ascii") + b"\n"
    report = {
        "schema": "pokemon.core.battle.expected-utility-train-only-fit.v1",
        "inputs": {
            "base_model_file_sha256": base_file_sha256,
            "datasets": list(dataset_inputs),
        },
        "coverage": {
            "input_examples": len(examples),
            "input_root_lineages": len(root_counts),
            "input_examples_by_lineage": dict(sorted(root_counts.items())),
            "balanced_examples_per_lineage": quota,
            "balanced_training_examples": len(balanced),
            "excluded_for_lineage_balance": len(examples) - len(balanced),
            "informative_examples": sum(
                example.learner_update_eligible for example in balanced
            ),
            "semantic_clusters": len(
                {example.semantic_cluster_sha256 for example in balanced}
            ),
            "rng_trials_per_candidate": len(next(iter(schedules))),
            "pre_attack_frame_targets": list(next(iter(schedules))),
        },
        "update": update.report.public_dict(),
        "updated_model_file_sha256": hashlib.sha256(model_payload).hexdigest(),
        "target": "mean_cartridge_utility_across_hidden_rng_trajectories",
        "lineage_balancing": "equal_example_count_per_root",
        "development_outcomes_opened": 0,
        "test_outcomes_opened": 0,
        "teacher_queries": 0,
        "authority_promoted": False,
        "crystal_transfer_claim": False,
    }
    report_payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode(
        "ascii"
    )
    _write_new(args.out_model, model_payload)
    try:
        _write_new(args.out_report, report_payload)
    except Exception:
        args.out_model.unlink(missing_ok=True)
        raise
    return report


def _lineage_balanced(
    examples: tuple[BattleExpectedUtilityExample, ...],
) -> tuple[
    tuple[BattleExpectedUtilityExample, ...],
    Counter[str],
    int,
]:
    by_root: dict[str, list[BattleExpectedUtilityExample]] = defaultdict(list)
    for example in examples:
        by_root[example.root_lineage_id].append(example)
    counts = Counter({root: len(rows) for root, rows in by_root.items()})
    quota = min(counts.values())
    used: Counter[str] = Counter()
    balanced = []
    for example in examples:
        if used[example.root_lineage_id] < quota:
            balanced.append(example)
            used[example.root_lineage_id] += 1
    return tuple(balanced), counts, quota


def _require_output(path: Path, *, subject: str) -> None:
    if path.exists() or not path.parent.is_dir():
        raise RepeatableBattleExpectedUtilityFitError(
            f"{subject} is unavailable or already exists"
        )
    if path.resolve().is_relative_to(PROJECT_ROOT.resolve()):
        raise RepeatableBattleExpectedUtilityFitError(
            f"{subject} must remain outside the repository"
        )


def _write_new(path: Path, payload: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise FileExistsError(path)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.close(descriptor)
        temporary.unlink(missing_ok=True)


def main() -> int:
    try:
        result = _run(_parser().parse_args())
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"expected-utility fit failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
