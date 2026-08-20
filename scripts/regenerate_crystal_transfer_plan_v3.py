#!/usr/bin/env python3
"""Regenerate or verify the prospective Crystal transfer V3 plan."""

from __future__ import annotations

import argparse
from pathlib import Path

from pokemon_crystal_completion.transfer_protocol_v3 import (
    CRYSTAL_TRANSFER_V3_PLAN_FILENAME,
    canonical_crystal_transfer_v3_plan_bytes,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    path = PROJECT_ROOT / "configs" / CRYSTAL_TRANSFER_V3_PLAN_FILENAME
    payload = canonical_crystal_transfer_v3_plan_bytes()
    if args.check:
        if not path.is_file() or path.read_bytes() != payload:
            raise SystemExit("Crystal transfer V3 plan differs from generator")
        return 0
    path.write_bytes(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
