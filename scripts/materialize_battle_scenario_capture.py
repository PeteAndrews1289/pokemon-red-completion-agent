#!/usr/bin/env python3
"""Create one authenticated wild-battle MAIN-menu capture without choosing a move."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_recovery import (  # noqa: E402
    switch_active_battler,
)
from pokemon_red_completion.battle_runtime import (  # noqa: E402
    BattlePolicyBoundary,
    advance_battle_to_policy_boundary,
)
from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    build_battle_scenario_capture_payload,
)
from pokemon_red_completion.blaine import (  # noqa: E402
    DIGLETTS_CAVE_TRAINING_VENUE,
    MANSION_TRAINING_VENUE,
    ROUTE_11_TRAINING_VENUE,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.observation import (  # noqa: E402
    BattleMenuPhase,
    MapId,
    PokemonRedStateReader,
    RawGameState,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_battle_scenario import (  # noqa: E402
    PreparedRedBattleScenario,
    prepare_red_battle_scenario,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder  # noqa: E402
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.training_venue import TrainingVenue  # noqa: E402


class BattleScenarioMaterializationError(RuntimeError):
    """Raised before a private capture can be authenticated."""


_MAXIMUM_BATTLE_STATE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class MaterializedBattleBoundary:
    state: RawGameState
    prepared: PreparedRedBattleScenario
    encounter_steps: int
    encounter_walk_calls: int
    boundary: BattlePolicyBoundary
    switch_actions: int


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-state", type=Path, required=True)
    parser.add_argument("--source-state-sha256", required=True)
    parser.add_argument(
        "--source-location",
        choices=("route_11", "digletts_cave", "mansion", "cinnabar_center"),
        required=True,
    )
    parser.add_argument(
        "--party-slot",
        type=int,
        choices=range(1, 7),
        default=1,
        help="one-based living party slot prospectively chosen for the capture",
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


def _fsync_existing_private_output(path: Path) -> bytes:
    """Authenticate, privatize, and durably retain an emulator-created file."""

    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        named = path.lstat()
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            named.st_dev != opened.st_dev
            or named.st_ino != opened.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or not 1 <= opened.st_size <= _MAXIMUM_BATTLE_STATE_BYTES
        ):
            raise OSError("unsafe materialized output")
        os.fchmod(descriptor, 0o600)
        payload = b""
        while len(payload) < opened.st_size:
            chunk = os.read(descriptor, opened.st_size - len(payload))
            if not chunk:
                raise OSError("materialized output changed while opening")
            payload += chunk
        os.fsync(descriptor)
    except OSError:
        raise BattleScenarioMaterializationError(
            "battle state could not be retained durably"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    _fsync_directory(path.parent)
    return payload


def _write_private_output(destination: Path, payload: bytes) -> None:
    """Publish one new owner-only file and its directory entry durably."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    created = False
    failed = False
    try:
        descriptor = os.open(destination, flags, 0o600)
        created = True
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("materialized output write made no progress")
            offset += written
        os.fsync(descriptor)
    except OSError:
        failed = True
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                failed = True
    if failed:
        if created:
            with suppress(OSError):
                destination.unlink()
            with suppress(BattleScenarioMaterializationError):
                _fsync_directory(destination.parent)
        raise BattleScenarioMaterializationError(
            "battle manifest could not be retained durably"
        ) from None
    _fsync_directory(destination.parent)


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    descriptor = -1
    try:
        descriptor = os.open(directory, flags)
        os.fsync(descriptor)
    except OSError:
        raise BattleScenarioMaterializationError(
            "battle capture directory could not be retained durably"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _venue_for_source_location(source_location: str) -> TrainingVenue:
    venues = {
        "route_11": ROUTE_11_TRAINING_VENUE,
        "digletts_cave": DIGLETTS_CAVE_TRAINING_VENUE,
        "mansion": MANSION_TRAINING_VENUE,
        "cinnabar_center": MANSION_TRAINING_VENUE,
    }
    try:
        return venues[source_location]
    except KeyError:
        raise BattleScenarioMaterializationError(
            "source location has no measured battle venue"
        ) from None


def _require_living_party_slot(raw: object, one_based_party_slot: int) -> int:
    if type(one_based_party_slot) is not int or not 1 <= one_based_party_slot <= 6:  # noqa: E721
        raise BattleScenarioMaterializationError("party slot must be between one and six")
    party_count = getattr(raw, "party_count", None)
    party_hp = getattr(raw, "party_hp", None)
    party_index = one_based_party_slot - 1
    if (
        type(party_count) is not int  # noqa: E721
        or not isinstance(party_hp, tuple)
        or party_count != len(party_hp)
        or party_index >= party_count
        or type(party_hp[party_index]) is not int  # noqa: E721
        or party_hp[party_index] <= 0
    ):
        raise BattleScenarioMaterializationError(
            "prospectively selected party slot is not a living party member"
        )
    return party_index


def _materialize_loaded_battle_boundary(
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    controller: FrameSafeExecutor,
    actions: CountingExecutor,
    venue: TrainingVenue,
    *,
    one_based_party_slot: int,
    maximum_encounter_steps: int,
) -> MaterializedBattleBoundary:
    venue_boundary = reader.read()
    if venue_boundary.map_id != venue.map_id or venue_boundary.battle_state != 0:
        raise BattleScenarioMaterializationError(
            "source did not reach its measured encounter venue"
        )
    party_index = _require_living_party_slot(
        venue_boundary,
        one_based_party_slot,
    )
    encounter_steps = 0
    encounter_walk_calls = 0
    walk_to_grass = venue.fresh_walk_to_grass()
    while reader.read().battle_state == 0:
        encounter_walk_calls += 1
        if encounter_walk_calls > maximum_encounter_steps * 4:
            raise BattleScenarioMaterializationError(
                "wild encounter walker made no bounded progress"
            )
        encounter_steps += walk_to_grass(actions, reader, emulator)
        if encounter_steps > maximum_encounter_steps:
            raise BattleScenarioMaterializationError(
                "wild encounter did not begin inside the configured bound"
            )
    boundary = advance_battle_to_policy_boundary(
        reader,
        controller,
        expected_map=venue.map_id,
        expected_battle_state=1,
        timing=venue.battle_timing,
        label="battle scenario materialization",
    )
    switch_action_start = actions.actions_executed
    switch_active_battler(
        actions,
        reader,
        emulator,
        party_index,
        expected_battle_state=1,
        label="battle scenario materialization",
    )
    switch_actions = actions.actions_executed - switch_action_start
    capture_boundary = reader.read()
    menu = reader.read_battle_menu_state(capture_boundary)
    if menu.phase is not BattleMenuPhase.MAIN:
        raise BattleScenarioMaterializationError(
            "materialized capture is not at the MAIN policy boundary"
        )
    if (
        capture_boundary.map_id != venue.map_id
        or capture_boundary.battle_state != 1
        or capture_boundary.active_party_index != party_index
        or (capture_boundary.battler_hp or 0) <= 0
    ):
        raise BattleScenarioMaterializationError(
            "materialized capture did not preserve its selected battle boundary"
        )
    prepared = prepare_red_battle_scenario(
        PokemonRedObservationEncoder.from_state_reader(reader),
        capture_boundary,
    )
    return MaterializedBattleBoundary(
        state=capture_boundary,
        prepared=prepared,
        encounter_steps=encounter_steps,
        encounter_walk_calls=encounter_walk_calls,
        boundary=boundary,
        switch_actions=switch_actions,
    )


def _prepare_source_venue(
    source_location: str,
    venue: TrainingVenue,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
) -> None:
    raw = reader.read()
    if source_location == "cinnabar_center":
        if raw.map_id != MapId.CINNABAR_POKECENTER or raw.battle_state != 0:
            raise BattleScenarioMaterializationError(
                "center source is not at the expected safe boundary"
            )
        venue.heal_and_return(actions, reader, emulator)
    elif raw.map_id != venue.map_id or raw.battle_state != 0:
        raise BattleScenarioMaterializationError(
            "venue source is not at the expected safe boundary"
        )
    prepared = reader.read()
    if prepared.map_id != venue.map_id or prepared.battle_state != 0:
        raise BattleScenarioMaterializationError(
            "source did not reach its measured encounter venue"
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
    venue = _venue_for_source_location(args.source_location)

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
        _prepare_source_venue(
            args.source_location,
            venue,
            actions,
            reader,
            emulator,
        )
        materialized = _materialize_loaded_battle_boundary(
            reader,
            emulator,
            controller,
            actions,
            venue,
            one_based_party_slot=args.party_slot,
            maximum_encounter_steps=args.maximum_encounter_steps,
        )
        emulator.save_state(out_state)

    state_bytes = _fsync_existing_private_output(out_state)
    manifest_payload = build_battle_scenario_capture_payload(
        capture_id=args.capture_id,
        root_lineage_id=args.root_lineage_id,
        partition=partition,
        state_bytes=state_bytes,
        initial_observation_sha256=materialized.prepared.initial_observation_sha256,
        source_commit=source.git_commit,
        expected_map=venue.map_id,
        expected_battle_state=1,
        source_state_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )
    _write_private_output(out_manifest, manifest_payload)
    return {
        "schema": "pokemon-private-battle-scenario-materialization-receipt-v2",
        "status": "ok",
        "capture_id": args.capture_id,
        "root_lineage_id": args.root_lineage_id,
        "partition": partition.value,
        "source_commit": source.git_commit,
        "source_state_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "state_sha256": hashlib.sha256(state_bytes).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
        "initial_observation_sha256": materialized.prepared.initial_observation_sha256,
        "candidate_count": len(materialized.prepared.features.candidate_vectors),
        "supported_candidate_count": sum(materialized.prepared.supported_candidate_mask),
        "venue_id": venue.area_id,
        "venue_minimum_encounter_level": venue.band.minimum_encounter_level,
        "venue_maximum_encounter_level": venue.band.maximum_encounter_level,
        "source_location": args.source_location,
        "party_slot": args.party_slot,
        "encounter_steps": materialized.encounter_steps,
        "encounter_walk_calls": materialized.encounter_walk_calls,
        "boundary_actions": materialized.boundary.actions_executed,
        "boundary_frames": materialized.boundary.frames_executed,
        "switch_actions": materialized.switch_actions,
        "party_switches_executed": int(materialized.switch_actions > 0),
        "total_actions": (
            actions.actions_executed + materialized.boundary.actions_executed
        ),
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
