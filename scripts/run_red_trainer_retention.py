"""One cache-authenticated, hard-retention terminal fit; no emulator access."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import run_fresh_red_trainer_curriculum as common
from audit_red_trainer_retention import MODELS

from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_fit import (
    TrainerPracticeThreeHeadModel,
    _append_examples,
    summarize_trainer_practice_training,
)
from pokemon_red_completion.red_trainer_retention import bridge_control, fit_retained_head

ROOT = Path(__file__).resolve().parents[1]


def admitted_cache(audit: Path):
    manifest = json.loads((audit / "manifest.json").read_bytes())
    target_path = audit / "targets.json"
    if common._binding(target_path) != manifest["targets"] or manifest["counts"] != [52, 48, 80]:
        raise ValueError("authenticated cache differs")
    path = Path(manifest["models"]["ancestor"]["path"])
    if common._binding(path)["sha256"] != MODELS["ancestor"][1]:
        raise ValueError("retention ancestor differs")
    model = TrainerPracticeThreeHeadModel.from_dict(json.loads(path.read_bytes()))
    targets = json.loads(target_path.read_bytes())
    if (
        len(targets) != 180
        or len({t["capture_id"] for t in targets}) != 180
        or any(t.get("partition") != "train" for t in targets)
        or set(model.train_capture_ids) != {t["capture_id"] for t in targets[:100]}
        or set(model.train_root_ids) != {t["root_lineage_id"] for t in targets}
    ):
        raise ValueError("retention TRAIN lineage differs")
    return model, targets


def examples(targets, model, catalog):
    rows = {name: [] for name in ("move", "control", "switch")}
    for target in targets:
        _append_examples(
            rows,
            target,
            catalog,
            control_components=(model.move, model.switch),
            control_input_schema=model.control.schema_id,
        )
    return rows


def reports(targets, model, catalog):
    return {
        name: summarize_trainer_practice_training(
            rows, model, catalog=catalog, initial_move_model=model.move
        )
        for name, rows in (
            ("original44", targets[:44]),
            ("retained52", targets[:52]),
            ("terminal128", targets[52:]),
            ("new80", targets[100:]),
        )
    }


def gates(before, after):
    def regret(report, group, head):
        return report[group][head]["model_mean_train_regret"]

    return {
        "original44_move": regret(after, "original44", "move") <= 0.0554,
        "retained52_move": regret(after, "retained52", "move") <= 0.0648,
        "retained52_composed": regret(after, "retained52", "composed_action") <= 0.1609,
        "terminal128_composed_improves_ten_percent": regret(after, "terminal128", "composed_action")
        < 0.9 * regret(before, "terminal128", "composed_action"),
        "new80_composed_no_regression": regret(after, "new80", "composed_action")
        <= regret(before, "new80", "composed_action"),
    }


def run(audit: Path, output: Path):
    if (
        output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("retention fit requires new output and committed source")
    model, targets = admitted_cache(audit)
    catalog = PokemonRedBattleCatalog()
    before = reports(targets, model, catalog)
    if not all(
        gates(before, before)[key]
        for key in ("original44_move", "retained52_move", "retained52_composed")
    ):
        raise ValueError("retention start is not feasible")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    common._write(
        output / "plan.json",
        {
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip(),
            "audit": common._binding(audit / "audit.json"),
            "manifest": common._binding(audit / "manifest.json"),
            "plan": common._binding(
                ROOT / "docs/evidence/red-trainer-retention-plan-2026-09-19.json"
            ),
            "epochs_per_head": 1200,
            "learning_rate": 0.2,
            "fits": 1,
            "constraint": "Preserve all older head decisions at every accepted update",
            "terminal_gate": "10% lower composed regret on terminal128 and no regression on new80",
            "new_emulator_runs": 0,
        },
    )
    model = replace(
        model, control=bridge_control(model.control), control_target_mode="fitted_components"
    )
    receipts = {}
    started = time.monotonic()
    for name in ("move", "switch", "control"):
        old = examples(targets[:52], model, catalog)[name]
        new = examples(targets[52:], model, catalog)[name]
        fitted, receipt = fit_retained_head(getattr(model, name), tuple(new), tuple(old))
        model = replace(model, **{name: fitted})
        receipts[name] = receipt
        common._write(output / f"{name}-optimizer.json", receipt)
        common._write(output / f"after-{name}-model.json", model.to_dict())
        print(
            json.dumps(
                {
                    "head": name,
                    "accepted_steps": receipt["accepted_steps"],
                    "initial_loss": receipt["initial_loss"],
                    "final_loss": receipt["final_loss"],
                    "elapsed_seconds": time.monotonic() - started,
                }
            ),
            flush=True,
        )
    model = replace(model, train_capture_ids=tuple(t["capture_id"] for t in targets))
    common._write(output / "model.json", model.to_dict())
    after = reports(targets, model, catalog)
    checks = gates(before, after)
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
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.audit, args.output)
