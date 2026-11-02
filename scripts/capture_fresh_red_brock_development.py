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

import red_natural_six_preparation as six
import run_fresh_red_trainer_curriculum as common
from run_red_six_party_assisted_pilot import (
    INVENTORY_SHA256,
    binding,
    inventory_ancestry,
    prior_sources,
    write_new,
)

from pokemon_red_completion import cerulean as field
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.cerulean import run_cerulean_chapter
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    ControllerActionLimiter,
    CountingExecutor,
    FrameBudgetController,
    FrameSafeExecutor,
    MonotonicWallTimeBudgetController,
)
from pokemon_red_completion.observation import (
    MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER,
    ROCKET_OPPONENT_ID,
    ROCKET_TRAINER_CLASS_ID,
    BattleMenuPhase,
    MapId,
    PokemonRedStateReader,
)
from pokemon_red_completion.opening import run_opening_chapter
from pokemon_red_completion.pewter import run_pewter_chapter
from pokemon_red_completion.play import is_rival_victory_verified, run_oaks_errand_chapter
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld

ROOT = Path(__file__).resolve().parents[1]
BOOT_FRAMES = (2500, 2700)
MAX_FRAMES = 600000
TEAM_BOOT_FRAMES = (2900, 3100)
TEAM_MAX_FRAMES = 1000000


class BoundaryReached(Exception):
    """Intentional stop before the existing chapter can choose Brock attacks."""


def check_independence(reports):
    for key in ("origin_state_sha256", "first_party_ot_id", "root_lineage_id"):
        if len({r[key] for r in reports}) != len(reports):
            raise ValueError("natural sources do not establish distinct boot origins")


def check_new_six_origin(report, inventory, priors):
    used_hashes, used_roots = inventory_ancestry(inventory)
    for row in priors:
        used_hashes.update((row["origin_state_sha256"], row["battle_state_sha256"]))
        used_roots.add(row["root_lineage_id"])
    if (report["boot_frames"] not in six.BOOTS
            or report["root_lineage_id"] in used_roots
            or report["origin_state_sha256"] in used_hashes
            or report["battle_state_sha256"] in used_hashes
            or report["first_party_ot_id"] in {r["first_party_ot_id"] for r in priors}):
        raise ValueError("six-member source reused prior physical ancestry")


