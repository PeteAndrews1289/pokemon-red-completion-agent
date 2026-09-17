"""Capture one predeclared natural Celadon Gym Lass DEVELOPMENT decision.

This reads the historical validation checkpoint, walks the real cartridge to
the first trainer MAIN menu, and stops without choosing a battle action. It is
never fit material and is not an independent fresh-start gameplay lineage.
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
SOURCE_ID = "red-goal-v1-071-recover_control-validation-02"
SOURCE_SHA256 = "7d7e00345297d7cd1839eec413a75652a49c1fc40f756d98bc37d7125ee86829"
CAPTURE_ID = "celadon-lass-natural-development-071"
MAX_ACTIONS = 600
MAX_FRAMES = 180_000


def run(rom_path: Path, source_path: Path, output: Path) -> dict[str, object]:
    if output.exists():
        raise ValueError("natural development output must be new")
    if source_path.name != f"{SOURCE_ID}.state":
        raise ValueError("natural development source identity differs")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit natural development collector before capture")
    rom, source = rom_path.read_bytes(), source_path.read_bytes()
    if (
        hashlib.sha256(rom).hexdigest() != ROM_SHA256
        or hashlib.sha256(source).hexdigest() != SOURCE_SHA256
    ):
        raise ValueError("natural development Red inputs differ")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    report: dict[str, object] = {
        "schema": "pokemon.red.celadon-lass-natural-development-source.v1",
        "capture_id": CAPTURE_ID,
        "root_lineage_id": SOURCE_ID,
        "partition": "development",
        "source_state_sha256": SOURCE_SHA256,
        "source_commit": commit,
        "status": "started",
        "model_queries": 0,
        "model_updates": 0,
        "trainer_battle_actions": 0,
        "authority_promotions": 0,
    }
    (output / "outcome.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    try:
        with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
            emulator.load_state_bytes(source)
            reader = PokemonRedStateReader(emulator)
            actions = CountingExecutor(
                FrameSafeExecutor(emulator, DEFAULT_NEW_GAME_TIMING.controller_timing())
            )
            # This validation checkpoint retains a harmless movement latch.
            # A bounded neutral settle reaches the same Center tile without input.
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=8))
            raw = reader.read()
            if (
                raw.map_id != MapId.CELADON_POKECENTER
                or (raw.player_x, raw.player_y) != (3, 3)
                or raw.battle_state != 0
                or raw.party_count != 4
                or raw.event_flags is None
                or event_flag_is_set(raw.event_flags, int(EventFlag.BEAT_ERIKA))
                or event_flag_is_set(
                    raw.event_flags, int(EventFlag.BEAT_CELADON_GYM_TRAINER_0)
                )
                or not reader.read_input_readiness().ready
            ):
                raise ValueError("natural development source is not an untouched Gym approach")
            timing = DEFAULT_ERIKA_TIMING
            _move(actions, reader, emulator, CENTER_EXIT, timing, "Center exit")
            _move(actions, reader, emulator, CITY_TO_OUTER_TREE, timing, "outer tree")
            _cut(actions, reader, emulator, timing, "down", 0x2C, "outer Cut")
            _move(actions, reader, emulator, ("down",), timing, "outer crossing")
            _move(actions, reader, emulator, LOWER_CITY_TO_GYM, timing, "Gym door")
            _move(actions, reader, emulator, ("up",), timing, "Gym entry")
            _move(
                actions, reader, emulator, ("up",) * 6, timing,
                "Lass trigger", allow_trigger=True,
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
                raise ValueError("natural development capture missed first MAIN")
            if (
                raw.map_id != MapId.CELADON_GYM
                or raw.enemy_party_count is None
                or raw.enemy_party_count < 1
                or raw.enemy_party_position != 0
                or (raw.enemy_hp or 0) <= 0
                or emulator.pressed_buttons
                or actions.actions_executed > MAX_ACTIONS
                or emulator.frame_count > MAX_FRAMES
            ):
                raise ValueError("natural development trainer boundary differs")
            prepared = prepare_red_battle_scenario(
                PokemonRedObservationEncoder.from_state_reader(
                    reader,
                    include_battle_stats=True,
                    public_species_base_stats=RedPracticeCartridge(rom).public_base_stats,
                ),
                raw,
                allow_no_attack=True,
            )
            state = emulator.save_state_bytes()
            manifest = build_battle_scenario_capture_payload(
                capture_id=CAPTURE_ID,
                root_lineage_id=SOURCE_ID,
                partition=ScenarioPartition.DEVELOPMENT,
                state_bytes=state,
                source_state_sha256=SOURCE_SHA256,
                initial_observation_sha256=prepared.initial_observation_sha256,
                source_commit=commit,
                expected_map=int(MapId.CELADON_GYM),
                expected_battle_state=2,
                observation_schema=OBSERVATION_SCHEMA_V2,
            )
            report.update(
                status="captured",
                state_sha256=hashlib.sha256(state).hexdigest(),
                observation_sha256=prepared.initial_observation_sha256,
                actions_executed=actions.actions_executed,
                frames_executed=emulator.frame_count,
                opponent_party_count=raw.enemy_party_count,
            )
        (output / "source.state").write_bytes(state)
        (output / "source.state.json").write_bytes(manifest)
        opened = open_battle_scenario_capture(
            output / "source.state", output / "source.state.json"
        )
        if opened.manifest.partition is not ScenarioPartition.DEVELOPMENT:
            raise ValueError("natural development capture partition differs")
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__)
        raise
    finally:
        (output / "outcome.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.rom, args.source, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
