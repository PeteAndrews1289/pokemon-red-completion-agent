"""Reconcile actual closed-loop collection, fit isolation and selected actor behavior."""

import argparse
import json
from pathlib import Path
from statistics import fmean

import numpy as np
import run_red_closed_loop_status as run
from audit_red_status_learning import audit, sha

from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_balanced_status_features import (
    BALANCED_STATUS_NAMES,
    project_balanced_status_moves,
)
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_status_battle_features import STATUS_MOVE_NAMES, status_choice_slots
from pokemon_red_completion.red_status_closed_loop_returns import closed_loop_return
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel


def model(path):
    return TrainerPracticeThreeHeadModel.from_dict(run.load(path))


def verify_screen(directory, candidate, baseline):
    rows = run.load(directory / "summary.json")
    count = 0
    for row in rows:
        episode = run.load(directory / row["case"] / "episode.json")
        assert episode["battle_won"] == row["won"]
        assert episode["decision_count"] == row["decisions"]
        assert abs(closed_loop_return(episode) - row["return"]) < 1e-10
        identity = run.load(directory / row["case"] / "events/event-00001.json")[
            "payload"]["identity"]
        assert identity["model_sha256"] == canonical_sha256(candidate.to_dict())
        assert identity["first_slot"] is None
        if candidate.damage_reference is None:
            continue
        assert row["status_choices"] == run.balanced.choice_diagnostics(episode)
        for step in episode["decisions"]:
            if step["kind"] != "attack":
                continue
            obs = step["observation"]
            projected = project_balanced_status_moves(
                obs, BattleFeatureProjector(PokemonRedBattleCatalog()).project(obs))
            slots = status_choice_slots(projected, tuple(step["legal_move_slots"]), baseline.move)
            vectors = tuple(projected.candidate_vectors[projected.candidate_slots.index(s)]
                            for s in slots)
            assert step["move_slot"] == slots[candidate.move.predict_index(vectors)]
            count += 1
    return rows, count


