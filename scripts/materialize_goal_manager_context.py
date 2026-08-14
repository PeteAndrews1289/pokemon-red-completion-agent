#!/usr/bin/env python3
"""Materialize one real, uncounted Red goal-manager mechanic boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_recovery import (
    ProtectedRecoveryError,
    switch_active_battler,
)
from pokemon_red_completion.blaine import (
    CENTER_TO_MART,
    DIGLETT_SPECIES_ID,
    DIGLETTS_CAVE_TRAINING_VENUE,
    MANSION_BALANCED_TEAM_TRAINING_INTENT,
    MANSION_ESCORT_ENEMY_SPECIES,
    MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
    MANSION_MAX_CONSECUTIVE_FLEES,
    MANSION_TRAINING_FLEE_TIMING,
    MANSION_TRAINING_VENUE,
    MANSION_VOLATILE_ENEMY_SPECIES,
    ROUTE_11_TRAINING_VENUE,
    BlaineChapterError,
    _fly_to_town,
    _heal,
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
from pokemon_red_completion.celadon import CeladonChapterError
from pokemon_red_completion.celadon import _flee as _timed_flee
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter
from pokemon_red_completion.executor import (
    ControllerTiming,
    CountingExecutor,
    FrameSafeExecutor,
)
from pokemon_red_completion.field_recovery import (
    FieldRecoveryError,
    plan_party_recovery,
)
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalogError,
    open_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_protocol import (
    GoalManagerProtocolError,
    load_committed_goal_manager_registry,
)
from pokemon_red_completion.goal_manager_state import party_safety_satisfaction
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING
from pokemon_red_completion.observation import (
    MapId,
    PokemonRedStateReader,
    RawGameState,
)
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_goal_context import (
    _targeted_evolution_index,
    red_team_development_quantum_policy,
)
from pokemon_red_completion.red_goal_manager import RedGoalManagerConfig
from pokemon_red_completion.red_party import (
    BLASTOISE_SPECIES_ID,
    DUGTRIO_SPECIES_ID,
    party_observation_from_raw,
)
from pokemon_red_completion.red_player_observer import (
    CapturedPokemonRedObserver,
    ResumedStateError,
)
from pokemon_red_completion.red_team_training import run_red_team_balancing
from pokemon_red_completion.rom import RomValidationError, resolve_rom_path, verify_rom
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts
from pokemon_red_completion.surge import (
    VERMILION_PC_TO_NURSE,
    SurgeChapterError,
)
from pokemon_red_completion.surge import (
    _flee as _protected_flee,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Catalog admission starts at 0.50, but the fixed completion-first teacher's
# emergency restoration gate is 0.55.  Setup must reach the teacher contract
# rather than merely scrape past the weaker structural threshold.
_ACTIVE_SAFETY_PRESSURE = 0.55
_DAMAGE_SWITCH_LIMIT = 64
_MODES = (
    "mansion",
    "mart",
    "pc",
    "blocked-movement",
    "damaged-field",
    "damaged-center",
    "evolved-team",
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


def _normalize_cinnabar_nurse(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
) -> None:
    raw = reader.read()
    if raw.battle_state or not reader.read_input_readiness().ready:
        raise GoalManagerContextMaterializationError(
            "materialization requires a stable relocation boundary"
        )
    if raw.map_id == MapId.INDIGO_PLATEAU_LOBBY and (
        raw.player_x,
        raw.player_y,
    ) == (2, 5):
        _move(
            actions,
            reader,
            ("right", "down", "down") + ("right",) * 4 + ("down",) * 5,
            "goal-manager Indigo departure",
        )
        _require(
            reader.read(),
            MapId.INDIGO_PLATEAU,
            (9, 6),
            "goal-manager Indigo field",
        )
        _fly_to_town(
            actions,
            reader,
            emulator,
            MapId.CINNABAR_ISLAND,
            "goal-manager Indigo to Cinnabar",
        )
        _move(actions, reader, ("up",) * 5, "goal-manager Cinnabar Center")
        raw = reader.read()
    if raw.map_id != MapId.CINNABAR_POKECENTER or (
        raw.player_x,
        raw.player_y,
    ) != (3, 3):
        raise GoalManagerContextMaterializationError(
            "materialization did not reach the stable Cinnabar nurse boundary"
        )
    _heal(actions, reader, emulator)


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
            _protected_flee(emulator, actions, reader, raw)
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
    *,
    require_field_recovery: bool,
) -> None:
    source = reader.read()
    species = source.party_species_ids or ()
    levels = source.party_levels or ()
    hp = source.party_hp or ()
    maximum = source.party_max_hp or ()
    if not (
        species
        and len(species) == len(levels) == len(hp) == len(maximum)
        and all(
            current > 0 and current == limit
            for current, limit in zip(hp, maximum, strict=True)
        )
        and _safety_pressure(source) == 0.0
    ):
        raise GoalManagerContextMaterializationError(
            "damage materialization requires a complete healthy party observation"
        )
    _mansion_boundary(actions, reader, emulator)
    for _ in range(48):
        raw = reader.read()
        if _damage_context_ready(
            raw,
            require_field_recovery=require_field_recovery,
        ):
            return
        MANSION_TRAINING_VENUE.walk_to_grass(actions, reader, emulator)
        raw = reader.read()
        if raw.battle_state:
            fastest_index = max(
                range(len(levels)),
                key=lambda index: (levels[index], hp[index], -index),
            )
            for _ in range(_DAMAGE_SWITCH_LIMIT):
                raw = reader.read()
                _require_safe_damage_state(raw)
                if _safety_pressure(raw) >= _ACTIVE_SAFETY_PRESSURE:
                    break
                active_index = raw.active_party_index
                if active_index is None:
                    raise GoalManagerContextMaterializationError(
                        "damage materialization lost the active party index"
                    )
                current_hp = raw.party_hp or ()
                if (
                    _safety_pressure(raw) >= _ACTIVE_SAFETY_PRESSURE - 0.05
                    and active_index != fastest_index
                ):
                    target_index = fastest_index
                else:
                    target_index = max(
                        (
                            index
                            for index in range(len(current_hp))
                            if index != active_index
                        ),
                        key=lambda index: (current_hp[index], levels[index], -index),
                    )
                switch_active_battler(
                    actions,
                    reader,
                    emulator,
                    target_index,
                    expected_battle_state=1,
                    label="goal-manager controlled wild damage",
                    wait_frames=120,
                )
            else:
                raise GoalManagerContextMaterializationError(
                    "bounded party switches did not reach active safety pressure"
                )
            raw = reader.read()
            _require_safe_damage_state(raw)
            if raw.active_party_index != fastest_index:
                switch_active_battler(
                    actions,
                    reader,
                    emulator,
                    fastest_index,
                    expected_battle_state=1,
                    label="goal-manager safe escape lead",
                    wait_frames=120,
                )
            _protected_flee(emulator, actions, reader, raw)
        _require_safe_damage_state(reader.read())
    raise GoalManagerContextMaterializationError(
        "bounded wild encounters did not reach active safety pressure"
    )


def _safety_pressure(raw: RawGameState) -> float:
    return 1.0 - party_safety_satisfaction(party_observation_from_raw(raw))


def _require_safe_damage_state(raw: RawGameState) -> None:
    current_hp = raw.party_hp or ()
    current_maximum = raw.party_max_hp or ()
    current_status = raw.party_status or ()
    if (
        not current_hp
        or len(current_hp) != len(current_maximum)
        or len(current_hp) != len(current_status)
    ):
        raise GoalManagerContextMaterializationError(
            "damage materialization lost complete party evidence"
        )
    if any(value <= 0 for value in current_hp):
        raise GoalManagerContextMaterializationError(
            "damage materialization allowed a party member to faint"
        )


def _damage_context_ready(
    raw: RawGameState,
    *,
    require_field_recovery: bool,
) -> bool:
    _require_safe_damage_state(raw)
    if _safety_pressure(raw) < _ACTIVE_SAFETY_PRESSURE:
        return False
    if not require_field_recovery:
        return True
    try:
        plan = plan_party_recovery(
            tuple(raw.party_hp or ()),
            tuple(raw.party_max_hp or ()),
            tuple(raw.party_status or ()),
        )
    except FieldRecoveryError:
        return False
    inventory = dict(raw.bag_items or ())
    required = Counter(item for _, item in plan)
    return all(
        inventory.get(int(item), 0) >= quantity
        for item, quantity in required.items()
    )


def _evolved_team_boundary(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
) -> None:
    before = reader.read()
    before_species = tuple(before.party_species_ids or ())
    before_levels = tuple(before.party_levels or ())
    if (
        BLASTOISE_SPECIES_ID not in before_species
        or DIGLETT_SPECIES_ID not in before_species
        or DUGTRIO_SPECIES_ID in before_species
        or len(before_species) != len(before_levels)
    ):
        raise GoalManagerContextMaterializationError(
            "evolved-team setup requires the unevolved qualified party"
        )
    policy = red_team_development_quantum_policy(
        party_observation_from_raw(before),
        RedGoalManagerConfig(),
        kind=GoalKind.EVOLVE_SPECIES,
    )
    run_red_team_balancing(
        actions,
        reader,
        emulator,
        policy=policy,
        venues=(
            ROUTE_11_TRAINING_VENUE,
            DIGLETTS_CAVE_TRAINING_VENUE,
            MANSION_TRAINING_VENUE,
        ),
        intent=MANSION_BALANCED_TEAM_TRAINING_INTENT,
        flee_timing=MANSION_TRAINING_FLEE_TIMING,
        hideout_timing=DEFAULT_HIDEOUT_TIMING,
        flee_func=_timed_flee,
        volatile_enemy_species=MANSION_VOLATILE_ENEMY_SPECIES,
        escort_enemy_species=MANSION_ESCORT_ENEMY_SPECIES,
        max_consecutive_flees=MANSION_MAX_CONSECUTIVE_FLEES,
        cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
        evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID),
        report_label="goal-manager evolved-team setup",
        checkpoint_count=1,
    )
    after = reader.read()
    target_index = _targeted_evolution_index(
        before_species,
        tuple(after.party_species_ids or ()),
        source_species_id=DIGLETT_SPECIES_ID,
        target_species_id=DUGTRIO_SPECIES_ID,
    )
    after_levels = tuple(after.party_levels or ())
    _require_safe_damage_state(after)
    if (
        target_index is None
        or len(after_levels) != len(before_levels)
        or after_levels[target_index] <= before_levels[target_index]
        or after.map_id
        not in {MapId.CINNABAR_POKECENTER, MapId.VERMILION_POKECENTER}
        or (after.player_x, after.player_y) != (3, 3)
        or not reader.read_input_readiness().ready
    ):
        raise GoalManagerContextMaterializationError(
            "evolved-team setup did not reach its exact stable transformation boundary"
        )


def _apply_mode(
    mode: str,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
) -> None:
    _normalize_cinnabar_nurse(actions, reader, emulator)
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
    if mode == "evolved-team":
        _evolved_team_boundary(actions, reader, emulator)
        return
    if mode in {"damaged-field", "damaged-center"}:
        _damage_party(
            actions,
            reader,
            emulator,
            require_field_recovery=mode == "damaged-field",
        )
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
            _require_safe_damage_state(reader.read())
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
        CeladonChapterError,
        CapturedProgressError,
        EmulatorError,
        EvaluationIdentityError,
        FieldRecoveryError,
        GoalManagerContextCatalogError,
        GoalManagerContextMaterializationError,
        GoalManagerProtocolError,
        ProtectedRecoveryError,
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