def run(args):
    six_party = getattr(args, "six_party", False)
    team = getattr(args, "team", False) or six_party
    boots = six.BOOTS if six_party else TEAM_BOOT_FRAMES if team else BOOT_FRAMES
    maximum_frames = TEAM_MAX_FRAMES if team else MAX_FRAMES
    boundary = "required_rocket" if team else "brock_battle"
    expected_map = MapId.MT_MOON_B2F if team else MapId.PEWTER_GYM
    if (
        args.output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("natural preparation needs committed source and new output")
    if common._binding(args.rom)["sha256"] != common.ROM_SHA256:
        raise ValueError("natural preparation ROM differs")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    inventory, priors, world = {}, [], None
    if six_party:
        if binding(args.inventory)["sha256"] != INVENTORY_SHA256:
            raise ValueError("six-member preparation inventory differs")
        inventory = json.loads(args.inventory.read_bytes())
        priors = prior_sources(inventory)
        for boot in (3300, 3500):
            path = args.assisted / f"source-{boot}" / "outcome.json"
            row = json.loads(path.read_bytes())
            if (row["boot_frames"] != boot
                    or binding(path.parent / "origin.state")["sha256"] != row["origin_state_sha256"]
                    or binding(path.parent / "source.state")["sha256"]
                    != row["battle_state_sha256"]):
                raise ValueError("latest assisted source exclusion differs")
            priors.append(row)
        write_new(args.inventory.parent / "natural-six-3700-3900-claim.json", {
            "boot_frames": list(boots), "source_commit": commit, "output": str(args.output),
            "inventory": binding(args.inventory), "prior_sources": priors,
            "max_frames": maximum_frames, "max_actions": 30000, "max_wall_seconds": 600,
            "no_retry_or_substitution": True, "memory_writes": 0, "fits": 0,
        })
        world = StrategicScenarioRouteWorld.from_rom(args.rom.read_bytes())
    args.output.mkdir(mode=0o700)
    common._write(
        args.output / "plan.json",
        {
            "source_commit": commit,
            "boot_frames": list(boots),
            "max_frames_per_start": maximum_frames,
            "partition": "development",
            "boundary": boundary + " before first battle decision",
            "preparation": "existing chapters; team mode includes item sales and Zubat capture",
            "memory_writes": 0,
            "model_queries": 0,
            "source_loads": 0,
            "setup_failure": "stop with failure snapshot; no route-specific repair or substitution",
            "natural_full_party_qualification": False,
            "six_party": six_party,
            "source_exclusions": priors if six_party else [],
            "six_party_preparation": {
                "maximum_steps": six.MAX_STEPS, "maximum_encounters": six.MAX_ENCOUNTERS,
                "first_encounters_any_species": True, "ordinary_slot_swap": [1, 6],
                "new_purchases": 0, "extra_training": 0, "state_edits": 0,
                "max_controller_actions": 30000, "max_wall_seconds": 600,
                "stop_on_setup_failure": True,
            } if six_party else None,
            "full_game_runs": 0,
        },
    )
    stats = RedPracticeCartridge(args.rom.read_bytes()).public_base_stats
    reports = []
    for boot_frames in boots:
        mode = "six" if six_party else "team" if team else "brock"
        source_id = f"fresh-red-{mode}-development-boot{boot_frames}"
        directory = args.output / source_id
        directory.mkdir(mode=0o700)
        with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
            session = FrameBudgetController(emulator, maximum_frames=maximum_frames)
            if six_party:
                session = MonotonicWallTimeBudgetController(session, maximum_wall_seconds=600)
            reader = PokemonRedStateReader(session)
            base_actions = FrameSafeExecutor(session, DEFAULT_NEW_GAME_TIMING.controller_timing())
            limited = ControllerActionLimiter(base_actions, maximum_actions=30000)
            actions = CountingExecutor(limited if six_party else base_actions)
            checkpoints = []
            preparation = {}

            def prepare_six(directory=directory, session=session, actions=actions,
                            reader=reader, boot_frames=boot_frames):
                nonlocal preparation
                (directory / "preparation-start.state").write_bytes(session.save_state_bytes())
                def record(row):
                    write_new(directory / f"capture-{row['encounter']:02d}.json", row)
                    print(json.dumps({"boot_frames": boot_frames, **row}), flush=True)
                preparation = six.fill_party(session, actions, reader, world, record)
                write_new(directory / "party-preparation.json", preparation)
                raise BoundaryReached

            def progress(
                event, checkpoints=checkpoints, directory=directory, boot_frames=boot_frames
            ):
                checkpoints.append(
                    {"checkpoint": event.checkpoint_id, "frames": event.frames_executed}
                )
                common._write(directory / "progress.json", {"checkpoints": checkpoints})
                print(json.dumps({"boot_frames": boot_frames, **checkpoints[-1]}), flush=True)
                if event.checkpoint_id == boundary:
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
                    pewter = run_pewter_chapter(
                        session,
                        reader,
                        actions,
                        progress=progress,
                        lab_rival_loss_recovery_required=not is_rival_victory_verified(
                            errand.rival_evidence, saw_trainer_battle=errand.saw_trainer_battle
                        ),
                    )
                    if team:
                        if not pewter.passed:
                            raise ValueError("natural team preparation did not verify Brock")
                        common._write(directory / "pewter.json", pewter.public_dict())
                        run_cerulean_chapter(
                            session, reader, actions, progress=progress,
                            before_required_rocket=prepare_six if six_party else None,
                        )
                except BoundaryReached:
                    pass
                else:
                    raise ValueError("natural preparation missed pre-battle stop")
                if six_party:
                    if not preparation:
                        raise ValueError("natural six preparation boundary not executed")
                    field._move(actions, reader, field.ROCKET_TRIGGER_DIRECTIONS,
                                "natural six Rocket engagement", allow_trainer_trigger=True)
                    field._wait(actions, field.DEFAULT_CERULEAN_TIMING.transition_wait_frames)
                    field._enter_trainer_battle(actions, reader, field.DEFAULT_CERULEAN_TIMING,
                                               expected_map, "natural six Rocket")
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
                if six_party:
                    encounter = reader.read_cerulean_chapter_state(raw)
                    if (encounter.trainer_class != ROCKET_TRAINER_CLASS_ID
                            or encounter.trainer_number != MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER
                            or encounter.engaged_trainer_class != ROCKET_OPPONENT_ID
                            or encounter.engaged_trainer_set
                            != MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER
                            or encounter.beat_required_rocket):
                        raise ValueError("natural six source has wrong or consumed trainer")
                if (
                    raw.map_id != expected_map
                    or raw.enemy_party_count != 2
                    or raw.enemy_party_position != 0
                    or raw.party_count != (6 if six_party else 2 if team else 1)
                    or (team and (raw.party_hp is None or any(hp <= 0 for hp in raw.party_hp)))
                    or session.pressed_buttons
                    or (raw.enemy_hp or 0) <= 0
                ):
                    raise ValueError("natural trainer boundary differs")
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
                    expected_map=int(expected_map),
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
                    "party_hp": raw.party_hp,
                    "model_queries": 0,
                    "memory_writes": 0,
                    "full_game_runs": 0,
                    "authority_promotions": 0,
                    "preparation": preparation,
                    "cash": raw.player_money,
                }
                check_independence(reports + [report])
                if six_party:
                    check_new_six_origin(report, inventory, priors + reports)
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
    parser.add_argument("--six-party", action="store_true")
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--assisted", type=Path)
    parser.add_argument(
        "--team", action="store_true", help="Use the declared fresh natural team sources"
    )
    run(parser.parse_args())
