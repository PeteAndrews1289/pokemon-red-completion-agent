#!/usr/bin/env python3
"""Train a repeatable mechanics-initialized battle model without opening a ROM."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.repeatable_battle_curriculum import (  # noqa: E402
    build_repeatable_red_battle_curriculum,
    fit_repeatable_battle_curriculum,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-examples", type=int, default=2000)
    parser.add_argument("--development-examples", type=int, default=500)
    parser.add_argument("--seed", type=int, default=1289)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--hidden-units", type=int, default=32)
    parser.add_argument("--out-model", type=Path, required=True)
    parser.add_argument("--out-report", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    curriculum = build_repeatable_red_battle_curriculum(
        training_examples=args.training_examples,
        development_examples=args.development_examples,
        seed=args.seed,
    )
    model, report = fit_repeatable_battle_curriculum(
        curriculum,
        seed=args.seed,
        hidden_units=args.hidden_units,
        epochs=args.epochs,
    )
    _write_new(args.out_model, (model.to_json() + "\n").encode("ascii"))
    _write_new(
        args.out_report,
        (
            json.dumps(
                {**curriculum.public_dict(), **report.public_dict()},
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("ascii"),
    )
    print(json.dumps(report.public_dict(), indent=2, sort_keys=True))
    return 0


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
