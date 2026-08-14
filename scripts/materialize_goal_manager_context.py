#!/usr/bin/env python3
"""Materialize one real, uncounted Red goal-manager mechanic boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.blaine import (
    CENTER_TO_MART,
    MANSION_TRAINING_VENUE,
    BlaineChapterError,
    _move,
    _pulse,
    _require,
    _training_dig_to_cinnabar,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.captured_progress import (
    CapturedProgressError,
    write_captured_progress,
)
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter
from pokemon_red_completion.executor import (
    ControllerTiming,
    CountingExecutor,
    FrameSafeExecutor,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalogError,
    open_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_protocol import (
    GoalManagerProtocolError,
    load_committed_goal_manager_registry,
)
from pokemon_red_completion.observation import MapId, PokemonRedStateReader
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_player_observer import (
    CapturedPokemonRedObserver,
    ResumedStateError,
)
from pokemon_red_completion.rom import RomValidationError, resolve_rom_path, verify_rom
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts
from pokemon_red_completion.surge import VERMILION_PC_TO_NURSE, SurgeChapterError, _flee

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MODES = (
    "mansion",
    "mart",
    "pc",
    "blocked-movement",
    "damaged-field",
    "damaged-center",
)


class GoalManagerContextMaterializationError(RuntimeError):
    """Raised when a real mechanic boundary cannot be derived safely."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=_MODES, required=True)
    parser.add_argument("--context-id", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, default=None)
    parser.add_argument("--out-state", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=None)
    return parser


def _new_external_output(destination: Path, rom_path: Path) -> Path:
    resolved = destination.resolve()
    envelope = Path(f"{resolved}.json")
    if (
        resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved.parent == rom_path.resolve().parent
        or not resolved.parent.is_dir()
        or resolved.exists()
        or envelope.exists()
    ):
        raise GoalManagerContextMaterializationError(
            "materialized context must use a new private external path"
        )
    return resolved


def _inverse(directions: tuple[str, ...]) -> tuple[str, ...]:
    opposite = {"up": "down", "right": "left", "down": "up", "left": "right"}
    return tuple(opposite[item] for item in reversed(directions))


def _require_cinnabar_nurse(reader: PokemonRedStateReader) -> None:
    raw = reader.read()
    if (
        raw.map_id != MapId.CINNABAR_POKECENTER
        or (raw.player_x, raw.player_y) != (3, 3)
        or raw.battle_state
        or not reader.read_input_readiness().ready
    ):
        raise GoalManagerContextMaterializationError(
            "materialization requires the stable Cinnabar nurse boundary"
        )


def _mansion_boundary(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
) -> None:
    MANSION_TRAINING_VENUE.heal_and_return(actions, reader, emulator)
    for _ in range(16):
        MANSION_TRAINING_VENUE.walk_to_grass(actions, reader, emulator)
        raw = reader.read()
        if raw.battle_state:
            _flee(emulator, actions, reader, raw)
            raw = reader.read()
        if (
            raw.map_id == MapId.POKEMON_MANSION_1F
            and raw.player_x is not None
            and raw.player_y is not None
            and reader.read_input_readiness().ready
        ):
            return
    raise GoalManagerContextMaterializationError(
        "Mansion context did not reach a stable encounter boundary"
    )


def _damage_party(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
) -> None:
    _mansion_boundary(actions, reader, emulator)
    initial = reader.read()
    initial_hp = initial.party_hp or ()
    for _ in range(48):
        MANSION_TRAINING_VENUE.walk_to_grass(actions, reader, emulator)
        raw = reader.read()
        if raw.battle_state:
            _flee(emulator, actions, reader, raw)
            raw = reader.read()
        hp = raw.party_hp or ()
        if (
            hp
            and len(hp) == len(initial_hp)
            and all(value > 0 for value in hp)
            and hp != initial_hp
        ):
            return
    raise GoalManagerContextMaterializationError(
        "bounded wild encounters did not produce safe party damage"
    )


