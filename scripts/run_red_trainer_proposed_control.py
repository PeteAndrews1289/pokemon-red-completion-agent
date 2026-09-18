"""One authenticated control-only successor and bounded TRAIN comparisons."""

from __future__ import annotations

import argparse
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import materialize_red_teacher_battle_practice as materializer
import run_fresh_red_trainer_curriculum as common
import run_red_trainer_practice_model as player
from run_red_trainer_terminal_curriculum import retained_targets, terminal_anchor_targets

from pokemon_red_completion.red_trainer_practice_fit import (
    TrainerPracticeThreeHeadModel,
    fit_trainer_practice_three_heads,
    refit_trainer_proposed_control,
    summarize_trainer_practice_training,
)
from pokemon_red_completion.red_trainer_proposed_control import PROPOSED_CONTROL_SCHEMA

ROOT = Path(__file__).resolve().parents[1]
FROZEN_SHA = "2d944149bf2c61b6e498ff677222414e59f131b4adc53065e737b26e8f7b81d6"


def fresh_recipe(old: dict, *, expected_return: bool = False) -> dict:
    plan = deepcopy(old)
    practice = plan["practice"]
    practice.update(actor_hp=42, opponent_hp=56, opponent_level=30)
    if expected_return:
        practice.update(actor_hp=40, opponent_hp=58)
    for member in practice["opponent_reserves"]:
        member["level"] = 30
    return plan


def run(args):
    expected_return = getattr(args, "expected_return", False)
    expected_sha = (
        "1925a27a7c73f4d49833f45527849b5ce9dd92e103e737d8e777a5708fa33e54"
        if expected_return
        else FROZEN_SHA
    )
    seed = 2026091804 if expected_return else 2026091803
    public_plan = (
        "red-trainer-return-objective-plan-2026-09-17.json"
        if expected_return
        else "red-trainer-proposed-control-plan-2026-09-17.json"
    )
    terminal_model = args.terminal_model if expected_return else args.frozen_model
    if (
        args.output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("control experiment requires committed source and new output")
    if common._binding(args.frozen_model)["sha256"] != expected_sha:
        raise ValueError("frozen component model differs")
    if expected_return and (
        terminal_model is None or common._binding(terminal_model)["sha256"] != FROZEN_SHA
    ):
        raise ValueError("terminal training source model differs")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    frozen = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.frozen_model.read_bytes()))
    ancestor = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.ancestor_model.read_bytes()))
    regression = json.loads(args.regression_plan.read_bytes())
    for key in ("rom", "capture_state", "capture_manifest"):
        player._bound_file(regression[key], key)
    if (
        regression["capture_state"]["sha256"]
        != "537a290a9cf91ec8d2d47751482ec93417b9de60b632a3574ffe1da72137a4fc"
    ):
        raise ValueError("known regression identity differs")
    recipes = [
        fresh_recipe(json.loads(p.read_bytes()), expected_return=expected_return)
        for p in sorted(
            args.frozen_model.parent.glob(
                "variant-*/materialize-plan.json"
                if expected_return
                else "reserved/*/materialize-plan.json"
            )
        )
    ]
    if len(recipes) != 8:
        raise ValueError("eight prospective variant recipes required")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    common._write(
        args.output / "plan.json",
        {
            "source_commit": revision,
            "frozen": common._binding(args.frozen_model),
            "ancestor": common._binding(args.ancestor_model),
            "terminal_model": common._binding(terminal_model),
            "prior": common._binding(args.prior_plan),
            "regression": common._binding(args.regression_plan),
            "fresh_recipes": recipes,
            "public_plan": common._binding(ROOT / "docs/evidence" / public_plan),
            "seed": seed,
            "training_objective": "expected_regret" if expected_return else "cross_entropy",
            "epochs": 1200,
            "fits": 1,
            "authority_promotions": 0,
        },
    )
    try:
        old = retained_targets(json.loads(args.prior_plan.read_bytes()))
        old_ids = {t["capture_id"] for t in old}
        inherited = terminal_anchor_targets(
            args.ancestor_model, set(ancestor.train_capture_ids) - old_ids
        )
        newer = terminal_anchor_targets(
            terminal_model,
            set(frozen.train_capture_ids) - old_ids - {t["capture_id"] for t in inherited},
        )
        targets = old + inherited + newer
        if (len(old), len(inherited), len(newer)) != (52, 48, 80):
            raise ValueError("exact 180-context curriculum required")
        print(json.dumps({"authenticated_contexts": len(targets)}), flush=True)
        fitted = (
            fit_trainer_practice_three_heads(
                targets,
                seed=seed,
                epochs=1200,
                require_corpus_floor=False,
                warm_start_move=frozen,
                warm_start_move_epochs=1200,
                control_target_mode="fitted_components",
                control_input_schema=PROPOSED_CONTROL_SCHEMA,
                training_objective="expected_regret",
            )
            if expected_return
            else refit_trainer_proposed_control(targets, frozen, seed=seed, epochs=1200)
        )
        model_path = args.output / "model.json"
        common._write(model_path, fitted.to_dict())
        reports = {
            name: summarize_trainer_practice_training(rows, fitted)
            for name, rows in (
                ("original44", old[:44]),
                ("retained52", old),
                ("inherited_terminal", inherited),
                ("new_terminal", newer),
            )
        }
        common._write(
            args.output / "fit-receipt.json",
            {"model": common._binding(model_path), "reports": reports, "fits": 1},
        )
        print(
            json.dumps(
                {"fit_complete": True, "composed_regret": reports["retained52"]["composed_action"]}
            ),
            flush=True,
        )
        regression.update(
            source_commit=revision,
            outcome_model=common._binding(model_path),
            output=str(args.output / "regression"),
        )
        rp = args.output / "regression-plan.json"
        common._write(rp, regression)
        regression_result = player.run(rp)
        print(json.dumps({"regression": regression_result}), flush=True)
        evaluations = []
        for index, recipe in enumerate(recipes):
            directory = args.output / f"variant-{index:02d}"
            directory.mkdir(mode=0o700)
            recipe.update(source_commit=revision, output=str(directory / "materialized"))
            path = directory / "materialize-plan.json"
            common._write(path, recipe)
            materializer.run(path, check_only=True)
            materializer.run(path)
            state = directory / "materialized" / "assisted.state"
            for name, model in (("frozen", args.frozen_model), ("candidate", model_path)):
                path = directory / f"{name}-plan.json"
                common._write(
                    path,
                    {
                        "schema": player.OUTCOME_SCHEMA,
                        "source_commit": revision,
                        "rom": recipe["rom"],
                        "outcome_model": common._binding(model),
                        "capture_state": common._binding(state),
                        "capture_manifest": common._binding(state.with_suffix(".state.json")),
                        "max_decisions": 160,
                        "maximum_frames": 240000,
                        "opening_idle_frames": 4 if expected_return else 2,
                        "output": str(directory / name),
                    },
                )
                result = player.run(path)
                evaluations.append({"case": index, "arm": name, **result})
            print(json.dumps({"paired_variants_completed": index + 1}), flush=True)
        result = {
            "reports": reports,
            "evaluations": evaluations,
            "regression": regression_result,
            "status": "completed_train_only",
            "fits": 1,
            "authority_promotions": 0,
        }
        common._write(args.output / "summary.json", result)
        return result
    except Exception as error:
        common._write(
            args.output / "failure.json", {"type": type(error).__name__, "error": str(error)}
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("frozen-model", "ancestor-model", "prior-plan", "regression-plan", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--expected-return", action="store_true")
    parser.add_argument("--terminal-model", type=Path)
    run(parser.parse_args())
