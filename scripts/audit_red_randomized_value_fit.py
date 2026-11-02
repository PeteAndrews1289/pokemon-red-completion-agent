"""Independently recompute staged RNG fit and comparison; no fit or gameplay."""

import argparse
from dataclasses import replace
from pathlib import Path

import numpy as np
from audit_red_outcome_value_pilot import metrics_equal, verify_frozen
from audit_red_status_learning import audit
from inspect_red_outcome_capacity import load_problem
from red_hidden_value_learning import HiddenProblem
from red_outcome_value_learning import outcome_gate
from red_randomized_value_learning import additive_basis, extend_randomized
from run_red_randomized_value_fit import ADDITIVE_COHORTS, COHORTS, combined, lab, loop

from pokemon_red_completion.red_balanced_status_features import BALANCED_STATUS_NAMES as N
from pokemon_red_completion.red_status_retention_fit import group_metrics


def inspect(root, directory):
    bind = lab.common._binding
    plan, result = loop.load(directory / "plan.json"), loop.load(directory / "result.json")
    for binding in [plan["actor"], plan["data_audit"], *plan["targets"]]:
        if bind(Path(binding["path"])) != binding:
            raise ValueError("fitting input binding changed")
    data = Path(plan["data_audit"]["path"]).parent
    checked, dp = loop.load(data / "independent-audit.json"), loop.load(data / "plan.json")
    if not checked["coverage_passed"] or checked["target_bindings"] != plan["targets"]:
        raise ValueError("collection admission differs")
    old, actor, groups, initial, frozen = load_problem(root)
    targets = [loop.load(Path(b["path"])) for b in plan["targets"]]
    inputs = {"seeds": dp["rng_seeds"], "continuation_sha": lab.canonical_sha256(frozen.to_dict())}
    problem, labels = extend_randomized(old, actor, targets, **inputs)
    if labels != loop.load(directory / "training-objective.json"):
        raise ValueError("conservative target calculation differs")
    all_targets = [t for g in [*groups, targets] for t in g]
    pretrained = combined.model(directory / "pretrained-model.json")
    pre = loop.load(directory / "pretraining.json")
    additive = plan.get("fixed_additive", False)
    cohorts = ADDITIVE_COHORTS if additive else COHORTS
    if additive:
        if pretrained.to_dict() != additive_basis(actor).to_dict() or not pre["not_run"]:
            raise ValueError("fixed additive representation differs")
        probe, _, _, _, _ = load_problem(root, representation=pretrained)
        slack = float(np.min(probe.constraints@probe.anchor-probe.minimum))
    else:
        verify_frozen(pretrained, actor, all_targets, allow_hidden=True)
        hidden = HiddenProblem(problem, actor, all_targets)
        theta = np.concatenate((pretrained.move.weights1[hidden.prefix:].ravel(),
            pretrained.move.bias1, pretrained.move.weights2, pretrained.move.effect_readout))
        slack = float(np.min(hidden.constraints(theta)))
    if (pre != result["pretraining"] or abs(slack-pre["minimum_slack"]) > 1e-9 or
            (slack >= -1e-8) != result["representation_usable"]):
        raise ValueError("pretraining margin evidence differs")
    fit_passed, screen, choices = False, None, 0
    if result["optimizer_stages"] == (1 if additive else 2):
        if not result["representation_usable"]:
            raise ValueError("readout ran after infeasible pretraining")
        rebuilt, _, retained, _, _ = load_problem(root, representation=pretrained)
        anchor = pretrained if additive else actor
        rebuilt = replace(rebuilt, anchor=np.append(anchor.move.weights2,
                                                     anchor.move.effect_readout))
        final_problem, _ = extend_randomized(rebuilt, pretrained, targets, **inputs)
        candidate = combined.model(directory / "candidate-model.json")
        verify_frozen(candidate, pretrained, targets if additive else [], allow_hidden=False)
        fit = loop.load(directory / "fit.json")
        theta = np.append(candidate.move.weights2, candidate.move.effect_readout)
        final_slack = float(np.min(final_problem.constraints@theta-final_problem.minimum))
        statuses = [next(i for i, v in enumerate(t["vectors"]) if v[N.index("choice.status")])
                    for t in all_targets]
        regressions = sum(candidate.move.predict_index(all_targets[i]["vectors"]) == statuses[i]
                          for i in final_problem.protected)
        old_metrics = [{"initial": group_metrics(g, initial),
                        "candidate": group_metrics(g, candidate)} for g in retained]
        new = {"actor": group_metrics(targets, actor),
               "candidate": group_metrics(targets, candidate)}
        fit_passed = bool(fit["solver_success"] and final_slack >= -1e-8 and regressions == 0 and
            old_metrics[0]["candidate"]["regret"] <= old_metrics[0]["initial"]["regret"] and
            new["candidate"]["regret"] <= .75*new["actor"]["regret"])
        if (abs(final_slack-fit["minimum_slack"]) > 1e-9 or fit_passed != fit["passed"] or
                fit["candidate"] != bind(directory / "candidate-model.json") or
                regressions != fit["retention_regressions"] or
                any(not metrics_equal(g[k], fit["old_groups"][i][k])
                    for i, g in enumerate(old_metrics) for k in g) or
                any(not metrics_equal(new[k], fit["new_group"][k]) for k in new)):
            raise ValueError("final TRAIN metric or margin evidence differs")
        if result["screen"] is not None:
            if not fit_passed or plan["cohorts"] != list(cohorts) or len(plan["recipes"]) != 128:
                raise ValueError("comparison admission differs")
            excluded = set(plan["excluded_state_sha256"])
            for recipe in plan["recipes"]:
                folder = directory / "starts" / recipe["id"]
                capture = lab.open_battle_scenario_capture(folder / "capture.state",
                                                           folder / "capture.state.json")
                if (recipe["role"] != "holdout" or
                        loop.load(folder / "setup.json")["recipe"] != recipe or
                        capture.manifest.state_sha256 in excluded or
                        capture.manifest.capture_id in candidate.train_capture_ids):
                    raise ValueError("comparison recipe or disjointness differs")
                excluded.add(capture.manifest.state_sha256)
            base_rows, _ = combined.verify_screen(directory / "screen-baseline", frozen, frozen)
            selected_rows, choices = combined.verify_screen(
                directory / "screen-candidate", candidate, frozen)
            screen = outcome_gate(selected_rows, base_rows)
            if screen != result["screen"]:
                raise ValueError("comparison outcome gate differs")
            for seed in cohorts:
                prefix = f"randomized-screen-{seed}-"
                cohort = outcome_gate(
                    [r for r in selected_rows if r["case"].startswith(prefix)],
                    [r for r in base_rows if r["case"].startswith(prefix)])
                if cohort != result["cohorts"][str(seed)]:
                    raise ValueError("cohort result differs")
    native = audit(directory)
    if native != result["native"]:
        raise ValueError("native counts differ")
    return {"plan": bind(directory / "plan.json"), "result": bind(directory / "result.json"),
            "fit_passed": fit_passed, "native": native, "screen": screen,
            "candidate_attacks_recomputed": choices,
            "ready_for_party_qualification": bool(screen and screen["passed"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "directory"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.root, args.directory)
    lab.write(args.directory / "independent-audit.json", report)
    print(report)