def _apply_mode(
    mode: str,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
) -> None:
    _require_cinnabar_nurse(reader)
    if mode == "mansion":
        _mansion_boundary(actions, reader, emulator)
        return
    if mode == "mart":
        _move(actions, reader, CENTER_TO_MART, "goal-manager Cinnabar Mart")
        _require(reader.read(), MapId.CINNABAR_MART, (3, 7), "goal-manager Mart entry")
        _move(actions, reader, ("up", "up", "left"), "goal-manager Mart clerk")
        _pulse(actions, MacroActionKind.MOVE, "left", 120)
        return
    if mode == "pc":
        _move(
            actions,
            reader,
            _inverse(VERMILION_PC_TO_NURSE),
            "goal-manager Center PC",
        )
        _require(reader.read(), MapId.CINNABAR_POKECENTER, (13, 4), "goal-manager PC")
        _pulse(actions, MacroActionKind.MOVE, "up", 60)
        return
    if mode == "blocked-movement":
        actions.execute(MacroAction(MacroActionKind.MOVE, "down"))
        if reader.read_input_readiness().ready:
            raise GoalManagerContextMaterializationError(
                "released movement pulse did not create a blocked-control context"
            )
        return
    if mode in {"damaged-field", "damaged-center"}:
        _damage_party(actions, reader, emulator)
        if mode == "damaged-center":
            _training_dig_to_cinnabar(actions, reader, emulator)
            _move(actions, reader, ("up",), "goal-manager damaged Center entry")
            _require(
                reader.read(),
                MapId.CINNABAR_POKECENTER,
                (3, 7),
                "goal-manager damaged Center",
            )
            _move(actions, reader, ("up",) * 4, "goal-manager damaged nurse")
        return
    raise GoalManagerContextMaterializationError("materialization mode is unsupported")


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.speed is not None and not args.watch:
        raise GoalManagerContextMaterializationError("--speed requires --watch")
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    registry = load_committed_goal_manager_registry(PROJECT_ROOT)
    if (
        source.git_commit != registry.execution.source_commit
        or working_source_bundle_sha256(PROJECT_ROOT)
        != registry.execution.source_bundle_sha256
    ):
        raise GoalManagerContextMaterializationError(
            "working source differs from the committed goal-manager registry"
        )

    rom_path = resolve_rom_path(args.rom)
    verify_rom(rom_path)
    out_state = _new_external_output(args.out_state, rom_path)
    state_path = args.state.resolve()
    envelope_path = (args.envelope or Path(f"{state_path}.json")).resolve()
    capture = open_goal_manager_context_capture(state_path, envelope_path)
    state_before = hashlib.sha256(state_path.read_bytes()).hexdigest()
    envelope_before = hashlib.sha256(envelope_path.read_bytes()).hexdigest()
    adjacent_before = rom_adjacent_artifacts(rom_path)

    with PyBoyAdapter(rom_path, watch=args.watch, speed=args.speed) as emulator:
        emulator.load_state_bytes(capture.state_bytes)
        reader = PokemonRedStateReader(emulator)
        observer = CapturedPokemonRedObserver(reader, COMPLETION_QUEST, capture.envelope)
        completed_before = COMPLETION_QUEST.completed_ids(observer.observe())
        timing = (
            ControllerTiming()
            if args.mode == "blocked-movement"
            else DEFAULT_NEW_GAME_TIMING.controller_timing()
        )
        controller = FrameSafeExecutor(emulator, timing)
        actions = CountingExecutor(controller)
        _apply_mode(args.mode, actions, reader, emulator)
        final = reader.read()
        completed_after = COMPLETION_QUEST.completed_ids(observer.observe())
        if (
            final.battle_state
            or completed_after != completed_before
            or not emulator.pressed_buttons == frozenset()
        ):
            raise GoalManagerContextMaterializationError(
                "materialization changed story, retained input, or ended in battle"
            )
        if args.mode != "blocked-movement" and not reader.read_input_readiness().ready:
            raise GoalManagerContextMaterializationError(
                "materialization did not end at a stable control boundary"
            )
        final_input_ready = reader.read_input_readiness().ready
        emulator.save_state(out_state)
        output = write_captured_progress(
            Path(f"{out_state}.json"),
            state_path=out_state,
            checkpoint_id=args.context_id,
            checkpoint_label=f"Goal-manager {args.mode} mechanic boundary",
            checkpoints_completed=capture.envelope.checkpoints_completed,
            checkpoints_total=capture.envelope.checkpoints_total,
            verified_objective_ids=capture.envelope.verified_objective_ids,
        )

    if (
        hashlib.sha256(state_path.read_bytes()).hexdigest() != state_before
        or hashlib.sha256(envelope_path.read_bytes()).hexdigest() != envelope_before
        or rom_adjacent_artifacts(rom_path) != adjacent_before
    ):
        raise GoalManagerContextMaterializationError(
            "source capture or ROM-adjacent artifacts changed during materialization"
        )
    return {
        "schema": "pokemon-red-goal-manager-context-materialization-v1",
        "status": "complete",
        "counted": False,
        "episode_created": False,
        "mode": args.mode,
        "capture_id": output.checkpoint_id,
        "state_sha256": output.state_sha256,
        "actions_executed": actions.actions_executed,
        "map_id": int(final.map_id or 0),
        "coordinate": [final.player_x, final.player_y],
        "input_ready": final_input_ready,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        summary = _run(args)
    except (
        BlaineChapterError,
        CapturedProgressError,
        EmulatorError,
        EvaluationIdentityError,
        GoalManagerContextCatalogError,
        GoalManagerContextMaterializationError,
        GoalManagerProtocolError,
        ResumedStateError,
        RomValidationError,
        SurgeChapterError,
        OSError,
    ):
        parser.error(
            "Goal-manager materialization failed closed; private paths were withheld."
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
