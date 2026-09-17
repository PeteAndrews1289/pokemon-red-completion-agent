"""Capture the predeclared Bruno, Agatha and Lance DEVELOPMENT battles.

Each source is an authenticated historical progression checkpoint. All share
one unresolved ancestral Red run. Only legal field controls lead to the first
battle menu; no battle choice, teacher action or model query is made here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.agatha import AGATHA_APPROACH, AGATHA_PARTY
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.bruno import BRUNO_APPROACH, BRUNO_PARTY
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor
from pokemon_red_completion.lance import LANCE_APPROACH, LANCE_PARTY
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
from pokemon_red_completion.victory_road import _move, _pulse, _settle_confirm

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
LINEAGE_ID = "red-goal-root-portable-loop-legacy"
MAX_ACTIONS = 600
MAX_FRAMES = 180_000
SOURCES = {
    "bruno": {
        "file": "portable-loop-post-lorelei.state",
        "sha256": "cbc7a2d68593e4a3b113793ec918fc51868e804d3c8d120586c91971d643660f",
        "map": MapId.BRUNOS_ROOM,
        "position": (4, 5),
        "required_event": EventFlag.BEAT_LORELEI,
        "unplayed_event": EventFlag.BEAT_BRUNO,
        "route": BRUNO_APPROACH,
        "party": BRUNO_PARTY,
        "trigger": "interact",
    },
    "agatha": {
        "file": "portable-loop-post-bruno.state",
        "sha256": "d95052c4b016a1487cba5620a6f883c4e96b618246f62c8555dc4b4715d0aac4",
        "map": MapId.AGATHAS_ROOM,
        "position": (4, 5),
        "required_event": EventFlag.BEAT_BRUNO,
        "unplayed_event": EventFlag.BEAT_AGATHA,
        "route": AGATHA_APPROACH,
        "party": AGATHA_PARTY,
        "trigger": "interact",
    },
    "lance": {
        "file": "portable-loop-post-agatha.state",
        "sha256": "57817362e4b020cbbe7cc85d282d8079139ae0f974126e24f342e699a95a2a02",
        "map": MapId.LANCES_ROOM,
        "position": (18, 23),
        "required_event": EventFlag.BEAT_AGATHA,
        "unplayed_event": EventFlag.BEAT_LANCE,
        "route": LANCE_APPROACH,
        "party": LANCE_PARTY,
        "trigger": "sight_line",
    },
}


def run(stage: str, rom_path: Path, source_path: Path, output: Path) -> dict[str, object]:
    spec = SOURCES[stage]
    if output.exists():
        raise ValueError("League development output must be new")
    if source_path.name != spec["file"]:
        raise ValueError("League development source identity differs")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit League development collector before capture")
    rom, source = rom_path.read_bytes(), source_path.read_bytes()
    if (
        hashlib.sha256(rom).hexdigest() != ROM_SHA256
        or hashlib.sha256(source).hexdigest() != spec["sha256"]
    ):
        raise ValueError("League development Red inputs differ")
    source_receipt = json.loads(source_path.with_suffix(source_path.suffix + ".json").read_bytes())
    if source_receipt.get("state_sha256") != spec["sha256"]:
        raise ValueError("League progression checkpoint receipt differs")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    capture_id = f"league-{stage}-natural-development-portable-loop"
    report: dict[str, object] = {
        "schema": "pokemon.red.league-natural-development-source.v1",
        "capture_id": capture_id,
        "root_lineage_id": LINEAGE_ID,
        "partition": "development",
        "stage": stage,
        "source_state_sha256": spec["sha256"],
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
                raw.map_id != spec["map"]
                or (raw.player_x, raw.player_y) != spec["position"]
                or raw.battle_state != 0
                or raw.party_count != 6
                or raw.event_flags is None
                or not event_flag_is_set(raw.event_flags, int(spec["required_event"]))
                or event_flag_is_set(raw.event_flags, int(spec["unplayed_event"]))
            ):
                raise ValueError("League checkpoint is not the declared trainer approach")
            actions = CountingExecutor(
                FrameSafeExecutor(emulator, DEFAULT_NEW_GAME_TIMING.controller_timing())
            )
            if stage == "lance":
                _settle_confirm(actions, reader, 200)
                if (reader.read().player_x, reader.read().player_y) != (6, 11):
                    raise ValueError("Lance entrance autowalk did not settle")
            else:
                actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
            if not reader.read_input_readiness().ready:
                raise ValueError("League checkpoint did not settle to field input")
            if spec["trigger"] == "interact":
                _move(actions, reader, spec["route"], f"{stage} approach")
                _pulse(actions, MacroActionKind.INTERACT)
            else:
                _move(actions, reader, spec["route"][:-1], f"{stage} approach")
                _pulse(actions, MacroActionKind.MOVE, spec["route"][-1], 240)
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
                raise ValueError("League natural trainer capture missed first MAIN")
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
                raw.map_id != spec["map"]
                or raw.enemy_party_count != len(spec["party"])
                or raw.enemy_party_position != 0
                or (raw.enemy_species_id, raw.enemy_level) != spec["party"][0]
                or (raw.enemy_hp or 0) <= 0
                or emulator.pressed_buttons
                or actions.actions_executed > MAX_ACTIONS
                or emulator.frame_count > MAX_FRAMES
            ):
                raise ValueError("League natural trainer boundary differs")
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
                capture_id=capture_id,
                root_lineage_id=LINEAGE_ID,
                partition=ScenarioPartition.DEVELOPMENT,
                state_bytes=state,
                source_state_sha256=spec["sha256"],
                initial_observation_sha256=prepared.initial_observation_sha256,
                source_commit=commit,
                expected_map=int(spec["map"]),
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
            raise ValueError("League natural development partition differs")
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__)
        raise
    finally:
        (output / "outcome.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=tuple(SOURCES))
    parser.add_argument("rom", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.stage, args.rom, args.source, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
