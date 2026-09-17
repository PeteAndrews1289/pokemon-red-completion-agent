"""Prospective paired TRAIN pilot on four authenticated fresh Red origins.

Each origin contributes one matchup reversal and one resource/party variation.
Earlier 28 scenarios are authenticated again without replay. This pilot neither
opens DEVELOPMENT nor promotes the fitted policy.
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

from pokemon_red_completion.battle_practice_factory import BattlePracticeSpec
from pokemon_red_completion.battle_scenario_capture import OBSERVATION_SCHEMA_V2

ROOT = Path(__file__).resolve().parents[1]
REVERSAL_OPPONENTS = (
    (177, 7),  # Pikachu: Ground immunity -> Water weakness.
    (153, 1),  # Squirtle: Rock weakness -> Grass resistance.
    (176, 4),  # Bulbasaur: Water weakness -> Fire resistance.
    (177, 7),  # Charmander: Grass weakness -> Water resistance.
)


def prospective_cases(
    templates: tuple[dict[str, object], ...],
) -> tuple[tuple[int, str, dict[str, object]], ...]:
    """Freeze eight distinct actor-visible configurations before execution."""

    if len(templates) != 4:
        raise ValueError("pilot needs four base MAIN practice templates")
    cases = []
    for root_index, template in enumerate(templates):
        reversal = deepcopy(template)
        species_id, national_number = REVERSAL_OPPONENTS[root_index]
        reversal["opponent_species_ref"] = f"pokemon.red.gb.us.rev0:species:{species_id:03d}"
        reversal["opponent_national_number"] = national_number
        cases.append((root_index, "type-reversal", reversal))

        resources = deepcopy(template)
        resources["actor_hp"] = 8
        moves = resources.get("actor_moves")
        if not isinstance(moves, list) or len(moves) < 2:
            raise ValueError("resource contrast has no attack alternatives")
        moves[0]["pp"] = 1
        if root_index < 2:
            reserves = resources.get("party_reserves")
            if not isinstance(reserves, list) or len(reserves) < 2:
                raise ValueError("party-size contrast has no reserve alternatives")
            resources["party_reserves"] = reserves[:1]
        else:
            resources["opponent_party_count"] = 1
            resources.pop("opponent_reserves", None)
        cases.append((root_index, "scarce-resource", resources))
    return tuple(cases)


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.output.exists():
        raise ValueError("trainer paired pilot output must be new")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit paired trainer pilot before execution")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    summary = json.loads((args.previous / "summary.json").read_bytes())
    previous_plan = json.loads((args.previous / "fit-plan.json").read_bytes())
    old_cases = previous_plan.get("scenarios")
    if (
        summary.get("status") != "qualified_train_fit_completed"
        or summary.get("source_roots") != 4
        or summary.get("total_admitted_contexts") != 28
        or not isinstance(old_cases, list)
        or len(old_cases) != 28
    ):
        raise ValueError("paired pilot needs the admitted 28-context predecessor")
    rom = original._binding(args.rom)
    if rom["sha256"] != original.ROM_SHA256:
        raise ValueError("paired pilot cartridge differs")
    frozen = original._binding(args.frozen_model)
    if len(args.main_templates) != 4:
        raise ValueError("paired pilot needs four original MAIN templates")
    templates = []
    for path in args.main_templates:
        template = json.loads(path.read_bytes())
        if (
            template.get("schema") != materializer.TRAINER_SCHEMA
            or template.get("observation_schema") != OBSERVATION_SCHEMA_V2
            or not isinstance(template.get("practice"), dict)
        ):
            raise ValueError("paired pilot template differs")
        templates.append(template["practice"])
    recipes = prospective_cases(tuple(templates))
    sources = original._source_rows(args.batch)
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    stage = "start"
    completed = 0
    new_cases = []
    try:
        for root_index, name, practice in recipes:
            source, receipt = sources[root_index]
            source_state = source / "source.state"
            source_manifest = source / "source.state.json"
            root = str(receipt["source_id"])
            practice["source_state_sha256"] = original._binding(source_state)["sha256"]
            practice["root_lineage_id"] = root
            BattlePracticeSpec.from_dict(practice)
            directory = args.output / f"root-{root_index + 1:02d}-{name}"
            directory.mkdir(mode=0o700, exist_ok=False)
            stage = f"{root}:{name}:materialize"
            materialized = directory / "materialized"
            materialize_plan = directory / "materialize-plan.json"
            original._write(
                materialize_plan,
                {
                    "schema": materializer.TRAINER_SCHEMA,
                    "source_commit": commit,
                    "rom": rom,
                    "source_state": original._binding(source_state),
                    "source_capture_manifest": original._binding(source_manifest),
                    "practice": practice,
                    "observation_schema": OBSERVATION_SCHEMA_V2,
                    "output": str(materialized),
                },
            )
            materializer.run(materialize_plan, check_only=True)
            materializer.run(materialize_plan)

            stage = f"{root}:{name}:branches"
            branch_output = directory / "baseline"
            baseline_plan = directory / "baseline-plan.json"
            original._write(
                baseline_plan,
                {
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
                    "output": str(branch_output),
                },
            )
            baseline.run(baseline_plan, check_only=True)
            baseline.run(baseline_plan)
            trials = []
            for offset in original.OFFSETS:
                branch = branch_output / f"timing-{offset:02d}"
                trials.append(
                    {
                        "choices": original._binding(branch / "matched-choices.json"),
                        "plan": original._binding(branch / "matched-plan.json"),
                        "branch_log_prefix": "matched-branch",
                    }
                )
            new_cases.append(
                {
                    "state": original._binding(materialized / "assisted.state"),
                    "manifest": original._binding(materialized / "assisted.state.json"),
                    "fresh_source_state": original._binding(source_state),
                    "fresh_source_manifest": original._binding(source_manifest),
                    "origin_state": original._binding(source / "origin.state"),
                    "origin_receipt": original._binding(source / "outcome.json"),
                    "timing_offsets": list(original.OFFSETS),
                    "trials": trials,
                }
            )
            completed += 1
        stage = "admission"
        fit_plan = args.output / "fit-plan.json"
        original._write(
            fit_plan,
            {
                "schema": fitter.SCHEMA,
                "source_commit": commit,
                "seed": 22092026,
                "scenarios": old_cases + new_cases,
                "output": str(args.output / "fit"),
            },
        )
        admitted = fitter.run(fit_plan, check_only=True)
        stage = "fit"
        fitted = fitter.run(fit_plan)
    except Exception as error:
        original._write(
            args.output / "failure.json",
            {
                "schema": "pokemon.red.trainer-distinct-pilot-failure.v1",
                "stage": stage,
                "completed_new_contexts": completed,
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise
    result = {
        "schema": "pokemon.red.trainer-distinct-pilot-result.v1",
        "status": "train_fit_completed",
        "source_commit": commit,
        "new_contexts": completed,
        "reused_contexts_not_replayed": len(old_cases),
        "total_contexts": len(old_cases) + completed,
        "admission": admitted,
        "fit": {
            "model_sha256": fitted["model_sha256"],
            "training_diagnostics": fitted["training_diagnostics"],
        },
        "development_opened": False,
        "authority_promotions": 0,
        "full_game_runs": 0,
    }
    original._write(args.output / "summary.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--frozen-model", type=Path, required=True)
    parser.add_argument(
        "--main-template", dest="main_templates", type=Path, action="append", required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(parser.parse_args()), sort_keys=True))


if __name__ == "__main__":
    main()
