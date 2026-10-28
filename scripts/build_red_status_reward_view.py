"""Authenticate and rescore existing TRAIN branches; never play or rewrite a source."""

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from statistics import fmean

from audit_red_status_learning import sha

from pokemon_red_completion import red_status_win_conditioned_returns as reward
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_balanced_status_features import BALANCED_STATUS_NAMES
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog

SCHEMA = "pokemon.red.status.reward-view.v2"


def rescore_branch(directory, target, slot, offset):
    import run_red_closed_loop_status as loop
    ep = loop.load(directory / "episode.json")
    log = loop.lab.verify_trainer_practice_event_log(directory / "events")
    identity = loop.load(directory / "events/event-00001.json")["payload"]["identity"]
    expected = {"capture_id": target["capture_id"], "root": target["root"],
                "partition": "train", "first_slot": slot, "offset": offset,
                "model_sha256": target["continuation_sha256"], "learner_continuation": True}
    if any(identity.get(k) != v for k, v in expected.items()):
        raise ValueError("TRAIN branch identity differs")
    terminal = loop.load(sorted((directory / "events").glob("event-*.json"))[-1])
    final = loop.load(directory / "final-state.json")
    if (log["terminal_event"] != "run_finished"
            or terminal["payload"]["outcome"]["episode_sha256"] != loop.canonical_sha256(ep)
            or final["state_sha256"] != sha(directory / "final.state")
            or not final["episode_returned"] or final["pressed_buttons"]
            or ep["metrics"]["invalid_action_failures"]):
        raise ValueError("TRAIN branch terminal authentication differs")
    observation = ep["decisions"][0]["observation"]
    if ep["decisions"][0]["move_slot"] != slot:
        raise ValueError("measured first action differs")
    projected = loop.project_balanced_status_moves(
        observation, BattleFeatureProjector(PokemonRedBattleCatalog()).project(observation))
    if target["vectors"] != [list(projected.candidate_vectors[
            projected.candidate_slots.index(s)]) for s in target["slots"]]:
        raise ValueError("measured first observation differs")
    value = loop.closed_loop_return(ep)
    if abs(value - target["timing_returns"][str(slot)][loop.OFFSETS.index(offset)]) > 1e-10:
        raise ValueError("original v1 reward reproduction differs")
    return reward.win_conditioned_return(ep), {
        "episode": loop.lab.common._binding(directory / "episode.json"),
        "terminal_event": loop.lab.common._binding(
            sorted((directory / "events").glob("event-*.json"))[-1]),
        "state_sha256": final["state_sha256"], "v1": value,
        "stop": ep["stop_reason"], "decisions": ep["decision_count"]}


def build(root):
    import run_red_status_readout_learning as runner
    loop = runner.loop
    _, inputs, originals, _, _ = runner.load_inputs(root)
    paths = {loop.load(Path(b["path"]))["capture_id"]: Path(b["path"])
             for group in inputs["groups"] for b in group}
    groups, branches, changes = [], [], []
    for original in originals:
        group = []
        for target in original:
            timing = {}
            stops = Counter()
            for slot in target["slots"]:
                timing[str(slot)] = []
                for offset in loop.OFFSETS:
                    directory = paths[target["capture_id"]].parent / f"branch-{offset}-{slot}"
                    value, binding = rescore_branch(directory, target, slot, offset)
                    branches.append(binding)
                    stops.update([binding["stop"]])
                    timing[str(slot)].append(value)
            revised = {**target, "return_schema": reward.RETURN_SCHEMA,
                       "timing_returns": timing,
                       "returns": [fmean(timing[str(s)]) for s in target["slots"]]}
            s = next(i for i, v in enumerate(target["vectors"])
                     if v[BALANCED_STATUS_NAMES.index("choice.status")])
            concerns = [n for n in ("major_status_occupied", "poison_type_immune",
                "electric_paralysis_type_immune", "already_confused", "accuracy_floor",
                "heal_full_hp") if target["vectors"][s][BALANCED_STATUS_NAMES.index("choice."+n)]]
            changes.append({"capture_id": target["capture_id"], "concerns": concerns,
                "v1_status_gap": target["returns"][s] - target["returns"][1-s],
                "v2_status_gap": revised["returns"][s] - revised["returns"][1-s],
                "all_branches_lost": stops == {"party_defeated": 6}})
            group.append(revised)
        groups.append(group)
    return {"schema": SCHEMA, "return_schema": reward.RETURN_SCHEMA,
        "inputs_sha256": loop.canonical_sha256(inputs), "groups": groups,
        "reward_source_sha256": sha(Path(reward.__file__)), "branches": branches,
        "diagnostics": {"contexts": sum(map(len, groups)), "authenticated_branches": len(branches),
            "changed_preferences": sum((r["v1_status_gap"] > 0) != (r["v2_status_gap"] > 0)
                                       for r in changes),
            "v1_flagged_status_preferred": sum(bool(r["concerns"]) and r["v1_status_gap"] > 0
                                              for r in changes),
            "v2_flagged_status_preferred": sum(bool(r["concerns"]) and r["v2_status_gap"] > 0
                                              for r in changes),
            "prior_flagged_preferences": [r for r in changes if r["concerns"] and
                                          r["v1_status_gap"] > 0]},
        "new_collection": 0, "source_outcomes_changed": 0}


def validate_view(path, root):
    import run_red_closed_loop_status as loop
    view = loop.load(path)
    if view != build(root):
        raise ValueError("reward view differs from authenticated measured branches")
    return view


if __name__ == "__main__":
    import run_red_closed_loop_status as loop
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=loop.lab.ROOT).strip():
        raise ValueError("reward view requires new output and committed source")
    view = build(args.root)
    loop.lab.write(args.output, view)
    print(json.dumps(view["diagnostics"], indent=2), flush=True)
