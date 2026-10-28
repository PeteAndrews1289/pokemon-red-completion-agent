"""Read-only reconciliation of retained-preference fits and actual battle choices."""

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import fmean

import numpy as np
import run_red_status_retention_fit as run
from audit_red_closed_loop_status import model, verify_screen
from audit_red_status_learning import audit, sha

from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_balanced_status_features import (
    BALANCED_STATUS_NAMES,
    project_balanced_status_moves,
)
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_status_battle_features import STATUS_MOVE_NAMES
from pokemon_red_completion.red_status_closed_loop_returns import RETURN_SCHEMA, closed_loop_return


def metrics(targets, actor):
    gaps = [max(t["returns"]) - t["returns"][actor.move.predict_index(t["vectors"])]
            for t in targets]
    return {"contexts": len(gaps), "regret": fmean(gaps),
            "errors": sum(g > .05 for g in gaps), "high_cost_errors": sum(g >= 1 for g in gaps)}


def preference_check(targets, initial, candidate):
    slacks, regressions = [], 0
    for t in targets:
        status = next(i for i, v in enumerate(t["vectors"])
                      if v[BALANCED_STATUS_NAMES.index("choice.status")])
        damage = 1 - status
        vectors = np.asarray(t["vectors"])

        def scores(actor, vectors=vectors):
            head = actor.move
            return np.tanh(vectors @ head.weights1 + head.bias1) @ head.weights2

        before = scores(initial)
        margin = before[damage] - before[status]
        robust = all(d - s > .05 for d, s in zip(
            t["timing_returns"][str(t["slots"][damage])],
            t["timing_returns"][str(t["slots"][status])], strict=True))
        if robust and margin > 0:
            after = scores(candidate)
            slacks.append(float(after[damage] - after[status] - min(margin, .05)))
            regressions += candidate.move.predict_index(t["vectors"]) != damage
    return {"protected_preferences": len(slacks), "retention_regressions": int(regressions),
            "minimum_constraint_slack": min(slacks, default=0.)}


def concern_coverage(directory, targets):
    """Describe failed TRAIN decisions without fabricating new counterfactual labels."""
    known = {tuple(v[len(STATUS_MOVE_NAMES):]) for t in targets for v in t["vectors"]
             if v[BALANCED_STATUS_NAMES.index("choice.status")]}
    counts, exact, cases, turns = Counter(), 0, set(), []
    asleep = suppressed = 0
    matches = []
    projector = BattleFeatureProjector(PokemonRedBattleCatalog())
    for row in run.loop.load(directory / "summary.json"):
        episode = run.loop.load(directory / row["case"] / "episode.json")
        by_number = dict(enumerate(episode["decisions"], 1))
        for choice in row["status_choices"]:
            if not choice["concerns"]:
                continue
            counts.update(choice["concerns"])
            cases.add(row["case"])
            turns.append(choice["decision"])
            obs = by_number[choice["decision"]]["observation"]
            projected = project_balanced_status_moves(obs, projector.project(obs))
            v = projected.candidate_vectors[projected.candidate_slots.index(choice["slot"])]
            exact += tuple(v[len(STATUS_MOVE_NAMES):]) in known
            asleep += bool(v[BALANCED_STATUS_NAMES.index("choice.player_asleep")])
            suppressed += not by_number[choice["decision"]]["outcome"]["move_executed"]
            for t in targets:
                for index, tv in enumerate(t["vectors"]):
                    if tuple(tv[len(STATUS_MOVE_NAMES):]) == tuple(v[len(STATUS_MOVE_NAMES):]):
                        matches.append({"case": row["case"], "decision": choice["decision"],
                                        "target_capture_id": t["capture_id"],
                                        "selected_return_gap":
                                        max(t["returns"]) - t["returns"][index]})
    return {"concerns_by_kind": dict(sorted(counts.items())), "affected_cases": len(cases),
            "affected_decisions": len(turns), "exact_training_input_matches": exact,
            "player_asleep_at_concerning_selection": asleep, "matched_target_gaps": matches,
            "concerning_selections_not_executed": suppressed,
            "first_affected_decision": min(turns, default=None),
            "last_affected_decision": max(turns, default=None)}


