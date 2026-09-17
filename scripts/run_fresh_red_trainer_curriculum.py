"""Run the fixed four-by-four fresh-root TRAIN trainer curriculum.

This script copies declared practice specifications onto separately booted
TRAIN captures, measures every legal first choice at five timing offsets, and
fits only if all sixteen contexts pass the existing admission gate. It never
opens DEVELOPMENT, promotes authority, or runs a full game.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import fit_red_trainer_practice_outcomes as fitter
import materialize_red_teacher_battle_practice as materializer
import run_red_trainer_practice_baseline as baseline

from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    open_battle_scenario_capture,
)

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
OFFSETS = (0, 2, 4, 6, 8)
CONTEXTS = ("main", "depleted", "prompt", "forced")


def _binding(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _write(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def _source_rows(batch: Path) -> tuple[tuple[Path, dict[str, object]], ...]:
    summary = json.loads((batch / "batch-outcome.json").read_bytes())
    ids = summary.get("source_ids")
    if (
        summary.get("schema") != "pokemon.red.fresh-trainer-train-batch.v1"
        or summary.get("status") != "captured"
        or summary.get("fresh_power_on_sources") != 4
        or summary.get("distinct_origin_state_hashes") != 4
        or summary.get("distinct_player_trainer_ids") != 4
        or not isinstance(ids, list)
        or len(ids) != 4
        or len(set(ids)) != 4
    ):
        raise ValueError("fresh trainer source batch is not four-root qualified")
    rows = []
    for source_id in ids:
        if not isinstance(source_id, str):
            raise ValueError("fresh trainer source identity differs")
        source = batch / source_id
        outcome = json.loads((source / "outcome.json").read_bytes())
        capture = open_battle_scenario_capture(
            source / "source.state", source / "source.state.json"
        )
        if (
            outcome.get("source_id") != source_id
            or outcome.get("fresh_power_on") is not True
            or outcome.get("origin_state_sha256") != _binding(source / "origin.state")["sha256"]
            or outcome.get("battle_state_sha256") != capture.manifest.state_sha256
            or capture.manifest.source_state_sha256 != outcome["origin_state_sha256"]
            or capture.manifest.root_lineage_id != source_id
            or capture.manifest.observation_schema != OBSERVATION_SCHEMA_V2
            or capture.manifest.partition.value != "train"
        ):
            raise ValueError("fresh trainer source ancestry or capture differs")
        rows.append((source, outcome))
    return tuple(rows)


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.output.exists():
        raise ValueError("fresh trainer curriculum output must be new")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit trainer curriculum code before collection")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    rom_binding = _binding(args.rom)
    if rom_binding["sha256"] != ROM_SHA256:
        raise ValueError("fresh trainer curriculum Red cartridge differs")
    frozen_binding = _binding(args.frozen_model)
    templates = (
        tuple(args.main_templates)
        + (args.depleted_template, args.prompt_template, args.forced_template)
    )
    specs = []
    template_hashes = []
    for path in templates:
        template_hashes.append(_binding(path)["sha256"])
        value = json.loads(path.read_bytes())
        if (
            value.get("schema") != materializer.TRAINER_SCHEMA
            or value.get("observation_schema") != OBSERVATION_SCHEMA_V2
            or not isinstance(value.get("practice"), dict)
            or value["practice"].get("battle_kind") != "trainer"
        ):
            raise ValueError("fresh trainer practice template differs")
        specs.append(value["practice"])
    rows = _source_rows(args.batch)
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    stage = "start"
    scenarios = []
    completed = 0
    try:
        for root_index, (source, receipt) in enumerate(rows):
            source_state = source / "source.state"
            source_manifest = source / "source.state.json"
            root = str(receipt["source_id"])
            for context in CONTEXTS:
                stage = f"{root}:{context}:materialize"
                index = root_index if context == "main" else {
                    "depleted": 4, "prompt": 5, "forced": 6,
                }[context]
                practice = deepcopy(specs[index])
                practice["source_state_sha256"] = _binding(source_state)["sha256"]
                practice["root_lineage_id"] = root
                directory = args.output / f"root-{root_index + 1:02d}-{context}"
                directory.mkdir(mode=0o700, exist_ok=False)
                materialized = directory / "materialized"
                materialize_plan = directory / "materialize-plan.json"
                _write(materialize_plan, {
                    "schema": materializer.TRAINER_SCHEMA,
                    "source_commit": commit,
                    "rom": rom_binding,
                    "source_state": _binding(source_state),
                    "source_capture_manifest": _binding(source_manifest),
                    "practice": practice,
                    "observation_schema": OBSERVATION_SCHEMA_V2,
                    "output": str(materialized),
                })
                materializer.run(materialize_plan, check_only=True)
                materializer.run(materialize_plan)
                stage = f"{root}:{context}:branches"
                baseline_output = directory / "baseline"
                baseline_plan = directory / "baseline-plan.json"
                plan = {
                    "schema": baseline.SCHEMA,
                    "source_commit": commit,
                    "rom": rom_binding,
                    "model": frozen_binding,
                    "capture_state": _binding(materialized / "assisted.state"),
                    "capture_manifest": _binding(materialized / "assisted.state.json"),
                    "max_decisions": 80,
                    "maximum_frames": 120000,
                    "matched_timing_offsets": list(OFFSETS),
                    "output": str(baseline_output),
                }
                if context in {"main", "depleted"}:
                    plan["matched_choices"] = "all_legal_opening"
                else:
                    plan[f"matched_{context}_choices"] = True
                _write(baseline_plan, plan)
                baseline.run(baseline_plan, check_only=True)
                baseline.run(baseline_plan)
                if context == "prompt":
                    state = baseline_output / "prompt.state"
                    manifest = baseline_output / "prompt.state.json"
                    prefix = "prompt-branch"
                    directory_prefix = "prompt-timing"
                    choice_name, plan_name = (
                        "matched-prompt-choices.json", "matched-prompt-plan.json"
                    )
                elif context == "forced":
                    state = baseline_output / "forced.state"
                    manifest = baseline_output / "forced.state.json"
                    prefix = "forced-branch"
                    directory_prefix = "forced-timing"
                    choice_name, plan_name = (
                        "matched-forced-choices.json", "matched-forced-plan.json"
                    )
                else:
                    state = materialized / "assisted.state"
                    manifest = materialized / "assisted.state.json"
                    prefix = "matched-branch"
                    directory_prefix = "timing"
                    choice_name, plan_name = "matched-choices.json", "matched-plan.json"
                scenario: dict[str, object] = {
                    "state": _binding(state),
                    "manifest": _binding(manifest),
                    "fresh_source_state": _binding(source_state),
                    "fresh_source_manifest": _binding(source_manifest),
                    "origin_state": _binding(source / "origin.state"),
                    "origin_receipt": _binding(source / "outcome.json"),
                    "timing_offsets": list(OFFSETS),
                    "trials": [],
                }
                if context in {"prompt", "forced"}:
                    scenario["parent_state"] = _binding(materialized / "assisted.state")
                    scenario["parent_manifest"] = _binding(materialized / "assisted.state.json")
                trials = []
                for offset in OFFSETS:
                    branch = baseline_output / f"{directory_prefix}-{offset:02d}"
                    trials.append({
                        "choices": _binding(branch / choice_name),
                        "plan": _binding(branch / plan_name),
                        "branch_log_prefix": prefix,
                    })
                scenario["trials"] = trials
                scenarios.append(scenario)
                completed += 1
        stage = "admission"
        fit_plan = args.output / "fit-plan.json"
        _write(fit_plan, {
            "schema": fitter.SCHEMA,
            "source_commit": commit,
            "seed": 17092026,
            "scenarios": scenarios,
            "output": str(args.output / "fit"),
        })
        admitted = fitter.run(fit_plan, check_only=True)
        stage = "fit"
        fitted = fitter.run(fit_plan)
    except Exception as error:
        _write(args.output / "failure.json", {
            "schema": "pokemon.red.fresh-trainer-curriculum-failure.v1",
            "stage": stage,
            "completed_contexts": completed,
            "error_type": type(error).__name__,
        })
        raise
    summary: dict[str, object] = {
        "schema": "pokemon.red.fresh-trainer-curriculum-result.v1",
        "status": "qualified_train_fit_completed",
        "source_commit": commit,
        "source_roots": len(rows),
        "admitted_contexts": completed,
        "timing_offsets_per_context": len(OFFSETS),
        "template_sha256": template_hashes,
        "admission": admitted,
        "fit": fitted,
        "development_opened": False,
        "authority_promotions": 0,
        "full_game_runs": 0,
    }
    _write(args.output / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--batch", required=True, type=Path)
    parser.add_argument("--frozen-model", required=True, type=Path)
    parser.add_argument(
        "--main-template", dest="main_templates", action="append", required=True, type=Path
    )
    parser.add_argument("--depleted-template", required=True, type=Path)
    parser.add_argument("--prompt-template", required=True, type=Path)
    parser.add_argument("--forced-template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if len(args.main_templates) != 4:
        parser.error("exactly four --main-template entries are required")
    print(json.dumps(run(args), sort_keys=True))


if __name__ == "__main__":
    main()
