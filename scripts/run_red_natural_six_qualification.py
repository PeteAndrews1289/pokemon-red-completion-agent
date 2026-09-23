"""Frozen eight-cell J/K natural six-member comparison; no fitting or retries."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

import run_red_trainer_practice_model as player
from continue_red_natural_party import ROM_SHA, bound
from run_red_six_party_assisted_pilot import binding, write_new
from run_red_trainer_earned_switch import completion_ledger
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2, build_battle_scenario_capture_payload,
)
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.observation import BattleMenuPhase, PokemonRedStateReader
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "J": "260b227a2fb3ba46a80be9c42e1f7e17977068e890f135407f8faafe2336fb09",
    "K": "e626e3435d1aa75654593535acf0e5e52a7eb7430481217a80aff3a53c191472",
}
SOURCES = {
    3700: ("d7fcab9c0c7d48c39320fe212fef7a40fe5cdb66b7040757a987918b58d713a0",
           "69c0a4cef85e2599da1285c65492dd22db402c8c3df9f70095f44563941eee20", 31214),
    3900: ("c857790c3080ffe60f608130d490af9228e986433c196990993609a39193d6b3",
           "cfab4b26abe00934a61be22e3ec2802a373c4a8b801728a6f3db637cedbc5ecd", 45646),
}


def actual_slots(row):
    slots = {d[when]["active_party_slot"] for d in row.get("decisions", [])
        for when in ("state_before", "state_after") if when in d}
    # A battle-ending observation has no active battler. Do not invent a slot
    # for it, or confuse a postprocessing failure with a failed model episode.
    slots.discard(None)
    if any(type(slot) is not int or not 1 <= slot <= 6 for slot in slots):
        raise ValueError("observed active slot is invalid")
    return sorted(slots)


def summarize(rows):
    expected = {(boot, timing, arm) for boot in SOURCES for timing in (0, 4) for arm in MODELS}
    if len(rows) != 8 or {(r["boot"], r["timing"], r["arm"]) for r in rows} != expected:
        raise ValueError("qualification requires all eight unique frozen cells")
    checks = {
        "all_valid_retained_terminals": all(
            r.get("stop_reason") in {"battle_won", "party_defeated"}
            and r.get("final_state_verified") is True and r.get("log_verified") is True
            and r.get("teacher_queries") == r.get("memory_write_actions")
            == r.get("metrics", {}).get("invalid_action_failures") == 0 for r in rows),
        "K_win_each_origin": all(any(r["boot"] == boot and r["arm"] == "K"
            and r.get("battle_won") is True for r in rows) for boot in SOURCES),
        "K_late_slot_use_each_origin": all(any(r["boot"] == boot and r["arm"] == "K"
            and set(r.get("actual_slots", ())) & {4, 5, 6} for r in rows) for boot in SOURCES),
    }
    totals = {}
    for arm in MODELS:
        selected = [r for r in rows if r["arm"] == arm]
        totals[arm] = {
            "wins": sum(r.get("battle_won") is True for r in selected),
            "decisions": sum(r.get("decision_count", 0) for r in selected),
            "faints": sum(r.get("metrics", {}).get("party_faints", 0) for r in selected),
            "hp_lost": sum(r.get("metrics", {}).get("party_hp_lost", 0) for r in selected),
            "pp_spent": sum(r.get("metrics", {}).get("party_pp_spent", 0) for r in selected),
            "cash_delta": sum(r.get("cash_delta", 0) for r in selected),
            "mean_attack_utility": sum(r.get("metrics", {}).get("attack_turn_utility_sum", 0)
                                       for r in selected) / len(selected),
            "actions": {kind: sum(r.get("action_counts", {}).get(kind, 0) for r in selected)
                for kind in ("attack", "voluntary_switch", "forced_switch", "switch_prompt")},
        }
    checks["K_wins_no_regression"] = totals["K"]["wins"] >= totals["J"]["wins"]
    return {"qualified": all(checks.values()), "checks": checks, "totals": totals,
        "independent_origins": 2, "perfect_wins_required": False,
        "scope": "measured natural six-member early-game trainer workload only",
        "same_opponent_roster_both_origins": True, "3700_prior_three_member_diagnostic": True,
        "model_updates": 0, "authority_promotions": 0, "funding_qualified": False,
        "league_qualified": False, "fresh_red_complete": False}


def run(args):
    if args.output.exists() or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("qualification needs new output and committed source")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    rom = bound(args.rom, ROM_SHA)
    for arm, path in (("J", args.frozen), ("K", args.candidate)):
        bound(path, MODELS[arm])
    stats = RedPracticeCartridge(rom).public_base_stats
    sources = []
    for boot in SOURCES:
        directory, origin = getattr(args, f"source{boot}"), getattr(args, f"origin{boot}")
        state_sha, origin_sha, ot = SOURCES[boot]
        state = bound(directory / "final.state", state_sha)
        bound(origin, origin_sha)
        parent = json.loads((directory / "result.json").read_bytes())
        root_id = f"fresh-red-six-development-boot{boot}"
        if (parent.get("error") is not None or parent["final_state_sha256"] != state_sha
                or parent["root_lineage_id"] != root_id or parent["model_queries"] != 0
                or parent["memory_writes"] != 0 or parent["held_buttons"]):
            raise ValueError("preparation source receipt differs")
        with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
            emulator.load_state_bytes(state)
            reader = PokemonRedStateReader(emulator)
            raw = reader.read()
            if (raw.battle_state != 2 or raw.party_count != 6 or min(raw.party_hp) <= 0
                    or any(raw.party_status) or reader.read_party_original_trainer_ids()[0] != ot
                    or reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN):
                raise ValueError("natural six-member MAIN source differs")
            prepared = prepare_red_battle_scenario(PokemonRedObservationEncoder.from_state_reader(
                reader, include_battle_stats=True, public_species_base_stats=stats), raw, allow_no_attack=True)
            manifest = build_battle_scenario_capture_payload(capture_id=f"natural-six-boot{boot}-20260920",
                root_lineage_id=root_id, partition=ScenarioPartition.DEVELOPMENT, state_bytes=state,
                source_state_sha256=origin_sha, initial_observation_sha256=prepared.initial_observation_sha256,
                source_commit=parent["source_commit"], expected_map=raw.map_id, expected_battle_state=2,
                observation_schema=OBSERVATION_SCHEMA_V2)
            sources.append({"boot": boot, "state": state, "manifest": manifest,
                "source": binding(directory / "result.json"), "origin": binding(origin),
                "ot": ot, "before": completion_ledger(reader), "bag": raw.bag_items,
                "preparation_cost": parent["preparation_cumulative"]})
            assert emulator.frame_count == 0
    write_new(args.claim, {"source_commit": revision, "models": MODELS,
        "sources": [s["source"] for s in sources], "max_cells": 8, "no_retries": True})
    args.output.mkdir(mode=0o700)
    plans = []
    for i, source in enumerate(sources):
        boot = source["boot"]
        for suffix, data in (("state", source["state"]), ("state.json", source["manifest"])):
            with (args.output / f"boot{boot}.{suffix}").open("xb") as stream:
                stream.write(data)
        for timing in (0, 4):
            arms = ("J", "K") if (i + timing // 4) % 2 == 0 else ("K", "J")
            for arm in arms:
                key = f"boot{boot}-timing{timing}-{arm}"
                plan = {"schema": player.OUTCOME_SCHEMA, "source_commit": revision,
                    "rom": binding(args.rom), "outcome_model": binding(args.frozen if arm == "J" else args.candidate),
                    "capture_state": binding(args.output / f"boot{boot}.state"),
                    "capture_manifest": binding(args.output / f"boot{boot}.state.json"),
                    "max_decisions": 80, "maximum_frames": 120000,
                    "maximum_controller_actions": 5000, "maximum_wall_seconds": 45,
                    "opening_idle_frames": timing, "output": str(args.output / key)}
                path = args.output / f"{key}-plan.json"
                write_new(path, plan)
                plans.append((boot, timing, arm, path, source["before"]["cash"]))
    write_new(args.output / "plan.json", {"source_commit": revision,
        "cells": [binding(p) for _, _, _, p, _ in plans], "maximum_seconds": 900,
        "sources": [{k: v for k, v in s.items() if k not in {"state", "manifest"}} for s in sources],
        "gate": "all valid retained terminals; K wins >= J; K win and actual late-slot use on each origin",
        "same_roster_scope_limit": "Both naturally nearest trainers have one level14 Clefairy."})
    execute_plans(plans, args.output, args.rom)


def execute_plans(plans, output, rom_path):
    """Run a frozen schedule once; preflight every cell before any query."""
    expected = {(boot, timing, arm) for boot in SOURCES for timing in (0, 4) for arm in MODELS}
    if len(plans) != 8 or {(b, t, a) for b, t, a, _, _ in plans} != expected:
        raise ValueError("execution schedule differs from the eight frozen cells")
    for _, _, _, path, _ in plans:
        player.run(path, check_only=True)
    rows, started = [], time.monotonic()
    for boot, timing, arm, path, cash in plans:
        if time.monotonic() - started >= 850:
            raise ValueError("qualification campaign time budget exhausted before next cell")
        directory = Path(json.loads(path.read_bytes())["output"])
        try:
            player.run(path)
            row = json.loads((directory / "outcome.json").read_bytes())
            row["final_state_verified"] = binding(directory / "final.state")["sha256"] == row["final_state_sha256"]
            verified = verify_trainer_practice_event_log(directory / "events")
            row["log_verified"] = (verified["terminal_event"] == "run_finished"
                and verified["incomplete_decisions"] == 0)
            row["actual_slots"] = actual_slots(row)
            with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
                emulator.load_state_bytes((directory / "final.state").read_bytes())
                row["final_ledger"] = completion_ledger(PokemonRedStateReader(emulator))
                row["cash_delta"] = row["final_ledger"]["cash"] - cash
                assert emulator.frame_count == 0
        except Exception as exc:
            row = {"stop_reason": "execution_failed", "error_type": type(exc).__name__, "error": str(exc)}
        row.update(boot=boot, timing=timing, arm=arm)
        write_new(output / f"completed-cell-{len(rows) + 1:02}.json", row)
        rows.append(row)
        print(json.dumps({k: row.get(k) for k in ("boot", "timing", "arm", "stop_reason", "decision_count", "actual_slots", "cash_delta", "error")}), flush=True)
    result = {**summarize(rows), "cells": [binding(output / f"completed-cell-{i:02}.json") for i in range(1, 9)],
              "wall_seconds": time.monotonic() - started}
    write_new(output / "result.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "frozen", "candidate", "source3700", "source3900", "origin3700", "origin3900", "claim", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
