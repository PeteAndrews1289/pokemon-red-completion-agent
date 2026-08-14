#!/usr/bin/env python3
"""Authenticate a private correction stream and emit a path-free audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pokemon_red_completion.battle_correction_audit import (
    audit_battle_correction_artifact,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--total-decisions", type=int, required=True)
    parser.add_argument("--model-executions", type=int, required=True)
    parser.add_argument("--teacher-fallbacks", type=int, required=True)
    args = parser.parse_args(argv)
    audit = audit_battle_correction_artifact(
        args.artifact,
        total_decisions=args.total_decisions,
        model_executions=args.model_executions,
        teacher_fallbacks=args.teacher_fallbacks,
    )
    print(
        json.dumps(
            audit.public_dict(),
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
