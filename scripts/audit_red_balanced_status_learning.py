"""Read-only reconciliation of the frozen balanced experiment and actual decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean

import numpy as np
import run_red_balanced_status_curriculum as experiment
from audit_red_status_learning import audit, sha

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_balanced_status_features import project_balanced_status_moves
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_status_battle_features import STATUS_MOVE_NAMES, status_choice_slots
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.scenario_lab import ScenarioPartition


def load(path):
    return json.loads(path.read_bytes())


def run(directory, frozen_path):
    assert sha(frozen_path) == experiment.lab.K_SHA
    plan, result, fit, collection = [load(directory / (name + ".json"))
                                   for name in ("plan", "result", "fit", "collection")]
    assert not (directory / "failure.json").exists()
    assert plan["seed"] == experiment.SEED and plan["max_fits"] == fit["fits"] == 1
    assert plan["frozen"]["sha256"] == sha(frozen_path)
    candidate = TrainerPracticeThreeHeadModel.from_dict(load(directory / "candidate-model.json"))
    frozen = TrainerPracticeThreeHeadModel.from_dict(load(frozen_path))
    assert fit["candidate"]["sha256"] == sha(directory / "candidate-model.json")
    assert candidate.damage_reference.to_dict() == frozen.move.to_dict()
    assert candidate.control.to_dict() == frozen.control.to_dict()
    assert candidate.switch.to_dict() == frozen.switch.to_dict()
    assert candidate.train_root_ids == frozen.train_root_ids
    assert np.count_nonzero(candidate.move.weights1[:len(STATUS_MOVE_NAMES)]) == 0
    summary = audit(directory, projector=project_balanced_status_moves)
    targets = [load(p) for p in sorted(directory.glob("*/target.json"))]
    assert len(targets) == collection["contexts"] == fit["examples"]
    assert set(candidate.train_capture_ids) == {
        *frozen.train_capture_ids, *(t["capture_id"] for t in targets)}
    train_ids = {r["id"] for r in plan["recipes"] if r["role"] == "train"}
    heldout_ids = {r["id"] for r in plan["recipes"] if r["role"] == "holdout"}
    assert len(train_ids) == 64 and len(heldout_ids) == 32 and not train_ids & heldout_ids
    regrets = {"baseline": [], "candidate": []}
    for path in sorted(directory.glob("*/target.json")):
        target = load(path)
        case = path.parent.name.removesuffix("-post")
        assert case in train_ids and target["root"] in frozen.train_root_ids
        stem = "intermediate.state" if path.parent.name.endswith("-post") else "capture.state"
        capture = open_battle_scenario_capture(path.parent / stem, path.parent / (stem + ".json"))
        assert capture.manifest.capture_id == target["capture_id"]
        assert capture.manifest.partition is ScenarioPartition.TRAIN
        branches = list(path.parent.glob("branch-*/episode.json"))
        expected = {(offset, slot) for offset in experiment.OFFSETS for slot in target["slots"]}
        assert {(int(p.parent.name.split("-")[1]), int(p.parent.name.split("-")[2]))
                for p in branches} == expected
        for branch in branches:
            identity = load(branch.parent / "events/event-00001.json")["payload"]["identity"]
            assert identity["capture_id"] == capture.manifest.capture_id
            assert identity["model_sha256"] == canonical_sha256(frozen.to_dict())
            assert identity["actor_memory_writes"] == 0 and identity["horizon"] == 8
        damage = next(i for i, v in enumerate(target["vectors"])
                      if v[STATUS_MOVE_NAMES.index("move.category.status")] == 0)
        chosen = candidate.move.predict_index(target["vectors"])
        for key, index in (("baseline", damage), ("candidate", chosen)):
            regrets[key].append(max(target["returns"]) - target["returns"][index])
    for key, values in regrets.items():
        assert abs(fmean(values) - fit[key + "_regret"]) < 1e-10
    evaluations = result["evaluations"]
    assert {(e["case"], e["arm"]) for e in evaluations} == {
        (case, arm) for case in heldout_ids for arm in ("candidate", "frozen")}
    assert len(evaluations) == 64
    verified_predictions = 0
    for row in evaluations:
        case = directory / row["case"]
        capture = open_battle_scenario_capture(case / "capture.state", case / "capture.state.json")
        assert capture.manifest.capture_id not in candidate.train_capture_ids
        episode = load(case / row["arm"] / "episode.json")
        identity = load(case / row["arm"] / "events/event-00001.json")["payload"]["identity"]
        model = candidate if row["arm"] == "candidate" else frozen
        assert identity["capture_id"] == capture.manifest.capture_id
        assert identity["model_sha256"] == canonical_sha256(model.to_dict())
        assert identity["first_slot"] is None and identity["actor_memory_writes"] == 0
        assert row["won"] == episode["battle_won"]
        assert row["metrics"] == episode["metrics"]
        assert row["decisions"] == episode["decision_count"]
        assert abs(row["return"] - experiment.lab.outcome_value(episode)) < 1e-10
        if row["arm"] != "candidate":
            continue
        assert row["status_choices"] == experiment.choice_diagnostics(episode)
        for step in episode["decisions"]:
            if step["kind"] != "attack":
                continue
            obs = step["observation"]
            projected = project_balanced_status_moves(
                obs, BattleFeatureProjector(PokemonRedBattleCatalog()).project(obs))
            slots = status_choice_slots(projected, tuple(step["legal_move_slots"]), frozen.move)
            vectors = tuple(projected.candidate_vectors[projected.candidate_slots.index(s)]
                            for s in slots)
            assert step["move_slot"] == slots[candidate.move.predict_index(vectors)]
            verified_predictions += 1
    wins = {arm: sum(e["won"] for e in evaluations if e["arm"] == arm)
            for arm in ("frozen", "candidate")}
    concerns = sum(bool(c["concerns"]) for e in evaluations if e["arm"] == "candidate"
                   for c in e["status_choices"])
    baselines = {e["case"]: e for e in evaluations if e["arm"] == "frozen"}
    useful = sum(e["won"] and e["return"] > baselines[e["case"]]["return"] + .05
                 and any(not c["concerns"] for c in e["status_choices"])
                 for e in evaluations if e["arm"] == "candidate")
    passed = wins["candidate"] >= wins["frozen"] and concerns == 0 and useful > 0
    assert wins == result["wins"] and concerns == result["concerning_status_selections"]
    assert useful == result["improved_won_cases_with_status"]
    assert passed == result["bounded_screen_passed"]
    assert summary["episodes"] == 6*len(targets) + 16 + 64 <= plan["max_episodes"]
    return {"schema": "pokemon.red.balanced-status-learning-audit.v1", **summary,
            "source_commit": plan["source_commit"], "candidate_sha256": sha(
                directory / "candidate-model.json"), "fits": 1,
            "baseline_train_regret": fit["baseline_regret"],
            "candidate_train_regret": fit["candidate_regret"],
            "withheld_pairs": 32, "withheld_wins": wins,
            "concerning_status_selections": concerns,
            "improved_won_cases_with_status": useful, "bounded_screen_passed": passed,
            "verified_candidate_move_predictions": verified_predictions,
            "frozen_damage_control_switch_preserved": True,
            "legacy_feature_weights_zero": True, "holdout_capture_ids_excluded": True,
            "censored_preparations": collection["censored"],
            "independent_heldout_roots": 0, "authority_promotions": 0,
            "collection_delta": 0, "giovanni_completed": False,
            "gameplay_running": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--frozen", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.experiment, args.frozen), sort_keys=True, indent=2))
