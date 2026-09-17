"""Read-only admission report for one authenticated TRAIN trainer-choice set."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.red_trainer_practice_admission import (
    inspect_trainer_practice_choices,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("choices", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--branch-log-prefix", choices=("matched-branch", "prompt-branch"))
    args = parser.parse_args()
    capture = open_battle_scenario_capture(args.state, args.manifest)
    document = json.loads(args.choices.read_bytes())
    plan = json.loads(args.plan.read_bytes())
    if (
        plan.get("schema") != "pokemon.red.trainer-practice-choice-plan.v1"
        or plan.get("capture_manifest_sha256") != capture.manifest_sha256
        or plan.get("source_commit") != capture.manifest.source_commit
        or not isinstance(plan.get("model_sha256"), str)
        or len(plan["model_sha256"]) != 64
        or type(plan.get("max_decisions")) is not int
        or type(plan.get("opening_idle_frames")) is not int
        or plan.get("player_turn_horizon") != document.get("player_turn_horizon")
        or plan.get("first_choice_refs")
        != [branch.get("first_choice_ref") for branch in document.get("branches", [])]
    ):
        raise ValueError("trainer practice choice plan differs")
    logs = None
    if args.branch_log_prefix is not None:
        logs = {
            ref: args.choices.parent / f"{args.branch_log_prefix}-{index:02d}-events"
            for index, ref in enumerate(plan["first_choice_refs"])
        }
    print(
        json.dumps(
            inspect_trainer_practice_choices(
                capture,
                document,
                expected_choice_refs=tuple(plan["first_choice_refs"]),
                continuation_policy_id=plan["continuation_policy_id"],
                branch_event_logs=logs,
                plan_sha256=hashlib.sha256(args.plan.read_bytes()).hexdigest(),
                model_sha256=plan["model_sha256"],
                max_decisions=plan["max_decisions"],
                expected_opening_idle_frames=plan["opening_idle_frames"],
            ),
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
