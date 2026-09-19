"""Policy-bound TRAIN returns: sixteen declared captures, frozen H continuation.

Teacher targets remain immutable and separate. A policy target is a wrapper,
not a legacy target with its meaning silently changed. No DEVELOPMENT is read.
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
from pokemon_red_completion.provenance import canonical_sha256
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
POLICY = "train-frozen-learner-continuation-H-v1"
SCHEMA = "pokemon.red.policy-bound-trainer-target.v1"


def first_choice(ref):
    if ref == "pokemon.core:battle:decline-switch":
        return TrainerPracticeFirstChoice(None)
    prefix, slot = ref.rsplit(":", 1)
    if prefix == "pokemon.core:battle:move":
        return TrainerPracticeFirstChoice(BattleAction.move(int(slot)))
    if prefix == "pokemon.core:battle:switch":
        return TrainerPracticeFirstChoice(BattleAction.switch(int(slot)))
    raise ValueError("unknown first action reference")


def select_cases(rows):
    """Metadata-only selection; never inspect return values or success labels."""
    roots = sorted({row["root_lineage_id"] for row in rows})
    if len(roots) != 4:
        raise ValueError("four TRAIN origins required")
    selected = []
    for root in roots:
        group = sorted(
            (row for row in rows if row["root_lineage_id"] == root),
            key=lambda row: row["capture_id"],
        )
        openings = [r for r in group if r["capture_id"].startswith("assisted-train-")]
        replacements = [r for r in group if r["decision_context"] in {"forced", "prompt"}]
        endgames = [
            r
            for r in group
            if r["decision_context"] == "main"
            and r["capture_id"].startswith("terminal-intermediate-")
            and r["source_profile"] == "late-main"
        ]
        if len(openings) < 2 or not replacements or not endgames:
            raise ValueError("root lacks declared useful contexts")
        selected.extend(openings[:2] + replacements[:1] + endgames[:1])
    if len({r["capture_id"] for r in selected}) != 16:
        raise ValueError("duplicate selected context")
    return selected


def bind_target(target, *, policy_id, model_sha256):
    if target.get("partition") != "train" or policy_id != POLICY or model_sha256 != LATE_MODEL_SHA:
        raise ValueError("policy target is not declared frozen-H TRAIN")
    contract = {
        "policy_id": policy_id,
        "model_sha256": model_sha256,
        "history_initialization": "fresh actor at capture; forced first action observed",
        "player_turn_horizon": 40,
        "timing_offsets": list(common.OFFSETS),
    }
    return {
        "schema": SCHEMA,
        "target_id": canonical_sha256({"capture_id": target["capture_id"], **contract}),
        "continuation": contract,
        "target": target,
    }


def unwrap_target(wrapper):
    if wrapper.get("schema") != SCHEMA:
        raise ValueError("policy-bound wrapper required; legacy targets cannot be mixed")
    target = wrapper.get("target", {})
    if wrapper != bind_target(target, policy_id=POLICY, model_sha256=LATE_MODEL_SHA):
        raise ValueError("policy target contract differs")
    return target


def measured_target(capture, directory, refs):
    timed = []
    for offset in common.OFFSETS:
        branch = directory / f"timing-{offset:02d}"
        plan = json.loads((branch / "plan.json").read_bytes())
        choices = json.loads((branch / "choices.json").read_bytes())
        if (
            plan["continuation_policy_id"] != POLICY
            or plan["model_sha256"] != LATE_MODEL_SHA
            or plan["first_choice_refs"] != list(refs)
            or plan["player_turn_horizon"] != 40
            or plan["max_decisions"] != 160
            or any(
                r["episode"]["stop_reason"] not in {"battle_won", "party_defeated"}
                for r in choices["branches"]
            )
        ):
            raise ValueError("learner continuation is incomplete or contract differs")
        admitted = inspect_trainer_practice_choices(
            capture,
            choices,
            expected_choice_refs=refs,
            continuation_policy_id=POLICY,
            branch_event_logs={
                ref: branch / f"branch-{i:02d}-events" for i, ref in enumerate(refs)
            },
            plan_sha256=common._binding(branch / "plan.json")["sha256"],
            model_sha256=LATE_MODEL_SHA,
            max_decisions=160,
            expected_opening_idle_frames=offset,
        )
        timed.append(extract_trainer_practice_targets(admitted, choices))
    return aggregate_trainer_timing_targets(tuple(timed), expected_offsets=common.OFFSETS)


def admitted_policy_supply(directory):
    receipt = json.loads((directory / "collection.json").read_bytes())
    if (
        receipt["plan"] != common._binding(directory / "plan.json")
        or receipt["targets"] != common._binding(directory / "policy-targets.json")
        or receipt["fits"] != 0
        or receipt["contexts"] != 16
    ):
        raise ValueError("policy supply receipt differs")
    plan = json.loads((directory / "plan.json").read_bytes())
    wrappers = json.loads((directory / "policy-targets.json").read_bytes())
    if len(wrappers) != 16 or len(plan["cases"]) != 16:
        raise ValueError("policy supply inventory differs")
    targets = []
    for index, (case, wrapper) in enumerate(zip(plan["cases"], wrappers, strict=True)):
        state = Path(case["state"]["path"])
        if common._binding(state) != case["state"]:
            raise ValueError("policy source state differs")
        capture = open_battle_scenario_capture(state, state.with_suffix(".state.json"))
        if common._binding(state.with_suffix(".state.json")) != case["manifest"]:
            raise ValueError("policy source manifest differs")
        target = measured_target(capture, directory / f"case-{index:02d}", tuple(case["refs"]))
        if unwrap_target(wrapper) != json.loads(json.dumps(target)):
            raise ValueError("policy target differs from measured branch logs")
        targets.append(target)
    if (
        len({r["capture_id"] for r in targets}) != 16
        or len({r["root_lineage_id"] for r in targets}) != 4
    ):
        raise ValueError("policy supply duplicate contexts or roots")
    return targets


def run(args):
    if (
        args.output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("new policy supply requires committed source and new output")
    if (
        common._binding(args.model)["sha256"] != LATE_MODEL_SHA
        or common._binding(args.rom)["sha256"] != common.ROM_SHA256
    ):
        raise ValueError("frozen learner or ROM differs")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    model = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.model.read_bytes()))
    rows = []
    for supply, late_main in ((args.late_supply, False), (args.late_main_supply, True)):
        authenticated = admitted_supply(
            supply, set(model.train_root_ids), set(), late=True, late_main=late_main
        )
        paths = {
            json.loads(p.read_bytes())["capture_id"]: p
            for p in sorted(supply.glob("train/*/target-*.json"))
        }
        for row in authenticated:
            path = paths[row["capture_id"]]
            index = int(path.stem.rsplit("-", 1)[1])
            state = path.parent / (
                "materialized/assisted.state" if index == 0 else f"intermediate-{index:02d}.state"
            )
            refs = row["heads"].get("control", row["heads"].get("switch", {}))["choice_refs"]
            if len(refs) >= 2:
                rows.append(
                    {
                        **row,
                        "state_path": state,
                        "refs": refs,
                        "source_profile": "late-main" if late_main else "late",
                    }
                )
    selected = select_cases(rows)
    cases = [
        {
            "capture_id": r["capture_id"],
            "root": r["root_lineage_id"],
            "context": r["decision_context"],
            "refs": r["refs"],
            "state": common._binding(r["state_path"]),
            "manifest": common._binding(r["state_path"].with_suffix(".state.json")),
        }
        for r in selected
    ]
    args.output.mkdir(mode=0o700)
    common._write(
        args.output / "plan.json",
        {
            "source_commit": commit,
            "model": common._binding(args.model),
            "cases": cases,
            "continuation_policy_id": POLICY,
            "fits": 0,
            "history_initialization": "fresh actor at capture; forced first action observed",
        },
    )
    stats = RedPracticeCartridge(args.rom.read_bytes()).public_base_stats

    @contextmanager
    def session_factory():
        with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
            yield FrameBudgetController(emulator, maximum_frames=240000)

    wrappers = []
    try:
        for case_index, row in enumerate(selected):
            state = row["state_path"]
            capture = open_battle_scenario_capture(state, state.with_suffix(".state.json"))
            directory = args.output / f"case-{case_index:02d}"
            directory.mkdir(mode=0o700)
            refs = tuple(row["refs"])
            for offset in common.OFFSETS:
                branch = directory / f"timing-{offset:02d}"
                branch.mkdir(mode=0o700)
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
                common._write(branch / "plan.json", plan)
                plan_sha = common._binding(branch / "plan.json")["sha256"]

                def event_log(index, choice, branch=branch, plan=plan, plan_sha=plan_sha):
                    return TrainerPracticeEventLog(
                        branch / f"branch-{index:02d}-events",
                        run_identity={
                            **plan,
                            "plan_sha256": plan_sha,
                            "first_choice_ref": choice.semantic_ref,
                        },
                    )

                result = collect_trainer_practice_counterfactuals(
                    capture,
                    session_factory=session_factory,
                    continuation_policy_factory=lambda capture=capture: (
                        RedTrainerPracticeOutcomePolicy(
                            policy_id=POLICY,
                            battle_plan_id=capture.manifest.capture_id,
                            model=model,
                        )
                    ),
                    first_choices=tuple(first_choice(ref) for ref in refs),
                    max_decisions=160,
                    player_turn_horizon=40,
                    public_species_base_stats=stats,
                    opening_idle_frames=offset,
                    branch_event_log_factory=event_log,
                ).public_dict()
                common._write(branch / "choices.json", result)
            target = measured_target(capture, directory, refs)
            wrappers.append(bind_target(target, policy_id=POLICY, model_sha256=LATE_MODEL_SHA))
            common._write(directory / "policy-target.json", wrappers[-1])
            print(
                json.dumps(
                    {"contexts_complete": len(wrappers), "context": target["decision_context"]}
                ),
                flush=True,
            )
    except Exception as error:
        common._write(
            args.output / "failure.json",
            {"error_type": type(error).__name__, "completed_contexts": len(wrappers), "fits": 0},
        )
        raise
    common._write(args.output / "policy-targets.json", wrappers)
    common._write(
        args.output / "collection.json",
        {
            "plan": common._binding(args.output / "plan.json"),
            "targets": common._binding(args.output / "policy-targets.json"),
            "contexts": len(wrappers),
            "new_unique_physical_contexts": 0,
            "new_policy_conditioned_measurements": len(wrappers),
            "fits": 0,
            "authority_promotions": 0,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "model", "late-supply", "late-main-supply", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
