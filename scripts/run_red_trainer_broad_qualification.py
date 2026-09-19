"""Frozen broader-data learner comparison on a distinct predeclared TRAIN sample.

A disclosed teacher is a separate reference arm, never fallback for either
learner. Assisted cases cannot establish independent natural generalization.
"""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from pathlib import Path

import run_fresh_red_trainer_curriculum as common
from run_red_trainer_broad_probe import CANDIDATE_SHA, run
from run_red_trainer_terminal_curriculum import StatDamageTeacher

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameBudgetController
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_trainer_practice_episode import run_red_trainer_practice_episode
from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)


def run_teacher_reference(state, rom, output, commit):
    output.mkdir(mode=0o700)
    capture = open_battle_scenario_capture(state, state.with_suffix(".state.json"))
    log = TrainerPracticeEventLog(
        output / "events",
        run_identity={
            "source_commit": commit,
            "capture_id": capture.manifest.capture_id,
            "capture_manifest_sha256": capture.manifest_sha256,
            "partition": "train",
            "policy_id": StatDamageTeacher.policy_id,
            "role": "disclosed_teacher_reference",
        },
    )

    @contextmanager
    def session_factory():
        with PyBoyAdapter(rom, watch=False, speed=None) as emulator:
            yield FrameBudgetController(emulator, maximum_frames=240000)

    try:
        episode = run_red_trainer_practice_episode(
            capture,
            session_factory=session_factory,
            policy=StatDamageTeacher(),
            max_decisions=160,
            event_sink=log.emit,
            public_species_base_stats=RedPracticeCartridge(rom.read_bytes()).public_base_stats,
        )
        result = episode.public_dict()
        result["role"] = "disclosed_teacher_reference_not_learner"
        common._write(output / "outcome.json", result)
        log.finish({"stop_reason": episode.stop_reason})
    except Exception as error:
        log.fail(error)
        raise
    check = verify_trainer_practice_event_log(output / "events")
    common._write(output / "event-log-verification.json", check)
    if not check["complete"]:
        raise ValueError("teacher reference log incomplete")
    return {k: v for k, v in result.items() if k not in ("decisions", "final_observation")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "batch", "candidate", "frozen", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads((args.candidate.parent / "result.json").read_bytes())
    plan = json.loads((args.candidate.parent / "plan.json").read_bytes())
    if (
        not receipt["train_qualified"]
        or plan["initial"]["sha256"] != CANDIDATE_SHA
        or receipt["new_contexts"] < 24
    ):
        raise ValueError("a qualified broader-data candidate is required")
    run(
        args,
        candidate_sha=receipt["model"]["sha256"],
        frozen_sha=CANDIDATE_SHA,
        seed=2026091903,
        teacher_reference=True,
    )


if __name__ == "__main__":
    main()
