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
from pokemon_crystal_completion.transfer_protocol import (
    CRYSTAL_TRANSFER_PLAN_FILENAME,
    parse_crystal_transfer_plan,
)
from pokemon_red_completion.rom import fingerprint_rom

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "configs" / CRYSTAL_TRANSFER_PLAN_FILENAME


def _print_json(document: dict[str, object]) -> None:
    print(
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


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
    _print_json(audit.public_dict())
    return 0 if audit.ready_for_private_context_inventory else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CrystalPrerequisiteError as error:
        _print_json(
            {
                "schema": "pokemon.crystal.transfer-entry-gate-error.v1",
                "status": "blocked",
                "reason": str(error),
                "teacher_executed": False,
                "context_opened": False,
                "prediction_computed": False,
                "private_path_fields": 0,
            }
        )
        raise SystemExit(2) from None
