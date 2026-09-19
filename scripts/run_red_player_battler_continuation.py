"""Consume the exact retained failed endpoint once, without reissuing funding.

This DEVELOPMENT continuation retains the prior 247 actions / 19284 frames and
failed funding verdict. It cannot reset to the original source or fit the model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from run_red_player_battler_checkpoint import ROM_SHA256
from run_red_trainer_earned_switch import completion_ledger

from pokemon_red_completion.battle_runtime import DEFAULT_BATTLE_RUNTIME_TIMING
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameBudgetController,
    FrameSafeExecutor,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
)
from pokemon_red_completion.observation import PokemonRedStateReader, event_flag_is_set
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_learned_trainer import (
    FROZEN_J_SHA256,
    FrozenTrainerBattler,
    load_frozen_trainer_model,
)
from pokemon_red_completion.red_trainer_battle_lifecycle import continue_learned_trainer_battle
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = "e7616aff8abe5d7444419785c65ada63626d448d57d79dbd9a627fa5a5d34024"
PRIOR_RESULT_SHA256 = "b5779065eebee9d47e49b5527bf4f7b4f3f19621bdbd9e852332355f6a549a0c"


def run(args):
    source = args.state.read_bytes()
    prior_bytes = args.prior_result.read_bytes()
    rom = args.rom.read_bytes()
    if (
        hashlib.sha256(source).hexdigest() != SOURCE_SHA256
        or hashlib.sha256(prior_bytes).hexdigest() != PRIOR_RESULT_SHA256
        or hashlib.sha256(rom).hexdigest() != ROM_SHA256
    ):
        raise ValueError("retained failed endpoint, prior result or cartridge differs")
    prior = json.loads(prior_bytes)
    if prior["final_state_sha256"] != SOURCE_SHA256 or prior["status"] != "failed":
        raise ValueError("parent must remain the exact failed funding attempt")
    model = load_frozen_trainer_model(args.model.read_bytes(), FROZEN_J_SHA256)
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit source before execution")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    args.output.mkdir(mode=0o700, exist_ok=False)
    plan = {
        "schema": "pokemon.red.learned-trainer-continuation-plan.v1",
        "source_commit": commit,
        "source_state_sha256": SOURCE_SHA256,
        "prior_result_sha256": PRIOR_RESULT_SHA256,
        "model_sha256": FROZEN_J_SHA256,
        "root_lineage_id": "fresh-red-team-development-boot3100",
        "partition": "development",
        "prior_funding_verdict": "failed",
        "prior_actions": prior["actions"],
        "prior_frames": prior["frames"],
        "maximum_actions": 1000,
        "maximum_frames": 100000,
        "maximum_decisions": 80,
        "maximum_settle_pulses": 128,
        "trainer_identity": [230, 30, 4],
        "target_event": 1405,
        "ordinary_victory_money": 480,
        "resets_after_start": 0,
        "teacher_queries": 0,
        "fits": 0,
        "stop_condition": "One battle terminal, unsupported boundary or budget; no replay.",
    }
    _record(args.output / "plan.json", plan)
    # Source-side exclusive marker prevents a second output directory from replaying it.
    _record(args.state.with_name(args.state.name + ".learned-continuation-claim.json"), plan)
    result = None
    failure = None
    with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(source)
        session = FrameBudgetController(emulator, maximum_frames=100000)
        reader = PokemonRedStateReader(session)
        actions = CountingExecutor(
            HardCompositionActionLimiter(
                FrameSafeExecutor(session, DEFAULT_NEW_GAME_TIMING.controller_timing()),
                maximum_actions_per_decision=1000,
                maximum_episode_actions=1000,
            )
        )
        battler = FrozenTrainerBattler(
            session,
            model,
            args.output / "trainer-battles",
            commit,
            plan["root_lineage_id"],
            SOURCE_SHA256,
            RedPracticeCartridge(rom).public_base_stats,
        )
        try:
            before = completion_ledger(reader)
            _record(args.output / "before-ledger.json", before)
            if before != prior["final_ledger"]:
                raise ValueError("fresh source ledger differs from the retained failure")
            result = continue_learned_trainer_battle(
                battler,
                reader,
                actions,
                trainer_identity=(230, 30, 4),
                defeated_event=1405,
                ordinary_victory_money=480,
                timing=DEFAULT_BATTLE_RUNTIME_TIMING,
            )
        except Exception as error:
            failure = {"error_type": type(error).__name__, "error": str(error)}
        finally:
            final = session.save_state_bytes()
            _write(args.output / "final.state", final)
            after = completion_ledger(reader)
            _record(args.output / "final-ledger.json", after)
            log_dir = args.output / "trainer-battles" / "battle-0001" / "events"
            log = verify_trainer_practice_event_log(log_dir) if log_dir.exists() else None
            report = {
                "schema": "pokemon.red.learned-trainer-continuation-result.v1",
                "source_commit": commit,
                "source_state_sha256": SOURCE_SHA256,
                "prior_result_sha256": PRIOR_RESULT_SHA256,
                "final_state_sha256": hashlib.sha256(final).hexdigest(),
                "model_sha256": FROZEN_J_SHA256,
                "prior_funding_verdict": "failed",
                "funding_success": False,
                "failure": failure,
                "status": "verified_battle_terminal"
                if result and result.field_ready
                else "unresolved",
                "completion": result.public_dict() if result else None,
                "actions": actions.actions_executed,
                "frames": session.frame_count,
                "cumulative_actions": prior["actions"] + actions.actions_executed,
                "cumulative_frames": prior["frames"] + session.frame_count,
                "final_ledger": after,
                "target_defeated": event_flag_is_set(
                    reader.read().event_flags,
                    1405,
                ),
                "log_verification": log,
                "pressed_buttons": sorted(session.pressed_buttons),
                "resets_after_start": 0,
                "teacher_queries": 0,
                "fits": 0,
                "memory_writes": 0,
                "new_training_examples": 0,
            }
            _record(args.output / "result.json", report)
    # Reopen only for observation: no executor, tick, button or policy invocation.
    with PyBoyAdapter(args.rom, watch=False, speed=None) as reopened:
        reopened.load_state_bytes(final)
        reader = PokemonRedStateReader(reopened)
        verified = (
            completion_ledger(reader) == after
            and reopened.save_state_bytes() == final
            and event_flag_is_set(reader.read().event_flags, 1405) == report["target_defeated"]
        )
        _record(
            args.output / "reopened.json",
            {
                "matches": verified,
                "actions": 0,
                "frames": 0,
                "final_state_sha256": report["final_state_sha256"],
            },
        )
    print(
        json.dumps({key: value for key, value in report.items() if key != "completion"}, indent=2)
    )
    if not verified:
        raise RuntimeError("retained final state did not reopen exactly")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "state", "prior-result", "model", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
