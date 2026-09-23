"""Read-only linear feasibility of retained TRAIN preferences; no candidate fit."""

import argparse
import json
from pathlib import Path

import numpy as np
import run_red_outcome_value_pilot as pilot
from scipy.optimize import linprog

from pokemon_red_completion.red_balanced_status_features import BALANCED_STATUS_NAMES as N


def load_problem(root, *, representation=None):
    combined = pilot.combined
    loop = combined.loop
    parent = root / "red-outcome-value-pilot-20260922-v3"
    actor = (combined.model(parent / "candidate-model.json") if representation is None
             else representation)
    _, _, originals, initial, frozen = combined.previous.load_inputs(root)
    prior = loop.load(root /
        "red-native-later-effect-qualification-20260922-v1/combination/plan.json")
    groups = combined.validate_view(Path(prior["reward"]["path"]), root)["groups"]
    basis = combined.model(Path(prior["prior"]["path"])) if representation is None else actor
    problem = combined.prepare_combination(groups, initial, frozen, basis, originals,
                                           loop.load(Path(prior["effect"]["path"])))
    for version in (2, 3):
        directory = root / f"red-outcome-value-pilot-20260922-v{version}"
        targets = [loop.load(p) for p in sorted((directory / "targets").glob("*/target.json"))]
        problem = pilot.extend_problem(problem, actor, targets)
        groups = [*groups, targets]
    return problem, actor, groups, initial, frozen


def inspect(root):
    problem, actor, groups, _, _ = load_problem(root)
    errors, rows, unprotected = [], [], []
    for i, target in enumerate(t for g in groups for t in g):
        status = next(j for j, v in enumerate(target["vectors"]) if v[N.index("choice.status")])
        regret = max(target["returns"]) - target["returns"][actor.move.predict_index(
            target["vectors"])]
        if regret <= .05:
            continue
        sign = 1 if target["returns"][status] > target["returns"][1-status] else -1
        row = sign * problem.contrast[i]
        a = np.vstack((problem.constraints, row))
        b = np.append(problem.minimum, .05)
        answer = linprog(np.zeros(len(problem.anchor)), A_ub=-a, b_ub=-b,
                         bounds=[(None, None)]*len(problem.anchor), method="highs",
                         options={"time_limit": 1.})
        errors.append({"capture_id": target["capture_id"], "regret": regret,
                       "original_protected": i in problem.protected,
                       "individually_feasible": bool(answer.success),
                       "solver_status": int(answer.status)})
        rows.append(row)
        if i not in problem.protected:
            unprotected.append(row)
    a = np.vstack((problem.constraints, rows))
    b = np.append(problem.minimum, np.full(len(rows), .05))
    joint = linprog(np.zeros(len(problem.anchor)), A_ub=-a, b_ub=-b,
                    bounds=[(None, None)]*len(problem.anchor), method="highs",
                    options={"time_limit": 10.})
    a = np.vstack((problem.constraints, unprotected))
    b = np.append(problem.minimum, np.full(len(unprotected), .05))
    nonconflicting = linprog(np.zeros(len(problem.anchor)), A_ub=-a, b_ub=-b,
        bounds=[(None, None)]*len(problem.anchor), method="highs", options={"time_limit": 10.})
    return {"readout_parameters": len(problem.anchor),
        "contrast_rank": int(np.linalg.matrix_rank(problem.contrast)),
        "targets": sum(map(len, groups)), "original_constraints": len(problem.protected),
        "current_errors": errors,
        "individually_feasible": sum(r["individually_feasible"] for r in errors),
        "jointly_feasible": bool(joint.success), "joint_solver_status": int(joint.status),
        "unprotected_jointly_feasible": bool(nonconflicting.success),
        "unprotected_joint_solver_status": int(nonconflicting.status),
        "candidate_fits": 0, "frames": 0,
        "interpretation": "Feasibility only; noisy preferences are not ground-truth optimality."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.root), indent=2))
