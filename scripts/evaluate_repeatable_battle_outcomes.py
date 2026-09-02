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

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker  # noqa: E402
from pokemon_red_completion.battle_outcome_learning import (  # noqa: E402
    compare_battle_outcome_preferences,
    evaluate_battle_outcome_preferences,
)
from pokemon_red_completion.repeatable_battle_dataset import (  # noqa: E402
    parse_repeatable_battle_outcome_record,
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
    base = _read_model(args.base_model)
    challenger = _read_model(args.challenger_model)
    examples = tuple(
        parse_repeatable_battle_outcome_record(json.loads(line))
        for dataset in args.dataset
        for line in dataset.read_text("ascii").splitlines()
        if line
    )
    if not examples or any(
        item.partition is not ScenarioPartition.DEVELOPMENT for item in examples
    ):
        raise ValueError("evaluation requires only development examples")
    report = {
        "schema": "pokemon.core.battle.repeatable-authentic-evaluation.v1",
        "base": evaluate_battle_outcome_preferences(base, examples).public_dict(),
        "challenger": evaluate_battle_outcome_preferences(
            challenger, examples
        ).public_dict(),
        "paired": compare_battle_outcome_preferences(
            base, challenger, examples
        ).public_dict(),
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


def _read_model(path: Path) -> MaskedMLPMoveRanker:
    return MaskedMLPMoveRanker.from_dict(json.loads(path.read_text("ascii")))


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
