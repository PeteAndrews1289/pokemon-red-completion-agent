"""Fixed paired TRAIN gameplay diagnostic; never a natural qualification or refit."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import run_red_trainer_practice_model as player
from run_red_six_party_assisted_pilot import binding, revision, write_new
from run_red_trainer_switching_comparison import MODEL_SHA256, bound, read, require_terminal

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log
from pokemon_red_completion.red_trainer_practice_returns import score_trainer_practice_episode
from pokemon_red_completion.scenario_lab import ScenarioPartition

CANDIDATE_SHA = "e626e3435d1aa75654593535acf0e5e52a7eb7430481217a80aff3a53c191472"
FIT_SHA = "7e276a34f2658bc5fb5725e0b7b4010b5edbd26179fa7cf11cb7fa5dfe0176e0"


def summarize(rows):
    keys = {(r["case"], r["arm"]) for r in rows}
    if len(rows) != 16 or keys != {(i, arm) for i in range(8) for arm in ("J", "K")}:
        raise ValueError("all16unique declared TRAIN cells required")
    totals = {}
    for arm in ("J", "K"):
        selected = [r["episode"] for r in rows if r["arm"] == arm]
        for row in selected:
            require_terminal(row)
            if row["teacher_queries"] or row["memory_write_actions"]:
                raise ValueError("model-only diagnostic required")
        totals[arm] = {
            "wins": sum(e["battle_won"] for e in selected),
            "losses": sum(e["stop_reason"] == "party_defeated" for e in selected),
            "decisions": sum(e["decision_count"] for e in selected),
            "faints": sum(e["metrics"]["party_faints"] for e in selected),
            "hp_lost": sum(e["metrics"]["party_hp_lost"] for e in selected),
            "pp_spent": sum(e["metrics"]["party_pp_spent"] for e in selected),
            "voluntary_switches": sum(e["action_counts"]["voluntary_switch"] for e in selected),
            "forced_switches": sum(e["action_counts"]["forced_switch"] for e in selected),
            "frames": sum(e["frames_executed"] for e in selected),
            "mean_return": sum(score_trainer_practice_episode(e).value for e in selected) / 8,
        }
    j, k = totals["J"], totals["K"]
    checks = {"wins_nonregression": k["wins"] >= j["wins"],
              "whole_party_return_nonregression": k["mean_return"] >= j["mean_return"],
              "useful_win_or_cost_gain": (k["wins"] > j["wins"] or k["faints"] < j["faints"]
                                          or k["hp_lost"] < j["hp_lost"])}
    return {"totals": totals, "checks": checks, "train_rollout_passed": all(checks.values()),
            "natural_qualified": False, "authority_promotions": 0, "fits": 0,
            "independent_evaluation_origins": 0, "existing_train_origin_clusters": 4}


def run(args):
    commit = revision()
    if args.output.exists():
        raise ValueError("diagnostic output already exists")
    models = {"J": args.baseline, "K": args.candidate}
    if (binding(args.baseline)["sha256"] != MODEL_SHA256
            or binding(args.candidate)["sha256"] != CANDIDATE_SHA
            or binding(args.candidate.parent / "result.json")["sha256"] != FIT_SHA
            or binding(args.rom)["sha256"] != player.ROM_SHA256):
        raise ValueError("fixed baseline, accepted TRAIN fit and ROM required")
    model = TrainerPracticeThreeHeadModel.from_dict(read(binding(args.candidate)))
    states = sorted(args.source.glob("reserved/*/materialized/assisted.state"))
    captures = [open_battle_scenario_capture(p, p.with_suffix(".state.json")) for p in states]
    if (len(captures) != 8 or len({c.manifest.capture_id for c in captures}) != 8
            or {c.manifest.root_lineage_id for c in captures} != set(model.train_root_ids)
            or any(c.manifest.partition is not ScenarioPartition.TRAIN
                   or c.manifest.capture_id in model.train_capture_ids for c in captures)):
        raise ValueError("requires all8non-fitted TRAIN variations on original4roots")
    args.output.mkdir(mode=0o700)
    cells = []
    for i, state in enumerate(states):
        for arm in (("J", "K") if i % 2 == 0 else ("K", "J")):
            path = args.output / f"case-{i:02d}-{arm}-plan.json"
            write_new(path, {"schema": player.OUTCOME_SCHEMA, "source_commit": commit,
                "rom": binding(args.rom), "outcome_model": binding(models[arm]),
                "capture_state": binding(state), "capture_manifest": binding(state.with_suffix(
                    ".state.json")), "max_decisions": 160, "maximum_frames": 240000,
                "maximum_controller_actions": 5000, "maximum_wall_seconds": 45,
                "opening_idle_frames": 0, "output": str(args.output / f"case-{i:02d}-{arm}")})
            player.run(path, check_only=True)
            cells.append({"case": i, "arm": arm, "plan": binding(path)})
    declaration = {"source_commit": commit, "cells": cells,
        "classification": "paired TRAIN diagnostic, not natural or independent evaluation",
        "candidate_fit": binding(args.candidate.parent / "result.json"),
        "maximum_cells": 16, "maximum_wall_seconds": 900, "fits": 0,
        "no_retry": True, "global_stop_on_invalid_or_nonterminal": True,
        "gates": ["all terminals valid", "wins nonregression", "mean return nonregression",
                  "strict gain in wins or faints or HP cost"], "authority_promotions": 0}
    write_new(args.source / "canonical-rollout-20260920-claim.json", declaration)
    write_new(args.output / "plan.json", declaration)
    rows, started = [], time.monotonic()
    for cell in cells:
        try:
            if time.monotonic() - started >= 900:
                raise TimeoutError("paired TRAIN diagnostic wall budget")
            path = bound(cell["plan"])
            player.run(path)
            directory = Path(read(cell["plan"])["output"])
            episode = json.loads((directory / "outcome.json").read_bytes())
            require_terminal(episode)
            if binding(directory / "final.state")["sha256"] != episode["final_state_sha256"]:
                raise ValueError("diagnostic endpoint differs")
            verified = verify_trainer_practice_event_log(directory / "events")
            if verified["incomplete_decisions"] or verified["terminal_event"] != "run_finished":
                raise ValueError("diagnostic event chain incomplete")
            rows.append({**cell, "episode": episode})
            write_new(args.output / f"completed-{len(rows):02d}.json", rows[-1])
            print(json.dumps({"cells": len(rows), "arm": cell["arm"],
                              "stop": episode["stop_reason"]}), flush=True)
        except Exception as error:
            write_new(args.output / "failure.json", {"completed": len(rows),
                "case": cell["case"], "arm": cell["arm"], "error_type": type(error).__name__,
                "error": str(error), "fits": 0, "global_stop": True})
            raise
    result = {**summarize(rows), "cells": [{k: v for k, v in row.items() if k != "episode"}
                                         for row in rows],
              "elapsed_seconds": time.monotonic() - started}
    write_new(args.output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "source", "baseline", "candidate", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    print(json.dumps(run(parser.parse_args())), flush=True)
