#!/usr/bin/env python3
"""Report whether private Crystal context inventory may begin; execute nothing."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pokemon_crystal_completion.prerequisites import (
    CrystalPrerequisiteError,
    assess_crystal_transfer_prerequisites,
)
from pokemon_crystal_completion.source_contract import CRYSTAL_ROM_ENVIRONMENT_VARIABLE
from pokemon_crystal_completion.transfer_protocol import parse_crystal_transfer_plan
from pokemon_red_completion.rom import fingerprint_rom

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "configs" / "crystal-goal-manager-transfer-v1.json"


def main() -> int:
    plan = parse_crystal_transfer_plan(PLAN.read_bytes())
    raw_path = os.environ.get(CRYSTAL_ROM_ENVIRONMENT_VARIABLE)
    fingerprint = None
    if raw_path:
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise CrystalPrerequisiteError("owner-supplied Crystal ROM is not a file")
        fingerprint = fingerprint_rom(path)
    audit = assess_crystal_transfer_prerequisites(plan, fingerprint=fingerprint)
    print(
        json.dumps(
            audit.public_dict(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0 if audit.ready_for_private_context_inventory else 2


if __name__ == "__main__":
    raise SystemExit(main())
