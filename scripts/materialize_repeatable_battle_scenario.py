#!/usr/bin/env python3
"""Materialize one frozen Red battle scenario through natural cartridge input."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from contextlib import suppress
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_repeatable_battle_scenario_runtime import (  # noqa: E402
    materialize_repeatable_red_battle_scenario,
)
from pokemon_red_completion.red_repeatable_battle_scenario_source import (  # noqa: E402
    inspect_repeatable_red_battle_source,
)
from pokemon_red_completion.repeatable_battle_scenario_factory import (  # noqa: E402
    parse_repeatable_battle_scenario_plan,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402

_MAXIMUM_PLAN_BYTES = 16 * 1024 * 1024
_MAXIMUM_STATE_BYTES = 64 * 1024 * 1024


class RepeatableBattleScenarioMaterializationError(RuntimeError):
    """Raised before or during one frozen natural scenario execution."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--source-state", type=Path, required=True)
    parser.add_argument("--out-state", type=Path, required=True)
    parser.add_argument("--out-manifest", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--maximum-encounter-steps", type=int, default=512)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=None)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.speed is not None and not args.watch:
        raise RepeatableBattleScenarioMaterializationError("--speed requires --watch")
    _require_new_private_output(args.out_state)
    _require_new_private_output(args.out_manifest)
    if args.out_state.resolve() == args.out_manifest.resolve():
        raise RepeatableBattleScenarioMaterializationError(
            "state and manifest outputs must be distinct"
        )
    plan_payload = _read_bounded(args.private_plan, maximum_bytes=_MAXIMUM_PLAN_BYTES)
    plan = parse_repeatable_battle_scenario_plan(plan_payload)
    if plan.sha256 != args.expected_plan_sha256:
        raise RepeatableBattleScenarioMaterializationError("private plan digest differs")
    matches = tuple(
        item for item in plan.assignments if item.scenario_id == args.scenario_id
    )
    if len(matches) != 1:
        raise RepeatableBattleScenarioMaterializationError(
            "scenario identity is absent or ambiguous"
        )
    assignment = matches[0]
    state_bytes = _read_bounded(args.source_state, maximum_bytes=_MAXIMUM_STATE_BYTES)
    if hashlib.sha256(state_bytes).hexdigest() != assignment.source_state_sha256:
        raise RepeatableBattleScenarioMaterializationError("source state digest differs")

    source_identity = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source_identity)
    require_published_source(PROJECT_ROOT, source_identity)
    if source_identity.git_commit is None:  # pragma: no cover - clean source owns this
        raise AssertionError("published source lacks a commit")
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    rom_bytes = rom_path.read_bytes()

    def session_factory() -> PyBoyAdapter:
        return PyBoyAdapter(
            rom_path,
            watch=args.watch,
            speed=args.speed,
        )

    source = inspect_repeatable_red_battle_source(
        state_bytes,
        source_id=assignment.source_id,
        source_lineage_id=assignment.source_lineage_id,
        partition=assignment.partition,
        source_commit=assignment.source_commit,
        session_factory=session_factory,
    )
    result = materialize_repeatable_red_battle_scenario(
        source,
        assignment,
        state_bytes,
        rom_bytes=rom_bytes,
        materializer_source_commit=source_identity.git_commit,
        session_factory=session_factory,
        maximum_encounter_steps=args.maximum_encounter_steps,
    )
    _write_new_private(args.out_state, result.state_bytes)
    try:
        _write_new_private(args.out_manifest, result.manifest_payload)
    except Exception:
        with suppress(OSError):
            args.out_state.unlink()
        raise
    return {
        **result.public_dict(),
        "plan_sha256": plan.sha256,
        "rom_sha256": rom.sha256,
        "materializer_source_commit": source_identity.git_commit,
        "private_path_fields": 0,
    }


def _read_bounded(path: Path, *, maximum_bytes: int) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError:
        raise RepeatableBattleScenarioMaterializationError(
            "private materialization input is unavailable"
        ) from None
    if not 1 <= len(payload) <= maximum_bytes:
        raise RepeatableBattleScenarioMaterializationError(
            "private materialization input size is invalid"
        )
    return payload


def _require_new_private_output(path: Path) -> None:
    if path.resolve().is_relative_to(PROJECT_ROOT.resolve()):
        raise RepeatableBattleScenarioMaterializationError(
            "materialized battle captures must remain outside the repository"
        )
    if not path.parent.is_dir() or path.exists():
        raise RepeatableBattleScenarioMaterializationError(
            "materialization output is unavailable or already exists"
        )


def _write_new_private(path: Path, payload: bytes) -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("private output write made no progress")
            offset += written
        os.fsync(descriptor)
    except OSError:
        raise RepeatableBattleScenarioMaterializationError(
            "materialization output could not be published"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def main() -> int:
    args = _parser().parse_args()
    try:
        result = _run(args)
    except (RepeatableBattleScenarioMaterializationError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "failed", "reason": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
