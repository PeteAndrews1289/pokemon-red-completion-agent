#!/usr/bin/env python3
"""Create one authenticated wild-battle MAIN-menu capture without choosing a move."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_runtime import (  # noqa: E402
    advance_battle_to_policy_boundary,
)
from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    build_battle_scenario_capture_payload,
)
from pokemon_red_completion.blaine import MANSION_TRAINING_VENUE  # noqa: E402
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.observation import (  # noqa: E402
    BattleMenuPhase,
    MapId,
    PokemonRedStateReader,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_battle_scenario import (  # noqa: E402
    prepare_red_battle_scenario,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder  # noqa: E402
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


class BattleScenarioMaterializationError(RuntimeError):
    """Raised before a private capture can be authenticated."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-state", type=Path, required=True)
    parser.add_argument("--source-state-sha256", required=True)
    parser.add_argument(
        "--source-location",
        choices=("mansion", "cinnabar_center"),
        required=True,
    )
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--root-lineage-id", required=True)
    parser.add_argument(
        "--partition",
        choices=(ScenarioPartition.TRAIN.value, ScenarioPartition.DEVELOPMENT.value),
        required=True,
    )
    parser.add_argument("--out-state", type=Path, required=True)
    parser.add_argument("--out-manifest", type=Path, default=None)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--maximum-encounter-steps", type=int, default=512)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=None)
    return parser


def _private_new_output(destination: Path, *, rom_path: Path) -> Path:
    resolved = destination.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise BattleScenarioMaterializationError("battle capture must remain private")
    if resolved.parent == rom_path.resolve().parent:
        raise BattleScenarioMaterializationError("battle capture cannot be written beside the ROM")
    if not resolved.parent.is_dir():
        raise BattleScenarioMaterializationError("battle capture parent does not exist")
    if resolved.exists():
        raise BattleScenarioMaterializationError("battle capture output already exists")
    return resolved


def _read_authenticated_source(path: Path, expected_sha256: str) -> bytes:
    if path.is_symlink():
        raise BattleScenarioMaterializationError("source state cannot be a symlink")
    try:
        payload = path.read_bytes()
    except OSError:
        raise BattleScenarioMaterializationError("source state is unavailable") from None
    if not payload or hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise BattleScenarioMaterializationError("source state digest differs")
    return payload


def _require_distinct_outputs(state: Path, manifest: Path) -> None:
    if state == manifest:
        raise BattleScenarioMaterializationError(
            "battle state and manifest outputs must be distinct"
        )


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.speed is not None and not args.watch:
        raise BattleScenarioMaterializationError("--speed requires --watch")
    if args.maximum_encounter_steps < 1:
        raise BattleScenarioMaterializationError(
            "--maximum-encounter-steps must be positive"
        )
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - clean source establishes this
        raise AssertionError("clean source identity lacks a commit")

    rom_path = resolve_rom_path(args.rom)
    source_bytes = _read_authenticated_source(
        args.source_state.resolve(),
        args.source_state_sha256,
    )
    out_state = _private_new_output(args.out_state, rom_path=rom_path)
    out_manifest = _private_new_output(
        args.out_manifest or Path(f"{out_state}.json"),
        rom_path=rom_path,
    )
    _require_distinct_outputs(out_state, out_manifest)
    partition = ScenarioPartition(args.partition)

    with PyBoyAdapter(
        rom_path,
        watch=args.watch,
        speed=args.speed,
    ) as emulator:
        emulator.load_state_bytes(source_bytes)
        reader = PokemonRedStateReader(emulator)
        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        actions = CountingExecutor(controller)
        raw = reader.read()
        if args.source_location == "cinnabar_center":
            if raw.map_id != MapId.CINNABAR_POKECENTER or raw.battle_state != 0:
                raise BattleScenarioMaterializationError(
                    "center source is not at the expected safe boundary"
                )
            MANSION_TRAINING_VENUE.heal_and_return(actions, reader, emulator)
        elif raw.map_id != MapId.POKEMON_MANSION_1F or raw.battle_state != 0:
            raise BattleScenarioMaterializationError(
                "mansion source is not at the expected safe boundary"
            )

        encounter_steps = 0
        while reader.read().battle_state == 0:
            encounter_steps += MANSION_TRAINING_VENUE.walk_to_grass(
                actions,
                reader,
                emulator,
            )
            if encounter_steps > args.maximum_encounter_steps:
                raise BattleScenarioMaterializationError(
                    "wild encounter did not begin inside the configured bound"
                )
        boundary = advance_battle_to_policy_boundary(
            reader,
            controller,
            expected_map=int(MapId.POKEMON_MANSION_1F),
            expected_battle_state=1,
            timing=MANSION_TRAINING_VENUE.battle_timing,
            label="battle scenario materialization",
        )
        menu = reader.read_battle_menu_state(boundary.state)
        if menu.phase is not BattleMenuPhase.MAIN:
            raise BattleScenarioMaterializationError(
                "materialized capture is not at the MAIN policy boundary"
            )
        prepared = prepare_red_battle_scenario(
            PokemonRedObservationEncoder.from_state_reader(reader),
            boundary.state,
        )
        emulator.save_state(out_state)

    state_bytes = out_state.read_bytes()
    manifest_payload = build_battle_scenario_capture_payload(
        capture_id=args.capture_id,
        root_lineage_id=args.root_lineage_id,
        partition=partition,
        state_bytes=state_bytes,
        initial_observation_sha256=prepared.initial_observation_sha256,
        source_commit=source.git_commit,
        expected_map=int(MapId.POKEMON_MANSION_1F),
        expected_battle_state=1,
    )
    out_manifest.write_bytes(manifest_payload)
    return {
        "schema": "pokemon-private-battle-scenario-materialization-receipt-v1",
        "status": "ok",
        "capture_id": args.capture_id,
        "root_lineage_id": args.root_lineage_id,
        "partition": partition.value,
        "source_commit": source.git_commit,
        "source_state_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "state_sha256": hashlib.sha256(state_bytes).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
        "initial_observation_sha256": prepared.initial_observation_sha256,
        "candidate_count": len(prepared.features.candidate_vectors),
        "supported_candidate_count": sum(prepared.supported_candidate_mask),
        "encounter_steps": encounter_steps,
        "boundary_actions": boundary.actions_executed,
        "boundary_frames": boundary.frames_executed,
        "teacher_queries": 0,
        "move_choices_executed": 0,
        "private_path_fields": 0,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(_run(args), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
