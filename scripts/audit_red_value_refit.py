"""Independently recompute refit constraints, metrics and all fresh native choices."""

import argparse
import json
from pathlib import Path

import numpy as np
from audit_red_outcome_value_pilot import metrics_equal, verify_frozen
from audit_red_status_learning import audit
from inspect_red_outcome_capacity import load_problem
from red_hidden_value_learning import HiddenProblem
from red_outcome_value_learning import empirical_preferences, outcome_gate
from run_red_outcome_value_pilot import combined

from pokemon_red_completion.red_balanced_status_features import BALANCED_STATUS_NAMES as N
from pokemon_red_completion.red_status_retention_fit import group_metrics


def inspect(root, directory):
    loop, lab = combined.loop, combined.lab
    bind = lab.common._binding
    plan, result = loop.load(directory / "plan.json"), loop.load(directory / "result.json")
    fit = loop.load(directory / "fit.json")
    for binding in [plan["actor"], plan["parent_audit"], *plan["targets"]]:
        if bind(Path(binding["path"])) != binding:
            raise ValueError("refit input binding changed")
    if fit["candidate"] != bind(directory / "candidate-model.json"):
        raise ValueError("refit checkpoint changed")
    reference_actor = combined.model(Path(plan["actor"]["path"]))
    representation = None
    finish = plan.get("finish_readout", False)
    if finish:
        binding = plan["pretrained_representation"]
        if bind(Path(binding["path"])) != binding:
            raise ValueError("pretrained representation changed")
        representation = combined.model(Path(binding["path"]))
    problem, actor, groups, initial, frozen = load_problem(root, representation=representation)
    candidate = combined.model(directory / "candidate-model.json")
    targets = [t for g in groups for t in g]
    nonlinear = plan.get("learn_hidden", False)
    verify_frozen(candidate, actor, targets if nonlinear else groups[-1], allow_hidden=nonlinear)
    if nonlinear:
        hidden = HiddenProblem(problem, actor, targets)
        theta = np.concatenate((candidate.move.weights1[hidden.prefix:].ravel(),
            candidate.move.bias1, candidate.move.weights2, candidate.move.effect_readout))
        slack = float(np.min(hidden.constraints(theta)))
    else:
        if not finish:
            problem = empirical_preferences(problem, targets)
        theta = np.append(candidate.move.weights2, candidate.move.effect_readout)
        slack = float(np.min(problem.constraints@theta-problem.minimum))
    statuses = [next(i for i, v in enumerate(t["vectors"]) if v[N.index("choice.status")])
                for t in targets]
    regressions = sum(candidate.move.predict_index(targets[i]["vectors"]) == statuses[i]
                      for i in problem.protected)
    old = [{"initial": group_metrics(g, initial), "candidate": group_metrics(g, candidate)}
           for g in groups[:-1]]
    new = {"actor": group_metrics(groups[-1], reference_actor if finish else actor),
           "candidate": group_metrics(groups[-1], candidate)}
    passed = bool(fit["solver_success"] and slack >= -1e-8 and regressions == 0 and
        old[0]["candidate"]["regret"] <= old[0]["initial"]["regret"] and
        new["candidate"]["regret"] <= .75*new["actor"]["regret"])
    if (any(not metrics_equal(g[k], fit["old_groups"][i][k])
            for i, g in enumerate(old) for k in g) or
            any(not metrics_equal(new[k], fit["new_group"][k]) for k in new) or
            regressions != fit["retention_regressions"] or
            abs(slack-fit["minimum_slack"]) > 1e-9 or passed != fit["passed"] or
            result["fit"] != {k: v for k, v in fit.items() if k != "candidate"}):
        raise ValueError("recomputed training evidence differs")
    native = audit(directory)
    gate, choices = None, 0
    if result["screen"] is not None:
        if not passed:
            raise ValueError("comparison ran after rejected fit")
        recipes = plan["recipes"]
        if len(recipes) != 128 or len({r["id"] for r in recipes}) != 128:
            raise ValueError("comparison recipe inventory differs")
        excluded = set(plan["excluded_state_sha256"])
        for recipe in recipes:
            folder = directory / "starts" / recipe["id"]
            capture = loop.open_battle_scenario_capture(folder / "capture.state",
                                                       folder / "capture.state.json")
            if (loop.load(folder / "setup.json")["recipe"] != recipe or
                    capture.manifest.capture_id in candidate.train_capture_ids or
                    capture.manifest.state_sha256 in excluded or recipe["role"] != "holdout"):
                raise ValueError("fresh comparison recipe or exclusion differs")
            excluded.add(capture.manifest.state_sha256)
        baseline, _ = combined.verify_screen(directory / "screen-baseline", frozen, frozen)
        selected, choices = combined.verify_screen(directory / "screen-candidate",
                                                    candidate, frozen)
        gate = outcome_gate(selected, baseline)
        if gate != result["screen"] or native["episodes"] != 256:
            raise ValueError("native comparison result differs")
        for cohort in plan["cohorts"]:
            prefix = f"empirical-screen-{cohort}-"
            a = [r for r in selected if r["case"].startswith(prefix)]
            b = [r for r in baseline if r["case"].startswith(prefix)]
            if len(a) != 32 or outcome_gate(a, b) != result["cohorts"][str(cohort)]:
                raise ValueError("cohort accounting differs")
    if (native != result["native"] or native["frames"] > plan["max_frames"] or
            fit["iterations"] > plan.get("max_solver_iterations", 500) or
            result["fits"] != 1 or result["actor_promotions"] != 0 or
            result["seconds"] > plan["max_minutes"]*60):
        raise ValueError("packet accounting differs")
    return {"plan": bind(directory / "plan.json"), "result": bind(directory / "result.json"),
        "candidate": bind(directory / "candidate-model.json"), "fit_passed": passed,
        "retention_regressions": regressions, "minimum_slack": slack,
        "gate": gate, "candidate_attacks_recomputed": choices, "native": native,
        "ready_for_party_qualification": bool(passed and gate and gate["passed"]),
        "live_promotions": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.root, args.packet), indent=2))
