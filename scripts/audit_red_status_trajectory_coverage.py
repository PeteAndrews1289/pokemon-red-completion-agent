"""Independently verify retained trajectory snapshots, actions and outcome targets."""

import argparse
import json
from pathlib import Path

import run_red_status_trajectory_coverage as run
from audit_red_status_learning import audit, sha

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_balanced_status_features import project_balanced_status_moves
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_status_battle_features import status_choice_slots
from pokemon_red_completion.red_status_closed_loop_returns import closed_loop_return
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.scenario_lab import ScenarioPartition


def selected_move(actor, frozen, decision):
    obs = decision["observation"]
    projected = project_balanced_status_moves(
        obs, BattleFeatureProjector(PokemonRedBattleCatalog()).project(obs))
    slots = status_choice_slots(projected, tuple(decision["legal_move_slots"]), frozen.move)
    vectors = tuple(projected.candidate_vectors[projected.candidate_slots.index(s)] for s in slots)
    return slots[actor.move.predict_index(vectors)]


def inspect(directory, actor_path, frozen_path, parent, prior_train):
    loop = run.loop
    actor = TrainerPracticeThreeHeadModel.from_dict(loop.load(actor_path))
    frozen = TrainerPracticeThreeHeadModel.from_dict(loop.load(frozen_path))
    assert sha(actor_path) == run.ACTOR_SHA
    assert sha(frozen_path) == loop.lab.K_SHA
    plan, result = (loop.load(directory / name) for name in ("plan.json", "result.json"))
    assert plan["max_fits"] == result["fits"] == 0
    assert plan["decision_indices"] == list(run.INDICES)
    assert len(plan["starts"]) == result["trajectories"] == len(result["cases"]) == 64
    verified = audit(directory, projector=project_balanced_status_moves,
                     return_value=closed_loop_return)
    target_audit = audit(directory / "targets", projector=project_balanced_status_moves,
                          return_value=closed_loop_return, plan_path=directory / "plan.json")
    targets = [loop.load(p) for p in sorted((directory / "targets").glob("*/target.json"))]
    # Diagnostics preserve group insertion order: use case/decision plan order as the runner did.
    ordered = [loop.load(directory / "targets" / f"{c['case']}-decision-{s['index']:03d}"
                         / "target.json") for c in result["cases"] for s in c["samples"]
               if s["status"] == "measured"]
    assert run.target_diagnostics(ordered, actor) == result["diagnostics"]
    snapshots = trajectory_predictions = branch_predictions = unchanged_trajectories = 0
    indices = {str(i): {"measured": 0, "censored": 0} for i in run.INDICES}
    for c in result["cases"]:
        path = directory / "trajectories" / c["case"]
        episode = loop.load(path / "episode.json")
        original = loop.load(prior_train / c["case"] / "episode.json")
        def actions(e):
            return [(s["kind"], s.get("move_slot"), s["observation_sha256"])
                    for s in e["decisions"]]
        assert actions(episode) == actions(original)
        assert episode["stop_reason"] == original["stop_reason"]
        unchanged_trajectories += 1
        records = [loop.load(p) for p in sorted((path / "events").glob("event-*.json"))]
        identity = records[0]["payload"]["identity"]
        assert identity["model_sha256"] == canonical_sha256(actor.to_dict())
        assert identity["capture_decisions"] == list(run.INDICES)
        assert identity["first_slot"] is None
        starts = {r["payload"]["decision_index"]: r for r in records
                  if r["payload"]["event"] == "decision_started"}
        saved = {r["payload"]["decision_index"]: r["payload"] for r in records
                 if r["payload"]["event"] == "trajectory_capture_saved"}
        parent_capture = open_battle_scenario_capture(
            parent / c["case"] / "capture.state", parent / c["case"] / "capture.state.json")
        assert parent_capture.manifest.partition is ScenarioPartition.TRAIN
        for step in episode["decisions"]:
            assert step["kind"] == "attack"
            assert selected_move(actor, frozen, step) == step["move_slot"]
            trajectory_predictions += 1
        assert [s["index"] for s in c["samples"]] == list(run.INDICES)
        for sample in c["samples"]:
            index = sample["index"]
            indices[str(index)][sample["status"]] += 1
            snapshot = path / "snapshots" / f"decision-{index:03d}"
            if not snapshot.exists():
                assert sample["status"] == "censored"
                assert index not in saved
                assert (index > len(episode["decisions"])) == (sample["reason"] == "not_reached")
                continue
            capture = open_battle_scenario_capture(snapshot / "capture.state",
                                                   snapshot / "capture.state.json")
            binding = loop.load(snapshot / "binding.json")
            assert capture.manifest.partition is ScenarioPartition.TRAIN
            assert binding["parent_capture_id"] == parent_capture.manifest.capture_id
            assert binding["parent_manifest_sha256"] == parent_capture.manifest_sha256
            assert capture.manifest.root_lineage_id == parent_capture.manifest.root_lineage_id
            assert capture.manifest.source_state_sha256 == parent_capture.manifest.state_sha256
            assert binding["state_sha256"] == capture.manifest.state_sha256
            assert binding["decision_event_sha256"] == starts[index]["record_sha256"]
            assert canonical_sha256(binding) == saved[index]["binding_sha256"]
            step = episode["decisions"][index - 1]
            assert binding["policy_observation_sha256"] == step["observation_sha256"]
            snapshots += 1
            if sample["status"] == "measured":
                td = directory / "targets" / f"{c['case']}-decision-{index:03d}"
                target = loop.load(td / "target.json")
                assert target["capture_id"] == capture.manifest.capture_id
                assert target["continuation_sha256"] == canonical_sha256(actor.to_dict())
                assert target["return_schema"] == loop.RETURN_SCHEMA
                branches = list(td.glob("branch-*/episode.json"))
                assert {tuple(map(int, p.parent.name.split("-")[1:])) for p in branches} == {
                    (offset, slot) for offset in loop.OFFSETS for slot in target["slots"]}
                for p in branches:
                    branch = loop.load(p)
                    assert (branch["decisions"][0]["observation_sha256"]
                            == step["observation_sha256"])
                    identity = loop.load(p.parent / "events/event-00001.json")[
                        "payload"]["identity"]
                    assert identity["model_sha256"] == target["continuation_sha256"]
                    assert identity["capture_id"] == capture.manifest.capture_id
                    assert identity["learner_continuation"]
                    assert branch["decisions"][0]["move_slot"] == identity["first_slot"]
                    for d in branch["decisions"][1:]:
                        assert d["kind"] == "attack"
                        assert selected_move(actor, frozen, d) == d["move_slot"]
                        branch_predictions += 1
    assert snapshots == len(list(directory.glob("trajectories/*/snapshots/*/capture.state")))
    assert verified["episodes"] == 64 + len(targets) * 6
    assert sum(v["measured"] + v["censored"] for v in indices.values()) == 256
    assert not list(directory.glob("**/candidate-model.json"))
    return {"schema": "pokemon.red.status-trajectory-coverage-audit.v1", **verified,
            "new_target_contexts": target_audit["new_target_contexts"],
            "snapshots": snapshots, "indices": indices, "diagnostics": result["diagnostics"],
            "trajectory_predictions_verified": trajectory_predictions,
            "branch_continuation_predictions_verified": branch_predictions,
            "unchanged_trajectory_action_sequences": unchanged_trajectories,
            "fits": 0, "authority_promotions": 0, "independent_heldout_roots": 0,
            "collection_delta": 0, "gameplay_running": False,
            "actor_sha256": sha(actor_path), "giovanni_completed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("experiment", "actor", "frozen", "parent", "prior_train"):
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    a = parser.parse_args()
    print(json.dumps(inspect(a.experiment, a.actor, a.frozen, a.parent, a.prior_train), indent=2))
