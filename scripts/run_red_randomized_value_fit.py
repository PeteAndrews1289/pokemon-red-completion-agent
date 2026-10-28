"""One predeclared randomized-data training pipeline and fresh native comparison."""

import argparse
import subprocess
import time
from copy import copy
from dataclasses import replace
from pathlib import Path

import numpy as np
from audit_red_outcome_value_pilot import verify_frozen
from audit_red_randomized_collection import inspect as inspect_collection
from audit_red_status_learning import audit
from inspect_red_outcome_capacity import load_problem
from red_hidden_value_learning import fit_hidden
from red_outcome_value_learning import fit_once, outcome_gate
from red_randomized_value_learning import additive_basis, extend_randomized
from red_status_root_coverage import crossed_recipes
from run_red_outcome_value_pilot import combined

loop, lab = combined.loop, combined.lab
COHORTS = (2026092291, 2026092292, 2026092293, 2026092294)
ADDITIVE_COHORTS = (2026092301, 2026092302, 2026092303, 2026092304)


def run(args):
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new output and committed source required")
    data = args.root / "red-rng-training-collection-20260922-v1"
    checked = inspect_collection(data)
    if checked != loop.load(data / "independent-audit.json") or not checked["coverage_passed"]:
        raise ValueError("complete independently audited RNG collection required")
    bind = lab.common._binding
    additive = getattr(args, "additive", False)
    cohorts = ADDITIVE_COHORTS if additive else COHORTS
    if additive:
        rejected = args.root / "red-rng-value-fit-20260922-v1"
        if (bind(rejected / "result.json")["sha256"] !=
                "eb0b988c3712b8800b1114a47e202a5b5330c525c71d095b9d5060c2c4f6dba2" or
                loop.load(rejected / "independent-audit.json")["ready_for_party_qualification"]):
            raise ValueError("closed nonlinear predecessor differs")
    parent = args.root / "red-outcome-value-pilot-20260922-v3/candidate-model.json"
    if (bind(parent)["sha256"] !=
            "377160be3ac38c52a595da456c6b36abe65b4aac02f8472815869020944426a8" or
            bind(args.rom)["sha256"] != lab.common.ROM_SHA256):
        raise ValueError("V3 actor or cartridge differs")
    old, actor, groups, initial, frozen = load_problem(args.root)
    data_plan = loop.load(data / "plan.json")
    targets = [loop.load(Path(b["path"])) for b in checked["target_bindings"]]
    inputs = {"seeds": data_plan["rng_seeds"],
              "continuation_sha": lab.canonical_sha256(frozen.to_dict())}
    problem, labels = extend_randomized(old, actor, targets, **inputs)
    sources = sorted(lab.common._source_rows(args.root / "red-fresh-trainer-train-batch-20260917"),
                     key=lambda p: p[1]["source_id"])
    roots = [r["source_id"] for _, r in sources]
    if set(roots) != set(actor.train_root_ids):
        raise ValueError("TRAIN ancestry differs")
    cartridge = lab.RedPracticeCartridge(args.rom.read_bytes())
    recipes = [{**r, "id": f"randomized-screen-{seed}-"+r["id"], "cohort": seed}
               for seed in cohorts for r in crossed_recipes(cartridge, roots, seed=seed)
               if r["source_index"] == 3]
    if len(recipes) != 128:
        raise ValueError("four complete comparison cohorts required")
    excluded = set()
    previous = [data, args.root / "red-rng-training-diagnostic-20260922-v1",
        args.root / "red-value-readout-finish-20260922-v1",
        args.root / "red-native-later-effect-qualification-20260922-v1",
        *(args.root / f"red-outcome-value-pilot-20260922-v{v}" for v in (1, 2, 3))]
    if additive:
        previous.append(args.root / "red-rng-value-fit-20260922-v1")
    for folder in previous:
        for p in folder.glob("**/capture.state.json"):
            capture = lab.open_battle_scenario_capture(p.with_suffix(""), p)
            excluded.add(capture.manifest.state_sha256)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "plan.json", {"source_commit": commit, "actor": bind(parent),
        "data_audit": bind(data / "independent-audit.json"), "targets": checked["target_bindings"],
        "objective": "sigmoid(mean_gap-descriptive_SE-0.05);old_weight0.25;new_weight0.75",
        "fixed_additive": additive,
        "pretraining_iterations": 0 if additive else 5000,
        "pretraining_seconds": 0 if additive else 900,
        "readout_iterations": 500, "readout_seconds": 60,
        "max_optimizer_stages": 1 if additive else 2,
        "max_episodes": 256, "max_minutes": 90, "max_frames": 30720000,
        "recipes": recipes, "cohorts": cohorts, "excluded_state_sha256": sorted(excluded),
        "gates": ("unchanged182margins;original_first_regret;"
                  "new_regret25percent;outcome_readiness_v2"),
        "independent_natural_roots": 0, "actor_promotions": 0, "old_reserved_access": False})
    lab.write(args.output / "training-objective.json", labels)
    started = time.monotonic()

    def deadline():
        if time.monotonic()-started > 5400:
            raise TimeoutError("randomized learning90minute cap")

    result = {"optimizer_stages": 0, "screen": None, "actor_promotions": 0}
    try:
        if additive:
            pretrained = additive_basis(actor)
            probe, _, _, _, _ = load_problem(args.root, representation=pretrained)
            pre = {"not_run": True, "fixed_additive": True,
                   "minimum_slack": float(np.min(probe.constraints@probe.anchor-probe.minimum)),
                   "learned_parameters": 30}
        else:
            pretrained, pre = fit_hidden(problem, actor, [*groups, targets], initial,
                                          max_iterations=5000)
        result.update(optimizer_stages=0 if additive else 1, pretraining=pre,
            representation_usable=pre["minimum_slack"] >= -1e-8)
        lab.write(args.output / "pretrained-model.json", pretrained.to_dict())
        lab.write(args.output / "pretraining.json", pre)
        print({"pretraining": pre}, flush=True)
        if result["representation_usable"]:
            rebuilt, _, retained, _, _ = load_problem(args.root, representation=pretrained)
            anchor = pretrained if additive else actor
            rebuilt = replace(rebuilt, anchor=np.append(anchor.move.weights2,
                                                         anchor.move.effect_readout))
            final_problem, final_labels = extend_randomized(rebuilt, pretrained, targets, **inputs)
            if final_labels != labels:
                raise ValueError("staged objective changed")
            candidate, fit = fit_once(final_problem, pretrained, targets, retained, initial,
                start=np.append(pretrained.move.weights2, pretrained.move.effect_readout),
                reference_actor=actor)
            verify_frozen(candidate, pretrained if additive else actor,
                          [t for g in [*groups, targets] for t in g], allow_hidden=not additive)
            lab.write(args.output / "candidate-model.json", candidate.to_dict())
            reopened = combined.model(args.output / "candidate-model.json")
            if reopened.to_dict() != candidate.to_dict():
                raise ValueError("checkpoint round trip differs")
            lab.write(args.output / "fit.json", {**fit,
                      "candidate": bind(args.output / "candidate-model.json")})
            result.update(optimizer_stages=1 if additive else 2, fit=fit)
            print({"fit": fit}, flush=True)
            if fit["passed"]:
                runtime = copy(args)
                runtime.output = args.output / "starts"
                runtime.output.mkdir()
                starts = []
                for i, recipe in enumerate(recipes):
                    deadline()
                    capture = lab.materialize(runtime, recipe, i, sources, cartridge, commit)
                    if (capture.manifest.state_sha256 in excluded or
                            capture.manifest.capture_id in candidate.train_capture_ids):
                        raise ValueError("fresh comparison overlaps consumed or training state")
                    excluded.add(capture.manifest.state_sha256)
                    starts.append((recipe["id"], capture))
                baseline = loop.evaluate(args, starts, frozen, args.output / "screen-baseline",
                                         cartridge, status=False, deadline=deadline)
                selected = loop.evaluate(args, starts, candidate, args.output / "screen-candidate",
                                         cartridge, status=True, deadline=deadline)
                combined.verify_screen(args.output / "screen-baseline", frozen, frozen)
                combined.verify_screen(args.output / "screen-candidate", candidate, frozen)
                result["screen"] = outcome_gate(selected, baseline)
                result["cohorts"] = {str(seed): outcome_gate(
                    [r for r in selected if r["case"].startswith(f"randomized-screen-{seed}-")],
                    [r for r in baseline if r["case"].startswith(f"randomized-screen-{seed}-")])
                    for seed in cohorts}
        native = audit(args.output)
        if native["episodes"] > 256 or native["frames"] > 30720000:
            raise ValueError("native comparison budget exceeded")
        result.update(native=native, seconds=time.monotonic()-started)
        lab.write(args.output / "result.json", result)
        print(result, flush=True)
    except Exception as exc:
        lab.write(args.output / "failure.json", {"type": type(exc).__name__, "error": str(exc)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "rom", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--additive", action="store_true",
                        help="one fixed-basis30parameter successor after the rejected RNG model")
    run(parser.parse_args())
