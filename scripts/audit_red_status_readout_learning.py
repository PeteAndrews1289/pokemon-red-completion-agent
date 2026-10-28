"""Read-only audit of fixed-hidden readout fitting and gated native outcomes."""

import argparse
import json
from pathlib import Path

import numpy as np
import run_red_status_readout_learning as run
from audit_red_closed_loop_status import model, verify_screen
from audit_red_status_learning import audit, sha
from audit_red_status_retention_fit import metrics, preference_check
from scipy.optimize import nnls
from scipy.special import expit

from pokemon_red_completion.red_balanced_status_features import BALANCED_STATUS_NAMES
from pokemon_red_completion.red_status_battle_features import STATUS_MOVE_NAMES
from pokemon_red_completion.red_status_execution_learning import split_targets


def inspect(directory):
    loop, binding = run.loop, run.loop.lab.common._binding
    plan, fit, result = (loop.load(directory / n) for n in ("plan.json", "fit.json", "result.json"))
    for key in ("initial", "frozen", "rom", "inspection"):
        assert binding(Path(plan[key]["path"])) == plan[key]
    inspection = loop.load(Path(plan["inspection"]["path"]))
    for key in ("inputs_sha256", "initial_sha256", "frozen_sha256", "learner_source_sha256"):
        assert inspection[key] == plan[key]
    assert loop.canonical_sha256({k: plan[k] for k in (
        "groups", "eligibility", "continuations")}) == plan["inputs_sha256"]
    initial, frozen = (model(Path(plan[k]["path"])) for k in ("initial", "frozen"))
    basis = initial
    if "basis" in plan:
        assert binding(Path(plan["basis"]["path"])) == plan["basis"]
        assert plan["basis"]["sha256"] == plan["basis_sha256"] == run.BASIS_SHA
        assert inspection["basis_sha256"] == run.BASIS_SHA
        basis = model(Path(plan["basis"]["path"]))
    assert plan["initial"]["sha256"] == run.INITIAL_SHA
    assert plan["frozen"]["sha256"] == loop.lab.K_SHA
    groups = []
    for i, bindings in enumerate(plan["groups"]):
        targets = []
        for item in bindings:
            p = Path(item["path"])
            assert binding(p) == item
            t = loop.load(p)
            assert t["root"] in frozen.train_root_ids and t["return_schema"] == loop.RETURN_SCHEMA
            targets.append(t)
        eligible, report = split_targets(targets)
        assert report == plan["eligibility"][i]
        groups.append(eligible)
    assert [len(g) for g in groups] == [92, 94, 126]
    assert plan["continuations"] == [sorted({t["continuation_sha256"] for t in g}) for g in groups]
    original_groups = groups
    reward_diagnostics = None
    if "reward_view" in plan:
        from build_red_status_reward_view import validate_view
        reward_path = Path(plan["reward_view"]["path"])
        assert binding(reward_path) == plan["reward_view"]
        assert inspection["reward_view_sha256"] == plan["reward_view_sha256"]
        assert plan["reward_view_sha256"] == plan["reward_view"]["sha256"]
        view = validate_view(reward_path, reward_path.parent)
        groups = view["groups"]
        reward_diagnostics = view["diagnostics"]
    candidate = model(directory / "candidate-model.json")
    assert binding(directory / "candidate-model.json") == fit["candidate"]
    assert np.array_equal(candidate.move.weights1, basis.move.weights1)
    assert np.array_equal(candidate.move.bias1, basis.move.bias1)
    assert not np.count_nonzero(candidate.move.weights1[:len(STATUS_MOVE_NAMES)])
    for name in ("control", "switch"):
        assert getattr(candidate, name).to_dict() == getattr(frozen, name).to_dict()
    assert candidate.damage_reference.to_dict() == frozen.move.to_dict()
    targets = [t for g in groups for t in g]
    assert candidate.train_root_ids == frozen.train_root_ids
    assert set(candidate.train_capture_ids) == {
        *frozen.train_capture_ids, *(t["capture_id"] for t in targets)}
    for g, expected in zip(groups, fit["groups"], strict=True):
        for name, actor in (("initial", initial), ("candidate", candidate)):
            for k, v in metrics(g, actor).items():
                assert abs(v - expected[name][k]) < 1e-10
    original_targets = [t for g in original_groups for t in g]
    if "reward_view" in plan:
        for g, expected in zip(original_groups, fit["original_return_groups"], strict=True):
            for name, actor in (("initial", initial), ("candidate", candidate)):
                for k, v in metrics(g, actor).items():
                    assert abs(v - expected[name][k]) < 1e-10
    original_by_id = {t["capture_id"]: t for t in original_targets}
    retained = preference_check(original_targets, initial, candidate)
    for key in ("protected_preferences", "retention_regressions"):
        assert retained[key] == fit[key]
    assert abs(retained["minimum_constraint_slack"] -
               fit["solver_result"]["minimum_constraint_slack"]) < 1e-8
    # Recompute objective/gradient from full original vectors, not the fitting helper.
    objective, gradient, active = 0., np.zeros_like(candidate.move.weights2), []
    for g in groups:
        for t in g:
            s = next(i for i, v in enumerate(t["vectors"])
                     if v[BALANCED_STATUS_NAMES.index("choice.status")])
            x = np.asarray(t["vectors"])
            h = np.tanh(x @ basis.move.weights1 + basis.move.bias1)
            delta = h[s] - h[1-s]
            gap = t["returns"][s] - t["returns"][1-s]
            weight = min(4., max(.1, abs(gap))) / (len(groups) * len(g))
            z = float(delta @ candidate.move.weights2)
            desired = float(expit(3 * gap))
            objective += weight * (np.logaddexp(0., z) - desired * z)
            gradient += weight * (expit(z) - desired) * delta
            reference_h = np.tanh(x @ initial.move.weights1 + initial.move.bias1)
            margin = -float((reference_h[s] - reference_h[1-s]) @ initial.move.weights2)
            timing = original_by_id[t["capture_id"]]["timing_returns"]
            if (margin > 0 and -z - min(margin, .05) <= 1e-6
                    and all(d - st > .05 for d, st in zip(
                        timing[str(t["slots"][1-s])], timing[str(t["slots"][s])], strict=True))):
                active.append(-delta)
    displacement = candidate.move.weights2 - basis.move.weights2
    objective += .001 * np.mean(displacement ** 2)
    gradient += .002 * displacement / len(displacement)
    stationarity = float(np.linalg.norm(gradient))
    if active:
        _, stationarity = nnls(np.asarray(active).T, gradient, maxiter=10000)
    assert abs(objective - fit["solver_result"]["loss"]) < 1e-10
    assert abs(stationarity - fit["solver_result"]["stationarity_residual"]) < 1e-10
    solved = fit["solver_result"]["success"] and retained["minimum_constraint_slack"] >= -1e-8
    old_gate = fit["groups"][0]["candidate"]["regret"] <= fit["groups"][0]["initial"]["regret"]
    later_before = sum(g["initial"]["regret"] for g in fit["groups"][1:])
    later_after = sum(g["candidate"]["regret"] for g in fit["groups"][1:])
    gate = solved and retained["retention_regressions"] == 0 and old_gate
    gate = gate and later_after <= .75 * later_before
    assert gate == result["fit_gate"]
    native = audit(directory, projector=loop.project_balanced_status_moves,
                   return_value=loop.closed_loop_return)
    predictions = 0
    for key, base_name, selected_name, size in (("screen", "train-baseline", "train-screen", 64),
            ("withheld", "held-baseline", "held-candidate", 128)):
        if result[key] is None:
            assert not (directory / selected_name).exists()
            continue
        assert gate
        if key == "withheld":
            assert result["screen"]["passed"]
        base, _ = verify_screen(directory / base_name, frozen, frozen)
        selected, count = verify_screen(directory / selected_name, candidate, frozen)
        assert len(base) == len(selected) == size
        assert loop.gate(selected, base) == result[key]
        predictions += count
        if key == "withheld":
            assert result["cohorts"] == {str(s): loop.gate(
                [r for r in selected if r["case"].endswith(str(s))],
                [r for r in base if r["case"].endswith(str(s))]) for s in (2026092201,
                    2026092202, 2026092203, 2026092204)}
    if result["withheld"] is None:
        assert not list(directory.glob("balanced-*/capture.state"))
    return {"schema": "pokemon.red.status-readout-audit.v1", **native,
            "source_commit": plan["source_commit"], "candidate_sha256": sha(
                directory / "candidate-model.json"), "fit": {k: v for k, v in fit.items()
                                                           if k != "candidate"},
            "basis_sha256": plan.get("basis_sha256", plan["initial_sha256"]),
            **({"reward_view": reward_diagnostics} if reward_diagnostics is not None else {}),
            "representation": loop.load(Path(plan["inspection"]["path"]))["representation"],
            "retention": retained, "independently_verified_stationarity": stationarity,
            "later_group_regret_reduction_fraction": 1 - later_after / later_before,
            "oldest_group_gate": old_gate, "result": result,
            "candidate_predictions_verified": predictions, "training_contexts": len(targets),
            "authority_promotions": 0, "collection_delta": 0, "gameplay_running": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    print(json.dumps(inspect(parser.parse_args().experiment), indent=2, sort_keys=True))
