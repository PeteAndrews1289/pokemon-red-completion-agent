"""One TRAIN-only successor: replace exact-state old continuation labels, not guards.

No emulator entry point. The completed485branches are reused; old evidence is immutable.
Nonoverlap retention is measured independently so gains on revised cases cannot hide loss.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path

from run_red_six_party_assisted_pilot import binding, revision, write_new
from run_red_trainer_budgeted_fit import composed_offset
from run_red_trainer_retention import examples
from run_red_trainer_switching_comparison import (
    MODEL_SHA256,
    admitted_measurements,
    bound,
    learning_checks,
    load_training,
    read,
    report,
)
from run_red_trainer_terminal_curriculum import terminal_anchor_targets

from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_budgeted_fit import RegretBudget, fit_budgeted_head
from pokemon_red_completion.red_trainer_practice_returns import tied_best_indices

SOURCE_PLAN_SHA = "fec73aa3bece64f97524bde62d5ebf771cfe97127682a9346592364ab187cc53"
SOURCE_RESULT_SHA = "4eaa69ae1d482ad8ae6c1b5789942c4ba4dea5a2351e6ac736c3a3c8ab2f317e"
SCHEMA = "pokemon.red.canonical-current-policy-targets.v1"
CLAIM = "red-trainer-canonical-J-20260920-claim.json"


def same_capture_replacements(old, current):
    """Only returns/proof hashes may differ: never replace an observation or legal set."""
    original = {r["capture_id"]: r for r in old}
    replacement = {r["capture_id"]: r for r in current}
    if (len(original) != len(old) or len(replacement) != len(current)
            or not replacement or not replacement.keys() <= original.keys()):
        raise ValueError("distinct existing captures required")
    audit = []
    for capture_id, row in replacement.items():
        prior = original[capture_id]
        def unchanged(r):
            return {k: v for k, v in r.items()
                    if k not in {"heads", "timing_target_sha256s"}}
        if (row["partition"] != "train" or unchanged(prior) != unchanged(row)
                or set(prior["heads"]) != set(row["heads"])):
            raise ValueError("replacement must keep exact TRAIN capture and observation")
        disagreement = {}
        for name, head in row["heads"].items():
            old_head = prior["heads"][name]
            if head["choice_refs"] != old_head["choice_refs"]:
                raise ValueError("replacement legal choices differ")
            first = set(tied_best_indices(tuple(old_head["returns"])))
            second = set(tied_best_indices(tuple(head["returns"])))
            disagreement[name] = not bool(first & second)
        audit.append({"capture_id": capture_id, "old_new_disjoint_best": disagreement})
    return replacement, audit


def retention_groups(groups, old, current):
    replacement, audit = same_capture_replacements(old, current)
    revised = {}
    for name, rows in groups.items():
        if any(r["capture_id"] in replacement for r in rows):
            revised[name + "-canonical"] = [replacement.get(r["capture_id"], r) for r in rows]
            revised[name + "-nonoverlap"] = [r for r in rows if r["capture_id"] not in replacement]
            if not revised[name + "-nonoverlap"]:
                raise ValueError("nonoverlap retention must remain nonempty")
        else:
            revised[name] = rows
    revised["all-nonoverlap"] = [r for r in old if r["capture_id"] not in replacement]
    return revised, audit


def prepare(comparison, output):
    commit = revision()
    if output.exists():
        raise ValueError("new successor directory required")
    source_plan = comparison / "amended-plan.json"
    source_result = comparison / "fit-result.json"
    if (binding(source_plan)["sha256"] != SOURCE_PLAN_SHA
            or binding(source_result)["sha256"] != SOURCE_RESULT_SHA):
        raise ValueError("only the completed rejected comparison is eligible")
    old_plan = read(binding(source_plan))
    current = admitted_measurements(comparison, old_plan)
    model, old, prior, groups, _ = load_training(bound(old_plan["model"]))
    verified_old = terminal_anchor_targets(Path(old_plan["source"]) / "model.json",
                                          {r["capture_id"] for r in current})
    revised, audit = retention_groups(groups, old, current)
    same_capture_replacements(verified_old, current)
    if len(current) != 16 or len(revised["all-nonoverlap"]) != 302:
        raise ValueError("fixed context inventory differs")
    catalog = PokemonRedBattleCatalog()
    before = {name: report(rows, model, catalog) for name, rows in revised.items()}
    limits = {f"{name}:{head}": values[head]["model_mean_train_regret"] + 1e-9
              for name, values in before.items() for head in ("switch", "composed_action")
              if values.get(head, {}).get("examples", 0)}
    for name in groups.keys() & revised.keys():
        for head in ("switch", "composed_action"):
            key = f"{name}:{head}"
            if key in old_plan["limits"] and limits[key] != old_plan["limits"][key]:
                raise ValueError("unaffected retention limit changed")
    current_ids = {r["capture_id"] for r in current}
    prior_ids = {r["capture_id"] for r in prior}
    anchors = [r for r in old if r["capture_id"] not in current_ids | prior_ids]
    anchors += [r for r in prior if r["capture_id"] not in current_ids]
    data = {"current": current, "anchors": anchors, "retention": revised, "audit": audit}
    output.mkdir(mode=0o700)
    write_new(output / "audited-targets.json", data)
    plan = {
        "schema": SCHEMA, "source_commit": commit, "model": old_plan["model"],
        "source_plan": binding(source_plan), "source_result": binding(source_result),
        "source_collection": binding(comparison / "collection.json"),
        "targets": binding(output / "audited-targets.json"),
        "initial_fit_plan": old_plan["initial_fit_plan"],
        "source_retention": old_plan["retention_sources"],
        "source_policy": old_plan["prior_policy_supply"],
        "output": str(output.resolve()), "claim": str((comparison.parent / CLAIM).resolve()),
        "retention_counts": {k: len(v) for k, v in revised.items()},
        "before_retention": before, "before_current": report(current, model, catalog),
        "limits": limits, "maximum_fits": 1, "head_order": ["switch", "control"],
        "epochs_per_head": 2400, "learning_rate": 0.005, "objective": "pairwise_regret",
        "minimum_composed_improvement_fraction": 0.1, "move_head_frozen": True,
        "reason": ("Exact-state J continuation returns replace historical teacher returns "
                   "only on16captures; every unrelated case remains separately protected "
                   "at J baseline without extra slack."),
        "new_gameplay": 0, "new_measurements": 0, "development_used": False,
        "authority_promotions": 0,
    }
    write_new(Path(plan["claim"]), plan)
    write_new(output / "plan.json", plan)
    return {"prepared": True, "retention_groups": plan["retention_counts"],
            "maximum_fits": 1, "new_gameplay": 0}


def fit(output):
    plan = read(binding(output / "plan.json"))
    if (plan["schema"] != SCHEMA or plan["source_commit"] != revision()
            or plan["output"] != str(output.resolve())
            or read(binding(Path(plan["claim"]))) != plan
            or plan["model"]["sha256"] != MODEL_SHA256):
        raise ValueError("successor plan differs")
    for name in ("source_plan", "source_result", "source_collection", "initial_fit_plan"):
        bound(plan[name])
    data = read(plan["targets"])
    initial, _old, _prior, _groups, _fit_plan = load_training(bound(plan["model"]))
    write_new(output / "fit-claim.json", {"plan": binding(output / "plan.json"), "fits": 1})
    current, anchors, groups = data["current"], data["anchors"], data["retention"]
    catalog, model, started = PokemonRedBattleCatalog(), initial, time.monotonic()
    for name in plan["head_order"]:
        metric = "composed_action" if name == "control" else name
        budgets = []
        for key, maximum in plan["limits"].items():
            group, head = key.split(":")
            if head == metric:
                rows = tuple(examples(groups[group], model, catalog)[name])
                budgets.append(RegretBudget(key, rows, maximum,
                    composed_offset(groups[group], rows) if name == "control" else 0.0))
        fitted, receipt = fit_budgeted_head(
            getattr(model, name), tuple(examples(current, model, catalog)[name]),
            tuple(examples(anchors, model, catalog)[name]), tuple(budgets),
            epochs=plan["epochs_per_head"], learning_rate=plan["learning_rate"],
            objective=plan["objective"],
        )
        write_new(output / f"{name}-optimizer.json", receipt)
        if fitted is None:
            result = {"fits": 1, "train_qualified": False, "head": name,
                      "reason": "no_feasible_checkpoint", "authority_promotions": 0}
            write_new(output / "result.json", result)
            return result
        model = replace(model, **{name: fitted})
        write_new(output / f"after-{name}-model.json", model.to_dict())
        print(json.dumps({"head": name, "selected_epoch": receipt["selected_epoch"]}), flush=True)
    after = report(current, model, catalog)
    retention = {name: report(rows, model, catalog) for name, rows in groups.items()}
    gates = learning_checks(plan["before_current"], after, retention, plan["limits"])
    if initial.move.to_dict() != model.move.to_dict():
        raise ValueError("frozen move head changed")
    write_new(output / "candidate-model.json", model.to_dict())
    result = {"fits": 1, "train_qualified": all(gates.values()), "gates": gates,
              "before": plan["before_current"], "after": after, "retention": retention,
              "model": binding(output / "candidate-model.json"), "move_head_unchanged": True,
              "elapsed_seconds": time.monotonic() - started, "new_physical_contexts": 0,
              "new_measurements": 0, "new_gameplay": 0, "natural_qualified": False,
              "authority_promotions": 0}
    write_new(output / "result.json", result)
    return {"train_qualified": result["train_qualified"], "fits": 1, "gates": gates}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "fit"))
    parser.add_argument("--comparison", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.comparison, args.output) if args.stage == "prepare"
                     else fit(args.output)), flush=True)
