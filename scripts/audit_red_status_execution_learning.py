"""Reconcile execution-aware collection, fitting and actual predictions without gameplay."""

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import run_red_status_execution_learning as run
from audit_red_closed_loop_status import model, verify_screen
from audit_red_status_learning import audit, sha
from audit_red_status_retention_fit import concern_coverage, metrics, preference_check
from audit_red_status_trajectory_coverage import selected_move

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_status_battle_features import STATUS_MOVE_NAMES
from pokemon_red_completion.red_status_execution_learning import split_targets


def inspect(directory):
    loop = run.loop
    plan, result, fit, inputs = (loop.load(directory / n) for n in
                                ("plan.json", "result.json", "fit.json", "fit-inputs.json"))
    binding = loop.lab.common._binding
    for name in ("actor", "initial", "frozen", "rom"):
        assert binding(Path(plan[name]["path"])) == plan[name]
    actor, initial, frozen = (model(Path(plan[n]["path"])) for n in ("actor", "initial", "frozen"))
    assert plan["actor"]["sha256"] == run.ACTOR_SHA
    assert plan["initial"]["sha256"] == run.INITIAL_SHA
    assert plan["frozen"]["sha256"] == loop.lab.K_SHA
    groups = []
    for index, bindings in enumerate(inputs["groups"]):
        targets = []
        for item in bindings:
            p = Path(item["path"])
            assert binding(p) == item
            target = loop.load(p)
            assert target["root"] in frozen.train_root_ids
            assert target["return_schema"] == loop.RETURN_SCHEMA
            targets.append(target)
        eligible, report = split_targets(targets)
        assert report == inputs["eligibility"][index]
        groups.append(eligible)
    assert inputs["groups"][:2] == plan["old_groups"]
    assert inputs["continuations"] == [sorted({t["continuation_sha256"] for t in g})
                                       for g in groups]
    assert len(groups[2]) == result["new_contexts"]
    candidate = model(directory / "candidate-model.json")
    assert binding(directory / "candidate-model.json") == fit["candidate"]
    assert candidate.damage_reference.to_dict() == frozen.move.to_dict()
    assert candidate.control.to_dict() == frozen.control.to_dict()
    assert candidate.switch.to_dict() == frozen.switch.to_dict()
    assert candidate.train_root_ids == frozen.train_root_ids
    assert not np.count_nonzero(candidate.move.weights1[:len(STATUS_MOVE_NAMES)])
    all_targets = [t for g in groups for t in g]
    assert set(candidate.train_capture_ids) == {
        *frozen.train_capture_ids, *(t["capture_id"] for t in all_targets)}
    retained = preference_check(all_targets, initial, candidate)
    for key in ("protected_preferences", "retention_regressions"):
        assert retained[key] == fit[key]
    assert abs(retained["minimum_constraint_slack"] -
               fit["solver_result"]["minimum_constraint_slack"]) < 1e-8
    for group, expected in zip(groups, fit["groups"], strict=True):
        for name, m in (("initial", initial), ("candidate", candidate)):
            for k, value in metrics(group, m).items():
                assert abs(value - expected[name][k]) < 1e-10
    assert fit["solver_result"]["anchor_l2"] == plan["anchor_l2"] == .001
    passed = (fit["solver_result"]["success"] and retained["minimum_constraint_slack"] >= -1e-8
              and retained["retention_regressions"] == 0
              and fit["groups"][0]["candidate"]["regret"] <=
              fit["groups"][0]["initial"]["regret"]
              and sum(g["candidate"]["regret"] for g in fit["groups"][1:]) <=
              .75 * sum(g["initial"]["regret"] for g in fit["groups"][1:]))
    assert passed == result["fit_gate"]
    verified = audit(directory, projector=loop.project_balanced_status_moves,
                     return_value=loop.closed_loop_return)
    target_audit = audit(directory / "targets", projector=loop.project_balanced_status_moves,
                         return_value=loop.closed_loop_return, plan_path=directory / "plan.json")
    assert target_audit == loop.load(directory / "target-audit.json")
    counts = Counter(r["status"] for r in loop.load(directory / "coverage.json"))
    assert sum(counts.values()) == 512
    assert counts["measured"] == result["new_contexts"]
    snapshots = trajectory_predictions = branch_predictions = unchanged = 0
    previous = Path(plan["actor"]["path"]).parent
    for parent in plan["starts"]:
        name = parent["name"]
        path = directory / "trajectories" / name
        ep = loop.load(path / "episode.json")
        original = loop.load(previous / "train-screen" / name.removeprefix("execution-")
                             / "episode.json")
        def actions(e):
            return [(s["kind"], s["move_slot"], s["observation_sha256"]) for s in e["decisions"]]
        assert actions(ep) == actions(original)
        unchanged += 1
        records = [loop.load(p) for p in sorted((path / "events").glob("event-*.json"))]
        assert records[0]["payload"]["identity"]["model_sha256"] == canonical_sha256(
            actor.to_dict())
        starts = {r["payload"]["decision_index"]: r for r in records
                  if r["payload"]["event"] == "decision_started"}
        saved = {r["payload"]["decision_index"]: r["payload"] for r in records
                 if r["payload"]["event"] == "trajectory_capture_saved"}
        for step in ep["decisions"]:
            assert selected_move(actor, frozen, step) == step["move_slot"]
            trajectory_predictions += 1
        for state in path.glob("snapshots/*/capture.state"):
            c = loop.open_battle_scenario_capture(state, state.with_suffix(".state.json"))
            b = loop.load(state.parent / "binding.json")
            i = b["decision_index"]
            assert c.manifest.partition is loop.ScenarioPartition.TRAIN
            assert c.manifest.root_lineage_id in frozen.train_root_ids
            assert b["parent_capture_id"] == parent["capture_id"]
            assert b["parent_manifest_sha256"] == parent["manifest_sha256"]
            assert b["state_sha256"] == c.manifest.state_sha256
            assert b["decision_event_sha256"] == starts[i]["record_sha256"]
            assert canonical_sha256(b) == saved[i]["binding_sha256"]
            assert b["policy_observation_sha256"] == ep["decisions"][i-1]["observation_sha256"]
            td = directory / "targets" / f"{name}-decision-{i:03d}"
            if td.exists():
                t = loop.load(td / "target.json")
                assert t["capture_id"] == c.manifest.capture_id
                assert t["continuation_sha256"] == canonical_sha256(actor.to_dict())
                assert len(list(td.glob("branch-*/episode.json"))) == 6
                for slot in t["slots"]:
                    actual_returns = [loop.closed_loop_return(loop.load(
                        td / f"branch-{offset}-{slot}" / "episode.json"))
                        for offset in loop.OFFSETS]
                    assert actual_returns == t["timing_returns"][str(slot)]
                for p in td.glob("branch-*/episode.json"):
                    branch = loop.load(p)
                    identity = loop.load(p.parent / "events/event-00001.json")[
                        "payload"]["identity"]
                    assert identity["capture_id"] == c.manifest.capture_id
                    assert identity["model_sha256"] == t["continuation_sha256"]
                    assert branch["decisions"][0]["move_slot"] == identity["first_slot"]
                    assert branch["decisions"][0]["observation_sha256"] == b[
                        "policy_observation_sha256"]
                    for step in branch["decisions"][1:]:
                        assert selected_move(actor, frozen, step) == step["move_slot"]
                        branch_predictions += 1
            snapshots += 1
    evaluation_predictions, diagnostics = 0, {}
    for stage, base_name, candidate_name, size in (("screen", "train-baseline", "train-screen", 64),
            ("withheld", "held-baseline", "held-candidate", 128)):
        if result[stage] is None:
            assert not (directory / candidate_name).exists()
            continue
        assert passed
        if stage == "withheld":
            assert result["screen"]["passed"]
        base, _ = verify_screen(directory / base_name, frozen, frozen)
        chosen, count = verify_screen(directory / candidate_name, candidate, frozen)
        assert len(base) == len(chosen) == size
        assert loop.gate(chosen, base) == result[stage]
        evaluation_predictions += count
        diagnostics[stage] = concern_coverage(directory / candidate_name, all_targets)
    if result["withheld"] is None:
        assert not list(directory.glob("balanced-*/capture.state"))
    return {"schema": "pokemon.red.status-execution-learning-audit.v1", **verified,
            "new_target_contexts": len(groups[2]), "eligible_group_sizes": [len(g) for g in groups],
            "eligibility": inputs["eligibility"], "coverage": dict(counts), "snapshots": snapshots,
            "unchanged_trajectories": unchanged, "trajectory_predictions": trajectory_predictions,
            "branch_predictions": branch_predictions,
            "evaluation_predictions": evaluation_predictions,
            "retention": retained, "fit": {k: v for k, v in fit.items() if k != "candidate"},
            "result": result, "diagnostics": diagnostics,
            "candidate_sha256": sha(directory / "candidate-model.json"),
            "candidate_weight_norm": float(np.linalg.norm(candidate.move.weights1)),
            "source_commit": plan["source_commit"], "authority_promotions": 0,
            "collection_delta": 0, "independent_heldout_roots": 0, "gameplay_running": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    print(json.dumps(inspect(parser.parse_args().experiment), indent=2, sort_keys=True))
