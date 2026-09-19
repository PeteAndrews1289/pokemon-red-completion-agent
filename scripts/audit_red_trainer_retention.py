"""Authenticate the existing TRAIN corpus once and audit retention without a ROM."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean

import run_fresh_red_trainer_curriculum as common
from run_red_trainer_terminal_curriculum import retained_targets, terminal_anchor_targets

from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_fit import (
    TrainerPracticeThreeHeadModel,
    _append_examples,
    summarize_trainer_practice_training,
)

MODELS = {
    "ancestor": (
        "red-trainer-terminal-curriculum-20260917-v1",
        "3e7994142f4f7faa4e2a3a0c11f4b9d09a82eac1b7f274af8d21de64e0adf604",
    ),
    "learner": (
        "red-trainer-learner-five-20260917-v1",
        "2d944149bf2c61b6e498ff677222414e59f131b4adc53065e737b26e8f7b81d6",
    ),
    "proposed": (
        "red-trainer-proposed-control-20260917-v1",
        "1925a27a7c73f4d49833f45527849b5ce9dd92e103e737d8e777a5708fa33e54",
    ),
    "return": (
        "red-trainer-return-objective-20260917-v1",
        "df1182c3893715b9e4e4ea6c33bf2b6b59e2781664f683d0a8a9b9e7abb88957",
    ),
}


def contrast_audit(groups):
    """Exact-input lower bound is diagnostic, not evidence of neural learnability."""
    report = {}
    for head in ("move", "control", "switch"):
        matrices = defaultdict(list)
        scales = {}
        for group, examples in groups.items():
            rows = examples[head]
            gaps = []
            for row in rows:
                rewards = row.mean_returns
                assert rewards is not None
                gaps.append(max(rewards) - min(rewards))
                matrices[row.candidate_vectors].append((group, rewards))
            scales[group] = {
                "cases": len(rows),
                "mean_range": fmean(gaps) if gaps else 0,
                "max_range": max(gaps, default=0),
            }
        unavoidable = 0.0
        conflicts = []
        count = 0
        for matrix, rows in matrices.items():
            totals = [sum(max(r) - r[i] for _, r in rows) for i in range(len(matrix))]
            unavoidable += min(totals)
            count += len(rows)
            if min(totals) > 1e-9:
                conflicts.append(
                    {"groups": [g for g, _ in rows], "minimum_total_regret": min(totals)}
                )
        report[head] = {
            "scales": scales,
            "conflicts": conflicts,
            "exact_input_mean_regret_floor": unavoidable / count if count else 0,
        }
    return report


def run(root: Path, output: Path):
    models = {}
    bindings = {}
    for name, (directory, digest) in MODELS.items():
        path = root / directory / "model.json"
        binding = common._binding(path)
        if binding["sha256"] != digest:
            raise ValueError("frozen model differs: " + name)
        bindings[name] = binding
        models[name] = TrainerPracticeThreeHeadModel.from_dict(json.loads(path.read_bytes()))
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    prior = root / "red-trainer-corrected-mean-return-20260917-v1/fit-plan.json"
    old = retained_targets(json.loads(prior.read_bytes()))
    ids = {t["capture_id"] for t in old}
    inherited = terminal_anchor_targets(
        Path(bindings["ancestor"]["path"]), set(models["ancestor"].train_capture_ids) - ids
    )
    ids.update(t["capture_id"] for t in inherited)
    newer = terminal_anchor_targets(
        Path(bindings["learner"]["path"]), set(models["learner"].train_capture_ids) - ids
    )
    if (len(old), len(inherited), len(newer)) != (52, 48, 80):
        raise ValueError("authenticated curriculum inventory differs")
    records = old + inherited + newer
    if len({t["capture_id"] for t in records}) != 180:
        raise ValueError("duplicate TRAIN identity")
    common._write(output / "targets.json", records)
    manifest = {
        "targets": common._binding(output / "targets.json"),
        "models": bindings,
        "prior": common._binding(prior),
        "counts": [52, 48, 80],
        "authentication": "original state, manifest, plans and branch logs reconstructed",
    }
    common._write(output / "manifest.json", manifest)
    print(json.dumps({"authenticated_contexts": 180}), flush=True)
    catalog = PokemonRedBattleCatalog()
    reports = {}
    for name, model in models.items():
        reports[name] = {
            group: summarize_trainer_practice_training(
                rows, model, catalog=catalog, initial_move_model=model.move
            )
            for group, rows in (
                ("original44", old[:44]),
                ("retained52", old),
                ("inherited48", inherited),
                ("new80", newer),
            )
        }
    groups = {}
    for name, targets in (("old52", old), ("inherited48", inherited), ("new80", newer)):
        examples = {head: [] for head in ("move", "control", "switch")}
        for target in targets:
            _append_examples(examples, target, catalog)
        groups[name] = examples
    result = {
        "models": reports,
        "contrasts": contrast_audit(groups),
        "rom_runs": 0,
        "new_training_examples": 0,
        "fits": 0,
    }
    common._write(output / "audit.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.root, args.output)
