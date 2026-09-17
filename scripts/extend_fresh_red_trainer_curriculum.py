"""Add unplayed attack/control TRAIN contrasts without replaying 16 old cases.

Each of four fresh roots gains the three main matchup templates it did not
previously see. The twelve new scenarios join the already admitted sixteen;
the older outcome logs are authenticated again, never rerun.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import fit_red_trainer_practice_outcomes as fitter
import materialize_red_teacher_battle_practice as materializer
import run_fresh_red_trainer_curriculum as original
import run_red_trainer_practice_baseline as baseline

from pokemon_red_completion.battle_scenario_capture import OBSERVATION_SCHEMA_V2

ROOT = Path(__file__).resolve().parents[1]


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.output.exists():
        raise ValueError("trainer contrast extension output must be new")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit trainer contrast extension before collection")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    old_summary = json.loads((args.previous / "summary.json").read_bytes())
    old_plan = json.loads((args.previous / "fit-plan.json").read_bytes())
    old_cases = old_plan.get("scenarios")
    if (
        old_summary.get("status") != "qualified_train_fit_completed"
        or old_summary.get("source_roots") != 4
        or old_summary.get("admitted_contexts") != 16
        or not isinstance(old_cases, list)
        or len(old_cases) != 16
    ):
        raise ValueError("base trainer curriculum is not the admitted 16-case corpus")
    rom = original._binding(args.rom)
    if rom["sha256"] != original.ROM_SHA256:
        raise ValueError("trainer contrast extension Red cartridge differs")
    frozen = original._binding(args.frozen_model)
    if len(args.main_templates) != 4:
        raise ValueError("trainer contrast extension requires four declared main templates")
    specs = []
    for path in args.main_templates:
        template = json.loads(path.read_bytes())
        if (
            template.get("schema") != materializer.TRAINER_SCHEMA
            or template.get("observation_schema") != OBSERVATION_SCHEMA_V2
            or not isinstance(template.get("practice"), dict)
        ):
            raise ValueError("trainer contrast main template differs")
        specs.append(template["practice"])
    sources = original._source_rows(args.batch)
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    new_cases = []
    completed = 0
    stage = "start"
    try:
        for root_index, (source, receipt) in enumerate(sources):
            root = str(receipt["source_id"])
            source_state = source / "source.state"
            source_manifest = source / "source.state.json"
            for template_index, spec in enumerate(specs):
                if template_index == root_index:
                    continue  # Already executed, admitted, and retained in the base plan.
                stage = f"{root}:main-{template_index + 1}:materialize"
                directory = args.output / f"root-{root_index + 1:02d}-main-{template_index + 1}"
                directory.mkdir(mode=0o700, exist_ok=False)
                practice = deepcopy(spec)
                practice["source_state_sha256"] = original._binding(source_state)["sha256"]
                practice["root_lineage_id"] = root
                materialized = directory / "materialized"
                materialize_plan = directory / "materialize-plan.json"
                original._write(materialize_plan, {
                    "schema": materializer.TRAINER_SCHEMA,
                    "source_commit": commit,
                    "rom": rom,
                    "source_state": original._binding(source_state),
                    "source_capture_manifest": original._binding(source_manifest),
                    "practice": practice,
                    "observation_schema": OBSERVATION_SCHEMA_V2,
                    "output": str(materialized),
                })
                materializer.run(materialize_plan, check_only=True)
                materializer.run(materialize_plan)
                stage = f"{root}:main-{template_index + 1}:branches"
                baseline_output = directory / "baseline"
                baseline_plan = directory / "baseline-plan.json"
                original._write(baseline_plan, {
                    "schema": baseline.SCHEMA,
                    "source_commit": commit,
                    "rom": rom,
                    "model": frozen,
                    "capture_state": original._binding(materialized / "assisted.state"),
                    "capture_manifest": original._binding(materialized / "assisted.state.json"),
                    "max_decisions": 80,
                    "maximum_frames": 120000,
                    "matched_timing_offsets": list(original.OFFSETS),
                    "matched_choices": "all_legal_opening",
                    "output": str(baseline_output),
                })
                baseline.run(baseline_plan, check_only=True)
                baseline.run(baseline_plan)
                trials = []
                for offset in original.OFFSETS:
                    branch = baseline_output / f"timing-{offset:02d}"
                    trials.append({
                        "choices": original._binding(branch / "matched-choices.json"),
                        "plan": original._binding(branch / "matched-plan.json"),
                        "branch_log_prefix": "matched-branch",
                    })
                new_cases.append({
                    "state": original._binding(materialized / "assisted.state"),
                    "manifest": original._binding(materialized / "assisted.state.json"),
                    "fresh_source_state": original._binding(source_state),
                    "fresh_source_manifest": original._binding(source_manifest),
                    "origin_state": original._binding(source / "origin.state"),
                    "origin_receipt": original._binding(source / "outcome.json"),
                    "timing_offsets": list(original.OFFSETS),
                    "trials": trials,
                })
                completed += 1
        stage = "admission"
        fit_plan = args.output / "fit-plan.json"
        original._write(fit_plan, {
            "schema": fitter.SCHEMA,
            "source_commit": commit,
            "seed": 18092026,
            "scenarios": old_cases + new_cases,
            "output": str(args.output / "fit"),
        })
        admitted = fitter.run(fit_plan, check_only=True)
        stage = "fit"
        fitted = fitter.run(fit_plan)
    except Exception as error:
        original._write(args.output / "failure.json", {
            "schema": "pokemon.red.trainer-contrast-extension-failure.v1",
            "stage": stage,
            "completed_new_contexts": completed,
            "error_type": type(error).__name__,
        })
        raise
    summary: dict[str, object] = {
        "schema": "pokemon.red.trainer-contrast-extension-result.v1",
        "status": "qualified_train_fit_completed",
        "source_commit": commit,
        "source_roots": 4,
        "reused_admitted_contexts_not_replayed": len(old_cases),
        "new_admitted_contexts": completed,
        "total_admitted_contexts": len(old_cases) + completed,
        "admission": admitted,
        "fit": {
            "model_sha256": fitted["model_sha256"],
            "head_example_counts": fitted["head_example_counts"],
            "independent_train_supply_gate_passed": fitted[
                "independent_train_supply_gate_passed"
            ],
        },
        "development_opened": False,
        "authority_promotions": 0,
        "full_game_runs": 0,
    }
    original._write(args.output / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--frozen-model", type=Path, required=True)
    parser.add_argument("--main-template", dest="main_templates", action="append", type=Path,
                        required=True)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(parser.parse_args()), sort_keys=True))


if __name__ == "__main__":
    main()
