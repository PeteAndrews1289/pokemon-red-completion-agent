"""Start only the declared, unstarted 3900 origin; stop at Mt. Moon entrance."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

from capture_fresh_red_brock_development import BoundaryReached, check_new_six_origin
from continue_red_natural_party import ROM_SHA, bound
from run_red_six_party_assisted_pilot import INVENTORY_SHA256, write_new
from run_red_trainer_earned_switch import completion_ledger
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.cerulean import run_cerulean_chapter
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    ControllerActionLimiter, CountingExecutor, FrameBudgetController, FrameSafeExecutor,
    MonotonicWallTimeBudgetController,
)
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.opening import run_opening_chapter
from pokemon_red_completion.pewter import run_pewter_chapter
from pokemon_red_completion.play import is_rival_victory_verified, run_oaks_errand_chapter

ROOT = Path(__file__).resolve().parents[1]
CLAIM_SHA = "302fd22447a0f7aa0389d670773f165b18a1e20f4be9b216a0231b67303b0c1d"
ROOT_ID = "fresh-red-six-development-boot3900"


def boundary(event):
    if event.checkpoint_id == "mt_moon_entered":
        raise BoundaryReached


def run(args):
    bound(args.rom, ROM_SHA)
    claim = json.loads(bound(args.claim, CLAIM_SHA))
    inventory = json.loads(bound(args.inventory, INVENTORY_SHA256))
    if args.output.exists() or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("remaining origin needs new output and committed source")
    if (Path(claim["output"]) / ROOT_ID).exists():
        raise ValueError("3900 was already started by the original preparer")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    plan = {"source_commit": revision, "root_lineage_id": ROOT_ID, "boot_frames": 3900,
        "parent_claim_sha256": CLAIM_SHA, "maximum_frames": 1000000, "maximum_macros": 30000,
        "maximum_seconds": 600, "model_queries": 0, "memory_writes": 0, "state_loads": 0,
        "legacy_teacher_tm34_sale": 1000, "stop_checkpoint": "mt_moon_entered"}
    write_new(args.claim.parent / "natural-3900-dispatch-claim.json", plan)
    args.output.mkdir(mode=0o700)
    write_new(args.output / "plan.json", plan)
    with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
        session = MonotonicWallTimeBudgetController(
            FrameBudgetController(emulator, maximum_frames=1000000), maximum_wall_seconds=600)
        limiter = ControllerActionLimiter(FrameSafeExecutor(session,
            DEFAULT_NEW_GAME_TIMING.controller_timing()), maximum_actions=30000)
        actions, reader = CountingExecutor(limiter), PokemonRedStateReader(session)
        checkpoints, error, origin_sha, ot = [], None, None, None
        def progress(event):
            row = {"checkpoint": event.checkpoint_id, "frames": event.frames_executed}
            checkpoints.append(row)
            write_new(args.output / f"progress-{len(checkpoints):03d}.json", row)
            print(json.dumps(row), flush=True)
            boundary(event)
        try:
            opening = run_opening_chapter(args.rom, _emulator=session, _executor=actions,
                new_game_timing=replace(DEFAULT_NEW_GAME_TIMING, boot_frames=3900), progress=progress)
            if not opening.passed:
                raise ValueError("starter verification failed")
            origin = session.save_state_bytes()
            with (args.output / "origin.state").open("xb") as stream:
                stream.write(origin)
            origin_sha = hashlib.sha256(origin).hexdigest()
            ot = reader.read_party_original_trainer_ids()[0]
            check_new_six_origin({"boot_frames": 3900, "root_lineage_id": ROOT_ID,
                "origin_state_sha256": origin_sha, "battle_state_sha256": origin_sha,
                "first_party_ot_id": ot}, inventory, claim["prior_sources"] + [{
                    "root_lineage_id": "fresh-red-six-development-boot3700",
                    "origin_state_sha256": "69c0a4cef85e2599da1285c65492dd22db402c8c3df9f70095f44563941eee20",
                    "battle_state_sha256": "a0af2a39b75bdbbe3ed775360c790ed4cdbde06437ca3b4f3ea050d727b7363d",
                    "first_party_ot_id": 31214}])
            errand = run_oaks_errand_chapter(session, reader, actions, progress=progress)
            if not errand.passed:
                raise ValueError("errand verification failed")
            pewter = run_pewter_chapter(session, reader, actions, progress=progress,
                lab_rival_loss_recovery_required=not is_rival_victory_verified(
                    errand.rival_evidence, saw_trainer_battle=errand.saw_trainer_battle))
            if not pewter.passed:
                raise ValueError("Brock verification failed")
            run_cerulean_chapter(session, reader, actions, progress=progress)
            raise ValueError("declared entrance stop was missed")
        except BoundaryReached:
            if reader.read().map_id != 59 or reader.read().battle_state:
                error = {"type": "ValueError", "message": "entrance boundary differs"}
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
        finally:
            for button in tuple(session.pressed_buttons):
                session.release(button)
            final = session.save_state_bytes()
            with (args.output / "final.state").open("xb") as stream:
                stream.write(final)
            result = {**plan, "error": error, "origin_state_sha256": origin_sha,
                "first_party_ot_id": ot, "after": completion_ledger(reader),
                "final_state_sha256": hashlib.sha256(final).hexdigest(),
                "costs": {"frames": session.frame_count, "macros": limiter.attempted_actions,
                          "seconds": session.elapsed_seconds}, "held_buttons": sorted(session.pressed_buttons)}
            write_new(args.output / "result.json", result)
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "claim", "inventory", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
