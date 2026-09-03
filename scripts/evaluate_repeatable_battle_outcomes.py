#!/usr/bin/env python3
"""Compare two battle models on an authentic repeatable development dataset."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_outcome_learning import (  # noqa: E402
    compare_battle_outcome_preferences,
    evaluate_battle_outcome_preferences,
)
from pokemon_red_completion.repeatable_battle_evaluation import (  # noqa: E402
    compare_model_with_repeatable_fixed_heuristic,
    evaluate_repeatable_fixed_heuristic,
    load_repeatable_battle_datasets,
    load_repeatable_battle_model,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--challenger-model", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, action="append", required=True)
    parser.add_argument("--out-report", type=Path, required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    base, base_file_sha256 = load_repeatable_battle_model(args.base_model)
    challenger, challenger_file_sha256 = load_repeatable_battle_model(
        args.challenger_model
    )
    examples, dataset_inputs = load_repeatable_battle_datasets(
        args.dataset,
        subject="evaluation",
    )
    if not examples or any(
        item.partition is not ScenarioPartition.DEVELOPMENT for item in examples
    ):
        raise ValueError("evaluation requires only development examples")
    heuristic, heuristic_choices = evaluate_repeatable_fixed_heuristic(examples)
    challenger_vs_heuristic = compare_model_with_repeatable_fixed_heuristic(
        challenger,
        examples,
        heuristic_choices,
    )
    semantic_clusters = {example.semantic_cluster_sha256 for example in examples}
    report = {
        "schema": "pokemon.core.battle.repeatable-authentic-evaluation.v2",
        "inputs": {
            "base_model_file_sha256": base_file_sha256,
            "challenger_model_file_sha256": challenger_file_sha256,
            "datasets": list(dataset_inputs),
        },
        "coverage": {
            "examples": len(examples),
            "unique_semantic_clusters": len(semantic_clusters),
            "semantic_duplicate_examples": len(examples) - len(semantic_clusters),
        },
        "base": evaluate_battle_outcome_preferences(base, examples).public_dict(),
        "challenger": evaluate_battle_outcome_preferences(
            challenger, examples
        ).public_dict(),
        "fixed_heuristic": heuristic,
        "paired": compare_battle_outcome_preferences(
            base, challenger, examples
        ).public_dict(),
        "challenger_vs_fixed_heuristic": challenger_vs_heuristic,
        "development_artifact": True,
        "sealed_evidence": False,
        "learner_updates": 0,
        "authority_promoted": False,
    }
    _write_exclusive(
        args.out_report,
        (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("ascii"),
    )
    return report


def _write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def main() -> int:
    try:
        result = _run(_parser().parse_args())
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"repeatable authentic evaluation failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
