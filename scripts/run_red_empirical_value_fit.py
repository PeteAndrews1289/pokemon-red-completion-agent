"""Bounded status-value fits and fresh comparisons; explicit experimental modes."""

import argparse
import subprocess
import time
from copy import copy
from dataclasses import replace
from pathlib import Path

import numpy as np
import run_red_outcome_value_pilot as pilot
from audit_red_outcome_value_pilot import verify_frozen
from audit_red_status_learning import audit
from red_outcome_value_learning import empirical_preferences, extend_problem, fit_once, outcome_gate
from red_status_root_coverage import crossed_recipes

combined = pilot.combined
loop, lab = combined.loop, combined.lab
COHORTS = (2026092241, 2026092242, 2026092243, 2026092244)
PRIOR_SHA = "377160be3ac38c52a595da456c6b36abe65b4aac02f8472815869020944426a8"
RESULT_SHA = "3e81f0d4ef4487f90af5486d563cf6be8df33712aecff66159cf7b313f9f6123"


def run(args):
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new packet and committed source required")
    bind = lab.common._binding
    nonlinear = getattr(args, "learn_hidden", False)
    extended = getattr(args, "extended_solver", False)
    finish = getattr(args, "finish_readout", False)
    if finish and (nonlinear or extended):
        raise ValueError("readout finish is a distinct frozen-representation stage")
    if extended and not nonlinear:
        raise ValueError("extended numerical successor requires hidden learning")
    cohorts = (2026092251, 2026092252, 2026092253, 2026092254) if nonlinear else COHORTS
    if extended:
        closed = args.root / "red-hidden-value-fit-20260922-v1/result.json"
        if bind(closed)["sha256"] != (
                "ee93151a2c888758db3dbe5da120538e2dcf265a0a0174e77eece40dbd2bd652"):
            raise ValueError("closed numerical attempt differs")
        cohorts = (2026092261, 2026092262, 2026092263, 2026092264)
    if nonlinear:
        closed = args.root / "red-empirical-value-fit-20260922-v1/result.json"
        if bind(closed)["sha256"] != (
                "ec6bf3d0abb542c7374116e9231ad2bae4d6f08961e6e11b364a15c45622efc5"):
            raise ValueError("rejected empirical experiment differs")
    parent = args.root / "red-outcome-value-pilot-20260922-v3"
    actor_path = parent / "candidate-model.json"
    if (bind(actor_path)["sha256"] != PRIOR_SHA or
            bind(parent / "result.json")["sha256"] != RESULT_SHA or
            bind(args.rom)["sha256"] != lab.common.ROM_SHA256):
        raise ValueError("prior candidate/result/cartridge differs")
    checked = loop.load(parent / "full-choice-audit.json")
    if (checked["result"] != bind(parent / "result.json") or
            checked["plan"] != bind(parent / "plan.json") or
            not checked["fit_passed"] or checked["ready"] or checked["targets"] != 145):
        raise ValueError("independent V3 audit differs")
    actor = combined.model(actor_path)
    reference_actor = actor
    pretraining_binding = None
    if finish:
        pretraining = args.root / "red-hidden-value-fit-20260922-v2"
        if (bind(pretraining / "result.json")["sha256"] !=
                "cec78a15ca7d6c9e61f1da8df7f291e6e484e1d8a870a2f0898dd7f46705a69a" or
                bind(pretraining / "candidate-model.json")["sha256"] !=
                "77bbedf225e3b278725aab20440189518146a528662e11d52ef336bafea9679e"):
            raise ValueError("pretrained representation differs")
        pretraining_binding = bind(pretraining / "candidate-model.json")
        actor = combined.model(pretraining / "candidate-model.json")
        cohorts = (2026092271, 2026092272, 2026092273, 2026092274)
    _, inputs, originals, initial, frozen = combined.previous.load_inputs(args.root)
    prior = loop.load(args.root /
        "red-native-later-effect-qualification-20260922-v1/combination/plan.json")
    groups = combined.validate_view(Path(prior["reward"]["path"]), args.root)["groups"]
    basis = actor if finish else combined.model(Path(prior["prior"]["path"]))
    effect = loop.load(Path(prior["effect"]["path"]))
    problem = combined.prepare_combination(groups, initial, frozen, basis, originals, effect)
    target_bindings = []
    for version, count in ((2, 30), (3, 145)):
        directory = args.root / f"red-outcome-value-pilot-20260922-v{version}"
        plan = loop.load(directory / "plan.json")
        continuation = combined.model(Path(plan["actor"]["path"]))
        pilot.verify_targets(directory / "targets", continuation)
        paths = sorted((directory / "targets").glob("*/target.json"))
        targets = [loop.load(p) for p in paths]
        if len(targets) != count:
            raise ValueError("retained TRAIN target count differs")
        problem = extend_problem(problem, actor, targets)
        groups = [*groups, targets]
        target_bindings.extend(bind(p) for p in paths)
    all_targets = [t for g in groups for t in g]
    original_desired = problem.desired.copy()
    if finish:
        problem = replace(problem, anchor=np.append(reference_actor.move.weights2,
                                                     reference_actor.move.effect_readout))
    elif not nonlinear:
        problem = empirical_preferences(problem, all_targets)
    sources = sorted(lab.common._source_rows(args.root / "red-fresh-trainer-train-batch-20260917"),
                     key=lambda p: p[1]["source_id"])
    roots = [r["source_id"] for _, r in sources]
    if set(roots) != set(actor.train_root_ids):
        raise ValueError("TRAIN roots differ")
    cartridge = lab.RedPracticeCartridge(args.rom.read_bytes())
    recipes = [{**r, "id": f"empirical-screen-{seed}-"+r["id"], "cohort": seed}
               for seed in cohorts for r in crossed_recipes(cartridge, roots, seed=seed)
               if r["source_index"] == 3]
    if len(recipes) != 128 or len({r["id"] for r in recipes}) != 128:
        raise ValueError("four complete prospective cohorts required")
    excluded = set()
    for version in (1, 2, 3):
        for path in (args.root / f"red-outcome-value-pilot-20260922-v{version}").glob(
                "**/capture.state.json"):
            capture = loop.open_battle_scenario_capture(path.with_suffix(""), path)
            excluded.add(capture.manifest.state_sha256)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "plan.json", {"source_commit": commit, "actor": bind(actor_path),
        "parent_audit": bind(parent / "full-choice-audit.json"), "targets": target_bindings,
        "original_inputs_sha256": loop.canonical_sha256(inputs), "recipes": recipes,
        "objective": ("conditional_output_finish_of_pretrained_representation" if finish else
                      "original_mean_return_with_learned_hidden_representation" if nonlinear
                      else "mean_sigmoid_paired_timing_gap_not_sigmoid_mean_gap"),
        "unchanged": ("episode_returns;182constraints;weights;K_components;"
                      "effect_predictor;outcome_gate"),
        "learn_hidden": nonlinear, "max_solver_seconds": 900 if nonlinear else 60,
        "finish_readout": finish, "pretrained_representation": pretraining_binding,
        "max_solver_iterations": 5000 if extended else 500,
        "cohorts": cohorts, "max_fits": 1, "max_episodes": 256, "max_minutes": 90,
        "max_frames": 30720000, "new_train_contexts": 0, "independent_natural_roots": 0,
        "excluded_state_sha256": sorted(excluded), "old128access": False,
        "soft_label_changes": int(np.sum(np.abs(original_desired-problem.desired) > .01))})
    started = time.monotonic()

    def deadline():
        if time.monotonic()-started > 5400:
            raise TimeoutError("empirical packet90minute cap")

    result = {"fits": 0, "screen": None, "actor_promotions": 0, "new_train_contexts": 0}
    try:
        if nonlinear:
            from red_hidden_value_learning import fit_hidden
            candidate, fit = fit_hidden(problem, actor, groups, initial,
                                        max_iterations=5000 if extended else 500)
        else:
            start = np.append(actor.move.weights2, actor.move.effect_readout) if finish else None
            if finish and np.min(problem.constraints@start-problem.minimum) < -1e-8:
                raise ValueError("readout finishing start violates retained margins")
            candidate, fit = fit_once(problem, actor, groups[-1], groups[:-1], initial,
                                      start=start,
                                      reference_actor=reference_actor if finish else None)
        verify_frozen(candidate, actor, all_targets if nonlinear else groups[-1],
                      allow_hidden=nonlinear)
        lab.write(args.output / "candidate-model.json", candidate.to_dict())
        reopened = combined.model(args.output / "candidate-model.json")
        if reopened.to_dict() != candidate.to_dict() or any(not np.array_equal(
                reopened.move.scores(t["vectors"]), candidate.move.scores(t["vectors"]))
                for t in all_targets):
            raise ValueError("checkpoint round trip differs")
        lab.write(args.output / "fit.json", {**fit,
                  "candidate": bind(args.output / "candidate-model.json")})
        result.update(fits=1, fit=fit)
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
                    raise ValueError("comparison overlaps a consumed or training state")
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
                [r for r in selected if r["case"].startswith(f"empirical-screen-{seed}-")],
                [r for r in baseline if r["case"].startswith(f"empirical-screen-{seed}-")])
                for seed in cohorts}
        native = audit(args.output)
        if native["episodes"] > 256 or native["frames"] > 30720000:
            raise ValueError("native budget exceeded")
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
    parser.add_argument("--learn-hidden", action="store_true",
                        help="bounded status-representation successor; not empirical labels")
    parser.add_argument("--extended-solver", action="store_true",
                        help="single5000iteration numerical successor after closed hidden V1")
    parser.add_argument("--finish-readout", action="store_true",
                        help="finish pretrained hidden V2with one converged output fit")
    run(parser.parse_args())
