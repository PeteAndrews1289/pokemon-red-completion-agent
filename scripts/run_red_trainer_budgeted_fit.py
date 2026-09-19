"""One authenticated TRAIN-only attack/control fit under unchanged retention limits."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import run_fresh_red_trainer_curriculum as common
from run_red_trainer_retention import admitted_cache, examples, reports

from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_budgeted_fit import RegretBudget, fit_budgeted_head
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel

ROOT = Path(__file__).resolve().parents[1]
INITIAL_SHA = "9f2aa62d01b72217931a3fab4b60e69522734f69b7eeab43b90e46498c34cbbc"


def composed_offset(targets, rows):
    """Unavoidable child-proposal regret; adding control regret is exact composition."""
    control_targets = [t for t in targets if "control" in t["heads"]]
    if len(control_targets) != len(rows) or not rows:
        raise ValueError("control composition inventory differs")
    return sum(
        max(t["heads"]["control"]["returns"]) - max(row.mean_returns)
        for t, row in zip(control_targets, rows, strict=True)
    ) / len(rows)


def run(audit: Path, initial: Path, output: Path):
    if (
        output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("budgeted fit requires new output and committed source")
    _, targets = admitted_cache(audit)
    if common._binding(initial)["sha256"] != INITIAL_SHA:
        raise ValueError("declared initial model differs")
    model = TrainerPracticeThreeHeadModel.from_dict(json.loads(initial.read_bytes()))
    if set(model.train_capture_ids) != {t["capture_id"] for t in targets}:
        raise ValueError("initial TRAIN inventory differs")
    catalog = PokemonRedBattleCatalog()
    before = reports(targets, model, catalog)
    output.mkdir(parents=True, mode=0o700)
    common._write(
        output / "plan.json",
        {
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip(),
            "manifest": common._binding(audit / "manifest.json"),
            "initial": common._binding(initial),
            "plan": common._binding(
                ROOT / "docs/evidence/red-battler-readiness-plan-2026-09-19.json"
            ),
            "epochs_per_head": 2400,
            "learning_rate": 0.005,
            "fits": 1,
            "head_order": ["move", "control"],
            "switch_frozen": True,
            "loss": "equal-group old52 and terminal128 measured expected regret",
            "checkpoint_selection": (
                "TRAIN-only feasible minimum terminal argmax regret, then expected regret"
            ),
            "new_emulator_runs": 0,
        },
    )
    started = time.monotonic()
    for name in ("move", "control"):
        groups = {
            key: examples(rows, model, catalog)[name]
            for key, rows in (
                ("original44", targets[:44]),
                ("retained52", targets[:52]),
                ("terminal128", targets[52:]),
                ("new80", targets[100:]),
            )
        }
        if name == "move":
            budgets = (
                RegretBudget("original44_move", tuple(groups["original44"]), 0.0554),
                RegretBudget("retained52_move", tuple(groups["retained52"]), 0.0648),
                RegretBudget(
                    "new80_move",
                    tuple(groups["new80"]),
                    before["new80"]["move"]["model_mean_train_regret"],
                ),
            )
        else:
            budgets = tuple(
                RegretBudget(
                    key + "_composed",
                    tuple(groups[key]),
                    maximum,
                    composed_offset(rows, groups[key]),
                )
                for key, rows, maximum in (
                    ("retained52", targets[:52], 0.1609),
                    (
                        "new80",
                        targets[100:],
                        before["new80"]["composed_action"]["model_mean_train_regret"],
                    ),
                )
            )
        fitted, receipt = fit_budgeted_head(
            getattr(model, name),
            tuple(groups["terminal128"]),
            tuple(groups["retained52"]),
            budgets,
        )
        common._write(output / f"{name}-optimizer.json", receipt)
        print(
            json.dumps({"head": name, **{k: v for k, v in receipt.items() if k != "history"}}),
            flush=True,
        )
        if fitted is None:
            common._write(
                output / "result.json",
                {"train_qualified": False, "reason": "no_feasible_checkpoint", "head": name},
            )
            return
        model = replace(model, **{name: fitted})
        common._write(output / f"after-{name}-model.json", model.to_dict())
    after = reports(targets, model, catalog)

    def regret(report, group, head):
        return report[group][head]["model_mean_train_regret"]

    checks = {
        "original44_move": regret(after, "original44", "move") <= 0.0554,
        "retained52_move": regret(after, "retained52", "move") <= 0.0648,
        "retained52_composed": regret(after, "retained52", "composed_action") <= 0.1609,
        "terminal128_move_improves_ten_percent": regret(after, "terminal128", "move")
        < 0.9 * regret(before, "terminal128", "move"),
        "terminal128_composed_improves_ten_percent": regret(after, "terminal128", "composed_action")
        < 0.9 * regret(before, "terminal128", "composed_action"),
        "new80_move_no_regression": regret(after, "new80", "move")
        <= regret(before, "new80", "move"),
        "new80_composed_no_regression": regret(after, "new80", "composed_action")
        <= regret(before, "new80", "composed_action"),
    }
    common._write(output / "model.json", model.to_dict())
    result = {
        "before": before,
        "after": after,
        "gates": checks,
        "train_qualified": all(checks.values()),
        "natural_qualified": False,
        "model": common._binding(output / "model.json"),
        "fits": 1,
        "elapsed_seconds": time.monotonic() - started,
        "authority_promotions": 0,
    }
    common._write(output / "result.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("before", "after")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--initial", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.audit, args.initial, args.output)