def inspect(directory):
    loop = run.loop
    binding = loop.lab.common._binding
    plan, result, fit = (loop.load(directory / n) for n in ("plan.json", "result.json", "fit.json"))
    for name in ("initial", "frozen"):
        assert binding(Path(plan[name]["path"])) == plan[name]
    initial, frozen = (model(Path(plan[n]["path"])) for n in ("initial", "frozen"))
    assert plan["initial"]["sha256"] == run.INITIAL_SHA
    assert plan["frozen"]["sha256"] == loop.lab.K_SHA
    candidate = model(directory / "candidate-model.json")
    assert fit["candidate"] == binding(directory / "candidate-model.json")
    assert candidate.damage_reference.to_dict() == frozen.move.to_dict()
    assert candidate.control.to_dict() == frozen.control.to_dict()
    assert candidate.switch.to_dict() == frozen.switch.to_dict()
    assert candidate.train_root_ids == frozen.train_root_ids
    assert not np.count_nonzero(candidate.move.weights1[:len(STATUS_MOVE_NAMES)])
    groups = []
    for bindings in plan["groups"]:
        group = []
        for item in bindings:
            path = Path(item["path"])
            assert binding(path) == item
            t = loop.load(path)
            assert t["role"] == "train" and t["root"] in frozen.train_root_ids
            assert t["return_schema"] == RETURN_SCHEMA
            group.append(t)
        groups.append(group)
    assert [len(g) for g in groups] == [94, 97]
    assert plan["continuations"] == [sorted({t["continuation_sha256"] for t in g}) for g in groups]
    targets = [t for g in groups for t in g]
    assert set(candidate.train_capture_ids) == {
        *frozen.train_capture_ids, *(t["capture_id"] for t in targets)}
    for g, expected in zip(groups, fit["groups"], strict=True):
        for name, actor in (("initial", initial), ("candidate", candidate)):
            actual = metrics(g, actor)
            for key, value in actual.items():
                assert abs(value - expected[name][key]) < 1e-10
    retained = preference_check(targets, initial, candidate)
    assert retained["protected_preferences"] == fit["protected_preferences"]
    assert retained["retention_regressions"] == fit["retention_regressions"]
    solver = fit.get("solver_result")
    if solver:
        assert abs(retained["minimum_constraint_slack"] - solver["minimum_constraint_slack"]) < 1e-8
    solved = plan.get("solver", "backtracking") == "backtracking" or (
        solver["success"] and retained["minimum_constraint_slack"] >= -1e-8)
    gate = (solved and retained["retention_regressions"] == 0
            and fit["groups"][1]["candidate"]["regret"] <=
            .75 * fit["groups"][1]["initial"]["regret"]
            and fit["groups"][0]["candidate"]["regret"] <= fit["groups"][0]["initial"]["regret"])
    assert gate == result["fit_gate"]
    if plan.get("numeric_continuation"):
        item = plan["numeric_continuation"]
        assert binding(Path(item["path"])) == item
        previous = Path(item["path"]).parent
        old = loop.load(previous / "plan.json")
        for key in ("groups", "initial", "frozen", "holdout_recipes", "solver_ftol", "objective"):
            assert plan[key] == old[key]
        assert loop.load(previous / "result.json")["screen"] is None
        assert loop.load(previous / "result.json")["withheld"] is None
    rows = audit(directory, projector=project_balanced_status_moves,
                 return_value=closed_loop_return)
    predictions, coverage = 0, None
    if result["screen"] is not None:
        assert gate
        base, _ = verify_screen(directory / "train-baseline", frozen, frozen)
        chosen, predictions = verify_screen(directory / "train-screen", candidate, frozen)
        assert len(base) == len(chosen) == 64
        assert loop.gate(chosen, base) == result["screen"]
        coverage = concern_coverage(directory / "train-screen", targets)
    else:
        assert not (directory / "train-screen").exists()
    if result["withheld"] is not None:
        assert result["screen"]["passed"]
        base, _ = verify_screen(directory / "held-baseline", frozen, frozen)
        chosen, count = verify_screen(directory / "held-candidate", candidate, frozen)
        predictions += count
        assert len(base) == len(chosen) == 128
        assert loop.gate(chosen, base) == result["withheld"]
        assert result["cohorts"] == {str(seed): loop.gate(
            [r for r in chosen if r["case"].endswith(str(seed))],
            [r for r in base if r["case"].endswith(str(seed))]) for seed in run.SEEDS}
    else:
        assert not (directory / "held-candidate").exists()
        assert not list(directory.glob("balanced-*/capture.state"))
    return {"schema": "pokemon.red.status-retention-audit.v1", **rows,
            "candidate_sha256": sha(directory / "candidate-model.json"),
            "source_commit": plan["source_commit"], "groups": fit["groups"],
            "retention": retained, "solver_result": solver, "result": result,
            "verified_candidate_predictions": predictions, "failure_coverage": coverage,
            "optimizer_invocations": 1, "fit_targets": 191,
            "authority_promotions": 0, "collection_delta": 0, "gameplay_running": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    print(json.dumps(inspect(parser.parse_args().experiment), indent=2, sort_keys=True))
