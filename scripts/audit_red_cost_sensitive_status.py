"""Reconcile the cost-sensitive fit and every measured actor choice without gameplay."""

import argparse
import json
from pathlib import Path
from statistics import fmean

import numpy as np
import run_red_cost_sensitive_status as run
from audit_red_closed_loop_status import model, verify_screen
from audit_red_status_learning import audit, sha

from pokemon_red_completion.red_balanced_status_features import project_balanced_status_moves
from pokemon_red_completion.red_status_battle_features import STATUS_MOVE_NAMES
from pokemon_red_completion.red_status_closed_loop_returns import closed_loop_return


def inspect(directory, training, initial_path, frozen_path):
    loop = run.loop
    plan, result, fit = (loop.load(directory / name)
                         for name in ("plan.json", "result.json", "fit.json"))
    frozen, initial, candidate = (model(path) for path in (
        frozen_path, initial_path, directory / "candidate-model.json"))
    assert sha(frozen_path) == loop.lab.K_SHA
    assert sha(initial_path) == run.INITIAL_SHA == plan["initial"]["sha256"]
    assert candidate.move.training_objective == "expected_regret"
    assert candidate.damage_reference.to_dict() == frozen.move.to_dict()
    assert candidate.control.to_dict() == frozen.control.to_dict()
    assert candidate.switch.to_dict() == frozen.switch.to_dict()
    assert np.count_nonzero(candidate.move.weights1[:len(STATUS_MOVE_NAMES)]) == 0
    targets = [loop.load(p) for p in sorted(training.glob("*/target.json"))]
    assert len(targets) == fit["examples"] == 94
    assert [loop.lab.common._binding(p) for p in sorted(training.glob("*/target.json"))] == (
        plan["train_targets"])
    assert set(candidate.train_capture_ids) == set(initial.train_capture_ids)
    assert candidate.train_root_ids == frozen.train_root_ids
    for label, actor in (("initial", initial), ("candidate", candidate)):
        regret = fmean(max(t["returns"]) - t["returns"][actor.move.predict_index(t["vectors"])]
                       for t in targets)
        assert abs(regret - fit[label + "_regret"]) < 1e-10
    assert fit["candidate"]["sha256"] == sha(directory / "candidate-model.json")
    rows = audit(directory, projector=project_balanced_status_moves,
                 return_value=closed_loop_return)
    predictions = 0
    screen = withheld = None
    if result["screen"] is not None:
        assert fit["candidate_regret"] <= .70 * fit["initial_regret"]
        baseline, _ = verify_screen(directory / "train-baseline", frozen, frozen)
        chosen, count = verify_screen(directory / "train-screen", candidate, frozen)
        predictions += count
        assert len(baseline) == len(chosen) == 64
        screen = loop.gate(chosen, baseline)
        assert result["screen"] == screen
    if result["withheld"] is not None:
        assert screen["passed"]
        baseline, _ = verify_screen(directory / "held-baseline", frozen, frozen)
        chosen, count = verify_screen(directory / "held-candidate", candidate, frozen)
        predictions += count
        assert len(baseline) == len(chosen) == 32
        withheld = loop.gate(chosen, baseline)
        assert result["withheld"] == withheld
        for p in directory.glob("balanced-*/capture.state.json"):
            assert loop.load(p)["capture_id"] not in candidate.train_capture_ids
    else:
        assert not (directory / "held-candidate").exists()
    return {"schema": "pokemon.red.cost-sensitive-status-audit.v1", **rows,
            "fits": 1, "candidate_sha256": sha(directory / "candidate-model.json"),
            "reused_TRAIN_targets": len(targets), "new_target_contexts": 0,
            "initial_regret": fit["initial_regret"], "candidate_regret": fit["candidate_regret"],
            "screen": screen, "withheld": withheld,
            "verified_candidate_predictions": predictions, "independent_heldout_roots": 0,
            "authority_promotions": 0, "collection_delta": 0, "gameplay_running": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("experiment", "training", "initial", "frozen"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.experiment, args.training, args.initial, args.frozen), indent=2))
