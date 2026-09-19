"""One policy-bound H successor; immutable teacher-return retention constraints."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import run_fresh_red_trainer_curriculum as common
from run_red_trainer_broad_fit import LATE_MODEL_SHA, admitted_supply
from run_red_trainer_budgeted_fit import composed_offset
from run_red_trainer_learner_continuation import POLICY, admitted_policy_supply
from run_red_trainer_retention import admitted_cache, examples

from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_budgeted_fit import RegretBudget, fit_budgeted_head
from pokemon_red_completion.red_trainer_practice_fit import (
    TrainerPracticeThreeHeadModel,
    summarize_trainer_practice_training,
)

ROOT = Path(__file__).resolve().parents[1]


def retention_limits(before):
    limits = {
        ("original44", "move"): 0.0554,
        ("retained52", "move"): 0.0648,
        ("retained52", "composed_action"): 0.1609,
    }
    for group, heads in (
        ("retained52", ("switch",)),
        ("terminal128", ("move", "switch", "composed_action")),
        ("new80", ("composed_action",)),
        ("prior48", ("move", "switch", "composed_action")),
        ("late90", ("move", "switch", "composed_action")),
    ):
        for head in heads:
            limits[group, head] = before[group][head]["model_mean_train_regret"] + 1e-9
    return limits


def learning_checks(before_new, after_new, after_old, limits):
    checks = {
        f"{group}_{head}_retained": after_old[group][head]["model_mean_train_regret"] <= limit
        for (group, head), limit in limits.items()
    }
    checks["policy_bound_composed_improves_ten_percent"] = (
        after_new["composed_action"]["model_mean_train_regret"]
        < 0.9 * before_new["composed_action"]["model_mean_train_regret"]
    )
    return checks


def run(args):
    if (
        args.output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("one fit requires committed code and new output")
    if common._binding(args.initial)["sha256"] != LATE_MODEL_SHA:
        raise ValueError("initial is not frozen H")
    initial = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.initial.read_bytes()))
    _, retained = admitted_cache(args.audit)
    roots = set(initial.train_root_ids)
    prior = admitted_supply(args.prior_supply, roots, {t["capture_id"] for t in retained})
    late = admitted_supply(
        args.late_supply, roots, {t["capture_id"] for t in retained + prior}, late=True
    )
    late += admitted_supply(
        args.late_main_supply,
        roots,
        {t["capture_id"] for t in retained + prior + late},
        late=True,
        late_main=True,
    )
    old = retained + prior + late
    if len(old) != 318 or set(initial.train_capture_ids) != {t["capture_id"] for t in old}:
        raise ValueError("frozen H TRAIN inventory differs")
    added = admitted_policy_supply(args.supply)
    ids = {t["capture_id"] for t in added}
    if (
        not ids <= set(initial.train_capture_ids)
        or not {t["root_lineage_id"] for t in added} <= roots
    ):
        raise ValueError("learner-continuation inventory differs")
    # For these sixteen states optimize the new policy's values only. Their old
    # teacher values remain in retention checks, not contradictory training rows.
    anchors = [t for t in old if t["capture_id"] not in ids]
    groups = {
        "original44": retained[:44],
        "retained52": retained[:52],
        "terminal128": retained[52:],
        "new80": retained[100:],
        "prior48": prior,
        "late90": late,
    }
    catalog = PokemonRedBattleCatalog()

    def report(rows, model):
        return summarize_trainer_practice_training(
            rows, model, catalog=catalog, initial_move_model=initial.move
        )

    before = {name: report(rows, initial) for name, rows in groups.items()}
    before_new = report(added, initial)
    limits = retention_limits(before)
    args.output.mkdir(mode=0o700)
    common._write(
        args.output / "plan.json",
        {
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip(),
            "initial": common._binding(args.initial),
            "policy_id": POLICY,
            "policy_supply": common._binding(args.supply / "collection.json"),
            "retention_sources": [
                common._binding(p)
                for p in (
                    args.audit / "manifest.json",
                    args.prior_supply / "collection.json",
                    args.late_supply / "collection.json",
                    args.late_main_supply / "collection.json",
                )
            ],
            "limits": {f"{group}:{head}": limit for (group, head), limit in limits.items()},
            "epochs_per_head": 2400,
            "learning_rate": 0.005,
            "objective": "pairwise_regret",
            "fits": 1,
            "optimization_teacher_contexts": len(anchors),
            "learner_value_contexts": len(added),
            "unique_physical_contexts": 318,
            "new_physical_contexts": 0,
            "development_data_used": False,
            "authority_promotions": 0,
        },
    )
    started = time.monotonic()
    model = initial
    for name in ("move", "switch", "control"):
        metric = "composed_action" if name == "control" else name
        budgets = []
        for (group, head), limit in limits.items():
            if head != metric:
                continue
            rows = tuple(examples(groups[group], model, catalog)[name])
            budgets.append(
                RegretBudget(
                    group + "_" + head,
                    rows,
                    limit,
                    composed_offset(groups[group], rows) if name == "control" else 0.0,
                )
            )
        fitted, receipt = fit_budgeted_head(
            getattr(model, name),
            tuple(examples(added, model, catalog)[name]),
            tuple(examples(anchors, model, catalog)[name]),
            tuple(budgets),
            objective="pairwise_regret",
        )
        common._write(args.output / f"{name}-optimizer.json", receipt)
        print(
            json.dumps({"head": name, **{k: v for k, v in receipt.items() if k != "history"}}),
            flush=True,
        )
        if fitted is None:
            common._write(
                args.output / "result.json",
                {
                    "train_qualified": False,
                    "reason": "no_feasible_checkpoint",
                    "head": name,
                    "fits": 1,
                    "authority_promotions": 0,
                },
            )
            return
        model = replace(model, **{name: fitted})
        common._write(args.output / f"after-{name}-model.json", model.to_dict())
    after = {name: report(rows, model) for name, rows in groups.items()}
    after_new = report(added, model)
    checks = learning_checks(before_new, after_new, after, limits)
    common._write(args.output / "model.json", model.to_dict())
    result = {
        "before": before,
        "after": after,
        "before_policy_bound": before_new,
        "after_policy_bound": after_new,
        "gates": checks,
        "train_qualified": all(checks.values()),
        "fits": 1,
        "model": common._binding(args.output / "model.json"),
        "new_policy_conditioned_measurements": 16,
        "new_unique_physical_contexts": 0,
        "unique_physical_contexts": 318,
        "elapsed_seconds": time.monotonic() - started,
        "natural_qualified": False,
        "authority_promotions": 0,
    }
    common._write(args.output / "result.json", result)
    print(json.dumps({"train_qualified": result["train_qualified"], "gates": checks}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "audit",
        "initial",
        "prior-supply",
        "late-supply",
        "late-main-supply",
        "supply",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
