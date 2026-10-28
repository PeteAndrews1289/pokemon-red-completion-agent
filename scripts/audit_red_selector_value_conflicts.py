"""Read-only decomposition of retained TRAIN value conflicts; never fit or play."""

import argparse
import json
from math import isclose, isfinite
from pathlib import Path
from statistics import fmean

from pokemon_red_completion.red_status_closed_loop_returns import unchanged_status_turns
from pokemon_red_completion.red_status_win_conditioned_returns import win_conditioned_return


def reward_components(episode):
    """Reproduce v2 without modifying its pinned source or historical reward view."""
    total = win_conditioned_return(episode)
    steps = episode["decisions"]
    before, after = steps[0]["state_before"], steps[-1]["state_after"]
    won = episode["stop_reason"] == "battle_won"
    parts = {
        "terminal": 10. if won else -10.,
        "retained_hp": .5 * sum(after["party_hp"]) / sum(before["party_max_hp"]),
        "damage": .5 * (steps[0]["opponent_hp_before"] - steps[-1]["opponent_hp_after"])
        / steps[0]["observation"]["features"]["battle"]["opponent_max_hp"],
        "decision_cost": -.1 * len(steps) / 40 if won else 0.,
        "pp_cost": -.01 * min(episode["metrics"]["party_pp_spent"] / 40, 1.) if won else 0.,
        "unchanged_status_cost": -.5 * len(unchanged_status_turns(episode)) / 40 if won else 0.,
    }
    if not isclose(sum(parts.values()), total, rel_tol=0., abs_tol=1e-10):
        raise ValueError("reward component reconstruction differs")
    return {"terms": parts, "total": total}


def paired_summary(status_values, damage_values):
    if (len(status_values) != len(damage_values) or not status_values or
            any(isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x)
                for x in [*status_values, *damage_values])):
        raise ValueError("finite nonempty paired values required")
    gaps = [s - d for s, d in zip(status_values, damage_values, strict=True)]
    return {"paired_gaps": gaps, "mean_status_gap": fmean(gaps),
            "minimum_gap": min(gaps), "maximum_gap": max(gaps),
            "status_better_samples": sum(g > 0 for g in gaps),
            "damage_better_samples": sum(g < 0 for g in gaps),
            "tied_samples": sum(g == 0 for g in gaps),
            "preference_changes_sign": min(gaps) < 0 < max(gaps),
            "damage_better_by_original_margin_every_sample": all(g < -.05 for g in gaps),
            "statistical_confidence_claim": False, "fit_label_created": False}


def inspect(root, packet):
    from audit_red_timing_selector_preparation import inspect as verify_packet
    from build_red_status_reward_view import rescore_branch
    from run_red_effect_selector_combination import N, previous

    # Authenticate the rejected screen before using its logged flags or vectors.
    verified = verify_packet(root, packet)
    if verified["first_unpassed_gate"] != "native_train_screen":
        raise ValueError("expected retained rejected native screen")
    loop = previous.loop
    _, inputs, groups, _, _ = previous.load_inputs(root)
    targets = [t for g in groups for t in g]
    paths = {loop.load(Path(b["path"]))["capture_id"]: Path(b["path"])
             for group in inputs["groups"] for b in group}
    directory = packet / "combination/train-screen"
    findings, measurements = [], {}
    for row in loop.load(directory / "summary.json"):
        episode = loop.load(directory / row["case"] / "episode.json")
        for choice in row["status_choices"]:
            if not choice["concerns"]:
                continue
            step = next(s for s in episode["decisions"]
                        if s["decision_index"] == choice["decision"])
            vectors = step["model_diagnostics"]["move_candidate_vectors"]
            matches = [t for t in targets if t["vectors"] == vectors]
            findings.append({"case": row["case"], "decision": choice["decision"],
                "concerns": choice["concerns"], "move_executed": step["outcome"]["move_executed"],
                "actor_status": step["observation"]["features"]["party"]["lead"]["status"],
                "matched_targets": [t["capture_id"] for t in matches]})
            for target in matches:
                key = target["capture_id"]
                if key in measurements:
                    continue
                status_index = next(i for i, v in enumerate(target["vectors"])
                                    if v[N.index("choice.status")])
                arms = {}
                for kind, index in (("status", status_index), ("damage", 1-status_index)):
                    slot = target["slots"][index]
                    branches = []
                    for offset in loop.OFFSETS:
                        folder = paths[key].parent / f"branch-{offset}-{slot}"
                        value, binding = rescore_branch(folder, target, slot, offset)
                        ep = loop.load(folder / "episode.json")
                        parts = reward_components(ep)
                        if not isclose(parts["total"], value, rel_tol=0., abs_tol=1e-10):
                            raise ValueError("authenticated branch value differs")
                        branches.append({"offset": offset, "slot": slot,
                            "episode_sha256": binding["episode"]["sha256"],
                            "terminal_event_sha256": binding["terminal_event"]["sha256"],
                            "state_sha256": binding["state_sha256"],
                            "stop": ep["stop_reason"], "decisions": ep["decision_count"],
                            "first_move_executed": ep["decisions"][0]["outcome"]["move_executed"],
                            "reward": parts})
                    arms[kind] = branches
                summary = paired_summary([b["reward"]["total"] for b in arms["status"]],
                                         [b["reward"]["total"] for b in arms["damage"]])
                target_sha = loop.lab.common._binding(paths[key])["sha256"]
                measurements[key] = {"target_sha256": target_sha,
                    "continuation_sha256": target["continuation_sha256"],
                    "arms": arms, "paired": summary}
    return {"schema": "pokemon.red.selector-value-conflict-audit.v1",
        "packet_bindings": verified["bindings"], "findings": findings,
        "matched_targets": measurements, "raw_flags": len(findings),
        "suppressed_flagged_choices": sum(not f["move_executed"] for f in findings),
        "unmatched_flagged_choices": sum(not f["matched_targets"] for f in findings),
        "authenticated_branch_count": sum(len(a) for t in measurements.values()
                                           for a in t["arms"].values()),
        "fits": 0, "new_gameplay": 0, "reward_changes": 0, "gate_changes": 0,
        "actor_promotions": 0, "automatic_adjudication": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "packet", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("audit output already exists")
    report = inspect(args.root, args.packet)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({k: v for k, v in report.items() if k not in {"findings", "matched_targets"}}))
