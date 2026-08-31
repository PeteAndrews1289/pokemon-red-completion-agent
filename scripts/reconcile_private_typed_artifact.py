#!/usr/bin/env python3
"""Seal or publish one orphaned deterministic typed private artifact.

This recovery command performs no experiment work. It sends no emulator input,
opens no outcomes, computes no prediction, fits no model, and never retries a
claimed root. It only authenticates already-durable JSONL streams and gives the
one existing artifact identity an inspectable terminal state.
"""

# ruff: noqa: E402 -- pin the project source root before local imports.

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
while str(SRC_ROOT) in sys.path:
    sys.path.remove(str(SRC_ROOT))
sys.path.insert(0, str(SRC_ROOT))

from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    open_private_root,
)

RESULT_SCHEMA = "pokemon.private-typed-artifact-reconciliation.v1"


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise PrivateArtifactError("reconciliation arguments are invalid")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--expected-kind", required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    store = open_private_root(
        args.private_root,
        repository_root=PROJECT_ROOT,
    )
    recovery = store.reconcile_interrupted_artifact(
        args.artifact_id,
        expected_kind=args.expected_kind,
    )
    return {
        "schema": RESULT_SCHEMA,
        "status": "complete",
        "recovery": recovery.public_dict(),
        "emulator_inputs": 0,
        "outcome_reads": 0,
        "predictions": 0,
        "model_fits": 0,
        "root_retries": 0,
    }


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        stage = "reconciliation"
        result = _run(args)
    except (PrivateArtifactError, OSError, TypeError, ValueError):
        print(
            json.dumps(
                {
                    "schema": RESULT_SCHEMA,
                    "status": "failed",
                    "reason_code": stage,
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            result,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
