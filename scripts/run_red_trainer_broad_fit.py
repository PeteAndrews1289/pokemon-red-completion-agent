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


def admitted_supply(supply, roots, old_ids):
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
        plan.get("profile") != "broad"
        or plan.get("supply_seed") != 2026091902
        or plan["frozen_model"]["sha256"] != CANDIDATE_SHA
    ):
        raise ValueError("supply recipe or trajectory differs")
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


def run(args):
    if (
        args.output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("broad fit needs committed code and a new output")
    _, retained = admitted_cache(args.audit)
    if common._binding(args.initial)["sha256"] != CANDIDATE_SHA:
        raise ValueError("broad fit initial candidate differs")
    model = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.initial.read_bytes()))
    if set(model.train_capture_ids) != {t["capture_id"] for t in retained}:
        raise ValueError("initial model TRAIN inventory differs")
    added = admitted_supply(args.supply, set(model.train_root_ids), set(model.train_capture_ids))
    print(json.dumps({"authenticated_new_contexts": len(added)}), flush=True)
    catalog = PokemonRedBattleCatalog()
    before = reports(retained, model, catalog)
    before_broad = summarize_trainer_practice_training(
        added, model, catalog=catalog, initial_move_model=model.move
    )
    initial = model
    args.output.mkdir(parents=True, mode=0o700)
    common._write(
        args.output / "plan.json",
        {
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip(),
            "initial": common._binding(args.initial),
            "supply": common._binding(args.supply / "collection.json"),
            "audit": common._binding(args.audit / "manifest.json"),
            "epochs_per_head": 2400,
            "learning_rate": 0.005,
            "head_order": ["move", "switch", "control"],
            "fits": 1,
            "loss": "equal-group weight retained180 and new broad TRAIN; measured expected regret",
            "selection": (
                "feasible minimum broad selected regret, then broad expected regret, "
                "then earliest epoch"
            ),
            "budgets": (
                "unchanged original44/retained52; retain initial narrow128 move/switch/composed "
                "and new80 composed; old52 switch no regression"
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
        fitted, receipt = fit_budgeted_head(
            getattr(model, name), tuple(groups["broad"]), tuple(groups["retained180"]), budgets
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
    model = replace(model, train_capture_ids=tuple(t["capture_id"] for t in retained + added))
    after = reports(retained, model, catalog)
    after_broad = summarize_trainer_practice_training(
        added, model, catalog=catalog, initial_move_model=initial.move
    )

    checks = broad_gates(before, after, before_broad, after_broad)
    common._write(args.output / "model.json", model.to_dict())
    result = {
        "before": before,
        "after": after,
        "before_broad": before_broad,
        "after_broad": after_broad,
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
    run(parser.parse_args())
