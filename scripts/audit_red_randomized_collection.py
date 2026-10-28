"""Independent RNG collection audit; no fit or native execution."""

import argparse
import random
from pathlib import Path
from statistics import fmean, stdev

import numpy as np
from audit_red_status_learning import audit
from run_red_randomized_training_collection import SCHEMA, lab, loop

from pokemon_red_completion.red_balanced_status_features import BALANCED_STATUS_NAMES as N
from pokemon_red_completion.red_status_battle_features import project_for_head
from pokemon_red_completion.red_status_execution_learning import eligible_target
from pokemon_red_completion.red_status_win_conditioned_returns import (
    RETURN_SCHEMA,
    win_conditioned_return,
)


def validate_target(target, roots, seeds, model_sha):
    if (target["schema"] != SCHEMA or target["root"] not in roots or
            target["teacher_continuation"] != "K_damage_only" or not eligible_target(target) or
            target["rng_seeds"] != seeds or len(seeds) != 32 or len(set(seeds)) != 32 or
            any(type(s) is not int or not 0 <= s < 65536 for s in seeds) or
            target["continuation_sha256"] != model_sha or
            target["return_schema"] != RETURN_SCHEMA or
            len(target["slots"]) != 2 or len(set(target["slots"])) != 2):
        raise ValueError("RNG target scope differs")
    x = np.asarray(target["vectors"], float)
    y = np.asarray([target["rng_returns"][str(s)] for s in target["slots"]], float)
    if (x.shape != (2, len(N)) or y.shape != (2, 32) or not np.isfinite(x).all() or
            not np.isfinite(y).all() or set(target["rng_returns"]) !=
            {str(s) for s in target["slots"]} or
            not np.allclose(y.mean(axis=1), target["returns"], atol=1e-10, rtol=0)):
        raise ValueError("RNG target dimensions/means differ")
    gaps = y[1]-y[0]
    if any(abs(a-b) > 1e-10 for a, b in (
        (fmean(gaps[:16]), target["first_half_gap"]),
        (fmean(gaps[16:]), target["second_half_gap"]),
        (stdev(gaps.tolist())/32**.5, target["gap_standard_error_descriptive"]))):
        raise ValueError("RNG target split/uncertainty differs")
    return x, y


def verify_k_choices(episode, frozen, first_slot=None):
    projector = lab.BattleFeatureProjector(lab.PokemonRedBattleCatalog())
    count = 0
    for index, step in enumerate(episode["decisions"]):
        if step["kind"] != "attack":
            raise ValueError("single-member K trajectory has a non-attack")
        if index == 0 and first_slot is not None:
            if step["move_slot"] != first_slot:
                raise ValueError("prescribed alternative differs")
            continue
        obs = step["observation"]
        view = project_for_head(obs, projector.project(obs), frozen.move)
        legal = [s for s in view.candidate_slots if s in step["legal_move_slots"] and
                 not view.candidate_vectors[view.candidate_slots.index(s)][
                     view.feature_names.index("move.category.status")]]
        vectors = [view.candidate_vectors[view.candidate_slots.index(s)] for s in legal]
        if step["move_slot"] != legal[frozen.move.predict_index(vectors)]:
            raise ValueError("K continuation differs")
        count += 1
    return count


