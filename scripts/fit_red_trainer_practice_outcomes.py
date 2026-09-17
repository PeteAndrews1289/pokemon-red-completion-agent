"""Fit a TRAIN-only three-head challenger from five-timing admitted scenarios.

The private corpus plan lists exact state, manifest, report and prospective
choice-plan hashes. Every branch log must be complete and match the declared
source/model/choice/timing identity. No DEVELOPMENT input is opened here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.red_autonomous_player import _record
from pokemon_red_completion.red_trainer_practice_admission import inspect_trainer_practice_choices
from pokemon_red_completion.red_trainer_practice_fit import fit_trainer_practice_three_heads
from pokemon_red_completion.red_trainer_practice_targets import (
    aggregate_trainer_timing_targets,
    extract_trainer_practice_targets,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pokemon.red.trainer-practice-fit-corpus-plan.v1"
OFFSETS = (0, 2, 4, 6, 8)


def _bound_path(value: object, label: str) -> Path:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError(f"{label} binding differs")
    path, digest = value["path"], value["sha256"]
    if not isinstance(path, str) or not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(f"{label} identity differs")
    location = Path(path)
    if hashlib.sha256(location.read_bytes()).hexdigest() != digest:
        raise ValueError(f"{label} content differs")
    return location


def run(plan_path: Path, *, check_only: bool = False) -> dict[str, object]:
    plan = json.loads(plan_path.read_bytes())
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise ValueError("trainer fit corpus plan differs")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if (
        plan.get("source_commit") != revision
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("trainer fit requires its committed source")
    cases = plan.get("scenarios")
    seed = plan.get("seed")
    output = plan.get("output")
    if (
        not isinstance(cases, list) or len(cases) < 16
        or type(seed) is not int or seed < 0  # noqa: E721
        or not isinstance(output, str) or Path(output).exists()
    ):
        raise ValueError("trainer corpus size, seed, or output differs")
    scenario_targets = []
    scenario_receipts = []
    for scenario_index, scenario in enumerate(cases):
        if (
            not isinstance(scenario, dict)
            or scenario.get("timing_offsets") != list(OFFSETS)
            or not isinstance(scenario.get("trials"), list)
            or len(scenario["trials"]) != len(OFFSETS)
        ):
            raise ValueError("trainer timing inventory differs from five-offset schedule")
        state_path = _bound_path(scenario.get("state"), "trainer state")
        manifest_path = _bound_path(scenario.get("manifest"), "trainer manifest")
        capture = open_battle_scenario_capture(state_path, manifest_path)
        targets = []
        for offset, trial in zip(OFFSETS, scenario["trials"], strict=True):
            if not isinstance(trial, dict):
                raise ValueError("trainer timing trial differs")
            choices_path = _bound_path(trial.get("choices"), "trainer choices")
            choice_plan_path = _bound_path(trial.get("plan"), "trainer choice plan")
            document = json.loads(choices_path.read_bytes())
            choice_plan = json.loads(choice_plan_path.read_bytes())
            if (
                choice_plan.get("schema") != "pokemon.red.trainer-practice-choice-plan.v1"
                or choice_plan.get("capture_manifest_sha256") != capture.manifest_sha256
                or choice_plan.get("source_commit") != capture.manifest.source_commit
                or choice_plan.get("opening_idle_frames") != offset
                or choice_plan.get("player_turn_horizon") != document.get("player_turn_horizon")
                or choice_plan.get("first_choice_refs") != [
                    branch.get("first_choice_ref") for branch in document.get("branches", [])
                ]
                or not isinstance(choice_plan.get("model_sha256"), str)
                or type(choice_plan.get("max_decisions")) is not int  # noqa: E721
            ):
                raise ValueError("trainer timing choice plan differs")
            prefix = trial.get("branch_log_prefix")
            if not isinstance(prefix, str) or prefix not in {
                "matched-branch", "prompt-branch"
            }:
                raise ValueError("trainer branch log prefix differs")
            logs = {
                ref: choices_path.parent / f"{prefix}-{index:02d}-events"
                for index, ref in enumerate(choice_plan["first_choice_refs"])
            }
            admitted = inspect_trainer_practice_choices(
                capture, document,
                expected_choice_refs=tuple(choice_plan["first_choice_refs"]),
                continuation_policy_id=choice_plan["continuation_policy_id"],
                branch_event_logs=logs,
                plan_sha256=hashlib.sha256(choice_plan_path.read_bytes()).hexdigest(),
                model_sha256=choice_plan["model_sha256"],
                max_decisions=choice_plan["max_decisions"],
                expected_opening_idle_frames=offset,
            )
            targets.append(extract_trainer_practice_targets(admitted, document))
        aggregate = aggregate_trainer_timing_targets(
            tuple(targets), expected_offsets=OFFSETS
        )
        heads = aggregate["heads"]
        if not isinstance(heads, dict):
            raise ValueError("trainer scenario heads differ")
        scenario_targets.append(aggregate)
        scenario_receipts.append({
            "scenario_index": scenario_index,
            "capture_id": capture.manifest.capture_id,
            "root_lineage_id": capture.manifest.root_lineage_id,
            "timing_count": len(OFFSETS),
            "head_kinds": sorted(heads),
        })
    root_counts = Counter(row["root_lineage_id"] for row in scenario_receipts)
    if len(root_counts) < 4 or any(count < 4 for count in root_counts.values()):
        raise ValueError("four independent TRAIN roots with four scenarios each required")
    if not all(
        any(
            isinstance(row["head_kinds"], list) and head in row["head_kinds"]
            for row in scenario_receipts
        )
        for head in ("move", "control", "switch")
    ):
        raise ValueError("trainer corpus lacks one or more learnable heads")
    if check_only:
        return {
            "status": "train_only_corpus_admitted_no_fit",
            "scenario_count": len(scenario_targets),
            "root_count": len(root_counts),
            "model_updates": 0,
        }
    model = fit_trainer_practice_three_heads(scenario_targets, seed=seed)
    destination = Path(output)
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    _record(destination / "model.json", model.to_dict())
    report = {
        "schema": "pokemon.red.trainer-practice-fit-receipt.v1",
        "source_commit": revision,
        "corpus_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "scenario_count": len(scenario_targets),
        "distinct_upstream_train_roots": len(model.train_root_ids),
        "timing_trials_per_scenario": len(OFFSETS),
        "head_example_counts": {
            head: sum(
                isinstance(target["heads"], dict) and head in target["heads"]
                for target in scenario_targets
            )
            for head in ("move", "control", "switch")
        },
        "model_sha256": hashlib.sha256((destination / "model.json").read_bytes()).hexdigest(),
        "model_updates": 1,
        "development_evaluations": 0,
        "authority_promotions": 0,
        "scenarios": scenario_receipts,
    }
    _record(destination / "receipt.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.plan, check_only=args.check_only), sort_keys=True))


if __name__ == "__main__":
    main()
