#!/usr/bin/env python3
"""Regenerate or verify the prospective Crystal transfer preregistration."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pokemon_crystal_completion.transfer_protocol import (
    CRYSTAL_TRANSFER_PLAN_FILENAME,
    canonical_crystal_transfer_plan_bytes,
    parse_crystal_transfer_plan,
)

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed Crystal transfer plan is stale.",
    )
    args = parser.parse_args(argv)
    payload = canonical_crystal_transfer_plan_bytes()
    plan = parse_crystal_transfer_plan(payload)
    path = ROOT / "configs" / CRYSTAL_TRANSFER_PLAN_FILENAME
    if args.check:
        if path.read_bytes() != payload:
            raise SystemExit("Crystal transfer preregistration is stale")
    else:
        path.write_bytes(payload)
    print(
        json.dumps(
            {
                "bytes": len(payload),
                "contexts": len(plan.slots),
                "plan_sha256": hashlib.sha256(payload).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
