"""Capture an unplayed Cinnabar Gym quiz trainer before its first battle choice.

The authenticated historical checkpoint already has the Secret Key. This
collector uses only normal field controls to reach the first quiz's trainer;
it makes no battle choice and never updates a model.
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
from pokemon_red_completion.blaine import (
    BLAINE_GYM_BURGLAR_OPPONENT,
    GYM_ENTRY_ROUTE,
    GYM_GATE_EVENTS,
    GYM_QUIZ_ROUTES,
    GYM_TRAINER_EVENTS,
    QUIZ_ANSWERS,
    QUIZ_TEXT_PULSES,
    _bag,
    _face_and_interact,
    _move,
    _pulse,
    _return_from_mansion_to_cinnabar,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    ItemId,
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
SOURCE_ID = "red-goal-v1-079-explore-validation-01"
SOURCE_SHA256 = "8525760c64ec9da8e6e0ab891d98cb9f12b82aa1338ee95e43c4bcf652068eeb"
CAPTURE_ID = "cinnabar-quiz1-natural-development-079"
MAX_ACTIONS = 800
MAX_FRAMES = 240_000


def run(rom_path: Path, source_path: Path, output: Path) -> dict[str, object]:
    if output.exists():
        raise ValueError("Cinnabar development output must be new")
    if source_path.name != f"{SOURCE_ID}.state":
        raise ValueError("Cinnabar development source identity differs")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit Cinnabar development collector before capture")
    rom, source = rom_path.read_bytes(), source_path.read_bytes()
    if (
        hashlib.sha256(rom).hexdigest() != ROM_SHA256
        or hashlib.sha256(source).hexdigest() != SOURCE_SHA256
    ):
        raise ValueError("Cinnabar development Red inputs differ")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    report: dict[str, object] = {
        "schema": "pokemon.red.cinnabar-burglar-natural-development-source.v1",
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
                raw.map_id != MapId.POKEMON_MANSION_1F
                or (raw.player_x, raw.player_y) != (5, 26)
                or raw.battle_state != 0
                or raw.party_count != 4
                or raw.event_flags is None
                or _bag(emulator).get(ItemId.SECRET_KEY) != 1
                or any(
                    event_flag_is_set(raw.event_flags, int(event))
                    for event in GYM_TRAINER_EVENTS + GYM_GATE_EVENTS
                )
                or not reader.read_input_readiness().ready
            ):
                raise ValueError("Cinnabar validation source is not an unplayed Gym approach")
            actions = CountingExecutor(
                FrameSafeExecutor(emulator, DEFAULT_NEW_GAME_TIMING.controller_timing())
            )
            _return_from_mansion_to_cinnabar(actions, reader, emulator)
            _move(actions, reader, ("up",) * 5, "Cinnabar Center nurse")
            if reader.read().map_id != MapId.CINNABAR_POKECENTER or (
                reader.read().player_x,
                reader.read().player_y,
            ) != (3, 3):
                raise ValueError("Cinnabar development missed Center anchor")
            _move(actions, reader, ("down",) * 5 + GYM_ENTRY_ROUTE, "Cinnabar Gym entry")
            if reader.read().map_id != MapId.CINNABAR_GYM or (
                reader.read().player_x,
                reader.read().player_y,
            ) != (16, 17):
                raise ValueError("Cinnabar development missed Gym entrance")
            _move(actions, reader, GYM_QUIZ_ROUTES[0], "first Cinnabar quiz")
            _face_and_interact(actions, "up")
            for _ in range(QUIZ_TEXT_PULSES[0] - 1):
                _pulse(actions, MacroActionKind.CONFIRM)
            if not QUIZ_ANSWERS[0]:
                _pulse(actions, MacroActionKind.MOVE, "down", 120)
            _pulse(actions, MacroActionKind.CONFIRM)
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
                raise ValueError("Cinnabar natural trainer capture missed first MAIN")
            identity = (
                emulator.read_u8(RamAddress.CURRENT_OPPONENT),
                emulator.read_u8(RamAddress.TRAINER_CLASS),
                emulator.read_u8(RamAddress.TRAINER_NUMBER),
            )
            report["observed_boundary"] = {
                "map": int(raw.map_id),
                "opponent_identity": list(identity),
                "engaged_fields": [
                    emulator.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
                    emulator.read_u8(RamAddress.ENGAGED_TRAINER_SET),
                ],
                "opponent_party_count": raw.enemy_party_count,
                "opponent_party_position": raw.enemy_party_position,
                "opponent_hp": raw.enemy_hp,
                "opponent_species": raw.enemy_species_id,
                "opponent_level": raw.enemy_level,
                "actions_executed": actions.actions_executed,
                "frames_executed": emulator.frame_count,
                "pressed_buttons": sorted(emulator.pressed_buttons),
            }
            if (
                raw.map_id != MapId.CINNABAR_GYM
                or identity != (BLAINE_GYM_BURGLAR_OPPONENT, 0x0B, 4)
                or raw.enemy_party_count != 3
                or raw.enemy_party_position != 0
                or (raw.enemy_hp or 0) <= 0
                or emulator.pressed_buttons
                or actions.actions_executed > MAX_ACTIONS
                or emulator.frame_count > MAX_FRAMES
            ):
                raise ValueError("Cinnabar natural trainer boundary differs")
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
                expected_map=int(MapId.CINNABAR_GYM),
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
            raise ValueError("Cinnabar natural development partition differs")
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
