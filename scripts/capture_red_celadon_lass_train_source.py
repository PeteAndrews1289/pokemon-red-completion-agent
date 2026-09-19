"""Capture one untouched Celadon TRAIN root at the first Gym Lass MAIN decision.

This is a bounded source collector, not a battle teacher or a story run. Each
source identity has one output slot; a failed route is retained, not replaced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.erika import (
    CENTER_EXIT,
    CITY_TO_OUTER_TREE,
    DEFAULT_ERIKA_TIMING,
    LOWER_CITY_TO_GYM,
    _cut,
    _enter_battle,
    _move,
)
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    EventFlag,
    MapId,
    PokemonRedStateReader,
    event_flag_is_set,
)
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
SOURCE_SHA256 = {
    "red-goal-v1-001-advance_story-train-01": (
        "7d9ce6d351ca87ea83b6038e35c953a9e0f5f648f722d82ca252f87110b0a80e"
    ),
    "red-goal-v1-002-advance_story-train-02": (
        "1a4452bce3c704bcb50bb441cbe6885d3e0bf9556294d9c3c407513ebe9edc9f"
    ),
    "red-goal-v1-003-advance_story-train-03": (
        "3734daa5dfecb8534b9ee0141459e9032d04d9612d0e6b2a085da0e75748dd9f"
    ),
}
MAX_ACTIONS = 600
MAX_FRAMES = 180_000


def _validate_request(
    rom_path: Path, source_path: Path, source_id: str, output_root: Path
) -> tuple[bytes, bytes, Path]:
    if source_id not in SOURCE_SHA256:
        raise ValueError("Celadon source identity is not prospectively pinned")
    if source_path.name != f"{source_id}.state":
        raise ValueError("Celadon source filename differs from its identity")
    output = output_root / source_id
    if output.exists():
        raise ValueError("Celadon source identity already has a retained result")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit the Celadon source capture code before execution")
    rom = rom_path.read_bytes()
    source = source_path.read_bytes()
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError("Celadon source ROM differs from the pinned Red cartridge")
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256[source_id]:
        raise ValueError("Celadon source bytes differ from the pinned root")
    return rom, source, output


def _check_budget(actions: CountingExecutor, emulator: PyBoyAdapter) -> None:
    if actions.actions_executed > MAX_ACTIONS or emulator.frame_count > MAX_FRAMES:
        raise ValueError("Celadon source route exceeded its declared budget")


def _require_start(reader: PokemonRedStateReader) -> None:
    raw = reader.read()
    if (
        raw.map_id != MapId.CELADON_POKECENTER
        or (raw.player_x, raw.player_y) != (3, 3)
        or raw.battle_state != 0
        or raw.party_count != 3
        or raw.event_flags is None
        or event_flag_is_set(raw.event_flags, int(EventFlag.BEAT_ERIKA))
        or event_flag_is_set(raw.event_flags, int(EventFlag.BEAT_CELADON_GYM_TRAINER_0))
        or not reader.read_input_readiness().ready
    ):
        raise ValueError("Celadon source is not the untouched Gym approach boundary")


def _model_ready_observation(reader: PokemonRedStateReader, rom: bytes, raw):
    return prepare_red_battle_scenario(
        PokemonRedObservationEncoder.from_state_reader(
            reader,
            include_battle_stats=True,
            public_species_base_stats=RedPracticeCartridge(rom).public_base_stats,
        ),
        raw,
        allow_no_attack=True,
    )


def run(rom_path: Path, source_path: Path, source_id: str, output_root: Path) -> dict[str, object]:
    rom, source, output = _validate_request(rom_path, source_path, source_id, output_root)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    report: dict[str, object] = {
        "schema": "pokemon.red.celadon-lass-train-source.v1",
        "source_id": source_id,
        "root_lineage_id": source_id,
        "partition": "train",
        "source_state_sha256": SOURCE_SHA256[source_id],
        "source_commit": commit,
        "max_actions": MAX_ACTIONS,
        "max_frames": MAX_FRAMES,
        "model_queries": 0,
        "model_updates": 0,
        "full_game_runs": 0,
        "status": "started",
    }
    (output / "outcome.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    try:
        with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
            emulator.load_state_bytes(source)
            reader = PokemonRedStateReader(emulator)
            _require_start(reader)
            actions = CountingExecutor(
                FrameSafeExecutor(emulator, DEFAULT_NEW_GAME_TIMING.controller_timing())
            )
            try:
                timing = DEFAULT_ERIKA_TIMING
                _move(actions, reader, emulator, CENTER_EXIT, timing, "Center exit")
                _check_budget(actions, emulator)
                _move(actions, reader, emulator, CITY_TO_OUTER_TREE, timing, "outer tree")
                _check_budget(actions, emulator)
                _cut(actions, reader, emulator, timing, "down", 0x2C, "outer Cut")
                _move(actions, reader, emulator, ("down",), timing, "outer crossing")
                _move(actions, reader, emulator, LOWER_CITY_TO_GYM, timing, "Gym door")
                _move(actions, reader, emulator, ("up",), timing, "Gym entry")
                _check_budget(actions, emulator)
                _move(
                    actions,
                    reader,
                    emulator,
                    ("up",) * 6,
                    timing,
                    "Lass trigger",
                    allow_trigger=True,
                )
                _enter_battle(actions, reader, timing, "Celadon Gym Lass")
                for _ in range(45):
                    raw = reader.read()
                    if (
                        raw.battle_state == 2
                        and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
                    ):
                        break
                    actions.execute(MacroAction(MacroActionKind.CONFIRM))
                    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
                else:
                    raise ValueError("Celadon source missed its first MAIN decision")
                _check_budget(actions, emulator)
                if (
                    raw.map_id != MapId.CELADON_GYM
                    or raw.enemy_party_count is None
                    or raw.enemy_party_count < 1
                    or raw.enemy_party_position != 0
                    or (raw.enemy_hp or 0) <= 0
                    or emulator.pressed_buttons
                ):
                    raise ValueError("Celadon source trainer boundary differs")
                prepared = _model_ready_observation(reader, rom, raw)
                state = emulator.save_state_bytes()
                manifest = build_battle_scenario_capture_payload(
                    capture_id=f"celadon-lass-{source_id}",
                    root_lineage_id=source_id,
                    partition=ScenarioPartition.TRAIN,
                    state_bytes=state,
                    source_state_sha256=SOURCE_SHA256[source_id],
                    initial_observation_sha256=prepared.initial_observation_sha256,
                    source_commit=commit,
                    expected_map=int(MapId.CELADON_GYM),
                    expected_battle_state=2,
                    observation_schema=OBSERVATION_SCHEMA_V2,
                )
                (output / "source.state").write_bytes(state)
                (output / "source.state.json").write_bytes(manifest)
                capture = open_battle_scenario_capture(
                    output / "source.state", output / "source.state.json"
                )
                report.update(
                    status="captured",
                    state_sha256=capture.manifest.state_sha256,
                    observation_sha256=prepared.initial_observation_sha256,
                    map_id=int(raw.map_id),
                    opponent_party_count=raw.enemy_party_count,
                    actions_executed=actions.actions_executed,
                    frames_executed=emulator.frame_count,
                )
            finally:
                report["actions_executed"] = actions.actions_executed
                report["frames_executed"] = emulator.frame_count
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        (output / "outcome.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("source_id", choices=tuple(SOURCE_SHA256))
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.rom, args.source, args.source_id, args.output_root), sort_keys=True))


if __name__ == "__main__":
    main()
