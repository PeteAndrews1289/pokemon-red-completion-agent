"""Frozen H/J comparison on the two prospectively declared natural team sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import run_fresh_red_trainer_curriculum as common
import run_red_trainer_practice_model as player
from capture_fresh_red_brock_development import TEAM_BOOT_FRAMES, check_independence
from run_red_trainer_natural_comparison import qualified_fit_receipt

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture

ROOT = Path(__file__).resolve().parents[1]
MODEL_SHA = {
    "H": "ca8728daf4182fc712a4d6713a85a241398e0be376b54c2d6fd986fda084574b",
    "J": "260b227a2fb3ba46a80be9c42e1f7e17977068e890f135407f8faafe2336fb09",
}
TIMINGS = (0, 4, 8)


def summarize(rows):
    expected = {
        (boot, timing, arm) for boot in TEAM_BOOT_FRAMES for timing in TIMINGS for arm in MODEL_SHA
    }
    keys = {(r["boot"], r["timing"], r["arm"]) for r in rows}
    if keys != expected or len(rows) != len(expected):
        raise ValueError("natural team comparison needs every unique declared cell")
    totals = {}
    for arm in MODEL_SHA:
        selected = [r for r in rows if r["arm"] == arm]
        totals[arm] = {
            "wins": sum(r.get("battle_won", False) for r in selected),
            "failures": sum(
                r.get("stop_reason") not in {"battle_won", "party_defeated"} for r in selected
            ),
            "decisions": sum(r.get("decision_count", 0) for r in selected),
            "faints": sum(r.get("metrics", {}).get("party_faints", 0) for r in selected),
            "hp_lost": sum(r.get("metrics", {}).get("party_hp_lost", 0) for r in selected),
            "actions": {
                kind: sum(r.get("action_counts", {}).get(kind, 0) for r in selected)
                for kind in ("attack", "voluntary_switch", "forced_switch", "switch_prompt")
            },
        }
    terminal = all(
        r.get("stop_reason") in {"battle_won", "party_defeated"}
        and r.get("teacher_queries")
        == r.get("memory_write_actions")
        == r.get("metrics", {}).get("invalid_action_failures")
        == 0
        and r.get("final_state_verified") is True
        for r in rows
    )
    # Prompt declines alone do not establish reserve use.
    reserve_roots = sorted(
        {r["boot"] for r in rows if r["arm"] == "J" and r.get("reserve_used") is True}
    )
    checks = {
        "all_terminal_unassisted_with_endpoints": terminal,
        "wins_no_regression": totals["J"]["wins"] >= totals["H"]["wins"],
        "actual_reserve_use_each_origin": reserve_roots == list(TEAM_BOOT_FRAMES),
    }
    return {
        "totals": totals,
        "checks": checks,
        "natural_team_gate_passed": all(checks.values()),
        "reserve_use_origins": reserve_roots,
        "independent_natural_origins": 2,
        "perfect_wins_required": False,
        "six_member_qualification": False,
        "multiple_forced_target_choice_qualified": False,
        "final_player_ready": False,
        "model_updates": 0,
        "authority_promotions": 0,
    }


def run(args):
    if (
        args.output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("natural team test needs new output and committed source")
    for arm, path in (("H", args.frozen), ("J", args.candidate)):
        if common._binding(path)["sha256"] != MODEL_SHA[arm]:
            raise ValueError("frozen natural team model differs")
    source_plan = json.loads((args.sources / "plan.json").read_bytes())
    source_result = json.loads((args.sources / "result.json").read_bytes())
    sources = source_result["sources"]
    if (
        source_plan["boot_frames"] != list(TEAM_BOOT_FRAMES)
        or source_result["status"] != "captured"
        or [r["boot_frames"] for r in sources] != list(TEAM_BOOT_FRAMES)
    ):
        raise ValueError("natural team source batch differs")
    check_independence(sources)
    for source in sources:
        directory = args.sources / source["root_lineage_id"]
        capture = open_battle_scenario_capture(
            directory / "source.state", directory / "source.state.json"
        )
        if (
            common._binding(directory / "origin.state")["sha256"] != source["origin_state_sha256"]
            or capture.manifest.source_state_sha256 != source["origin_state_sha256"]
            or capture.manifest_sha256 != source["capture_manifest_sha256"]
            or capture.manifest.state_sha256 != source["battle_state_sha256"]
            or source["party_count"] != 2
            or len(source["party_hp"]) != 2
            or min(source["party_hp"]) <= 0
            or source["memory_writes"] != 0
            or source["model_queries"] != 0
        ):
            raise ValueError("natural team source authentication differs")
    eligibility = qualified_fit_receipt(args.candidate.parent)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    common._write(args.output / "eligibility.json", eligibility)
    plans = []
    for source in sources:
        directory = args.sources / source["root_lineage_id"]
        for timing in TIMINGS:
            for arm, model in (("H", args.frozen), ("J", args.candidate)):
                key = f"boot{source['boot_frames']}-timing{timing}-{arm}"
                plan = {
                    "schema": player.OUTCOME_SCHEMA,
                    "source_commit": commit,
                    "rom": common._binding(args.rom),
                    "outcome_model": common._binding(model),
                    "capture_state": common._binding(directory / "source.state"),
                    "capture_manifest": common._binding(directory / "source.state.json"),
                    "max_decisions": 80,
                    "maximum_frames": 120000,
                    "opening_idle_frames": timing,
                    "output": str(args.output / key),
                }
                path = args.output / (key + "-plan.json")
                common._write(path, plan)
                plans.append((source["boot_frames"], timing, arm, path))
    common._write(
        args.output / "plan.json",
        {
            "source_commit": commit,
            "sources": common._binding(args.sources / "result.json"),
            "cells": [common._binding(p) for _, _, _, p in plans],
            "model_updates": 0,
            "max_cells": 12,
            "no_retry": True,
        },
    )
    for _, _, _, path in plans:
        player.run(path, check_only=True)
    rows = []
    for boot, timing, arm, path in plans:
        plan = json.loads(path.read_bytes())
        directory = Path(plan["output"])
        try:
            player.run(path)
            row = json.loads((directory / "outcome.json").read_bytes())
            row["final_state_verified"] = (
                hashlib.sha256((directory / "final.state").read_bytes()).hexdigest()
                == row["final_state_sha256"]
            )
            row["reserve_used"] = any(
                d["kind"] in {"voluntary_switch", "forced_switch"}
                or (d["kind"] == "switch_prompt" and d.get("party_slot") is not None)
                for d in row["decisions"]
            )
        except Exception as error:
            row = {
                "stop_reason": "execution_failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
            common._write(args.output / f"boot{boot}-timing{timing}-{arm}-failure.json", row)
        row.update({"boot": boot, "timing": timing, "arm": arm})
        rows.append(row)
        common._write(args.output / f"completed-cell-{len(rows):02d}.json", row)
        print(
            json.dumps(
                {
                    k: row.get(k)
                    for k in (
                        "boot",
                        "timing",
                        "arm",
                        "battle_won",
                        "stop_reason",
                        "decision_count",
                        "reserve_used",
                    )
                }
            ),
            flush=True,
        )
    result = {**summarize(rows), "evaluations": rows}
    common._write(args.output / "result.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "evaluations"}), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "sources", "candidate", "frozen", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
