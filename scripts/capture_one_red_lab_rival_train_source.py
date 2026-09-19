"""Capture one bounded, fresh Red lab-rival TRAIN boundary for battle practice.

This stops before the first player attack. It does not run a story, collect a
model example, fit a model, or certify an independent evaluation root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_scenario_capture import (
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor
from pokemon_red_completion.observation import BattleMenuPhase, MapId, PokemonRedStateReader
from pokemon_red_completion.opening import run_opening_chapter
from pokemon_red_completion.play import (
    DEFAULT_QUALIFIED_PLAY_TIMING,
    LAB_RIVAL_TRIGGER_DIRECTIONS,
    _move,
)
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
SOURCE_ID = "red-lab-rival-train-20260917-offset137"
OFFSET_FRAMES = 137


def _validate_request(rom_path: Path, output: Path) -> bytes:
    if output.exists():
        raise ValueError("lab rival train source output must be new")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit the trainer source capture code before making a train artifact")
    rom = rom_path.read_bytes()
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError("lab rival source ROM differs from the pinned Red cartridge")
    return rom


def run(rom_path: Path, output: Path) -> dict[str, object]:
    _validate_request(rom_path, output)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        opening = run_opening_chapter(rom_path, _emulator=emulator)
        if not opening.passed:
            raise ValueError("lab rival train source missed the clean opening gate")
        reader = PokemonRedStateReader(emulator)
        actions = CountingExecutor(
            FrameSafeExecutor(emulator, DEFAULT_NEW_GAME_TIMING.controller_timing())
        )
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=OFFSET_FRAMES))
        _move(actions, reader, LAB_RIVAL_TRIGGER_DIRECTIONS, "train lab rival trigger")
        actions.execute(
            MacroAction(
                MacroActionKind.WAIT,
                repeat=DEFAULT_QUALIFIED_PLAY_TIMING.rival_trigger_wait_frames,
            )
        )
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
            raise ValueError("lab rival train source missed the first MAIN decision")
        if (
            raw.map_id != MapId.OAKS_LAB
            or raw.party_count != 1
            or raw.enemy_party_count != 1
            or raw.enemy_party_position != 0
            or (raw.enemy_hp or 0) <= 0
            or emulator.pressed_buttons
        ):
            raise ValueError("lab rival source roster or controller state differs")
        prepared = prepare_red_battle_scenario(
            PokemonRedObservationEncoder.from_state_reader(reader), raw
        )
        state = emulator.save_state_bytes()
        manifest = build_battle_scenario_capture_payload(
            capture_id=SOURCE_ID,
            root_lineage_id=SOURCE_ID,
            partition=ScenarioPartition.TRAIN,
            state_bytes=state,
            initial_observation_sha256=prepared.initial_observation_sha256,
            source_commit=commit,
            expected_map=int(MapId.OAKS_LAB),
            expected_battle_state=2,
        )
        report: dict[str, object] = {
            "schema": "pokemon.red.lab-rival-train-source.v1",
            "source_id": SOURCE_ID,
            "root_lineage_id": SOURCE_ID,
            "partition": "train",
            "source_commit": commit,
            "state_sha256": hashlib.sha256(state).hexdigest(),
            "observation_sha256": prepared.initial_observation_sha256,
            "opening_frames": opening.frames_executed,
            "total_frames": emulator.frame_count,
            "post_opening_actions": actions.actions_executed,
            "offset_frames": OFFSET_FRAMES,
            "opponent_party_count": raw.enemy_party_count,
            "model_queries": 0,
            "model_updates": 0,
            "authority_promotions": 0,
            "full_game_replays": 0,
        }
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (output / "source.state").write_bytes(state)
    (output / "source.state.json").write_bytes(manifest)
    capture = open_battle_scenario_capture(output / "source.state", output / "source.state.json")
    if capture.manifest.state_sha256 != report["state_sha256"]:
        raise ValueError("saved lab rival source failed exact capture authentication")
    (output / "outcome.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.rom, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
