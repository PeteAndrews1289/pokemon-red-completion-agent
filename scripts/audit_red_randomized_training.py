"""Recompute TRAIN RNG branches, lineage and K choices without playing or fitting."""

import argparse
import random
from pathlib import Path
from statistics import fmean, stdev

import run_red_randomized_training_diagnostic as experiment
from audit_red_status_learning import audit

from pokemon_red_completion.red_status_battle_features import project_for_head

lab, loop = experiment.lab, experiment.loop


def inspect(directory):
    plan, result = loop.load(directory / "plan.json"), loop.load(directory / "result.json")
    if plan["rng_seeds"] != random.Random(plan["seed"]).sample(range(65536), 32):
        raise ValueError("prospective RNG sampling differs")
    if lab.common._binding(Path(plan["frozen"]["path"])) != plan["frozen"]:
        raise ValueError("K binding differs")
    frozen = lab.TrainerPracticeThreeHeadModel.from_dict(loop.load(Path(plan["frozen"]["path"])))
    if plan["frozen"]["sha256"] != lab.K_SHA:
        raise ValueError("not qualified K")
    for binding in plan["sources"]:
        if lab.common._binding(Path(binding["path"])) != binding:
            raise ValueError("source binding differs")
    projector = lab.BattleFeatureProjector(lab.PokemonRedBattleCatalog())
    count = 0
    for recipe, summary in zip(plan["recipes"], result["contexts"], strict=True):
        folder = directory / recipe["id"]
        parent = lab.open_battle_scenario_capture(folder / "capture.state",
                                                  folder / "capture.state.json")
        if (parent.manifest.partition is not lab.ScenarioPartition.TRAIN or
                parent.manifest.root_lineage_id != recipe["root"] or
                recipe["role"] != "train" or summary != loop.load(folder / "diagnostic.json") or
                loop.load(folder / "setup.json")["recipe"] != recipe):
            raise ValueError("TRAIN source or recipe differs")
        values, signatures = {str(s): [] for s in summary["slots"]}, {str(s): set()
                                                                    for s in summary["slots"]}
        children = set()
        for seed in plan["rng_seeds"]:
            child_dir = folder / f"seed-{seed}"
            child = lab.open_battle_scenario_capture(child_dir / "capture.state",
                                                     child_dir / "capture.state.json")
            receipt = loop.load(child_dir / "intervention.json")
            if (child.manifest.partition is not lab.ScenarioPartition.TRAIN or
                    child.manifest.root_lineage_id != parent.manifest.root_lineage_id or
                    child.manifest.source_state_sha256 != parent.manifest.state_sha256 or
                    child.manifest.initial_observation_sha256 !=
                    parent.manifest.initial_observation_sha256 or
                    receipt["parent_manifest_sha256"] != parent.manifest_sha256 or
                    receipt["parent_state_sha256"] != parent.manifest.state_sha256 or
                    receipt["seed"] != seed or receipt["after"] != [seed >> 8, seed & 255] or
                    receipt["frames_advanced"] != 0 or receipt["actor_memory_writes"] != 0 or
                    receipt["teacher_memory_write_count"] != 2):
                raise ValueError("RNG child provenance differs")
            children.add(child.manifest.state_sha256)
            for slot in summary["slots"]:
                branch = folder / f"branch-{seed}-{slot}"
                ep = loop.load(branch / "episode.json")
                identity = loop.load(branch / "events/event-00001.json")["payload"]["identity"]
                if any(identity.get(k) != v for k, v in {
                    "capture_id": child.manifest.capture_id, "partition": "train",
                    "root": recipe["root"], "model_sha256": lab.canonical_sha256(frozen.to_dict()),
                    "first_slot": slot, "offset": 0, "horizon": 40, "actor_memory_writes": 0,
                    "allow_status_moves": True}.items()) or identity.get("learner_continuation"):
                    raise ValueError("branch identity/continuation differs")
                for index, step in enumerate(ep["decisions"]):
                    obs = step["observation"]
                    batch = projector.project(obs)
                    if step["kind"] != "attack":
                        raise ValueError("unaudited non-attack")
                    if index == 0:
                        view = loop.project_balanced_status_moves(obs, batch)
                        vectors = [list(view.candidate_vectors[view.candidate_slots.index(s)])
                                   for s in summary["slots"]]
                        if vectors != summary["vectors"] or step["move_slot"] != slot:
                            raise ValueError("prescribed action or visible inputs differ")
                        continue
                    view = project_for_head(obs, batch, frozen.move)
                    legal = [s for s in view.candidate_slots if s in step["legal_move_slots"] and
                             not view.candidate_vectors[view.candidate_slots.index(s)][
                                 view.feature_names.index("move.category.status")]]
                    vectors = [view.candidate_vectors[view.candidate_slots.index(s)] for s in legal]
                    if step["move_slot"] != legal[frozen.move.predict_index(vectors)]:
                        raise ValueError("K continuation choice differs")
                    count += 1
                values[str(slot)].append(experiment.win_conditioned_return(ep))
                signatures[str(slot)].add(lab.canonical_sha256([
                    (d["move_slot"], d["state_after"]["party_hp"], d["opponent_hp_after"])
                    for d in ep["decisions"]]))
        gaps = [b-a for a, b in zip(*(values[str(s)] for s in summary["slots"]), strict=True)]
        if (len(children) != 32 or values != summary["rng_returns"] or
                fmean(gaps) != summary["mean_gap_slot1_minus_slot0"] or
                stdev(gaps)/32**.5 != summary["gap_standard_error_descriptive"] or
                {k: len(v) for k, v in signatures.items()} != summary["distinct_trajectories"] or
                fmean(gaps[:16]) != summary["first_half_gap"] or
                fmean(gaps[16:]) != summary["second_half_gap"]):
            raise ValueError("recomputed diversity or return statistics differ")
    native = audit(directory)
    if native != result["native"] or native["episodes"] != plan["max_episodes"]:
        raise ValueError("native inventory differs")
    return {"plan": lab.common._binding(directory / "plan.json"),
        "result": lab.common._binding(directory / "result.json"), "native": native,
        "K_choices_recomputed": count, "fits": 0, "actor_promotions": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    report = inspect(args.directory)
    lab.write(args.directory / "independent-audit.json", report)
    print(report)
