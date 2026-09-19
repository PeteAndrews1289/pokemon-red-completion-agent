"""Four fixed TRAIN openings: measured teacher versus frozen-learner continuation.

This diagnostic creates no fit, promotion or independent qualification. Each
opening and timing is declared before play, independently of its old outcome.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

import run_fresh_red_trainer_curriculum as common
from run_red_trainer_broad_fit import LATE_MODEL_SHA, admitted_supply

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameBudgetController
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_trainer_practice_admission import inspect_trainer_practice_choices
from pokemon_red_completion.red_trainer_practice_counterfactual import (
    TrainerPracticeFirstChoice,
    collect_trainer_practice_counterfactuals,
)
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)
from pokemon_red_completion.red_trainer_practice_targets import (
    aggregate_trainer_timing_targets,
    extract_trainer_practice_targets,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY = "train-frozen-learner-continuation-diagnostic-v1"


def preference_comparison(old, new):
    left, right = old["heads"]["control"], new["heads"]["control"]
    if left["choice_refs"] != right["choice_refs"]:
        raise ValueError("continuation comparison action inventory differs")

    def best(head):
        maximum = max(head["returns"])
        return [
            ref
            for ref, value in zip(head["choice_refs"], head["returns"], strict=True)
            if abs(value - maximum) <= 1e-9
        ]

    a, b = best(left), best(right)
    return {
        "capture_id": old["capture_id"],
        "teacher_best": a,
        "learner_best": b,
        "best_sets_disjoint": not bool(set(a) & set(b)),
        "teacher_returns": left["returns"],
        "learner_returns": right["returns"],
        "choice_refs": left["choice_refs"],
    }


def run(args):
    if (
        args.output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("diagnostic needs new output and committed source")
    if common._binding(args.model)["sha256"] != LATE_MODEL_SHA:
        raise ValueError("diagnostic frozen learner differs")
    if common._binding(args.rom)["sha256"] != common.ROM_SHA256:
        raise ValueError("diagnostic ROM differs")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    model = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.model.read_bytes()))
    authenticated = {
        row["capture_id"]: row
        for row in admitted_supply(
            args.supply, set(model.train_root_ids), set(), late=True, late_main=True
        )
    }
    cases = [
        sorted((args.supply / "train").glob(f"root-{root:02d}-foe-*"))[0] for root in range(1, 5)
    ]
    args.output.mkdir(mode=0o700)
    common._write(
        args.output / "plan.json",
        {
            "source_commit": commit,
            "model": common._binding(args.model),
            "supply": common._binding(args.supply / "collection.json"),
            "selection": "lowest recipe index in each of four roots, independent of outcome",
            "cases": [common._binding(p / "target-00.json") for p in cases],
            "timing_offsets": list(common.OFFSETS),
            "horizon": 40,
            "max_decisions": 160,
            "continuation": POLICY,
            "fits": 0,
            "promotion_eligible": False,
        },
    )
    model = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.model.read_bytes()))
    stats = RedPracticeCartridge(args.rom.read_bytes()).public_base_stats

    @contextmanager
    def session_factory():
        with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
            yield FrameBudgetController(emulator, maximum_frames=240000)

    comparisons = []
    for case_index, source in enumerate(cases):
        state = source / "materialized/assisted.state"
        capture = open_battle_scenario_capture(state, state.with_suffix(".state.json"))
        old = json.loads((source / "target-00.json").read_bytes())
        if old != authenticated.get(old["capture_id"]):
            raise ValueError("teacher target differs from authenticated measured branches")
        if old["partition"] != "train" or old["capture_id"] != capture.manifest.capture_id:
            raise ValueError("diagnostic source is not matching TRAIN")
        refs = tuple(old["heads"]["control"]["choice_refs"])
        choices = tuple(
            TrainerPracticeFirstChoice(
                BattleAction.move(int(ref.rsplit(":", 1)[1]))
                if ":move:" in ref
                else BattleAction.switch(int(ref.rsplit(":", 1)[1]))
            )
            for ref in refs
        )
        timed = []
        for offset in common.OFFSETS:
            directory = args.output / f"case-{case_index:02d}-timing-{offset:02d}"
            directory.mkdir(mode=0o700)
            plan = {
                "source_commit": capture.manifest.source_commit,
                "execution_source_commit": commit,
                "capture_id": capture.manifest.capture_id,
                "capture_manifest_sha256": capture.manifest_sha256,
                "root_lineage_id": capture.manifest.root_lineage_id,
                "partition": "train",
                "model_sha256": LATE_MODEL_SHA,
                "policy_id": POLICY,
                "continuation_policy_id": POLICY,
                "max_decisions": 160,
                "player_turn_horizon": 40,
                "opening_idle_frames": offset,
                "first_choice_refs": list(refs),
            }
            common._write(directory / "plan.json", plan)
            plan_sha = common._binding(directory / "plan.json")["sha256"]

            def event_log(index, choice, directory=directory, plan=plan, plan_sha=plan_sha):
                return TrainerPracticeEventLog(
                    directory / f"branch-{index:02d}-events",
                    run_identity={
                        **plan,
                        "plan_sha256": plan_sha,
                        "first_choice_ref": choice.semantic_ref,
                    },
                )

            measured = collect_trainer_practice_counterfactuals(
                capture,
                session_factory=session_factory,
                continuation_policy_factory=lambda capture=capture: RedTrainerPracticeOutcomePolicy(
                    policy_id=POLICY, battle_plan_id=capture.manifest.capture_id, model=model
                ),
                first_choices=choices,
                max_decisions=160,
                player_turn_horizon=40,
                public_species_base_stats=stats,
                opening_idle_frames=offset,
                branch_event_log_factory=event_log,
            ).public_dict()
            common._write(directory / "choices.json", measured)
            if any(
                row["episode"]["stop_reason"] not in {"battle_won", "party_defeated"}
                for row in measured["branches"]
            ):
                raise ValueError("diagnostic continuation truncated")
            admission = inspect_trainer_practice_choices(
                capture,
                measured,
                expected_choice_refs=refs,
                continuation_policy_id=POLICY,
                branch_event_logs={
                    ref: directory / f"branch-{i:02d}-events" for i, ref in enumerate(refs)
                },
                plan_sha256=plan_sha,
                model_sha256=LATE_MODEL_SHA,
                max_decisions=160,
                expected_opening_idle_frames=offset,
            )
            timed.append(extract_trainer_practice_targets(admission, measured))
        new = aggregate_trainer_timing_targets(tuple(timed), expected_offsets=common.OFFSETS)
        common._write(args.output / f"learner-target-{case_index:02d}.json", new)
        comparisons.append(preference_comparison(old, new))
        print(json.dumps(comparisons[-1]), flush=True)
    common._write(
        args.output / "result.json",
        {
            "comparisons": comparisons,
            "fits": 0,
            "changed_best_sets": sum(r["best_sets_disjoint"] for r in comparisons),
            "authority_promotions": 0,
            "independent_qualification": False,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "model", "supply", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
