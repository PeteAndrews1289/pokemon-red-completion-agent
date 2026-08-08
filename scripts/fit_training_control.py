#!/usr/bin/env python3
"""Fit and serialize one authenticated training-control candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pokemon_red_completion.training_control_dataset import (
    audit_training_control_partitions,
    load_training_control_replay,
)
from pokemon_red_completion.training_control_model import fit_training_control_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train",
        action="append",
        nargs=2,
        metavar=("PATH", "SHA256"),
        required=True,
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
    parser.add_argument("--seed", type=int, default=20260808)
    parser.add_argument("--hidden-units", type=int, default=24)
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--l2", type=float, default=1e-4)
    parser.add_argument("--class-balance-power", type=float, required=True)
    args = parser.parse_args()
    if args.out_model.resolve() == args.out_summary.resolve():
        parser.error("model and summary outputs must differ")
    training = tuple(
        load_training_control_replay(path, expected_sha256=digest)
        for path, digest in args.train
    )
    validation = tuple(
        load_training_control_replay(path, expected_sha256=digest)
        for path, digest in args.validation
    )
    audit = audit_training_control_partitions((*training, *validation))
    candidate = fit_training_control_candidate(
        training,
        validation,
        seed=args.seed,
        hidden_units=args.hidden_units,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        l2=args.l2,
        class_balance_power=args.class_balance_power,
    )
    model_payload = json.dumps(candidate.model.to_dict(), indent=2, sort_keys=True) + "\n"
    model_sha256 = hashlib.sha256(model_payload.encode()).hexdigest()
    _atomic_text(args.out_model, model_payload)
    summary = candidate.public_summary()
    summary.update(
        {
            "fit": {
                "seed": args.seed,
                "hidden_units": args.hidden_units,
                "epochs": args.epochs,
                "learning_rate": args.learning_rate,
                "l2": args.l2,
                "class_balance_power": args.class_balance_power,
            },
            "partition_audit": audit.public_dict(),
            "private_model_file_sha256": model_sha256,
        }
    )
    _atomic_text(args.out_summary, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"model_sha256": candidate.model_sha256, "file_sha256": model_sha256}))
    return 0


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text)
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