def inspect(directory):
    plan, result = loop.load(directory / "plan.json"), loop.load(directory / "result.json")
    seeds = random.Random(plan["seed"]).sample(range(65536), 32)
    if seeds != plan["rng_seeds"] or plan["max_fits"] != 0:
        raise ValueError("sampling or fit scope differs")
    for binding in [plan["frozen"], *plan["sources"]]:
        if lab.common._binding(Path(binding["path"])) != binding:
            raise ValueError("collection input binding differs")
    frozen = lab.TrainerPracticeThreeHeadModel.from_dict(loop.load(Path(plan["frozen"]["path"])))
    if plan["frozen"]["sha256"] != lab.K_SHA:
        raise ValueError("not qualified K")
    model_sha = lab.canonical_sha256(frozen.to_dict())
    captures, seen, count = {}, set(plan["excluded_state_sha256"]), 0
    for recipe in plan["recipes"]:
        folder = directory / "starts" / recipe["id"]
        c = lab.open_battle_scenario_capture(folder / "capture.state",
                                             folder / "capture.state.json")
        if (recipe["role"] != "train" or c.manifest.root_lineage_id != recipe["root"] or
                loop.load(folder / "setup.json")["recipe"] != recipe or
                c.manifest.state_sha256 in seen):
            raise ValueError("opening recipe or exclusion differs")
        seen.add(c.manifest.state_sha256)
        captures[c.manifest.capture_id] = c
        trajectory = directory / "trajectories" / recipe["id"]
        identity = loop.load(trajectory / "events/event-00001.json")["payload"]["identity"]
        if (identity["capture_id"] != c.manifest.capture_id or
                identity["model_sha256"] != model_sha or not identity["damage_only_teacher"]):
            raise ValueError("teacher trajectory identity differs")
        count += verify_k_choices(loop.load(trajectory / "episode.json"), frozen)
        for path in trajectory.glob("snapshots/*/capture.state.json"):
            later = lab.open_battle_scenario_capture(path.with_suffix(""), path)
            binding = loop.load(path.parent / "binding.json")
            events = [loop.load(p) for p in (trajectory / "events").glob("event-*.json")]
            if (later.manifest.source_state_sha256 != c.manifest.state_sha256 or
                    binding["parent_manifest_sha256"] != c.manifest_sha256 or
                    not any(e["payload"].get("binding_sha256") == lab.canonical_sha256(binding)
                            for e in events) or later.manifest.state_sha256 in seen):
                raise ValueError("later snapshot provenance differs")
            seen.add(later.manifest.state_sha256)
            captures[later.manifest.capture_id] = later
    paths = sorted((directory / "targets").glob("*/target.json"))
    for path in paths:
        target = loop.load(path)
        validate_target(target, frozen.train_root_ids, seeds, model_sha)
        parent = captures[target["capture_id"]]
        if (parent.manifest.partition is not lab.ScenarioPartition.TRAIN or
                target["state_sha256"] != parent.manifest.state_sha256 or
                target["manifest_sha256"] != parent.manifest_sha256):
            raise ValueError("target parent binding differs")
        inventory = {(int(p.parent.name.split("-")[1]), int(p.parent.name.split("-")[2]))
                     for p in path.parent.glob("branch-*/episode.json")}
        if inventory != {(s, a) for s in seeds for a in target["slots"]}:
            raise ValueError("branch inventory differs")
        children = set()
        for i, seed in enumerate(seeds):
            folder = path.parent / f"seed-{seed}"
            child = lab.open_battle_scenario_capture(folder / "capture.state",
                                                     folder / "capture.state.json")
            receipt = loop.load(folder / "intervention.json")
            if (child.manifest.partition is not lab.ScenarioPartition.TRAIN or
                    child.manifest.source_state_sha256 != parent.manifest.state_sha256 or
                    child.manifest.root_lineage_id != parent.manifest.root_lineage_id or
                    child.manifest.initial_observation_sha256 !=
                    parent.manifest.initial_observation_sha256 or
                    receipt["parent_manifest_sha256"] != parent.manifest_sha256 or
                    receipt["after"] != [seed >> 8, seed & 255] or receipt["seed"] != seed or
                    receipt["actor_memory_writes"] != 0 or receipt["frames_advanced"] != 0):
                raise ValueError("RNG intervention lineage differs")
            children.add(child.manifest.state_sha256)
            for slot in target["slots"]:
                folder = path.parent / f"branch-{seed}-{slot}"
                episode = loop.load(folder / "episode.json")
                identity = loop.load(folder / "events/event-00001.json")["payload"]["identity"]
                if (identity["capture_id"] != child.manifest.capture_id or
                        identity["model_sha256"] != model_sha or identity["first_slot"] != slot or
                        identity["partition"] != "train" or identity["offset"] != 0 or
                        identity["horizon"] != 40 or identity.get("learner_continuation") or
                        identity["actor_memory_writes"] != 0):
                    raise ValueError("RNG branch identity differs")
                if abs(win_conditioned_return(episode)-target["rng_returns"][str(slot)][i]) > 1e-10:
                    raise ValueError("recomputed branch return differs")
                obs = episode["decisions"][0]["observation"]
                view = loop.project_balanced_status_moves(obs,
                    lab.BattleFeatureProjector(lab.PokemonRedBattleCatalog()).project(obs))
                if [list(view.candidate_vectors[view.candidate_slots.index(s)])
                        for s in target["slots"]] != target["vectors"]:
                    raise ValueError("branch features differ")
                count += verify_k_choices(episode, frozen, slot)
        if len(children) != 32:
            raise ValueError("RNG forks are not distinct")
    native = audit(directory)
    if native != result["native"] or native["episodes"] != len(plan["recipes"])+64*len(paths):
        raise ValueError("complete native inventory differs")
    coverage = loop.load(directory / "coverage.json")
    measured = [c for c in coverage if c["status"] == "measured"]
    passed = (len(paths) == len(measured) and
              sum(c["kind"] == "opening" for c in measured) == 64 and
              sum(c["kind"] == "later-002" for c in measured) >= 16)
    if passed != result["coverage_passed"] or len(paths) != result["targets"]:
        raise ValueError("coverage result differs")
    return {"plan": lab.common._binding(directory / "plan.json"),
            "result": lab.common._binding(directory / "result.json"), "native": native,
            "targets": len(paths), "K_choices_recomputed": count, "coverage_passed": passed,
            "target_bindings": [lab.common._binding(p) for p in paths]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    report = inspect(args.directory)
    lab.write(args.directory / "independent-audit.json", report)
    print({k: v for k, v in report.items() if k != "target_bindings"})
