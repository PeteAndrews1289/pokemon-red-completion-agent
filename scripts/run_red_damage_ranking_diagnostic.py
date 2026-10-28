"""Bounded TRAIN-only type-shortcut ablation, not a promoted actor or a refit.

Measure all three attacks for one native turn. Timing siblings share a root;
damage regret is not whole-battle utility. Excludes the Route22 story species.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import time
from dataclasses import asdict, replace
from pathlib import Path
from statistics import fmean

import numpy as np
import run_red_status_curriculum as lab

from pokemon_red_completion.red_battle_catalog import pokemon_red_species_ref
from pokemon_red_completion.red_status_practice import StatusPracticeConditions
from pokemon_red_completion.red_trainer_practice_features import project_trainer_move_features

SEED = 2026092231
EXCLUDED_SPECIES = frozenset({118, 104, 28, 64, 132, 151, 18, 22, 33, 149, 154})


def ablate_type_identity(head):
    """Preserve effectiveness/STAB/category/stats; remove raw move-type one-hots only."""
    indices = [i for i, name in enumerate(head.feature_names) if name.startswith("move.type.")]
    if not indices:
        raise ValueError("head has no raw move-type features")
    weights = head.weights1.copy()
    weights[indices] = 0
    return replace(head, weights1=weights)


def score_contributions(head, chosen, alternative):
    """Exact secant decomposition of a tanh score difference, NOT causal effects."""
    rows = np.asarray((chosen, alternative), dtype=float)
    head.scores(rows)  # Validate shape and finiteness before broadcasting.
    z1, z0 = rows @ head.weights1 + head.bias1
    dz = z1 - z0
    secant = np.divide(
        np.tanh(z1) - np.tanh(z0), dz, out=1 - np.tanh(z0) ** 2, where=np.abs(dz) > 1e-12
    )
    return (rows[0] - rows[1]) * (head.weights1 @ (head.weights2 * secant))


def recipes(cartridge):
    catalog, rng, rows = lab.PokemonRedBattleCatalog(), random.Random(SEED), []
    for index in range(16):
        level = (31, 37, 43, 49)[index % 4]
        pool = {}
        for species in cartridge.species_ids:
            if species in EXCLUDED_SPECIES:
                continue
            moves = [
                m
                for m in cartridge.species(species).teachable_moves_at_level(level)
                if catalog.recovery_attack_supported(lab.pokemon_red_move_ref(m))
                and 30 <= catalog.resolve_move(lab.pokemon_red_move_ref(m)).power <= 100
                and not catalog.resolve_move(lab.pokemon_red_move_ref(m)).effect_flags
                & {
                    "multi_hit",
                    "charge",
                    "drain",
                    "recoil",
                    "self_destruct",
                    "fixed_damage",
                    "ohko",
                    "counter",
                }
            ]
            if len(moves) >= 3:
                pool[species] = moves
        for _ in range(10000):
            actor, enemy = rng.sample(sorted(pool), 2)
            moves = rng.sample(pool[actor], 3)
            definitions = [catalog.resolve_move(lab.pokemon_red_move_ref(m)) for m in moves]
            foe_types = catalog.resolve_species(pokemon_red_species_ref(enemy)).types
            effects = [catalog.type_effectiveness(m.type_name, foe_types) for m in definitions]
            if (
                len({m.type_name for m in definitions}) >= 2
                and len(set(effects)) >= 2
                and max(effects) > 0
            ):
                break
        else:
            raise ValueError("could not construct prospective contrast")

        def move_rows(ids):
            return [
                {
                    "move_ref": lab.pokemon_red_move_ref(m),
                    "pp": catalog.resolve_move(lab.pokemon_red_move_ref(m)).max_pp,
                }
                for m in ids
            ]

        own, foe = cartridge.species(actor), cartridge.species(enemy)
        rows.append(
            {
                "id": f"damage-{index:02d}",
                "role": "diagnostic_train",
                "conditions": asdict(StatusPracticeConditions()),
                "practice": {
                    "partition": "train",
                    "battle_kind": "trainer",
                    "actor_species_ref": pokemon_red_species_ref(actor),
                    "actor_national_number": own.national_number,
                    "actor_level": level,
                    "actor_hp": own.neutral_stats(level).max_hp,
                    "actor_moves": move_rows(moves),
                    "opponent_species_ref": pokemon_red_species_ref(enemy),
                    "opponent_national_number": foe.national_number,
                    "opponent_level": level,
                    "opponent_hp": foe.trainer_stats(level).max_hp,
                    "opponent_moves": move_rows(rng.sample(pool[enemy], 2)),
                    "opponent_party_count": 1,
                },
            }
        )
    return rows


def run(args):
    if args.output.exists():
        raise ValueError("consumed output identity")
    frozen = lab.TrainerPracticeThreeHeadModel.from_dict(json.loads(args.frozen.read_bytes()))
    if lab.common._binding(args.frozen)["sha256"] != lab.K_SHA:
        raise ValueError("not the frozen K reference")
    if lab.common._binding(args.rom)["sha256"] != lab.common.ROM_SHA256:
        raise ValueError("cartridge differs")
    sources = lab.common._source_rows(args.batch)
    if {r["source_id"] for _, r in sources} != set(frozen.train_root_ids):
        raise ValueError("TRAIN ancestry differs")
    cartridge = lab.RedPracticeCartridge(args.rom.read_bytes())
    rows = recipes(cartridge)
    ablated = ablate_type_identity(frozen.move)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    plan = {
        "schema": "pokemon.red.damage-ranking-diagnostic.v1",
        "seed": SEED,
        "source_commit": commit,
        "driver": lab.common._binding(Path(__file__)),
        "frozen": lab.common._binding(args.frozen),
        "rom": lab.common._binding(args.rom),
        "sources": [lab.common._binding(s / "source.state.json") for s, _ in sources],
        "recipes": rows,
        "offsets": [0, 4, 8],
        "maximum_branches": 144,
        "maximum_player_turns": 1,
        "maximum_seconds": 1200,
        "ablation": "zero move.type.* input weights only; no fitting or selection",
        "rejection": (
            "aggregate damage regret fails to decrease, "
            "or any paired case regresses by >0.05 foe HP fraction"
        ),
        "fits": 0,
        "promotions": 0,
        "independent_heldout_roots": 0,
        "excluded_story_species": sorted(EXCLUDED_SPECIES),
    }
    lab.write(args.output / "plan.json", plan)  # Before any emulator materialization.
    start, results = time.monotonic(), []
    try:
        for index, row in enumerate(rows):
            if time.monotonic() - start > 1200:
                raise TimeoutError("global diagnostic deadline")
            capture = lab.materialize(args, row, index, sources, cartridge, commit)
            directory = args.output / row["id"]
            with lab.PyBoyAdapter(args.rom, watch=False, speed=None) as em:
                em.load_state_bytes(capture.state_bytes)
                reader = lab.PokemonRedStateReader(em)
                encoder = lab.PokemonRedObservationEncoder(
                    reader, True, cartridge.public_base_stats, True
                )
                raw = reader.read()
                prepared = lab.prepare_red_battle_scenario(encoder, raw, allow_status_moves=True)
                observation = encoder.snapshot_from_raw(raw).to_dict()
                batch = project_trainer_move_features(observation, prepared.features)
                slots = tuple(
                    s + 1
                    for s, ok in zip(
                        prepared.features.slot_indices, prepared.features.legal_mask, strict=True
                    )
                    if ok
                )
                if slots != (1, 2, 3):
                    raise ValueError("diagnostic legal attack inventory differs")
                vectors = [batch.candidate_vectors[batch.candidate_slots.index(s)] for s in slots]
            baseline = frozen.move.predict_index(vectors)
            candidate = ablated.predict_index(vectors)
            branch_rows = []
            for offset in (0, 4, 8):
                for slot in slots:
                    if time.monotonic() - start > 1200:
                        raise TimeoutError("global diagnostic deadline")
                    result = lab.play(
                        args,
                        capture,
                        frozen,
                        directory / f"branch-{offset}-{slot}",
                        cartridge,
                        first_slot=slot,
                        offset=offset,
                        horizon=1,
                    )
                    steps = result["decisions"]
                    attacks = [s for s in steps if s["kind"] == "attack"]
                    if len(attacks) != 1 or attacks[0]["move_slot"] != slot:
                        raise ValueError("forced first attack did not execute exactly once")
                    step = attacks[0]
                    hp = step["observation"]["features"]["battle"]["opponent_max_hp"]
                    damage = (step["opponent_hp_before"] - step["opponent_hp_after"]) / hp
                    branch_rows.append(
                        {
                            "slot": slot,
                            "offset": offset,
                            "damage_fraction": damage,
                            "utility": lab.outcome_value(result),
                            "stop": result["stop_reason"],
                            "metrics": result["metrics"],
                        }
                    )
            values = [
                fmean(b["damage_fraction"] for b in branch_rows if b["slot"] == s) for s in slots
            ]
            report = {
                "id": row["id"],
                "root": capture.manifest.root_lineage_id,
                "capture_sha256": capture.manifest.state_sha256,
                "vectors": vectors,
                "slots": slots,
                "baseline_index": baseline,
                "candidate_index": candidate,
                "mean_damage": values,
                "baseline_regret": max(values) - values[baseline],
                "candidate_regret": max(values) - values[candidate],
                "branches": branch_rows,
                "baseline_scores": frozen.move.scores(vectors).tolist(),
                "candidate_scores": ablated.scores(vectors).tolist(),
            }
            lab.write(directory / "result.json", report)
            results.append(report)
            print(
                json.dumps(
                    {
                        k: report[k]
                        for k in ("id", "baseline_index", "candidate_index", "mean_damage")
                    }
                ),
                flush=True,
            )
        baseline = fmean(r["baseline_regret"] for r in results)
        candidate = fmean(r["candidate_regret"] for r in results)
        regressions = [
            r["id"] for r in results if r["candidate_regret"] - r["baseline_regret"] > 0.05
        ]
        summary = {
            "schema": plan["schema"],
            "status": "completed",
            "configurations": len(results),
            "branches": len(results) * 9,
            "fits": 0,
            "promotions": 0,
            "baseline_damage_regret": baseline,
            "candidate_damage_regret": candidate,
            "material_regressions": regressions,
            "ablation_rejected": candidate >= baseline or bool(regressions),
            "changed_choices": sum(r["baseline_index"] != r["candidate_index"] for r in results),
            "seconds": time.monotonic() - start,
            "plan_sha256": hashlib.sha256((args.output / "plan.json").read_bytes()).hexdigest(),
            "results": results,
        }
        lab.write(args.output / "result.json", summary)
        print(json.dumps({k: v for k, v in summary.items() if k != "results"}), flush=True)
    except Exception as error:
        lab.write(
            args.output / "failure.json",
            {
                "error": str(error),
                "type": type(error).__name__,
                "completed_configurations": len(results),
                "seconds": time.monotonic() - start,
            },
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "frozen", "batch", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    run(parser.parse_args())
