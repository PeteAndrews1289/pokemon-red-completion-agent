#!/usr/bin/env python3
"""Select class balancing by whole-lineage cross-validation without opening validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pokemon_red_completion.training_control_dataset import load_training_control_replay
from pokemon_red_completion.training_control_model import (
    TrainingControlMLP,
    evaluate_training_control_model,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train",
        action="append",
        nargs=2,
        metavar=("PATH", "SHA256"),
        required=True,
        help="repeat for each authenticated training lineage",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260808)
    parser.add_argument("--hidden-units", type=int, default=24)
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--l2", type=float, default=1e-4)
    parser.add_argument(
        "--class-balance-power",
        action="append",
        type=float,
        dest="powers",
        help="repeat to override the preregistered 0/.25/.5/.75/1 grid",
    )
    args = parser.parse_args()
    if len(args.train) < 2:
        parser.error("selection needs at least two whole training lineages")
    datasets = tuple(
        load_training_control_replay(path, expected_sha256=digest)
        for path, digest in args.train
    )
    if any(dataset.partition != "train" or not dataset.lineage_qualified for dataset in datasets):
        parser.error("selection accepts only qualified training lineages")
    identities = tuple(
        (dataset.lineage_id, dataset.artifact_sha256, dataset.state_sha256)
        for dataset in datasets
    )
    duplicate_identity = any(
        len({identity[index] for identity in identities}) != len(identities)
        for index in (0, 1, 2)
    )
    if duplicate_identity:
        parser.error("selection lineages, artifacts, and roots must be distinct")

    powers = tuple(args.powers or (0.0, 0.25, 0.5, 0.75, 1.0))
    trials: list[dict[str, object]] = []
    for power in powers:
        folds: list[dict[str, object]] = []
        for held_out in datasets:
            training_rows = tuple(
                example
                for dataset in datasets
                if dataset is not held_out
                for example in dataset.examples
            )
            model = TrainingControlMLP.fit(
                training_rows,
                seed=args.seed,
                hidden_units=args.hidden_units,
                epochs=args.epochs,
                learning_rate=args.learning_rate,
                l2=args.l2,
                class_balance_power=power,
            )
            metrics = evaluate_training_control_model(model, held_out.examples)
            folds.append({"held_out_lineage": held_out.lineage_id, **metrics.public_dict()})
        critical = sum(
            int(fold["operational_errors"][name])
            for fold in folds
            for name in ("missed_required_heal", "premature_stop", "missed_stop")
        )
        unnecessary = sum(
            int(fold["operational_errors"]["unnecessary_heal"]) for fold in folds
        )
        genuine_examples = sum(int(fold["genuine_examples"]) for fold in folds)
        genuine_correct = sum(
            float(fold["genuine_accuracy"]) * int(fold["genuine_examples"])
            for fold in folds
        )
        genuine_accuracy = genuine_correct / genuine_examples
        cross_entropy = sum(float(fold["cross_entropy"]) for fold in folds) / len(folds)
        trials.append(
            {
                "class_balance_power": power,
                "critical_errors": critical,
                "unnecessary_heals": unnecessary,
                "genuine_accuracy": genuine_accuracy,
                "mean_cross_entropy": cross_entropy,
                "folds": folds,
            }
        )
    selected = min(
        trials,
        key=lambda trial: (
            int(trial["critical_errors"]),
            int(trial["unnecessary_heals"]),
            -float(trial["genuine_accuracy"]),
            float(trial["mean_cross_entropy"]),
            float(trial["class_balance_power"]),
        ),
    )
    payload = {
        "schema": "pokemon-training-control-balance-selection-v1",
        "validation_opened": False,
        "training_lineages": [
            {
                "lineage_id": lineage,
                "artifact_sha256": artifact,
                "state_sha256": state,
            }
            for lineage, artifact, state in identities
        ],
        "fit": {
            "seed": args.seed,
            "hidden_units": args.hidden_units,
            "epochs": args.epochs,
            "learning_rate": args.learning_rate,
            "l2": args.l2,
        },
        "selection_order": [
            "critical_errors",
            "unnecessary_heals",
            "negative_genuine_accuracy",
            "mean_cross_entropy",
            "class_balance_power",
        ],
        "trials": trials,
        "selected_class_balance_power": selected["class_balance_power"],
        "promotion_eligible": False,
    }
    _atomic_json(args.out, payload)
    print(json.dumps({"selected_class_balance_power": selected["class_balance_power"]}))
    return 0


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
