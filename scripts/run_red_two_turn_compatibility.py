"""One bounded Dig/Fly execution and frozen-actor compatibility packet; no fits."""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from statistics import fmean

import run_red_damage_composition as composition

from pokemon_red_completion.battle_practice_factory import BattlePracticeSpec
from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.red_trainer_practice_episode import validate_opening_idle_frames

old, read, require = composition.old, composition.read, composition.require
ROOT = composition.ROOT
OUTPUT = old.PRIVATE / "red-two-turn-compatibility-20260923-v1"
OFFSETS = (0, 12)
SEED = 23092341
MAX_SECONDS = 1200


def excluded_pairs():
    used = composition.exclusions()
    for team in read(composition.OUTPUT / "PLAN.json")["teams"]:
        used |= {
            tuple(sorted((a, b))) for a in team["own_species"] for b in team["opponent_species"]
        }
    return used


def recipes(cartridge, catalog, sources):
    rng = random.Random(SEED)
    used = excluded_pairs()
    rows = []
    for index in range(12):
        player = index < 8
        move = 91 if index < 4 or index in (8, 9) else 19
        context = ("neutral", "accuracy", "low_hp", "paralysis")[index % 4] if player else "neutral"
        level = (37, 41, 45, 49)[index % 4]
        pool = {
            s: old.legal_damage(cartridge, catalog, s, level)
            for s in cartridge.species_ids
            if s not in old.EXCLUDED_SPECIES
        }
        eligible = sorted(s for s in pool if len(pool[s]) >= 2)
        chargers = [
            s for s in eligible if move in cartridge.species(s).teachable_moves_at_level(level)
        ]
        for _ in range(10000):
            charged = rng.choice(chargers)
            other = rng.choice(eligible)
            own, foe = ([charged], [other]) if player else ([other], [charged])
            if not player:
                own.append(rng.choice(eligible))
                foe.append(rng.choice(eligible))
            pairs = {tuple(sorted((a, b))) for a in own for b in foe}
            if len(set(own + foe)) == len(own + foe) and not pairs & used:
                used |= pairs
                break
        else:
            raise ValueError("fresh own-level two-turn inventory unavailable")
        practice = {"partition": "train", "battle_kind": "trainer"}
        for side, ids, charging in (("actor", own, player), ("opponent", foe, not player)):
            moves = ([move] if charging else []) + rng.sample(pool[ids[0]], 2)
            move_rows = old._move_rows(catalog, moves)
            if charging and context == "low_hp":
                move_rows[0]["pp"] = 1
            practice.update(
                {
                    f"{side}_species_ref": old.pokemon_red_species_ref(ids[0]),
                    f"{side}_national_number": cartridge.species(ids[0]).national_number,
                    f"{side}_level": level,
                    f"{side}_moves": move_rows,
                }
            )
            cap = (
                cartridge.species(ids[0]).neutral_stats(level)
                if side == "actor"
                else cartridge.species(ids[0]).trainer_stats(level)
            ).max_hp
            practice[f"{side}_hp"] = (
                max(1, cap // 4) if side == "actor" and context == "low_hp" else cap
            )
            reserves = []
            for slot, species in enumerate(ids[1:], 2):
                reserves.append(
                    {
                        "party_slot": slot,
                        "species_ref": old.pokemon_red_species_ref(species),
                        "national_number": cartridge.species(species).national_number,
                        "level": level,
                        "moves": old._move_rows(catalog, rng.sample(pool[species], 2)),
                    }
                )
            if reserves:
                practice["party_reserves" if side == "actor" else "opponent_reserves"] = reserves
        practice["opponent_party_count"] = len(foe)
        root = (index // 4 + index % 4) % 4
        rows.append(
            {
                "id": f"two-turn-{index:02d}",
                "role": "probe" if player else "composition",
                "player_charge": player,
                "charge_move": move,
                "context": context,
                "own_species": own,
                "opponent_species": foe,
                "source_index": root,
                "root": sources[root][1]["source_id"],
                "conditions": asdict(
                    old.StatusPracticeConditions(
                        player_accuracy=-6 if context == "accuracy" else 0,
                        player_status="paralysis" if context == "paralysis" else "none",
                    )
                ),
                "practice": practice,
            }
        )
    return rows


def preflight():
    require(not OUTPUT.exists(), "two-turn execution identity consumed")
    for offset in OFFSETS:
        validate_opening_idle_frames(offset)
    require(old.sha(composition.CANDIDATE) == composition.CANDIDATE_SHA, "candidate changed")
    require(
        old.sha(composition.OUTPUT / "AUDIT.json")
        == "d1faa4ac7cf75f8aa3136391c274acfb3d3ca9ce31f110cfdd326f9256fb3f88",
        "composition audit changed",
    )
    cartridge, catalog, sources, _, admitted = old.inputs()
    candidate = old.TrainerPracticeThreeHeadModel.from_dict(read(composition.CANDIDATE))
    composition.assert_models(admitted, candidate)
    rows = recipes(cartridge, catalog, sources)
    for row in rows:
        source = sources[row["source_index"]][0]
        capture = open_battle_scenario_capture(
            source / "source.state", source / "source.state.json"
        )
        spec = row["practice"]
        BattlePracticeSpec.from_dict(
            {
                **spec,
                "root_lineage_id": row["root"],
                "source_state_sha256": capture.manifest.state_sha256,
            }
        )
        for side, reserves in (("actor", "party_reserves"), ("opponent", "opponent_reserves")):
            members = [{k: spec[f"{side}_{k}"] for k in ("species_ref", "level", "moves")}]
            members += spec.get(reserves, [])
            for member in members:
                species = int(member["species_ref"][-3:])
                legal = set(cartridge.species(species).teachable_moves_at_level(member["level"]))
                supported = set(old.legal_damage(cartridge, catalog, species, member["level"])) | {
                    19,
                    91,
                }
                require(
                    all(int(m["move_ref"][-3:]) in legal & supported for m in member["moves"]),
                    "own-level unsupported move",
                )
    return cartridge, catalog, sources, admitted, candidate, rows


def summarize(pairs):
    common = [p for p in pairs if p["admitted"]["win"] and p["candidate"]["win"]]
    counts = {
        a: {
            k: sum(p[a][k] for p in pairs)
            for k in (
                "win",
                "loss",
                "censored",
                "pp_spent",
                "actual_frames",
                "decisions",
                "actual_actions",
                "own_faints",
                "invalid_action_failures",
            )
        }
        for a in ("admitted", "candidate")
    }
    failures = []
    for key, bad in (
        ("win", lambda a, b: a < b),
        ("loss", lambda a, b: a > b),
        ("censored", lambda a, b: a > b),
    ):
        if bad(counts["candidate"][key], counts["admitted"][key]):
            failures.append(f"{key}_regression")
    if any(counts[a]["invalid_action_failures"] for a in counts):
        failures.append("illegal_action")
    efficiency = {}
    if not common:
        failures.append("no_common_win")
    for key, limit in (("pp_spent", 0.10), ("actual_frames", 0.25)):
        if common:
            base, new = (fmean(p[a][key] for p in common) for a in ("admitted", "candidate"))
            efficiency[key] = {
                "admitted": base,
                "candidate": new,
                "increase_fraction": (new - base) / base if base else None,
            }
            if not base or (new - base) / base > limit:
                failures.append(f"{key}_regression")
    return {
        "counts": counts,
        "common_wins": len(common),
        "efficiency": efficiency,
        "behavior_failures": failures,
    }


def run(*, inspect=False):
    cartridge, _, sources, admitted, candidate, rows = preflight()
    if inspect:
        return {
            "preflight": "ready",
            "rows": len(rows),
            "max_episodes": 64,
            "pairs": [
                (r["id"], r["charge_move"], r["context"], r["own_species"], r["opponent_species"])
                for r in rows
            ],
        }
    require(
        not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip(),
        "requires clean committed source",
    )
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    protected = dict(read(composition.OUTPUT / "PLAN.json")["protected_inputs"])
    protected.update(
        {
            str(composition.OUTPUT / name): old.sha(composition.OUTPUT / name)
            for name in ("PLAN.json", "RESULT.json", "AUDIT.json")
        }
    )
    pins = composition.damage._source_pins()
    for name in (
        "run_red_two_turn_compatibility.py",
        "audit_red_two_turn_compatibility.py",
        "run_red_damage_composition.py",
        "audit_red_damage_composition.py",
        "audit_red_interaction_damage_successor.py",
    ):
        pins[f"scripts/{name}"] = old.sha(ROOT / "scripts" / name)
    plan = {
        "schema": "pokemon.red.two-turn-compatibility.v1",
        "source_commit": commit,
        "source_hashes": pins,
        "protected_inputs": protected,
        "rows": rows,
        "offsets": OFFSETS,
        "seed": SEED,
        "maximum_episodes": 64,
        "maximum_elapsed_seconds": MAX_SECONDS,
        "orders": {
            f"{r['id']}:{offset}": (
                ["admitted", "candidate"] if (i + j) % 2 == 0 else ["candidate", "admitted"]
            )
            for i, r in enumerate(rows)
            for j, offset in enumerate(OFFSETS)
        },
        "gates": {
            "candidate_win_loss_censor_regressions_max": 0,
            "illegal_actions_max": 0,
            "choices_during_charge_max": 0,
            "both_sides_charge_moves_observed": [19, 91],
            "candidate_charge_moves_selected": [19, 91],
            "common_wins_required": True,
            "common_win_pp_increase_max": 0.10,
            "common_win_frame_increase_max": 0.25,
        },
        "fits": 0,
        "actor_memory_writes": 0,
        "story_actions": 0,
        "arm_caps": {"actions": 5000, "frames": 120000, "seconds": 45, "decisions": 80},
    }
    for path, digest in protected.items():
        require(old.sha(Path(path)) == digest, "protected input changed")
    OUTPUT.mkdir(mode=0o700)
    old.write_once(OUTPUT / "PLAN.json", plan)
    args = argparse.Namespace(output=OUTPUT, rom=old.ROM)
    start, active = time.monotonic(), None
    pairs, probes = [], []
    try:
        for row in rows:
            require(time.monotonic() - start < MAX_SECONDS, "packet deadline")
            capture = old.lab.materialize(
                args, row, row["source_index"], sources, cartridge, commit
            )
            for offset in OFFSETS:
                arms = {}
                order = (["probe"] if row["player_charge"] else []) + plan["orders"][
                    f"{row['id']}:{offset}"
                ]
                for arm in order:
                    require(time.monotonic() - start < MAX_SECONDS, "packet deadline")
                    active = {"row": row["id"], "offset": offset, "arm": arm}
                    path = OUTPUT / row["id"] / f"offset-{offset}-{arm}"
                    old.write_once(
                        path.with_suffix(".claim.json"),
                        {
                            **active,
                            "plan_sha256": old.sha(OUTPUT / "PLAN.json"),
                            "elapsed_seconds": time.monotonic() - start,
                        },
                    )
                    try:
                        episode = old.lab.play(
                            args,
                            capture,
                            admitted if arm == "admitted" else candidate,
                            path,
                            cartridge,
                            offset=offset,
                            first_slot=1 if arm == "probe" else None,
                            horizon=1 if arm == "probe" else None,
                            learner_continuation=True,
                            trace_two_turn=True,
                        )
                    except ValueError as error:
                        if not (path / "episode.json").exists():
                            raise
                        episode = read(path / "episode.json")
                        if (
                            episode["stop_reason"] not in composition.CENSORED_STOPS
                            or str(error) != f"unsupported stop {episode['stop_reason']}"
                        ):
                            raise
                        from audit_red_interaction_damage_successor import _audit_events

                        _audit_events(path, "run_finished")
                    terminal = read(path / "final-state.json")
                    metrics = old._composition_metrics(episode, path)
                    metrics.update(
                        {
                            "actual_frames": terminal["frame_delta"],
                            "actual_actions": terminal["completed_actions"],
                            "terminal_sha256": terminal["state_sha256"],
                        }
                    )
                    arms[arm] = metrics
                    if arm == "probe":
                        probes.append({**active, **metrics})
                pair = {
                    "row": row["id"],
                    "offset": offset,
                    "admitted": arms["admitted"],
                    "candidate": arms["candidate"],
                }
                old.write_once(OUTPUT / row["id"] / f"pair-{offset}.json", pair)
                pairs.append(pair)
                print(json.dumps({"pairs": len(pairs), "row": row["id"]}), flush=True)
        result = {
            "plan_sha256": old.sha(OUTPUT / "PLAN.json"),
            "pairs": pairs,
            "probes": probes,
            "native_elapsed_seconds": time.monotonic() - start,
            **summarize(pairs),
            "decision": "requires_independent_trace_and_coverage_audit",
        }
        old.write_once(OUTPUT / "RESULT.json", result)
        return {k: v for k, v in result.items() if k not in {"pairs", "probes"}}
    except BaseException as error:
        old.write_once(
            OUTPUT / "FAILURE.json",
            {
                "type": type(error).__name__,
                "message": str(error),
                "active": active,
                "completed_pairs": len(pairs),
                "completed_probes": len(probes),
                "elapsed_seconds": time.monotonic() - start,
                "retry_allowed": False,
            },
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    print(json.dumps(run(inspect=parser.parse_args().preflight)))
