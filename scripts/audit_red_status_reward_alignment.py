"""Read-only diagnosis of measured status rewards versus readiness concerns.

Does not change rewards, gate rules, model weights or recorded outcomes.
"""

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import fmean

from audit_red_status_retention_fit import concern_coverage
from run_red_status_readout_learning import load_inputs, loop

from pokemon_red_completion.red_balanced_status_features import BALANCED_STATUS_NAMES
from pokemon_red_completion.red_status_closed_loop_returns import (
    closed_loop_return,
    unchanged_status_turns,
)

CONCERNS = ("major_status_occupied", "poison_type_immune", "electric_paralysis_type_immune",
            "already_confused", "accuracy_floor", "heal_full_hp")


def return_components(episode):
    steps = episode["decisions"]
    before, after = steps[0]["state_before"], steps[-1]["state_after"]
    cap = steps[0]["observation"]["features"]["battle"]["opponent_max_hp"]
    result = {
        "terminal": 10. if episode["stop_reason"] == "battle_won" else -10.,
        "remaining_hp": .5 * sum(after["party_hp"]) / sum(before["party_max_hp"]),
        "damage": .5 * (steps[0]["opponent_hp_before"] - steps[-1]["opponent_hp_after"]) / cap,
        "turn_cost": -.1 * len(steps),
        "pp_cost": -.01 * episode["metrics"]["party_pp_spent"],
        "unchanged_status_cost": -.5 * len(unchanged_status_turns(episode)),
    }
    if abs(sum(result.values()) - closed_loop_return(episode)) > 1e-10:
        raise ValueError("return decomposition differs")
    return result


def inspect(root, experiment):
    _, inputs, groups, _, _ = load_inputs(root)
    paths = {loop.load(Path(b["path"]))["capture_id"]: Path(b["path"])
             for bindings in inputs["groups"] for b in bindings}
    all_targets = [t for g in groups for t in g]
    coverage = concern_coverage(experiment / "train-screen", all_targets)
    matched_ids = {r["target_capture_id"] for r in coverage["matched_target_gaps"]}
    groups_report, matching = [], []
    for group in groups:
        flagged, favored, losses, kinds = 0, 0, 0, Counter()
        for target in group:
            s = next(i for i, v in enumerate(target["vectors"])
                     if v[BALANCED_STATUS_NAMES.index("choice.status")])
            names = [n for n in CONCERNS if target["vectors"][s][
                BALANCED_STATUS_NAMES.index("choice." + n)]]
            if not names:
                continue
            flagged += 1
            kinds.update(names)
            if target["returns"][s] <= target["returns"][1-s]:
                continue
            favored += 1
            by_slot = {}
            stops = Counter()
            for index, slot in enumerate(target["slots"]):
                values = []
                for offset in loop.OFFSETS:
                    path = (paths[target["capture_id"]].parent /
                            f"branch-{offset}-{slot}/episode.json")
                    episode = loop.load(path)
                    if abs(closed_loop_return(episode) - target["timing_returns"][str(slot)][
                            loop.OFFSETS.index(offset)]) > 1e-10:
                        raise ValueError("branch differs from retained measured target")
                    values.append(return_components(episode))
                    stops.update([episode["stop_reason"]])
                by_slot["status" if index == s else "damage"] = {
                    k: fmean(v[k] for v in values) for k in values[0]}
            all_lost = stops == {"party_defeated": 6}
            losses += all_lost
            if target["capture_id"] in matched_ids:
                matching.append({"capture_id": target["capture_id"], "concerns": names,
                    "status_minus_damage_return": target["returns"][s] - target["returns"][1-s],
                    "all_six_branches_lost": all_lost, "stops": dict(stops),
                    "mean_components": by_slot})
        groups_report.append({"contexts": len(group), "concern_contexts": flagged,
            "concerns_by_kind": dict(kinds), "reward_favors_concerning_status": favored,
            "reward_favors_concerning_status_all_branches_lost": losses})
    return {"schema": "pokemon.red.status-reward-alignment-audit.v1", "groups": groups_report,
        "screen_coverage": coverage, "matched_reward_decomposition": matching,
        "reward_changes": 0, "new_fits": 0, "new_gameplay": 0,
        "interpretation": "Flags are readiness diagnostics, not proof of causal inefficacy. "
        "Existing return can favor flagged choices, including shorter all-loss continuations. "
        "This diagnoses objective mismatch, not an authorized reward change or gate exemption."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.root, args.experiment), indent=2, sort_keys=True))
