"""Two authorized independent natural starts; stop before Brock decisions.

Preparation uses existing ordinary-gameplay chapters only. No state loading,
memory edits, actor fitting, battle testing, route repair, or full-game run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import run_fresh_red_trainer_curriculum as common

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
)
from pokemon_red_completion.observation import BattleMenuPhase, MapId, PokemonRedStateReader
from pokemon_red_completion.opening import run_opening_chapter
from pokemon_red_completion.pewter import run_pewter_chapter
from pokemon_red_completion.play import is_rival_victory_verified, run_oaks_errand_chapter
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
BOOT_FRAMES = (2500, 2700)
MAX_FRAMES = 600000


class BoundaryReached(Exception):
    """Intentional stop before the existing chapter can choose Brock attacks."""


def check_independence(reports):
    for field in ("origin_state_sha256", "first_party_ot_id", "root_lineage_id"):
        if len({r[field] for r in reports}) != len(reports):
            raise ValueError("natural sources do not establish distinct boot origins")


def run(args):
    if (
        args.output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("natural preparation needs committed source and new output")
    if common._binding(args.rom)["sha256"] != common.ROM_SHA256:
        raise ValueError("natural preparation ROM differs")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    common._write(
        args.output / "plan.json",
        {
            "source_commit": commit,
            "boot_frames": list(BOOT_FRAMES),
            "max_frames_per_start": MAX_FRAMES,
            "partition": "development",
            "boundary": "Brock before first battle decision",
            "memory_writes": 0,
            "model_queries": 0,
            "source_loads": 0,
            "setup_failure": "stop with failure snapshot; no route-specific repair or substitution",
            "natural_full_party_qualification": False,
            "full_game_runs": 0,
        },
    )
    stats = RedPracticeCartridge(args.rom.read_bytes()).public_base_stats
    reports = []
    for boot_frames in BOOT_FRAMES:
        source_id = f"fresh-red-brock-development-boot{boot_frames}"
        directory = args.output / source_id
        directory.mkdir(mode=0o700)
        with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
            session = FrameBudgetController(emulator, maximum_frames=MAX_FRAMES)
            reader = PokemonRedStateReader(session)
            actions = CountingExecutor(
                FrameSafeExecutor(session, DEFAULT_NEW_GAME_TIMING.controller_timing())
            )
            checkpoints = []

            def progress(event, checkpoints=checkpoints, directory=directory, boot_frames=boot_frames):
                checkpoints.append(
                    {"checkpoint": event.checkpoint_id, "frames": event.frames_executed}
                )
                common._write(directory / "progress.json", {"checkpoints": checkpoints})
                print(json.dumps({"boot_frames": boot_frames, **checkpoints[-1]}), flush=True)
                if event.checkpoint_id == "brock_battle":
                    raise BoundaryReached

            try:
                opening = run_opening_chapter(
                    args.rom,
                    _emulator=session,
                    _executor=actions,
                    new_game_timing=replace(DEFAULT_NEW_GAME_TIMING, boot_frames=boot_frames),
                    progress=progress,
                )
                if not opening.passed:
                    raise ValueError("natural start did not reach verified starter")
                origin = session.save_state_bytes()
                (directory / "origin.state").write_bytes(origin)
                trainer_id = reader.read_party_original_trainer_ids()[0]
                errand = run_oaks_errand_chapter(session, reader, actions, progress=progress)
                if not errand.passed:
                    raise ValueError("natural start did not verify errand")
                common._write(directory / "errand.json", errand.public_dict())
                try:
                    run_pewter_chapter(
                        session,
                        reader,
                        actions,
                        progress=progress,
                        lab_rival_loss_recovery_required=not is_rival_victory_verified(
                            errand.rival_evidence, saw_trainer_battle=errand.saw_trainer_battle
                        ),
                    )
                except BoundaryReached:
                    pass
                else:
                    raise ValueError("natural preparation missed pre-battle stop")
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
                    raise ValueError("natural source did not reach MAIN")
                if (
                    raw.map_id != MapId.PEWTER_GYM
                    or raw.enemy_party_count != 2
                    or raw.enemy_party_position != 0
                    or raw.party_count != 1
                    or session.pressed_buttons
                    or (raw.enemy_hp or 0) <= 0
                ):
                    raise ValueError("natural Brock boundary differs")
                prepared = prepare_red_battle_scenario(
                    PokemonRedObservationEncoder.from_state_reader(
                        reader, include_battle_stats=True, public_species_base_stats=stats
                    ),
                    raw,
                    allow_no_attack=True,
                )
                state = session.save_state_bytes()
                origin_sha = hashlib.sha256(origin).hexdigest()
                manifest = build_battle_scenario_capture_payload(
                    capture_id=source_id,
                    root_lineage_id=source_id,
                    partition=ScenarioPartition.DEVELOPMENT,
                    state_bytes=state,
                    source_state_sha256=origin_sha,
                    initial_observation_sha256=prepared.initial_observation_sha256,
                    source_commit=commit,
                    expected_map=int(MapId.PEWTER_GYM),
                    expected_battle_state=2,
                    observation_schema=OBSERVATION_SCHEMA_V2,
                )
                (directory / "source.state").write_bytes(state)
                (directory / "source.state.json").write_bytes(manifest)
                opened = open_battle_scenario_capture(
                    directory / "source.state", directory / "source.state.json"
                )
                report = {
                    "root_lineage_id": source_id,
                    "partition": "development",
                    "fresh_power_on": True,
                    "boot_frames": boot_frames,
                    "first_party_ot_id": trainer_id,
                    "origin_state_sha256": origin_sha,
                    "capture_manifest_sha256": opened.manifest_sha256,
                    "battle_state_sha256": opened.manifest.state_sha256,
                    "source_commit": commit,
                    "frames": session.frame_count,
                    "actions": actions.actions_executed,
                    "party_count": raw.party_count,
                    "party_levels": raw.party_levels,
                    "party_moves": raw.party_moves,
                    "model_queries": 0,
                    "memory_writes": 0,
                    "full_game_runs": 0,
                    "authority_promotions": 0,
                }
                check_independence(reports + [report])
                common._write(directory / "outcome.json", report)
                reports.append(report)
            except Exception as error:
                (directory / "failure.state").write_bytes(session.save_state_bytes())
                common._write(
                    args.output / "failure.json",
                    {
                        "completed_sources": len(reports),
                        "failed_boot_frames": boot_frames,
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "frames": session.frame_count,
                        "actions": actions.actions_executed,
                        "route_repairs": 0,
                        "model_queries": 0,
                    },
                )
                raise
    result = {
        "status": "captured",
        "sources": reports,
        "independent_boot_origins": len(reports),
        "natural_battles_tested": 0,
        "full_party_switching_qualified": False,
        "authority_promotions": 0,
    }
    common._write(args.output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
