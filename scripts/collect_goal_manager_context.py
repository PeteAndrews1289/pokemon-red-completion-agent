#!/usr/bin/env python3
"""Execute exactly one frozen Red goal-manager context as a counted episode."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.captured_progress import CapturedProgressError
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter
from pokemon_red_completion.executor import FrameSafeExecutor
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.goal_manager_collection_runtime import (
    GoalManagerCollectionRuntimeError,
    record_goal_manager_context,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalogError,
    goal_manager_catalog_episode_metadata,
    open_goal_manager_context_capture,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (
    GoalManagerProtocolError,
    load_committed_goal_manager_registry,
)
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    open_private_root,
)
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    canonical_sha256,
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
from pokemon_red_completion.red_goal_skills import RedGoalSkillError
from pokemon_red_completion.red_player_observer import ResumedStateError
from pokemon_red_completion.red_trajectory import (
    POKEMON_CORE_ONTOLOGY_ID,
    POKEMON_RED_ADAPTER_ID,
    PokemonRedObservationEncoder,
)
from pokemon_red_completion.rom import RomValidationError, resolve_rom_path, verify_rom
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts
from pokemon_red_completion.runtime_identity import (
    RuntimeIdentityError,
    build_runtime_identity,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class GoalManagerContextCollectionError(RuntimeError):
    """Raised when one-shot collection differs from its frozen context."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, default=None)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=None)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.speed is not None and not args.watch:
        raise GoalManagerContextCollectionError("--speed requires --watch")
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    registry = load_committed_goal_manager_registry(PROJECT_ROOT)
    if (
        source.git_commit != registry.execution.source_commit
        or working_source_bundle_sha256(PROJECT_ROOT)
        != registry.execution.source_bundle_sha256
    ):
        raise GoalManagerContextCollectionError(
            "working source differs from the committed goal-manager registry"
        )
    assignment = registry.assignment(args.slot_id)
    catalog = parse_goal_manager_context_catalog(
        args.context_catalog.read_bytes(),
        registry,
    )
    state_path = args.state.resolve()
    envelope_path = (args.envelope or Path(f"{state_path}.json")).resolve()
    capture = open_goal_manager_context_capture(state_path, envelope_path)
    profile = load_red_goal_context_profile(args.profile)
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    private_root = open_private_root(
        args.private_root,
        repository_root=PROJECT_ROOT,
    )
    adjacent_before = rom_adjacent_artifacts(rom_path)
    runtime_identity = build_runtime_identity()
    metadata = goal_manager_catalog_episode_metadata(assignment, catalog)
    configuration = {
        "context_profile": profile.public_dict(),
        "emulator": {
            "human_input": False,
            "save_on_exit": False,
            "speed": args.speed if args.watch else 0,
            "watch": args.watch,
        },
        "execution_mode": "one_teacher_choice_then_selected_bounded_mechanic",
        "teacher_fallback": False,
    }
    metadata.update(
        {
            "adapter_id": POKEMON_RED_ADAPTER_ID,
            "configuration": configuration,
            "configuration_sha256": canonical_sha256(configuration),
            "ontology_id": POKEMON_CORE_ONTOLOGY_ID,
            "rom_identity": fingerprint.public_dict(),
            "runtime": runtime_identity.public_dict(),
            "runtime_sha256": runtime_identity.sha256,
        }
    )

    with PyBoyAdapter(
        rom_path,
        watch=args.watch,
        speed=args.speed,
    ) as emulator:
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
        result = record_goal_manager_context(
            private_root=private_root,
            assignment=assignment,
            capture=capture,
            context_catalog=catalog,
            metadata=metadata,
            adapter=runtime.adapter,
            snapshot_provider=PokemonRedObservationEncoder.from_state_reader(reader),
            action_delegate=controller,
            enumerator_factory=runtime.enumerator,
        )

    if (
        hashlib.sha256(state_path.read_bytes()).hexdigest() != capture.state_sha256
        or hashlib.sha256(envelope_path.read_bytes()).hexdigest()
        != capture.envelope_sha256
    ):
        raise GoalManagerContextCollectionError(
            "private context inputs changed during collection"
        )
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise GoalManagerContextCollectionError(
            "goal-manager collection created a ROM-adjacent artifact"
        )
    return {
        **result.public_dict(),
        "profile": profile.public_dict(),
        "status": "complete",
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
        GoalManagerContextCollectionError,
        GoalManagerProtocolError,
        PrivateArtifactError,
        RedGoalContextError,
        RedGoalContextProfileError,
        RedGoalSkillError,
        ResumedStateError,
        RomValidationError,
        RuntimeIdentityError,
        OSError,
    ):
        parser.error("Goal-manager collection failed closed; private paths were withheld.")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
