"""One predeclared broader-data fit; old retention and narrow competence stay gated."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import run_fresh_red_trainer_curriculum as common
from run_red_trainer_broad_probe import CANDIDATE_SHA
from run_red_trainer_budgeted_fit import composed_offset
from run_red_trainer_retention import admitted_cache, examples, reports
from run_red_trainer_terminal_curriculum import terminal_anchor_targets

from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_budgeted_fit import (
    RegretBudget,
    fit_budgeted_head,
    selected_regret,
)
from pokemon_red_completion.red_trainer_practice_fit import (
    TrainerPracticeThreeHeadModel,
    summarize_trainer_practice_training,
)

ROOT = Path(__file__).resolve().parents[1]
BROADER_MODEL_SHA = "f8d9be1a76dd1475e23db1080609b8318a052e1f7fa26ee4201d7f489dd9d241"


def admitted_supply(supply, roots, old_ids, *, late=False):
    receipt = json.loads((supply / "collection.json").read_bytes())
    if receipt["status"] != "terminal_collection_complete_train_only" or receipt["fits"] != 0:
        raise ValueError("supply is not an unfitted terminal collection")
    if (
        common._binding(supply / "plan.json") != receipt["plan"]
        or common._binding(supply / "targets.json") != receipt["targets"]
    ):
        raise ValueError("supply binding differs")
    plan = json.loads((supply / "plan.json").read_bytes())
    if (
        plan.get("profile") != ("late" if late else "broad")
        or plan.get("supply_seed") != (2026091904 if late else 2026091902)
        or plan["frozen_model"]["sha256"] != (BROADER_MODEL_SHA if late else CANDIDATE_SHA)
    ):
        raise ValueError("supply recipe or trajectory differs")
    if late and (
        plan.get("capture_decisions") != []
        or plan.get("capture_semantics")
        != ["first_forced_switch", "first_switch_prompt", "first_last_opponent", "first_last_ally"]
    ):
        raise ValueError("late supply does not declare semantic boundary coverage")
    declared = json.loads((supply / "targets.json").read_bytes())
    ids = {t["capture_id"] for t in declared}
    if (
        len(declared) != receipt["new_terminal_contexts"]
        or len(ids) != len(declared)
        or len(declared) < 24
        or ids & old_ids
        or any(t["partition"] != "train" or t["root_lineage_id"] not in roots for t in declared)
    ):
        raise ValueError("supply TRAIN inventory differs")
    # Reconstruct every target from its complete per-timing branch logs, not a
    # caller's editable JSON summary. The argument is a directory locator only.
    targets = terminal_anchor_targets(supply / "collection-anchor", ids)
    if {t["capture_id"]: t for t in targets} != {t["capture_id"]: t for t in declared}:
        raise ValueError("supply differs from measured complete branches")
    return targets


def broad_gates(before, after, before_broad, after_broad):
    def regret(report, group, head):
        return report[group][head]["model_mean_train_regret"]

    return {
        "retained52_switch_retained": regret(after, "retained52", "switch")
        <= regret(before, "retained52", "switch"),
        "narrow_switch_retained": regret(after, "terminal128", "switch")
        <= regret(before, "terminal128", "switch"),
        "original44_move": regret(after, "original44", "move") <= 0.0554,
        "retained52_move": regret(after, "retained52", "move") <= 0.0648,
        "retained52_composed": regret(after, "retained52", "composed_action") <= 0.1609,
        "narrow_move_retained": regret(after, "terminal128", "move")
        <= regret(before, "terminal128", "move"),
        "narrow_composed_retained": regret(after, "terminal128", "composed_action")
        <= regret(before, "terminal128", "composed_action"),
        "new80_composed_retained": regret(after, "new80", "composed_action")
        <= regret(before, "new80", "composed_action"),
        "broad_move_no_regression": after_broad["move"]["model_mean_train_regret"]
        <= before_broad["move"]["model_mean_train_regret"],
        "broad_composed_improves_ten_percent": after_broad["composed_action"][
            "model_mean_train_regret"
        ]
        < 0.9 * before_broad["composed_action"]["model_mean_train_regret"],
    }


def prior_broad_gates(before, after):
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("late fit lacks prior broad retention measurements")
    return {
        "prior_broad_" + name + "_retained": after[name]["model_mean_train_regret"]
        <= before[name]["model_mean_train_regret"] + 1e-9
        for name in ("move", "switch", "composed_action")
    }


def run(args):
    late = getattr(args, "late", False)
    if (
        args.output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("broad fit needs committed code and a new output")
    _, retained = admitted_cache(args.audit)
    if common._binding(args.initial)["sha256"] != (BROADER_MODEL_SHA if late else CANDIDATE_SHA):
        raise ValueError("broad fit initial candidate differs")
    model = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.initial.read_bytes()))
    prior_broad = (
        admitted_supply(
            args.prior_supply, set(model.train_root_ids), {t["capture_id"] for t in retained}
        )
        if late
        else []
    )
    anchors = retained + prior_broad
    if set(model.train_capture_ids) != {t["capture_id"] for t in anchors}:
        raise ValueError("initial model TRAIN inventory differs")
    added = admitted_supply(
        args.supply, set(model.train_root_ids), set(model.train_capture_ids), late=late
    )
    print(json.dumps({"authenticated_new_contexts": len(added)}), flush=True)
    catalog = PokemonRedBattleCatalog()
    before = reports(retained, model, catalog)
    before_broad = summarize_trainer_practice_training(
        added, model, catalog=catalog, initial_move_model=model.move
    )
    initial = model
    before_prior = (
        summarize_trainer_practice_training(
            prior_broad, model, catalog=catalog, initial_move_model=model.move
        )
        if late
        else None
    )
    args.output.mkdir(parents=True, mode=0o700)
    common._write(
        args.output / "plan.json",
        {
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip(),
            "initial": common._binding(args.initial),
            "profile": "late" if late else "broad",
            "prior_supply": common._binding(args.prior_supply / "collection.json")
            if late
            else None,
            "supply": common._binding(args.supply / "collection.json"),
            "audit": common._binding(args.audit / "manifest.json"),
            "epochs_per_head": 2400,
            "learning_rate": 0.005,
            "head_order": ["move", "switch", "control"],
            "fits": 1,
            "loss": "equal-group weight all prior TRAIN and new TRAIN; measured expected regret",
            "selection": (
                "feasible minimum broad selected regret, then broad expected regret, "
                "then earliest epoch"
            ),
            "budgets": (
                "unchanged original44/retained52; retain initial narrow128 move/switch/composed "
                "and new80 composed; old52 switch no regression; for late supply also retain "
                "all prior broad move, switch and composed regret"
            ),
            "gate": (
                "all retention checks, at least10% lower broad composed regret, "
                "broad move no regression"
            ),
            "probe_data_used": False,
            "development_data_used": False,
            "authority_promotions": 0,
        },
    )
    started = time.monotonic()
    for name in ("move", "switch", "control"):
        groups = {
            key: examples(rows, model, catalog)[name]
            for key, rows in (
                ("original44", retained[:44]),
                ("retained52", retained[:52]),
                ("terminal128", retained[52:]),
                ("new80", retained[100:]),
                ("retained180", retained),
                ("anchors", anchors),
                ("broad", added),
            )
        }
        if name == "move":
            narrow = tuple(examples(retained[52:], initial, catalog)[name])
            budgets = (
                RegretBudget("original44_move", tuple(groups["original44"]), 0.0554),
                RegretBudget("retained52_move", tuple(groups["retained52"]), 0.0648),
                RegretBudget(
                    "terminal128_move",
                    tuple(groups["terminal128"]),
                    selected_regret(initial.move, narrow),
                ),
            )
        elif name == "switch":
            budgets = tuple(
                RegretBudget(
                    key + "_switch",
                    tuple(groups[key]),
                    selected_regret(initial.switch, tuple(groups[key])),
                )
                for key in ("retained52", "terminal128")
            )
        else:
            budgets = tuple(
                RegretBudget(
                    key + "_composed", tuple(groups[key]), limit, composed_offset(rows, groups[key])
                )
                for key, rows, limit in (
                    ("retained52", retained[:52], 0.1609),
                    (
                        "terminal128",
                        retained[52:],
                        before["terminal128"]["composed_action"]["model_mean_train_regret"] + 1e-9,
                    ),
                    (
                        "new80",
                        retained[100:],
                        before["new80"]["composed_action"]["model_mean_train_regret"] + 1e-9,
                    ),
                )
            )
        if late:
            prior_rows = tuple(examples(prior_broad, model, catalog)[name])
            limit = before_prior["composed_action" if name == "control" else name][
                "model_mean_train_regret"
            ]
            offset = composed_offset(prior_broad, prior_rows) if name == "control" else 0.0
            budgets += (RegretBudget("prior_broad_" + name, prior_rows, limit + 1e-9, offset),)
        fitted, receipt = fit_budgeted_head(
            getattr(model, name), tuple(groups["broad"]), tuple(groups["anchors"]), budgets
        )
        common._write(args.output / f"{name}-optimizer.json", receipt)
        print(
            json.dumps({"head": name, **{k: v for k, v in receipt.items() if k != "history"}}),
            flush=True,
        )
        if fitted is None:
            common._write(
                args.output / "result.json",
                {"train_qualified": False, "reason": "no_feasible_checkpoint", "head": name},
            )
            return
        model = replace(model, **{name: fitted})
        common._write(args.output / f"after-{name}-model.json", model.to_dict())
    model = replace(model, train_capture_ids=tuple(t["capture_id"] for t in anchors + added))
    after = reports(retained, model, catalog)
    after_broad = summarize_trainer_practice_training(
        added, model, catalog=catalog, initial_move_model=initial.move
    )

    checks = broad_gates(before, after, before_broad, after_broad)
    after_prior = None
    if late:
        after_prior = summarize_trainer_practice_training(
            prior_broad, model, catalog=catalog, initial_move_model=initial.move
        )
        checks.update(prior_broad_gates(before_prior, after_prior))
    common._write(args.output / "model.json", model.to_dict())
    result = {
        "before": before,
        "after": after,
        "before_broad": before_broad,
        "after_broad": after_broad,
        "before_prior_broad": before_prior,
        "after_prior_broad": after_prior,
        "gates": checks,
        "train_qualified": all(checks.values()),
        "natural_qualified": False,
        "model": common._binding(args.output / "model.json"),
        "fits": 1,
        "new_contexts": len(added),
        "elapsed_seconds": time.monotonic() - started,
        "authority_promotions": 0,
    }
    common._write(args.output / "result.json", result)
    print(
        json.dumps({k: v for k, v in result.items() if not k.startswith(("before", "after"))}),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("audit", "initial", "supply", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--late", action="store_true")
    parser.add_argument("--prior-supply", type=Path)
    run(parser.parse_args())
