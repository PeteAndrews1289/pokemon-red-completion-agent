#!/usr/bin/env python3
"""Select candidate-ranker weighting using training lineages only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pokemon_red_completion.training_candidate_dataset import (
    TrainingCandidateDataset,
    load_training_candidate_replay,
)
from pokemon_red_completion.training_candidate_model import (
    CandidateShapeBaseline,
    TrainingCandidateMLP,
    evaluate_training_candidate_model,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train", action="append", nargs=2, metavar=("PATH", "SHA256"), required=True
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--hidden-units", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--l2", type=float, default=0.0001)
    parser.add_argument("--kind-balance-power", action="append", type=float)
    parser.add_argument("--seed", type=int, default=20260808)
    args = parser.parse_args()
    datasets = tuple(
        load_training_candidate_replay(path, expected_sha256=digest)
        for path, digest in args.train
    )
    if len(datasets) < 2:
        parser.error("candidate selection requires at least two training lineages")
    if any(dataset.partition != "train" or not dataset.lineage_qualified for dataset in datasets):
        parser.error("candidate selection inputs must be qualified training lineages")
    if len({dataset.lineage_id for dataset in datasets}) != len(datasets):
        parser.error("candidate selection lineages must be distinct")
    if len({dataset.state_sha256 for dataset in datasets}) != len(datasets):
        parser.error("candidate selection roots must be distinct")
    if len({dataset.source_commit for dataset in datasets}) != 1:
        parser.error("candidate selection lineages must use one source commit")
    powers = tuple(args.kind_balance_power or (0.0, 0.5, 1.0))
    if len(set(powers)) != len(powers):
        parser.error("candidate selection powers must be unique")

    trials = []
    for power in powers:
        folds = []
        for heldout in datasets:
            fit_rows = tuple(
                example
                for dataset in datasets
                if dataset is not heldout
                for example in dataset.examples
            )
            heldout_rows = heldout.examples
            baseline = CandidateShapeBaseline.fit(fit_rows)
            model = TrainingCandidateMLP.fit(
                fit_rows,
                hidden_units=args.hidden_units,
                epochs=args.epochs,
                learning_rate=args.learning_rate,
                l2=args.l2,
                kind_balance_power=power,
                seed=args.seed,
            )
            metrics = evaluate_training_candidate_model(
                model,
                heldout_rows,
                baseline=baseline,
            )
            folds.append(
                {
                    "heldout_lineage": heldout.lineage_id,
                    "metrics": metrics.public_dict(),
                    "model_margin_over_shape_baseline": (
                        metrics.accuracy - metrics.shape_baseline_accuracy
                    ),
                }
            )
        trials.append(
            {
                "kind_balance_power": power,
                "folds": folds,
                "mean_accuracy": sum(fold["metrics"]["accuracy"] for fold in folds)  # type: ignore[index]
                / len(folds),
                "mean_shape_baseline_accuracy": sum(
                    fold["metrics"]["shape_baseline_accuracy"] for fold in folds  # type: ignore[index]
                )
                / len(folds),
                "mean_model_margin_over_shape_baseline": sum(
                    fold["model_margin_over_shape_baseline"] for fold in folds  # type: ignore[misc]
                )
                / len(folds),
                "mean_cross_entropy": sum(
                    fold["metrics"]["cross_entropy"] for fold in folds  # type: ignore[index]
                )
                / len(folds),
            }
        )
    selected = max(
        trials,
        key=lambda trial: (
            trial["mean_model_margin_over_shape_baseline"],
            trial["mean_accuracy"],
            -trial["mean_cross_entropy"],
            -trial["kind_balance_power"],
        ),
    )
    payload = {
        "schema": "pokemon-training-candidate-selection-v1",
        "training_lineages": [_identity(dataset) for dataset in datasets],
        "selection_method": "bidirectional_whole_lineage_train_to_train_cross_validation",
        "validation_opened": False,
        "hyperparameters": {
            "hidden_units": args.hidden_units,
            "epochs": args.epochs,
            "learning_rate": args.learning_rate,
            "l2": args.l2,
            "seed": args.seed,
        },
        "trials": trials,
        "selected_kind_balance_power": selected["kind_balance_power"],
        "promotion_eligible": False,
    }
    _atomic_json(args.out, payload)
    print(
        json.dumps(
            {
                "selected_kind_balance_power": payload[
                    "selected_kind_balance_power"
                ],
                "validation_opened": False,
            }
        )
    )
    return 0


def _identity(dataset: TrainingCandidateDataset) -> dict[str, object]:
    return {
        "lineage_id": dataset.lineage_id,
        "artifact_sha256": dataset.artifact_sha256,
        "state_sha256": dataset.state_sha256,
        "source_commit": dataset.source_commit,
        "source_dirty": dataset.source_dirty,
    }


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