def inspect(directory, frozen_path, parent):
    assert sha(frozen_path) == run.lab.K_SHA
    result = run.load(directory / "result.json")
    plan = run.load(directory / "plan.json")
    frozen = model(frozen_path)
    assert result["fits"] <= plan["max_iterations"] == 3
    all_rows = audit(directory, projector=project_balanced_status_moves,
                     return_value=closed_loop_return)
    baseline, _ = verify_screen(directory / "train-baseline", frozen, frozen)
    rounds = []
    total_predictions = 0
    for number in range(result["fits"]):
        rd = directory / f"round-{number}"
        collected = audit(rd, projector=project_balanced_status_moves,
                          return_value=closed_loop_return, plan_path=directory / "plan.json")
        actor = model(rd / "candidate-model.json")
        continuation = model(rd / "continuation-model.json")
        fit = run.load(rd / "fit.json")
        assert fit["candidate"]["sha256"] == sha(rd / "candidate-model.json")
        assert actor.damage_reference.to_dict() == frozen.move.to_dict()
        assert actor.control.to_dict() == frozen.control.to_dict()
        assert actor.switch.to_dict() == frozen.switch.to_dict()
        assert actor.train_root_ids == frozen.train_root_ids
        assert np.count_nonzero(actor.move.weights1[:len(STATUS_MOVE_NAMES)]) == 0
        targets = [run.load(p) for p in rd.glob("*/target.json")]
        assert set(actor.train_capture_ids) == {
            *frozen.train_capture_ids, *(t["capture_id"] for t in targets)}
        assert len(targets) == fit["examples"]
        baseline_regret, fitted_regret = [], []
        no_change_contrasts = []
        for path in rd.glob("*/target.json"):
            t = run.load(path)
            assert t["return_schema"] == run.RETURN_SCHEMA
            assert t["continuation_sha256"] == canonical_sha256(continuation.to_dict())
            assert t["root"] in frozen.train_root_ids
            assert {tuple(map(int, p.parent.name.split("-")[1:]))
                    for p in path.parent.glob("branch-*/episode.json")} == {
                        (offset, slot) for offset in run.OFFSETS for slot in t["slots"]}
            for p in path.parent.glob("branch-*/episode.json"):
                identity = run.load(p.parent / "events/event-00001.json")["payload"]["identity"]
                assert identity["learner_continuation"]
                assert identity["model_sha256"] == t["continuation_sha256"]
                assert identity["capture_id"] == t["capture_id"]
            damage = next(i for i, v in enumerate(t["vectors"])
                          if v[BALANCED_STATUS_NAMES.index("choice.status")] == 0)
            selected = actor.move.predict_index(t["vectors"])
            baseline_regret.append(max(t["returns"]) - t["returns"][damage])
            fitted_regret.append(max(t["returns"]) - t["returns"][selected])
            status_values = dict(zip(BALANCED_STATUS_NAMES, t["vectors"][1-damage], strict=True))
            if any(status_values["choice." + k] for k in (
                "major_status_occupied", "already_confused", "accuracy_floor")):
                no_change_contrasts.append(t["returns"][damage] - t["returns"][1-damage])
        assert abs(fmean(baseline_regret) - fit["baseline_regret"]) < 1e-10
        assert abs(fmean(fitted_regret) - fit["candidate_regret"]) < 1e-10
        screen, predictions = verify_screen(rd / "train-screen", actor, frozen)
        verified_gate = run.gate(screen, baseline)
        assert verified_gate == run.load(rd / "screen.json") == result["train_screens"][number]
        total_predictions += predictions
        rounds.append({**collected, "candidate_sha256": sha(rd / "candidate-model.json"),
                       "screen": verified_gate, "baseline_regret": fit["baseline_regret"],
                       "candidate_regret": fit["candidate_regret"],
                       "stopping_vs_repetition_contrasts": len(no_change_contrasts),
                       "stopping_better": sum(v > .05 for v in no_change_contrasts)})
    heldout = None
    if result["withheld"] is not None:
        selected = model(directory / f"round-{result['selected_iteration']}"
                         / "candidate-model.json")
        held_base, _ = verify_screen(directory / "held-baseline", frozen, frozen)
        held_candidate, predictions = verify_screen(directory / "held-candidate", selected, frozen)
        total_predictions += predictions
        heldout = run.gate(held_candidate, held_base)
        assert heldout == result["withheld"]
        assert len(held_candidate) == len(held_base) == 32
        for p in directory.glob("balanced-*/capture.state.json"):
            assert run.load(p)["capture_id"] not in selected.train_capture_ids
    else:
        assert not (directory / "held-candidate").exists()
    for rd in directory.glob("round-*"):
        candidate = model(rd / "candidate-model.json")
        for p in parent.glob("balanced-*-2-*/capture.state.json"):
            assert run.load(p)["capture_id"] not in candidate.train_capture_ids
    amendment = run.load(directory / "timing-amendment.json")
    assert amendment["original_plan"]["sha256"] == sha(directory / "plan.json")
    assert amendment["original_failure"]["sha256"] == sha(directory / "failure.json")
    assert not (directory / "round-0/balanced-sleep-0-0/branch-29-2/final.state").exists()
    return {"schema": "pokemon.red.closed-loop-status-audit.v1", **all_rows,
            "new_target_contexts": sum(r["new_target_contexts"] for r in rounds),
            "unique_target_capture_ids": len({run.load(p)["capture_id"]
                                               for p in directory.glob("round-*/*/target.json")}),
            "rounds": rounds, "fits": result["fits"], "withheld": heldout,
            "verified_candidate_predictions": total_predictions,
            "recovered_preinput_timing_failures": 1, "completed_episode_replays": 0,
            "independent_heldout_roots": 0, "authority_promotions": 0,
            "gameplay_running": False, "collection_delta": 0, "giovanni_completed": False}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("experiment", "frozen", "parent"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(inspect(a.experiment, a.frozen, a.parent), sort_keys=True, indent=2))
