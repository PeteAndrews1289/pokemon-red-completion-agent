#!/usr/bin/env python3
"""Fit and evaluate the strategic trainee/venue candidate scorer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pokemon_red_completion.training_candidate_dataset import (
    TrainingCandidateDataset,
    audit_training_candidate_partitions,
    load_training_candidate_replay,
)
from pokemon_red_completion.training_candidate_model import (
    CandidateShapeBaseline,
    TrainingCandidateMLP,
    canonical_training_candidate_model_sha256,
    evaluate_training_candidate_model,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train", action="append", nargs=2, metavar=("PATH", "SHA256"), required=True
    )
    parser.add_argument(
        "--validation",
        action="append",
        nargs=2,
        metavar=("PATH", "SHA256"),
        required=True,
    )
    parser.add_argument("--out-model", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    parser.add_argument("--hidden-units", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=400)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--l2", type=float, default=0.0001)
    parser.add_argument("--kind-balance-power", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=20260808)
    args = parser.parse_args()

    training = tuple(
        load_training_candidate_replay(path, expected_sha256=digest)
        for path, digest in args.train
    )
    validation = tuple(
        load_training_candidate_replay(path, expected_sha256=digest)
        for path, digest in args.validation
    )
    if any(dataset.partition != "train" for dataset in training):
        parser.error("candidate training input contains a non-training lineage")
    if any(dataset.partition != "validation" for dataset in validation):
        parser.error("candidate validation input contains a non-validation lineage")
    partition_audit = audit_training_candidate_partitions((*training, *validation))
    if not partition_audit.promotion_eligible:
        parser.error(f"candidate partitions are ineligible: {partition_audit.reasons!r}")
    train_rows = tuple(example for dataset in training for example in dataset.examples)
    validation_rows = tuple(example for dataset in validation for example in dataset.examples)
    baseline = CandidateShapeBaseline.fit(train_rows)
    model = TrainingCandidateMLP.fit(
        train_rows,
        hidden_units=args.hidden_units,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        l2=args.l2,
        kind_balance_power=args.kind_balance_power,
        seed=args.seed,
    )
    model_payload = model.to_dict()
    _atomic_json(args.out_model, model_payload)
    model_file_sha256 = hashlib.sha256(args.out_model.read_bytes()).hexdigest()
    training_metrics = evaluate_training_candidate_model(
        model, train_rows, baseline=baseline
    ).public_dict()
    validation_metrics = evaluate_training_candidate_model(
        model, validation_rows, baseline=baseline
    ).public_dict()
    summary = {
        "schema": "pokemon-training-candidate-model-summary-v1",
        "model_id": model.model_id,
        "feature_schema_id": model.feature_schema_id,
        "model_sha256": canonical_training_candidate_model_sha256(model),
        "private_model_file_sha256": model_file_sha256,
        "training_lineages": [dataset.lineage_id for dataset in training],
        "validation_lineages": [dataset.lineage_id for dataset in validation],
        "lineage_roots": [_identity(dataset) for dataset in (*training, *validation)],
        "partition_audit": partition_audit.public_dict(),
        "hyperparameters": {
            "hidden_units": args.hidden_units,
            "epochs": args.epochs,
            "learning_rate": args.learning_rate,
            "l2": args.l2,
            "kind_balance_power": args.kind_balance_power,
            "seed": args.seed,
        },
        "shape_baseline": baseline.public_dict(),
        "training": training_metrics,
        "validation": validation_metrics,
        "validation_opened": True,
        "promotion_eligible": False,
    }
    _atomic_json(args.out_summary, summary)
    print(
        json.dumps(
            {
                "model_sha256": summary["model_sha256"],
                "validation_genuine_accuracy": validation_metrics[
                    "genuine_accuracy"
                ],
                "validation_genuine_shape_baseline_accuracy": validation_metrics[
                    "genuine_shape_baseline_accuracy"
                ],
            }
        )
    )
    return 0


def _identity(dataset: TrainingCandidateDataset) -> dict[str, object]:
    return {
        "lineage_id": dataset.lineage_id,
        "partition": dataset.partition,
        "state_sha256": dataset.state_sha256,
        "artifact_sha256": dataset.artifact_sha256,
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
