#!/usr/bin/env python3
"""Prove that two planners can inspect one Red state without controlling it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameSafeExecutor,
    ReadOnlyController,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    CompositionBudgetCheckpoint,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    open_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_model import (
    GoalManagerLinearModel,
    LearnedGoalManagerPolicy,
    canonical_goal_manager_model_sha256,
    load_goal_manager_model,
)
from pokemon_red_completion.goal_manager_runtime import CompletionFirstGoalTeacher
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.provenance import (
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_bounded_player import (
    RedBoundedPlayerObserver,
    preflight_red_bounded_player,
)
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import load_red_goal_context_profile
from pokemon_red_completion.rom import resolve_rom_path, verify_rom
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RedBoundedPlayerPreflightRunError(RuntimeError):
    """Raised when the action-free authenticated preflight cannot be trusted."""


@dataclass(frozen=True, slots=True)
class _ReadOnlyBudgetMeter:
    actions: CountingExecutor
    emulator: PyBoyAdapter
    initial_frame_count: int

    def checkpoint(self) -> CompositionBudgetCheckpoint:
        frames = self.emulator.frame_count - self.initial_frame_count
        if frames < 0:
            raise RedBoundedPlayerPreflightRunError("emulator frame count moved backwards")
        return CompositionBudgetCheckpoint(
            controller_actions=self.actions.actions_executed,
            emulator_frames=frames,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assignment-id", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _regular_external(path: Path, *, subject: str, rom_path: Path) -> Path:
    resolved = path.resolve()
    try:
        metadata = resolved.lstat()
    except OSError as error:
        raise RedBoundedPlayerPreflightRunError(f"{subject} is unavailable") from error
    if (
        resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved.parent == rom_path.resolve().parent
        or resolved.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
    ):
        raise RedBoundedPlayerPreflightRunError(
            f"{subject} must be a regular external private file"
        )
    return resolved


def _new_external_receipt(path: Path, *, rom_path: Path) -> Path:
    resolved = path.resolve()
    if (
        resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved.parent == rom_path.resolve().parent
        or not resolved.parent.is_dir()
        or resolved.exists()
        or resolved.suffix != ".json"
    ):
        raise RedBoundedPlayerPreflightRunError(
            "receipt must be a new JSON file in an existing external private directory"
        )
    return resolved


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        with suppress(OSError):
            path.unlink()
        raise


def _load_model(path: Path) -> tuple[GoalManagerLinearModel, str, str]:
    file_sha256 = _sha256(path)
    model = load_goal_manager_model(path, expected_sha256=file_sha256)
    return model, file_sha256, canonical_goal_manager_model_sha256(model)


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    paths = {
        "state": _regular_external(args.state, subject="state", rom_path=rom_path),
        "envelope": _regular_external(
            args.envelope, subject="envelope", rom_path=rom_path
        ),
        "profile": _regular_external(args.profile, subject="profile", rom_path=rom_path),
        "model": _regular_external(args.model, subject="model", rom_path=rom_path),
    }
    receipt_path = _new_external_receipt(args.out, rom_path=rom_path)
    protected_before = {name: _sha256(path) for name, path in paths.items()}
    adjacent_before = rom_adjacent_artifacts(rom_path)

    capture = open_goal_manager_context_capture(paths["state"], paths["envelope"])
    profile = load_red_goal_context_profile(paths["profile"])
    if capture.capture_id != profile.profile_id:
        raise RedBoundedPlayerPreflightRunError("capture and profile identity differ")
    model, model_file_sha256, model_sha256 = _load_model(paths["model"])

    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(capture.state_bytes)
        initial_frame_count = emulator.frame_count
        controller = ReadOnlyController(emulator)
        reader = PokemonRedStateReader(controller)
        runtime = build_red_goal_context_runtime(
            profile=profile,
            capture=capture,
            emulator=controller,
            reader=reader,
        )
        executor = FrameSafeExecutor(
            controller,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        actions = CountingExecutor(executor)
        meter = _ReadOnlyBudgetMeter(actions, emulator, initial_frame_count)
        preflight = preflight_red_bounded_player(
            observe=RedBoundedPlayerObserver(runtime=runtime, actions=actions),
            budget_meter=meter,
            assignment_id=args.assignment_id,
            authorities=(
                ("learned-goal-manager", LearnedGoalManagerPolicy(model)),
                ("completion-first-teacher", CompletionFirstGoalTeacher()),
            ),
        )
        if meter.checkpoint() != CompositionBudgetCheckpoint(0, 0):
            raise RedBoundedPlayerPreflightRunError(
                "preflight crossed its zero-input budget"
            )

    protected_after = {name: _sha256(path) for name, path in paths.items()}
    if protected_after != protected_before:
        raise RedBoundedPlayerPreflightRunError("private preflight inputs changed")
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise RedBoundedPlayerPreflightRunError(
            "preflight created a ROM-adjacent artifact"
        )
    summary = {
        **preflight.public_dict(),
        "capture_id": capture.capture_id,
        "capture_state_sha256": capture.state_sha256,
        "capture_envelope_sha256": capture.envelope_sha256,
        "model_file_sha256": model_file_sha256,
        "model_sha256": model_sha256,
        "profile_sha256": profile.profile_sha256,
        "rom_sha256": rom.sha256,
        "source_bundle_sha256": source_bundle_sha256,
        "source_commit": source.git_commit,
    }
    payload = (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_exclusive(receipt_path, payload)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        summary = _run(parser.parse_args(argv))
    except Exception:
        parser.error("Red bounded-player preflight failed closed; private paths were withheld.")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
