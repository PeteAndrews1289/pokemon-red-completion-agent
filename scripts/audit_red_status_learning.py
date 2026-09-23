"""Read-only audit of status experiments, labels, retained failures and model identities."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import fmean

import run_red_status_curriculum as lab

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_status_battle_features import project_status_moves
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(directory, *, projector=project_status_moves, return_value=lab.outcome_value,
          plan_path=None):
    episodes, forced, decisions, events, frames = [], 0, 0, 0, 0
    stops = {}
    status_choices = 0
    for path in sorted(directory.glob("**/episode.json")):
        episode = json.loads(path.read_bytes())
        endpoint = json.loads((path.parent / "final-state.json").read_bytes())
        log = verify_trainer_practice_event_log(path.parent / "events")
        terminal = json.loads(
            sorted((path.parent / "events").glob("event-*.json"))[-1].read_bytes()
        )
        assert log["terminal_event"] == "run_finished"
        assert terminal["payload"]["outcome"]["episode_sha256"] == canonical_sha256(episode)
        assert endpoint["state_sha256"] == sha(path.parent / "final.state")
        assert endpoint["episode_returned"] and endpoint["pressed_buttons"] == []
        assert episode["metrics"]["invalid_action_failures"] == 0
        assert episode["stop_reason"] in {"battle_won", "party_defeated", "player_turn_budget"}
        for step in episode["decisions"]:
            assert step["observation_sha256"] == canonical_sha256(step["observation"])
            diagnostics = step.get("model_diagnostics") or {}
            forced += int("forced_first_choice_ref" in diagnostics)
            if step["kind"] == "attack":
                assert step["move_slot"] in step["legal_move_slots"]
                move = next(
                    m
                    for m in step["observation"]["features"]["party"]["lead"]["moves"]
                    if m["slot_index"] == step["move_slot"] - 1
                )
                status_choices += (
                    lab.PokemonRedBattleCatalog().resolve_move(move["move_ref"]).category
                    == "status"
                )
        episodes.append(episode)
        events += log["event_count"]
        decisions += episode["decision_count"]
        frames += endpoint["frame_delta"]
        stops[episode["stop_reason"]] = stops.get(episode["stop_reason"], 0) + 1
    targets = []
    for path in sorted(directory.glob("*/target.json")):
        target = json.loads(path.read_bytes())
        assert target["role"] == "train"
        branches = list(path.parent.glob("branch-*/episode.json"))
        for branch in branches:
            observation = json.loads(branch.read_bytes())["decisions"][0]["observation"]
            projected = projector(
                observation,
                BattleFeatureProjector(lab.PokemonRedBattleCatalog()).project(observation),
            )
            assert target["vectors"] == [
                list(projected.candidate_vectors[projected.candidate_slots.index(slot)])
                for slot in target["slots"]
            ]
        for i, slot in enumerate(target["slots"]):
            values = [
                return_value(json.loads(p.read_bytes()))
                for p in branches
                if int(p.parent.name.rsplit("-", 1)[1]) == slot
            ]
            assert values and abs(fmean(values) - target["returns"][i]) < 1e-10
        targets.append(target)
    return {
        "episodes": len(episodes),
        "decision_records": decisions,
        "prescribed_first_choices": forced,
        "learned_continuation_or_evaluation_choices": decisions - forced,
        "status_move_attempts_including_prescribed": status_choices,
        "event_records": events,
        "frames": frames,
        "stops": stops,
        "invalid_actions": 0,
        "actor_memory_writes": 0,
        "new_target_contexts": len(targets),
        "plan_sha256": sha(plan_path or directory / "plan.json"),
        "all_event_and_terminal_hashes_verified": True,
    }


def run(args):
    frozen = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.frozen.read_bytes()))
    assert sha(args.frozen) == lab.K_SHA
    packets = {
        label: audit(path)
        for label, path in (
            ("pilot", args.pilot),
            ("opening", args.opening),
            ("sequence", args.sequence),
        )
    }
    for label, path in (("opening", args.opening), ("sequence", args.sequence)):
        fit = json.loads((path / "fit.json").read_bytes())
        result = json.loads((path / "result.json").read_bytes())
        model = TrainerPracticeThreeHeadModel.from_dict(
            json.loads((path / "candidate-model.json").read_bytes())
        )
        assert fit["candidate"]["sha256"] == sha(path / "candidate-model.json")
        assert model.control.to_dict() == frozen.control.to_dict()
        assert model.switch.to_dict() == frozen.switch.to_dict()
        assert model.train_root_ids == frozen.train_root_ids
        if label == "sequence":
            assert model.damage_reference.to_dict() == frozen.move.to_dict()
        for state in (
            *args.opening.glob("*-3/capture.state"),
            *args.sequence.glob("*-3/capture.state"),
        ):
            capture = open_battle_scenario_capture(state, state.with_suffix(".state.json"))
            assert capture.manifest.capture_id not in model.train_capture_ids
        pairs = result["evaluations"]
        assert len(pairs) == 16 and len({(p["case"], p["arm"]) for p in pairs}) == 16
        wins = {
            arm: sum(p["won"] for p in pairs if p["arm"] == arm) for arm in ("candidate", "frozen")
        }
        assert wins == result["wins"]
        packets[label].update(
            candidate_sha256=sha(path / "candidate-model.json"),
            fit_sha256=sha(path / "fit.json"),
            result_sha256=sha(path / "result.json"),
            fits=fit["fits"],
            fit_examples=fit["examples"],
            withheld_wins=wins,
            heldout_capture_ids_excluded_from_fit=True,
        )
        packets[label]["regret_before"] = fit.get("initial_regret", fit.get("baseline_regret"))
        packets[label]["regret_after"] = fit.get("fitted_regret", fit.get("candidate_regret"))
    return {
        "schema": "pokemon.red.status-learning-audit.v1",
        "packets": packets,
        "total_episodes": sum(p["episodes"] for p in packets.values()),
        "total_decision_records": sum(p["decision_records"] for p in packets.values()),
        "new_train_contexts": packets["opening"]["new_target_contexts"]
        + packets["sequence"]["new_target_contexts"],
        "independent_heldout_roots": 0,
        "promotions": 0,
        "fits": 2,
        "gameplay_running": False,
        "candidate_status": "both_rejected_for_live_use",
        "collection_delta": 0,
        "giovanni_completed": False,
        "limits": [
            "TRAIN-related generated holdouts, not independent natural transfer",
            "Single-member laboratory battles, not multi-opponent attrition qualification",
            "No learned item use or recovery switching qualification",
            "Status timing still fails on unseen contexts; these packets allow no third fit",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pilot", "opening", "sequence", "frozen"):
        parser.add_argument("--" + name, type=Path, required=True)
    print(json.dumps(run(parser.parse_args()), sort_keys=True, indent=2))
