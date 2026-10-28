"""Fresh TRAIN root x level diagnostic, with no fit or deployed-policy change.

Four new matchup families, four levels and all four existing TRAIN roots.
Each cell measures four attacks at three offsets. These 768 forced branches
diagnose root/level confounding; they are not independent transfer evidence.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from itertools import product
from pathlib import Path
from statistics import fmean

import numpy as np
import run_red_damage_proposal_overnight as old

lab = old.lab
LEVELS = (31, 37, 43, 49)
ROOTS = tuple(range(4))
SEED = 23092311
CANDIDATE_SHA = "9e81faf572be5a8cf1de27ec7f7fe933b15efc71f87a8bc60a3722a4478fd31b"


def validate_crossing(rows: list[dict]) -> None:
    families = sorted({r["family_id"] for r in rows})
    cells = Counter((r["family_id"], r["source_index"], r["practice"]["actor_level"]) for r in rows)
    if len(families) != 4 or cells != Counter(product(families, ROOTS, LEVELS)):
        raise ValueError("requires each family at every root and level exactly once")
    if len({r["id"] for r in rows}) != 64:
        raise ValueError("duplicate trial identity")
    pairs = set()
    for family in families:
        subset = [r for r in rows if r["family_id"] == family]
        signatures = {
            (
                r["practice"]["actor_species_ref"],
                r["practice"]["opponent_species_ref"],
                tuple(m["move_ref"] for m in r["practice"]["actor_moves"]),
                tuple(m["move_ref"] for m in r["practice"]["opponent_moves"]),
            )
            for r in subset
        }
        if len(signatures) != 1:
            raise ValueError("family moves or species change across root/level cells")
        signature = next(iter(signatures))
        pair = tuple(sorted(signature[:2]))
        if pair in pairs:
            raise ValueError("unordered matchup family repeats")
        pairs.add(pair)


def recipes(cartridge, catalog, sources, prior: dict) -> list[dict]:
    rng = random.Random(SEED)
    used = old._prior_pairs() | {
        tuple(sorted((f["actor_species_id"], f["opponent_species_id"]))) for f in prior["families"]
    }
    # Fix the moves at the lowest level so later-level cells do not add coverage.
    pool = {
        s: old.legal_damage(cartridge, catalog, s, min(LEVELS))
        for s in cartridge.species_ids
        if s not in old.EXCLUDED_SPECIES
    }
    physical = {
        s: tuple(
            m
            for m in moves
            if catalog.resolve_move(old.pokemon_red_move_ref(m)).category == "physical"
        )
        for s, moves in pool.items()
    }
    special = {
        s: tuple(
            m
            for m in moves
            if catalog.resolve_move(old.pokemon_red_move_ref(m)).category == "special"
        )
        for s, moves in pool.items()
    }
    actors = sorted(s for s in pool if len(physical[s]) >= 2 and len(special[s]) >= 2)
    enemies = sorted(s for s in pool if len(pool[s]) >= 2)
    used_actors = set()
    rows = []
    for family_index in range(4):
        options = []
        for _ in range(2000):
            actor, enemy = rng.choice(actors), rng.choice(enemies)
            if actor == enemy or actor in used_actors or tuple(sorted((actor, enemy))) in used:
                continue
            moves = tuple(rng.sample(physical[actor], 2) + rng.sample(special[actor], 2))
            ratio = (
                cartridge.species(actor).neutral_stats(37).attack
                / cartridge.species(enemy).trainer_stats(40).defense
            )
            score = old._family_score(catalog, actor, enemy, moves, stat_ratio=ratio)
            options.append((score + rng.random(), actor, enemy, moves))
        if not options:
            raise ValueError("no eligible fresh family")
        _, actor, enemy, moves = max(options)
        used.add(tuple(sorted((actor, enemy))))
        used_actors.add(actor)
        foe_moves = tuple(rng.sample(pool[enemy], 2))
        for root, level in product(ROOTS, LEVELS):
            own, foe = cartridge.species(actor), cartridge.species(enemy)
            rows.append(
                {
                    "id": f"cross-{family_index}-root-{root}-level-{level}",
                    "family_id": f"cross-{family_index}",
                    "role": "diagnostic",
                    "source_index": root,
                    "root": sources[root][1]["source_id"],
                    "conditions": asdict(old.StatusPracticeConditions()),
                    "practice": {
                        "partition": "train",
                        "battle_kind": "trainer",
                        "actor_species_ref": old.pokemon_red_species_ref(actor),
                        "actor_national_number": own.national_number,
                        "actor_level": level,
                        "actor_hp": own.neutral_stats(level).max_hp,
                        "actor_moves": old._move_rows(catalog, moves),
                        "opponent_species_ref": old.pokemon_red_species_ref(enemy),
                        "opponent_national_number": foe.national_number,
                        "opponent_level": level + 3,
                        "opponent_hp": foe.trainer_stats(level + 3).max_hp,
                        "opponent_moves": old._move_rows(catalog, foe_moves),
                        "opponent_party_count": 1,
                    },
                }
            )
    validate_crossing(rows)
    return rows


def choice_metrics(values, vectors, heads):
    best = max(values)
    return {
        name: {
            "slot": head.predict_index(vectors) + 1,
            "regret": best - values[head.predict_index(vectors)],
            "strict_best": best - values[head.predict_index(vectors)] <= 1e-12,
            "near_best_002": best - values[head.predict_index(vectors)] <= 0.02,
            "scores": head.scores(vectors).tolist(),
        }
        for name, head in heads.items()
    }


def summarize(targets):
    groups = defaultdict(list)
    for row in targets:
        groups[(row["family_id"], row["level"])].append(row)
    root_checks = []
    for (family, level), cells in sorted(groups.items()):
        if len(cells) != 4 or {c["source_index"] for c in cells} != set(ROOTS):
            raise ValueError("incomplete root group")
        root_checks.append(
            {
                "family_id": family,
                "level": level,
                "max_feature_delta_across_roots": max(
                    float(
                        np.max(np.abs(np.asarray(c["vectors"]) - np.asarray(cells[0]["vectors"])))
                    )
                    for c in cells
                ),
                "max_slot_mean_damage_spread": max(
                    max(c["mean_damage"][slot] for c in cells)
                    - min(c["mean_damage"][slot] for c in cells)
                    for slot in range(4)
                ),
                "selected_slots_by_root": {
                    name: [c["choices"][name]["slot"] for c in cells] for name in ("K", "rejected")
                },
            }
        )
    scores = {}
    for name in ("K", "rejected"):
        scores[name] = {
            "mean_regret": fmean(r["choices"][name]["regret"] for r in targets),
            "strict_best": sum(r["choices"][name]["strict_best"] for r in targets),
            "near_best_002": sum(r["choices"][name]["near_best_002"] for r in targets),
            "by_level": {
                str(level): fmean(
                    r["choices"][name]["regret"] for r in targets if r["level"] == level
                )
                for level in LEVELS
            },
            "by_root": {
                str(root): fmean(
                    r["choices"][name]["regret"] for r in targets if r["source_index"] == root
                )
                for root in ROOTS
            },
        }
    return {
        "configurations": len(targets),
        "scores": scores,
        "root_checks": root_checks,
        "fits": 0,
        "learned_native_actions": 0,
        "promotions": 0,
        "interpretation": "same-bank crossed diagnostic; no independent transfer claim",
    }


def run(args):
    if args.output.exists():
        raise ValueError("consumed output identity; no resume or retry")
    start = time.monotonic()
    cartridge, catalog, sources, k, _ = old.inputs()
    if (
        len(sources) != 4
        or old.sha(args.candidate) != CANDIDATE_SHA
        or old.sha(args.rom) != lab.common.ROM_SHA256
    ):
        raise ValueError("source count or rejected-candidate binding differs")
    candidate = old.TrainerPracticeThreeHeadModel.from_dict(json.loads(args.candidate.read_bytes()))
    prior_path = old.OUTPUT / "PLAN.json"
    prior = json.loads(prior_path.read_bytes())
    rows = recipes(cartridge, catalog, sources, prior)
    for row in rows:
        source = sources[row["source_index"]][0]
        capture = lab.open_battle_scenario_capture(
            source / "source.state", source / "source.state.json"
        )
        lab.BattlePracticeSpec.from_dict(
            {
                **row["practice"],
                "root_lineage_id": row["root"],
                "source_state_sha256": capture.manifest.state_sha256,
            }
        )
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=old.ROOT).decode().strip()
    source_hashes = {
        str(p.relative_to(old.ROOT)): old.sha(p)
        for p in (
            Path(__file__),
            Path(old.__file__),
            Path(lab.__file__),
            Path(lab.common.__file__),
            old.ROOT / "scripts/run_red_trainer_practice_model.py",
        )
    }
    # Runtime sources are pinned too; this packet records a dirty-source overlay explicitly.
    source_hashes.update(
        {str(p.relative_to(old.ROOT)): old.sha(p) for p in (old.ROOT / "src").rglob("*.py")}
    )
    protected = [
        old.K,
        old.ADMITTED,
        args.candidate,
        prior_path,
        old.PRIVATE
        / "goal-manager-v1/model141-earned-story-campaign-20260921-v1/stage-328/final.state",
        old.PRIVATE
        / "goal-manager-v1/model141-integrated-play-20260921-v1/step-006/terminal.state",
    ]
    pins = {str(p): old.sha(p) for p in protected}
    args.output.mkdir(mode=0o700)
    old.write_once(
        args.output / "PLAN.json",
        {
            "schema": "pokemon.red.crossed-damage-diagnostic.v1",
            "created_at": old.utc_now(),
            "source_commit": commit,
            "source_overlay_sha256": source_hashes,
            "protected_inputs": pins,
            "rom_sha256": old.sha(args.rom),
            "recipes": rows,
            "seed": SEED,
            "offsets": old.OFFSETS,
            "maximum_branches": 768,
            "maximum_elapsed_seconds": 2700,
            "fits": 0,
            "neutral_context_only": True,
            "decision": "diagnose root/level and interaction failures; no candidate admission",
        },
    )
    heads = {"K": k.move, "rejected": candidate.damage_reference}
    targets, costs = [], []
    try:
        for row in rows:
            if time.monotonic() - start >= 2700:
                raise TimeoutError("crossed diagnostic budget exhausted")
            capture = lab.materialize(args, row, row["source_index"], sources, cartridge, commit)
            vectors, slots = old._vectors(capture, cartridge)
            branches = []
            for offset, slot in product(old.OFFSETS, slots):
                if time.monotonic() - start >= 2700:
                    raise TimeoutError("crossed diagnostic budget exhausted")
                output = args.output / row["id"] / f"branch-{offset}-{slot}"
                episode = lab.play(
                    args, capture, k, output, cartridge, first_slot=slot, offset=offset, horizon=1
                )
                attacks = [d for d in episode["decisions"] if d["kind"] == "attack"]
                if len(attacks) != 1 or attacks[0]["move_slot"] != slot:
                    raise ValueError("forced action does not match frozen slot")
                d = attacks[0]
                observation = d["observation"]
                projected = old.project_trainer_move_features(
                    observation, lab.BattleFeatureProjector(catalog).project(observation)
                )
                if not np.allclose(projected.candidate_vectors, vectors, rtol=0, atol=1e-12) or d[
                    "legal_move_slots"
                ] != [1, 2, 3, 4]:
                    raise ValueError("branch initial observation or legal features differ")
                obs = observation["features"]
                if (
                    obs["party"]["lead"]["hp"] != row["practice"]["actor_hp"]
                    or obs["battle"]["opponent_hp"] != row["practice"]["opponent_hp"]
                    or obs["party"]["lead"]["status"] is not None
                    or obs["battle"]["opponent_status"] is not None
                ):
                    raise ValueError("branch conditioning differs from frozen neutral recipe")
                cap = d["observation"]["features"]["battle"]["opponent_max_hp"]
                damage = (d["opponent_hp_before"] - d["opponent_hp_after"]) / cap
                if not 0 <= damage <= 1:
                    raise ValueError("invalid damage target")
                endpoint = json.loads((output / "final-state.json").read_bytes())
                if old.sha(output / "final.state") != endpoint["state_sha256"]:
                    raise ValueError("terminal hash mismatch")
                if not 0 < endpoint["completed_actions"] <= endpoint["attempted_actions"] <= 5000:
                    raise ValueError("actual action count out of budget")
                costs.append(endpoint)
                branches.append(
                    {
                        "slot": slot,
                        "offset": offset,
                        "damage_fraction": damage,
                        "episode_sha256": old.sha(output / "episode.json"),
                        "stop_reason": episode["stop_reason"],
                    }
                )
            values = tuple(
                fmean(b["damage_fraction"] for b in branches if b["slot"] == slot) for slot in slots
            )
            target = {
                "id": row["id"],
                "family_id": row["family_id"],
                "level": row["practice"]["actor_level"],
                "source_index": row["source_index"],
                "root": row["root"],
                "vectors": vectors,
                "mean_damage": values,
                "capture_sha256": capture.manifest.state_sha256,
                "choices": choice_metrics(values, vectors, heads),
                "branches": branches,
            }
            old.write_once(args.output / row["id"] / "target.json", target)
            targets.append(target)
            print(json.dumps({"completed": len(targets), "id": row["id"]}), flush=True)
        result = summarize(targets)
        result["costs"] = {
            key: sum(c[key] for c in costs)
            for key in (
                "attempted_actions",
                "completed_actions",
                "frame_delta",
                "wall_elapsed_seconds",
            )
        }
        result["branches"] = len(costs)
        result["stop_counts"] = dict(
            Counter(b["stop_reason"] for t in targets for b in t["branches"])
        )
        result["elapsed_seconds"] = time.monotonic() - start
        result["protected_inputs_unchanged"] = all(old.sha(Path(p)) == h for p, h in pins.items())
        result["source_unchanged"] = all(
            old.sha(old.ROOT / p) == h for p, h in source_hashes.items()
        )
        if not result["protected_inputs_unchanged"] or not result["source_unchanged"]:
            raise ValueError("protected input or execution source changed")
        old.write_once(args.output / "RESULT.json", result)
        print(json.dumps(result), flush=True)
    except BaseException as error:
        old.write_once(
            args.output / "FAILURE.json",
            {
                "type": type(error).__name__,
                "message": str(error),
                "completed_configurations": len(targets),
                "completed_branches": len(costs),
                "elapsed_seconds": time.monotonic() - start,
            },
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=old.ROM)
    run(parser.parse_args())
