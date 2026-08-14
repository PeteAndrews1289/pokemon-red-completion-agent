#!/usr/bin/env python3
"""Execute one frozen Red goal context without creating a training episode."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameSafeExecutor
from pokemon_red_completion.goal_manager_collection_runtime import (
    rehearse_goal_manager_context,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    open_goal_manager_context_capture,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (
    load_committed_goal_manager_registry,
)
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.provenance import (
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import load_red_goal_context_profile
from pokemon_red_completion.rom import resolve_rom_path, verify_rom
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, default=None)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=None)
    return parser


def _protected_file_digests(paths: tuple[Path, ...]) -> tuple[tuple[Path, str], ...]:
    return tuple(
        (path, hashlib.sha256(path.read_bytes()).hexdigest()) for path in paths
    )


def _require_protected_files_unchanged(
    protected: tuple[tuple[Path, str], ...],
) -> None:
    if any(
        hashlib.sha256(path.read_bytes()).hexdigest() != expected
        for path, expected in protected
    ):
        raise RuntimeError("rehearsal changed a protected input")


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.speed is not None and not args.watch:
        raise RuntimeError("--speed requires --watch")
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    registry = load_committed_goal_manager_registry(PROJECT_ROOT)
    if (
        source.git_commit != registry.execution.source_commit
        or working_source_bundle_sha256(PROJECT_ROOT)
        != registry.execution.source_bundle_sha256
    ):
        raise RuntimeError("working source differs from the committed goal-manager registry")
    assignment = registry.assignment(args.slot_id)
    state_path = args.state.resolve()
    envelope_path = (args.envelope or Path(f"{state_path}.json")).resolve()
    profile_path = args.profile.resolve()
    catalog_path = args.context_catalog.resolve()
    rom_path = resolve_rom_path(args.rom)
    protected = _protected_file_digests(
        (state_path, envelope_path, profile_path, catalog_path, rom_path)
    )
    catalog = parse_goal_manager_context_catalog(catalog_path.read_bytes(), registry)
    capture = open_goal_manager_context_capture(state_path, envelope_path)
    profile = load_red_goal_context_profile(profile_path)
    verify_rom(rom_path)
    adjacent_before = rom_adjacent_artifacts(rom_path)

    try:
        with PyBoyAdapter(rom_path, watch=args.watch, speed=args.speed) as emulator:
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
            result = rehearse_goal_manager_context(
                assignment=assignment,
                capture=capture,
                context_catalog=catalog,
                adapter=runtime.adapter,
                action_delegate=controller,
                enumerator_factory=runtime.enumerator,
            )
    finally:
        _require_protected_files_unchanged(protected)
        if rom_adjacent_artifacts(rom_path) != adjacent_before:
            raise RuntimeError("rehearsal changed a ROM-adjacent artifact")
    return {**result.public_dict(), "status": "passed_uncounted_rehearsal"}


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        summary = _run(args)
    except Exception:
        parser.error("Goal-manager rehearsal failed closed; private paths were withheld.")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
