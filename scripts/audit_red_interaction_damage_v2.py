"""Reconstruct the complete V2 damage experiment from retained native records."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import fmean

import numpy as np
import run_red_interaction_damage_successor as packet
from audit_red_interaction_damage_successor import _audit_events, _audit_source

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_damage_interaction_head import (
    FEATURE_NAMES,
    RIDGE,
    project_damage_interactions,
)
from pokemon_red_completion.red_trainer_practice_features import project_trainer_move_features

old = packet.old


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_bytes())


def reconstruct_target(output, target, offsets, catalog, *, counters=None):
    directory = output / target["id"]
    capture = open_battle_scenario_capture(
        directory / "capture.state", directory / "capture.state.json"
    )
    require(capture.manifest.state_sha256 == target["capture_sha256"], "capture/target differs")
    require(capture.manifest.root_lineage_id == target["root"], "target/root differs")
    require(target["slots"] == [1, 2, 3, 4], "target slots differ")
    require(len(target["branches"]) == 4 * len(offsets), "branch inventory incomplete")
    require(
        {(b["offset"], b["slot"]) for b in target["branches"]}
        == {(offset, slot) for offset in offsets for slot in range(1, 5)},
        "branch identity differs",
    )
    values = {slot: [] for slot in range(1, 5)}
    for branch in target["branches"]:
        path = directory / f"branch-{branch['offset']}-{branch['slot']}"
        episode = read(path / "episode.json")
        require(old.sha(path / "episode.json") == branch["episode_sha256"], "episode hash differs")
        require(
            episode["opening_idle_frames"] == branch["offset"] and len(episode["decisions"]) == 1,
            "episode timing/decision inventory differs",
        )
        decision = episode["decisions"][0]
        observation = decision["observation"]
        require(
            old.lab.canonical_sha256(observation) == decision["observation_sha256"],
            "observation hash differs",
        )
        require(
            decision["kind"] == "attack"
            and decision["move_slot"] == branch["slot"]
            and decision["legal_move_slots"] == [1, 2, 3, 4],
            "forced action or mask differs",
        )
        projection = project_trainer_move_features(
            observation, BattleFeatureProjector(catalog).project(observation)
        )
        require(projection.candidate_slots == (1, 2, 3, 4), "projected action mask differs")
        np.testing.assert_allclose(
            projection.candidate_vectors, target["vectors"], atol=1e-12, rtol=0
        )
        require(
            decision["opponent_hp_before"] == decision["state_before"]["opponent_hp"]
            and decision["opponent_hp_after"] == decision["state_after"]["opponent_hp"],
            "raw HP joins differ",
        )
        damage = (decision["opponent_hp_before"] - decision["opponent_hp_after"]) / observation[
            "features"
        ]["battle"]["opponent_max_hp"]
        require(
            0 <= damage <= 1 and abs(damage - branch["damage_fraction"]) <= 1e-12,
            "native HP damage differs",
        )
        values[branch["slot"]].append(damage)
        terminal = read(path / "final-state.json")
        require(old.sha(path / "final.state") == terminal["state_sha256"], "terminal bytes differ")
        events = _audit_events(path, "run_finished")
        identity = read(path / "events/event-00001.json")["payload"]["identity"]
        require(
            identity["first_slot"] == branch["slot"]
            and identity["offset"] == branch["offset"]
            and identity["capture_id"] == capture.manifest.capture_id
            and identity["partition"] == "train",
            "event identity differs",
        )
        if counters is not None:
            require(
                branch["terminal_sha256"] == terminal["state_sha256"]
                and branch["actual_actions"] == terminal["completed_actions"]
                and branch["attempted_actions"] == terminal["attempted_actions"]
                and branch["actual_frames"] == terminal["frame_delta"],
                "cost/terminal joins differ",
            )
            require(
                0 < terminal["completed_actions"] <= terminal["attempted_actions"] <= 5000
                and terminal["frame_delta"] <= 120000
                and terminal["wall_elapsed_seconds"] <= 45,
                "native branch exceeded frozen caps",
            )
            require(
                branch["player_hp_before"] == decision["state_before"]["party_hp"]
                and branch["player_hp_after"] == decision["state_after"]["party_hp"]
                and branch["party_pp_spent"] == episode["metrics"]["party_pp_spent"]
                and branch["invalid_action_failures"]
                == episode["metrics"]["invalid_action_failures"]
                and episode["memory_write_actions"] == 0
                and episode["teacher_queries"] == 0,
                "resource cost or native authority differs",
            )
            counters["branches"] += 1
            counters["event_records"] += events
            counters["completed_actions"] += terminal["completed_actions"]
            counters["attempted_actions"] += terminal["attempted_actions"]
            counters["frames"] += terminal["frame_delta"]
    measured = [fmean(values[slot]) for slot in range(1, 5)]
    np.testing.assert_allclose(measured, target["mean_damage"], atol=1e-12, rtol=0)


def audit(output):
    plan, result = read(output / "PLAN.json"), read(output / "RESULT.json")
    _audit_source(plan)
    require(
        plan["schema"] == "pokemon.red.interaction-damage-successor.v2"
        and plan["offsets"] == list(packet.V2_OFFSETS),
        "V2 plan identity differs",
    )
    require(
        not (output / "FAILURE.json").exists(), "complete result has retained execution failure"
    )
    for path, expected in plan["protected_inputs"].items():
        require(old.sha(Path(path)) == expected, "protected input changed")
    _, catalog, sources, k, admitted = old.inputs()
    _, _, _, exclusions = packet.experiment_config(2)
    packet.validate_plan(
        plan["rows"], plan["inventory"]["families"], sources, excluded_pairs=exclusions
    )
    require(
        plan["additional_excluded_pairs"] == [list(x) for x in sorted(exclusions)],
        "V1 exclusions differ",
    )
    require(result["plan_sha256"] == old.sha(output / "PLAN.json"), "result plan binding differs")
    claim, receipt = read(output / "FIT_CLAIM.json"), read(output / "FIT_RECEIPT.json")
    candidate = old.TrainerPracticeThreeHeadModel.from_dict(read(output / "candidate-model.json"))
    old.assert_untouched_components(admitted, candidate)
    require(
        claim["fit_attempts"] == receipt["fit_attempts"] == receipt["fit_completed"] == 1,
        "sole fit claim differs",
    )
    require(
        claim["plan_sha256"] == old.sha(output / "PLAN.json")
        and claim["fit_targets_sha256"]
        == receipt["fit_targets_sha256"]
        == candidate.damage_reference.train_dataset_sha256
        == old.sha(output / "FIT_TARGETS.json"),
        "fit dataset binding differs",
    )
    require(
        receipt["candidate_sha256"]
        == result["candidate_sha256"]
        == old.sha(output / "candidate-model.json"),
        "candidate binding differs",
    )
    fit, comparison = read(output / "FIT_TARGETS.json"), read(output / "COMPARISON_TARGETS.json")
    require(len(fit) == 72 and len(comparison) == 48, "dataset inventory differs")
    require(
        old.sha(output / "COMPARISON_TARGETS.json") == result["comparison_targets_sha256"],
        "comparison hash differs",
    )
    candidate_time = (output / "candidate-model.json").stat().st_mtime_ns
    require(
        (output / "FIT_CLAIM.json").stat().st_mtime_ns
        <= candidate_time
        < min((output / row["id"] / "setup.json").stat().st_mtime_ns for row in comparison),
        "fit/comparison chronology differs",
    )
    counts = Counter()
    for role, targets in (("fit", fit), ("comparison", comparison)):
        recipes = [r for r in plan["rows"] if r["role"] == role]
        require(
            [t["id"] for t in targets] == [r["id"] for r in recipes], "frozen role order differs"
        )
        for recipe, target in zip(recipes, targets, strict=True):
            directory = output / recipe["id"]
            setup = read(directory / "setup.json")
            require(
                setup["recipe"] == recipe
                and read(directory / "target.json") == target
                and target["recipe_sha256"] == old.sha_recipe(recipe)
                and target["role"] == role
                and target["root"] == recipe["root"],
                "recipe/target differs",
            )
            reconstruct_target(output, target, plan["offsets"], catalog, counters=counts)
    x, y = [], []
    for target in fit:
        rows = project_damage_interactions(target["vectors"])
        for i in range(4):
            for j in range(i + 1, 4):
                x.append(rows[i] - rows[j])
                y.append(target["mean_damage"][i] - target["mean_damage"][j])
    x, y = np.asarray(x), np.asarray(y)
    expected = np.linalg.lstsq(
        np.vstack((x / np.sqrt(len(y)), np.sqrt(RIDGE) * np.eye(len(FEATURE_NAMES)))),
        np.concatenate((y / np.sqrt(len(y)), np.zeros(len(FEATURE_NAMES)))),
        rcond=None,
    )[0]
    np.testing.assert_allclose(
        expected, candidate.damage_reference.coefficients, atol=1e-10, rtol=0
    )
    checked = packet.score_comparison(
        comparison, plan["rows"], k.move, candidate.damage_reference, target_root=output
    )
    require(checked == read(output / "COMPARISON_RESULT.json"), "comparison score differs")
    for key, value in checked.items():
        if key in result["comparison"]:
            require(result["comparison"][key] == value, f"result comparison {key} differs")
    historical = read(old.OUTPUT / "train-targets.json")
    for target in historical:
        reconstruct_target(old.OUTPUT, target, old.OFFSETS, catalog)
    retention = packet.score_retention(historical, k.move, candidate.damage_reference)
    require(retention == result["retention"], "retention differs")
    require(
        counts["branches"] == 4320
        and counts["completed_actions"]
        == result["fit"]["controller_actions"] + result["comparison"]["controller_actions"]
        and counts["attempted_actions"]
        == result["fit"]["attempted_controller_actions"]
        + result["comparison"]["attempted_controller_actions"]
        and counts["frames"] == result["fit"]["frames"] + result["comparison"]["frames"],
        "aggregate cost differs",
    )
    decision = (
        "screen_passed_for_astra_review"
        if checked["gate_passed"] and retention["gate_passed"]
        else "rejected"
    )
    require(decision == result["decision"], "final gate decision differs")
    return {
        "schema": "pokemon.red.interaction-damage-v2-audit.v1",
        "passed": True,
        "decision": decision,
        "counts": dict(counts),
        "old_train_configurations_reconstructed": len(historical),
        "independent_ridge_coefficients_match": True,
        "protected_inputs_unchanged": True,
        "result_sha256": old.sha(output / "RESULT.json"),
        "plan_sha256": old.sha(output / "PLAN.json"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=old.PRIVATE / "red-interaction-damage-successor-20260923-v2"
    )
    args = parser.parse_args()
    report = audit(args.output)
    old.write_once(args.output / "AUDIT.json", report)
    print(json.dumps(report))
