"""Capture four separate clean-power Red lab-rival TRAIN sources.

The schedule is fixed in source. Every member boots a new emulator, completes
the opening independently and stops before its first battle decision. This is
training supply, not a model episode or a natural evaluation battle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameBudgetController,
    FrameSafeExecutor,
    MonotonicWallTimeBudgetController,
)
from pokemon_red_completion.observation import BattleMenuPhase, MapId, PokemonRedStateReader
from pokemon_red_completion.opening import run_opening_chapter
from pokemon_red_completion.play import (
    DEFAULT_QUALIFIED_PLAY_TIMING,
    LAB_RIVAL_TRIGGER_DIRECTIONS,
    _move,
)
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
# 1931 was an unretained feasibility pilot and is deliberately not reused.
BOOT_FRAMES = (2000, 2100, 2200, 2300)
MAX_TOTAL_FRAMES = 50_000
MAX_POST_OPENING_ACTIONS = 120
_PARTY_FIRST_OT_ID = 0xD177


@contextmanager
def _source_session(rom_path: Path, failure_output: Path | None):
    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        if failure_output is None:
            yield emulator
            return
        session = MonotonicWallTimeBudgetController(
            FrameBudgetController(emulator, maximum_frames=MAX_TOTAL_FRAMES),
            maximum_wall_seconds=180,
        )
        try:
            yield session
        except Exception as error:
            # Preserve the actual failed setup; never replay or replace it.
            diagnostic = {
                "error_type": type(error).__name__, "error": str(error),
                "frames": emulator.frame_count,
                "wall_elapsed_seconds": session.elapsed_seconds,
                "pressed_buttons": sorted(emulator.pressed_buttons),
            }
            try:
                payload = emulator.save_state_bytes()
                with (failure_output / "failed-source.state").open("xb") as stream:
                    stream.write(payload)
                diagnostic["state_sha256"] = hashlib.sha256(payload).hexdigest()
            except Exception as retention_error:
                diagnostic["retention_error"] = str(retention_error)
            with (failure_output / "source-failure.json").open("x") as stream:
                json.dump(diagnostic, stream, indent=2, sort_keys=True)
            raise


def _capture_one(
    rom_path: Path, rom: bytes, boot_frames: int, commit: str,
    *, partition: ScenarioPartition = ScenarioPartition.TRAIN,
    failure_output: Path | None = None,
):
    if partition not in {ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT}:
        raise ValueError("fresh source partition differs")
    if partition is ScenarioPartition.DEVELOPMENT and failure_output is None:
        raise ValueError("development source requires bounded retained setup")
    source_id = f"fresh-red-lab-rival-{partition.value}-boot{boot_frames}"
    with _source_session(rom_path, failure_output) as emulator:
        opening = run_opening_chapter(
            rom_path,
            _emulator=emulator,
            new_game_timing=replace(DEFAULT_NEW_GAME_TIMING, boot_frames=boot_frames),
        )
        if not opening.passed:
            raise ValueError("fresh trainer source missed its verified opening")
        origin = emulator.save_state_bytes()
        origin_sha256 = hashlib.sha256(origin).hexdigest()
        reader = PokemonRedStateReader(emulator)
        memory = emulator._require_backend().memory
        trainer_id = (int(memory[_PARTY_FIRST_OT_ID]) << 8) | int(
            memory[_PARTY_FIRST_OT_ID + 1]
        )
        actions = CountingExecutor(
            FrameSafeExecutor(emulator, DEFAULT_NEW_GAME_TIMING.controller_timing())
        )
        _move(actions, reader, LAB_RIVAL_TRIGGER_DIRECTIONS, "fresh trainer source")
        actions.execute(MacroAction(
            MacroActionKind.WAIT,
            repeat=DEFAULT_QUALIFIED_PLAY_TIMING.rival_trigger_wait_frames,
        ))
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
            raise ValueError("fresh trainer source missed first MAIN decision")
        if (
            raw.map_id != MapId.OAKS_LAB
            or raw.party_count != 1
            or raw.enemy_party_count != 1
            or raw.enemy_party_position != 0
            or (raw.enemy_hp or 0) <= 0
            or emulator.pressed_buttons
            or actions.actions_executed > MAX_POST_OPENING_ACTIONS
            or emulator.frame_count > MAX_TOTAL_FRAMES
        ):
            raise ValueError("fresh trainer source boundary or budget differs")
        cartridge = RedPracticeCartridge(rom)
        prepared = prepare_red_battle_scenario(
            PokemonRedObservationEncoder.from_state_reader(
                reader,
                include_battle_stats=True,
                public_species_base_stats=cartridge.public_base_stats,
            ),
            raw,
            allow_no_attack=True,
        )
        state = emulator.save_state_bytes()
        manifest = build_battle_scenario_capture_payload(
            capture_id=source_id,
            root_lineage_id=source_id,
            partition=partition,
            state_bytes=state,
            source_state_sha256=origin_sha256,
            initial_observation_sha256=prepared.initial_observation_sha256,
            source_commit=commit,
            expected_map=int(MapId.OAKS_LAB),
            expected_battle_state=2,
            observation_schema=OBSERVATION_SCHEMA_V2,
        )
        report = {
            "schema": f"pokemon.red.fresh-trainer-{partition.value}-source.v1",
            "source_id": source_id,
            "root_lineage_id": source_id,
            "partition": partition.value,
            "fresh_power_on": True,
            "boot_frames": boot_frames,
            "origin_state_sha256": origin_sha256,
            "battle_state_sha256": hashlib.sha256(state).hexdigest(),
            "observation_sha256": prepared.initial_observation_sha256,
            "source_commit": commit,
            "first_party_ot_id": trainer_id,
            "opening_frames": opening.frames_executed,
            "total_frames": emulator.frame_count,
            "post_opening_actions": actions.actions_executed,
            "model_queries": 0,
            "model_updates": 0,
            "full_game_runs": 0,
        }
        return origin, state, manifest, report


def run(rom_path: Path, output_root: Path) -> dict[str, object]:
    if output_root.exists():
        raise ValueError("fresh trainer batch output must be new")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit trainer source code before the fixed batch")
    rom = rom_path.read_bytes()
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError("fresh trainer source ROM differs")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    output_root.mkdir(parents=True, mode=0o700, exist_ok=False)
    reports: list[dict[str, object]] = []
    try:
        for boot_frames in BOOT_FRAMES:
            origin, state, manifest, report = _capture_one(
                rom_path, rom, boot_frames, commit
            )
            if report["first_party_ot_id"] in {
                prior["first_party_ot_id"] for prior in reports
            }:
                raise ValueError("fresh trainer batch repeated a player trainer identity")
            output = output_root / str(report["source_id"])
            output.mkdir(mode=0o700, exist_ok=False)
            (output / "origin.state").write_bytes(origin)
            (output / "source.state").write_bytes(state)
            (output / "source.state.json").write_bytes(manifest)
            opened = open_battle_scenario_capture(
                output / "source.state", output / "source.state.json"
            )
            if opened.manifest.source_state_sha256 != report["origin_state_sha256"]:
                raise ValueError("fresh trainer origin chain differs")
            (output / "outcome.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n"
            )
            reports.append(report)
    except Exception as error:
        (output_root / "failure.json").write_text(json.dumps({
            "schema": "pokemon.red.fresh-trainer-train-batch-failure.v1",
            "completed_sources": len(reports),
            "failed_boot_frames": BOOT_FRAMES[len(reports)],
            "error_type": type(error).__name__,
        }, indent=2, sort_keys=True) + "\n")
        raise
    summary: dict[str, object] = {
        "schema": "pokemon.red.fresh-trainer-train-batch.v1",
        "status": "captured",
        "source_commit": commit,
        "boot_frames": list(BOOT_FRAMES),
        "fresh_power_on_sources": len(reports),
        "distinct_origin_state_hashes": len({r["origin_state_sha256"] for r in reports}),
        "distinct_player_trainer_ids": len({r["first_party_ot_id"] for r in reports}),
        "source_ids": [r["source_id"] for r in reports],
        "model_queries": 0,
        "model_updates": 0,
        "authority_promotions": 0,
        "full_game_runs": 0,
    }
    (output_root / "batch-outcome.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.rom, args.output_root), sort_keys=True))


if __name__ == "__main__":
    main()
