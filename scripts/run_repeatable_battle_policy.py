#!/usr/bin/env python3
"""Let a learned model choose and execute one move on development captures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker  # noqa: E402
from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    open_battle_scenario_capture,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.red_battle_outcome_runtime import (  # noqa: E402
    execute_red_battle_candidate,
    prepare_red_battle_outcome_capture,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    model = MaskedMLPMoveRanker.from_dict(json.loads(args.model.read_text("ascii")))
    model_sha256 = hashlib.sha256(model.to_json().encode("ascii")).hexdigest()
    manifests = sorted(args.capture_dir.glob("*.state.json"))
    if not manifests:
        raise ValueError("no battle captures were discovered")
    executions: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for manifest in manifests:
        capture = open_battle_scenario_capture(manifest.with_suffix(""), manifest)
        if capture.manifest.partition is not ScenarioPartition.DEVELOPMENT:
            raise ValueError("model authority rehearsal requires development captures")
        try:
            prepared = prepare_red_battle_outcome_capture(
                capture,
                session_factory=lambda: PyBoyAdapter(rom_path),
            )
            selected = model.predict(
                prepared.features.candidate_vectors,
                legal_mask=prepared.features.legal_mask,
                current_pp=prepared.features.current_pp,
            )
            execution = execute_red_battle_candidate(
                capture,
                selected,
                session_factory=lambda: PyBoyAdapter(rom_path),
            )
            executions.append(execution.public_dict())
        except RuntimeError as error:
            failures.append(
                {
                    "capture_id": capture.manifest.capture_id,
                    "error_type": type(error).__name__,
                    "reason": str(error),
                }
            )
    report = {
        "schema": "pokemon.red.battle.repeatable-policy-execution.v1",
        "model_sha256": model_sha256,
        "rom_sha256": rom.sha256,
        "captures_presented": len(manifests),
        "actions_executed": len(executions),
        "failures": failures,
        "executions": executions,
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "model_authority": "battle_move_selection",
        "development_artifact": True,
        "sealed_evidence": False,
        "full_game_replays": 0,
        "private_path_fields": 0,
    }
    if not executions:
        raise RuntimeError("no model-selected action executed")
    _write_exclusive(
        args.output,
        (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("ascii"),
    )
    return report


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
        print(f"repeatable battle policy execution failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
