#!/usr/bin/env python3
"""Regenerate the public ROM-free Red prospective-plan qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pokemon_red_completion.red_living_dex_capture_plan import (
    qualify_red_living_dex_prospective_capture_plan,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "configs/red-living-dex-prospective-capture-plan-v1.json"


def _payload() -> bytes:
    document = qualify_red_living_dex_prospective_capture_plan().public_dict()
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    payload = _payload()
    if args.check:
        if not PLAN_PATH.is_file() or PLAN_PATH.read_bytes() != payload:
            raise SystemExit("Red living-Pokedex prospective capture plan is stale")
    else:
        PLAN_PATH.write_bytes(payload)
    result = qualify_red_living_dex_prospective_capture_plan()
    print(
        json.dumps(
            {
                "bytes": len(payload),
                "pilot_execution_ready": result.pilot_execution_ready,
                "plan_sha256": result.plan.plan_sha256,
                "qualification_sha256": result.qualification_sha256,
                "routed_slots": result.routed_slot_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
