"""Capture a fresh Lorelei battle from an authenticated pre-League checkpoint.

The field approach is ordinary controller play. Stop before the first battle
choice; no model is queried, no memory is edited and no opponent is fought.
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
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor
from pokemon_red_completion.lorelei import (
    INDIGO_TO_LORELEI,
    LORELEI_APPROACH,
    LORELEI_PARTY,
    _move,
    _pulse,
)
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    EventFlag,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    event_flag_is_set,
)
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
SOURCE_ID = "red-goal-v1-066-recover_control-train-03"
SOURCE_SHA256 = "e13c75dbb292b01dd670c70229cc328ef6c151c1dce45a7e8998b4ddc3589a50"
CAPTURE_ID = "lorelei-natural-development-066"
MAX_ACTIONS = 600
MAX_FRAMES = 180_000


def run(rom_path: Path, source_path: Path, output: Path) -> dict[str, object]:
    if output.exists():
        raise ValueError("Lorelei development output must be new")
    if source_path.name != f"{SOURCE_ID}.state":
        raise ValueError("Lorelei development source identity differs")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit Lorelei development collector before capture")
    rom, source = rom_path.read_bytes(), source_path.read_bytes()
    if (
        hashlib.sha256(rom).hexdigest() != ROM_SHA256
        or hashlib.sha256(source).hexdigest() != SOURCE_SHA256
    ):
        raise ValueError("Lorelei development Red inputs differ")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    report: dict[str, object] = {
        "schema": "pokemon.red.lorelei-natural-development-source.v1",
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
            raw = reader.read()
            if (
                raw.map_id != MapId.INDIGO_PLATEAU_LOBBY
                or (raw.player_x, raw.player_y) != (2, 5)
                or raw.battle_state != 0
                or raw.party_count != 6
                or raw.event_flags is None
                or event_flag_is_set(raw.event_flags, int(EventFlag.BEAT_LORELEI))
            ):
                raise ValueError("Indigo validation source is not an unplayed Lorelei approach")
            actions = CountingExecutor(
                FrameSafeExecutor(emulator, DEFAULT_NEW_GAME_TIMING.controller_timing())
            )
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
            if not reader.read_input_readiness().ready:
                raise ValueError("Indigo checkpoint did not settle to field input")
            _move(actions, reader, INDIGO_TO_LORELEI, "Lorelei room entry")
            entered = reader.read()
            if entered.map_id != MapId.LORELEIS_ROOM or (
                entered.player_x,
                entered.player_y,
            ) != (4, 5):
                raise ValueError("Lorelei development missed room entry")
            _move(actions, reader, LORELEI_APPROACH, "Lorelei approach")
            _pulse(actions, MacroActionKind.INTERACT)
            for _ in range(60):
                raw = reader.read()
                if (
                    raw.battle_state == 2
                    and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
                ):
                    break
                actions.execute(MacroAction(MacroActionKind.CONFIRM))
                actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
            else:
                raise ValueError("Lorelei natural trainer capture missed first MAIN")
            identity = (
                emulator.read_u8(RamAddress.CURRENT_OPPONENT),
                emulator.read_u8(RamAddress.TRAINER_CLASS),
                emulator.read_u8(RamAddress.TRAINER_NUMBER),
            )
            report["observed_boundary"] = {
                "map": int(raw.map_id),
                "opponent_identity": list(identity),
                "opponent_party_count": raw.enemy_party_count,
                "opponent_party_position": raw.enemy_party_position,
                "opponent_species": raw.enemy_species_id,
                "opponent_level": raw.enemy_level,
                "opponent_hp": raw.enemy_hp,
                "actions_executed": actions.actions_executed,
                "frames_executed": emulator.frame_count,
                "pressed_buttons": sorted(emulator.pressed_buttons),
            }
            if (
                raw.map_id != MapId.LORELEIS_ROOM
                or raw.enemy_party_count != len(LORELEI_PARTY)
                or raw.enemy_party_position != 0
                or (raw.enemy_species_id, raw.enemy_level) != LORELEI_PARTY[0]
                or (raw.enemy_hp or 0) <= 0
                or emulator.pressed_buttons
                or actions.actions_executed > MAX_ACTIONS
                or emulator.frame_count > MAX_FRAMES
            ):
                raise ValueError("Lorelei natural trainer boundary differs")
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
                expected_map=int(MapId.LORELEIS_ROOM),
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
                opponent_identity=list(identity),
            )
        (output / "source.state").write_bytes(state)
        (output / "source.state.json").write_bytes(manifest)
        opened = open_battle_scenario_capture(output / "source.state", output / "source.state.json")
        if opened.manifest.partition is not ScenarioPartition.DEVELOPMENT:
            raise ValueError("Lorelei natural development partition differs")
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
