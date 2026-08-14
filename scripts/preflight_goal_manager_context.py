#!/usr/bin/env python3
"""Read one Red context without acting and write its canonical private receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from contextlib import suppress
from pathlib import Path

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.captured_progress import CapturedProgressError
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.goal_manager_collection_runtime import (
    GoalManagerCollectionRuntimeError,
    preflight_goal_manager_context,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalogError,
    open_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_preflight import (
    GoalManagerPreflightError,
    build_goal_manager_preflight_payload,
    parse_goal_manager_preflight,
)
from pokemon_red_completion.goal_manager_protocol import (
    GoalManagerProtocolError,
    load_committed_goal_manager_registry,
)
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_goal_context import (
    RedGoalContextError,
    build_red_goal_context_runtime,
)
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    load_red_goal_context_profile,
)
from pokemon_red_completion.red_player_observer import ResumedStateError
from pokemon_red_completion.rom import RomValidationError, resolve_rom_path, verify_rom
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class GoalManagerContextPreflightError(RuntimeError):
    """Raised when a read-only context inspection crosses its authority."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, default=None)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _private_new_receipt(destination: Path, *, slot_id: str, rom_path: Path) -> Path:
    resolved = destination.resolve()
    if (
        resolved.name != f"{slot_id}.json"
        or resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved.parent == rom_path.resolve().parent
        or not resolved.parent.is_dir()
        or resolved.exists()
    ):
        raise GoalManagerContextPreflightError(
            "preflight receipt must use its new private external slot path"
        )
    return resolved


def _write_exclusive(destination: Path, payload: bytes) -> None:
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        with suppress(OSError):
            destination.unlink()
        raise


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    registry = load_committed_goal_manager_registry(PROJECT_ROOT)
    if (
        source.git_commit != registry.execution.source_commit
        or working_source_bundle_sha256(PROJECT_ROOT)
        != registry.execution.source_bundle_sha256
    ):
        raise GoalManagerContextPreflightError(
            "working source differs from the committed goal-manager registry"
        )
    assignment = registry.assignment(args.slot_id)
    rom_path = resolve_rom_path(args.rom)
    verify_rom(rom_path)
    destination = _private_new_receipt(
        args.out,
        slot_id=assignment.slot_id,
        rom_path=rom_path,
    )
    state_path = args.state.resolve()
    envelope_path = (args.envelope or Path(f"{state_path}.json")).resolve()
    capture = open_goal_manager_context_capture(state_path, envelope_path)
    profile = load_red_goal_context_profile(args.profile)
    adjacent_before = rom_adjacent_artifacts(rom_path)

    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(capture.state_bytes)
        reader = PokemonRedStateReader(emulator)
        runtime = build_red_goal_context_runtime(
            profile=profile,
            capture=capture,
            emulator=emulator,
            reader=reader,
        )
        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        actions = CountingExecutor(controller)
        preflight = preflight_goal_manager_context(
            assignment=assignment,
            capture=capture,
            adapter=runtime.adapter,
            enumerator=runtime.enumerator(actions),
        )
        if actions.actions_executed:
            raise GoalManagerContextPreflightError(
                "read-only preflight attempted a controller action"
            )

    if (
        hashlib.sha256(state_path.read_bytes()).hexdigest() != capture.state_sha256
        or hashlib.sha256(envelope_path.read_bytes()).hexdigest()
        != capture.envelope_sha256
    ):
        raise GoalManagerContextPreflightError(
            "private context inputs changed during preflight"
        )
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise GoalManagerContextPreflightError(
            "read-only preflight created a ROM-adjacent artifact"
        )
    payload = build_goal_manager_preflight_payload(preflight, assignment)
    parsed = parse_goal_manager_preflight(payload, assignment)
    if parsed != preflight:
        raise GoalManagerContextPreflightError("preflight receipt round trip differs")
    _write_exclusive(destination, payload)
    return {
        **preflight.public_dict(),
        "profile": profile.public_dict(),
        "actions_executed": 0,
        "episode_created": False,
        "status": "ready",
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        summary = _run(args)
    except (
        CapturedProgressError,
        CartridgeReadError,
        EmulatorError,
        EvaluationIdentityError,
        GoalManagerCollectionRuntimeError,
        GoalManagerContextCatalogError,
        GoalManagerContextPreflightError,
        GoalManagerPreflightError,
        GoalManagerProtocolError,
        RedGoalContextError,
        RedGoalContextProfileError,
        ResumedStateError,
        RomValidationError,
        OSError,
    ):
        parser.error("Goal-manager preflight failed closed; private paths were withheld.")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
