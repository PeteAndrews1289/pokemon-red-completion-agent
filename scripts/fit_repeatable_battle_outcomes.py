#!/usr/bin/env python3
"""Adapt a battle model on authentic repeatable Red outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker  # noqa: E402
from pokemon_red_completion.battle_outcome_learning import (  # noqa: E402
    compare_battle_outcome_preferences,
    run_battle_outcome_learning_cycle,
)
from pokemon_red_completion.repeatable_battle_dataset import (  # noqa: E402
    parse_repeatable_battle_outcome_record,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, action="append", required=True)
    parser.add_argument("--out-model", type=Path, required=True)
    parser.add_argument("--out-report", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--prior-l2", type=float, default=0.1)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    model = MaskedMLPMoveRanker.from_dict(json.loads(args.base_model.read_text("ascii")))
    records = [
        parse_repeatable_battle_outcome_record(json.loads(line))
        for dataset in args.dataset
        for line in dataset.read_text("ascii").splitlines()
        if line
    ]
    training = tuple(
        item for item in records if item.partition is ScenarioPartition.TRAIN
    )
    development = tuple(
        item for item in records if item.partition is ScenarioPartition.DEVELOPMENT
    )
    cycle = run_battle_outcome_learning_cycle(
        model,
        training_examples=training,
        development_examples=development,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        prior_l2=args.prior_l2,
    )
    paired = compare_battle_outcome_preferences(
        model,
        cycle.update.model,
        development,
    )
    _write_exclusive(args.out_model, cycle.update.model.to_json().encode("ascii") + b"\n")
    report = {
        "schema": "pokemon.core.battle.repeatable-authentic-fit.v1",
        "base_model_sha256": hashlib.sha256(model.to_json().encode("ascii")).hexdigest(),
        "updated_model_sha256": hashlib.sha256(
            cycle.update.model.to_json().encode("ascii")
        ).hexdigest(),
        "training": cycle.update.report.public_dict(),
        "base_development": cycle.base_development.public_dict(),
        "updated_development": cycle.updated_development.public_dict(),
        "paired_development": paired.public_dict(),
        "authentic_outcome_training": True,
        "development_artifact": True,
        "sealed_evidence": False,
        "authority_promoted": False,
        "crystal_transfer_claim": False,
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
        print(f"repeatable authentic fit failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
