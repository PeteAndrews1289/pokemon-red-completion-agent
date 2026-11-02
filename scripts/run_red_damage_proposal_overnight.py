"""One prospective TRAIN damage-head fit with family-held comparison.

Private outputs are never checked in. Every native dispatch has a unique identity,
an enforced limit, and either a retained episode or a retained failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean, median

import numpy as np
import run_red_status_curriculum as lab

from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref, pokemon_red_species_ref
from pokemon_red_completion.red_status_practice import StatusPracticeConditions
from pokemon_red_completion.red_trainer_practice_features import (
    MOVE_FEATURE_NAMES,
    MOVE_SCHEMA_ID,
    project_trainer_move_features,
)
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel
from pokemon_red_completion.red_trainer_practice_returns import tied_best_indices

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path(os.environ.get("POKEMON_PRIVATE_BASE", "/nonexistent/pokemon-private-base"))
WORKSPACE = Path(
    os.environ.get("POKEMON_OVERNIGHT_WORKSPACE", "/nonexistent/pokemon-overnight-workspace")
)
STATE = WORKSPACE / "run-state.json"
OUTPUT = PRIVATE / "red-damage-proposal-overnight-20260923-v1"
ROM = PRIVATE / "storage-migration/roms/PokemonRoms/Pokemon Red.gb"
BATCH = PRIVATE / "red-fresh-trainer-train-batch-20260917"
K = PRIVATE / "red-trainer-J-canonical-20260920-v1/candidate-model.json"
ADMITTED = PRIVATE / "red-additive-status-fit-20260922-v1/candidate-model.json"
DIAGNOSTIC = PRIVATE / "red-damage-ranking-diagnostic-20260922-v1/plan.json"
EXCLUDED_SPECIES = frozenset({118, 104, 28, 64, 132, 151, 18, 22, 33, 149, 154})
EXCLUDED_FLAGS = frozenset(
    {
        "charge",
        "recharge",
        "multi_hit",
        "trapping",
        "ohko",
        "fixed_damage",
        "counter",
        "self_destruct",
        "drain",
        "recoil",
    }
)
FEATURES = (
    "state.player_hp_ratio",
    "state.opponent_hp_ratio",
    "state.player_level_fraction",
    "state.opponent_level_fraction",
    "state.level_difference_fraction",
    "move.pp_fraction",
    "move.power_fraction",
    "move.accuracy",
    "move.category.physical",
    "move.category.special",
    "move.stab",
    "move.type_effectiveness_fraction",
    "move.effective_power_fraction",
    "move.accuracy_weighted_effective_power_fraction",
    "move.priority",
    "move.effect.status",
    "interaction.physical_x_player_attack_stage",
    "interaction.physical_x_opponent_defense_stage",
    "interaction.physical_x_player_burn",
    "interaction.move_accuracy_x_player_accuracy_stage",
    "interaction.effective_power_x_opponent_hp",
    "interaction.effective_power_x_level_difference",
    "interaction.pp_x_effective_power",
    "observable.player.special_stage",
    "interaction.physical_attack_over_estimated_defense",
    "interaction.special_over_estimated_special",
    "interaction.player_speed_over_estimated_speed",
)
FEATURE_INDICES = tuple(MOVE_FEATURE_NAMES.index(name) for name in FEATURES)
SEEDS = {"recipe": 230901, "fit": 230902, "paired_order": 230903, "bootstrap": 230904}
OFFSETS = (0, 4, 8)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_once(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write((json.dumps(data, sort_keys=True, indent=2) + "\n").encode())


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def state_update(*, unit: str | None = None, **changes: object) -> None:
    state = json.loads(STATE.read_bytes())
    if unit is not None:
        if unit in state["completed_units"]:
            raise ValueError(f"duplicate completed unit {unit}")
        state["completed_units"].append(unit)
    state.update(changes, last_updated_at_utc=utc_now())
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")
    os.replace(temporary, STATE)


def deadline_check(*, native: bool = False) -> None:
    state = json.loads(STATE.read_bytes())
    elapsed = time.monotonic() - state["started_monotonic_seconds"]
    if elapsed >= state["maximum_elapsed_seconds"]:
        raise TimeoutError("original eight-hour deadline")
    if native and elapsed >= state["native_dispatch_cutoff_seconds"]:
        raise TimeoutError("native dispatch cutoff")


def inputs() -> tuple[object, object, tuple, object, object]:
    expected = {
        ROM: lab.common.ROM_SHA256,
        K: lab.K_SHA,
        ADMITTED: "8ef6a8512bc6c2b4e21b6a95e98ed769bc1634ea90f997961f2e6fd3f7227a12",
    }
    for path, digest in expected.items():
        if sha(path) != digest:
            raise ValueError(f"input binding differs: {path.name}")
    sources = lab.common._source_rows(BATCH)
    k = TrainerPracticeThreeHeadModel.from_dict(json.loads(K.read_bytes()))
    admitted = TrainerPracticeThreeHeadModel.from_dict(json.loads(ADMITTED.read_bytes()))
    if {r["source_id"] for _, r in sources} != set(k.train_root_ids):
        raise ValueError("TRAIN ancestry differs")
    if admitted.damage_reference is None or admitted.damage_reference.to_dict() != k.move.to_dict():
        raise ValueError("admitted damage reference differs from K")
    cartridge = lab.RedPracticeCartridge(ROM.read_bytes())
    catalog = lab.PokemonRedBattleCatalog()
    return cartridge, catalog, sources, k, admitted


def legal_damage(cartridge, catalog, species: int, level: int) -> tuple[int, ...]:
    result = []
    for move in cartridge.species(species).teachable_moves_at_level(level):
        ref = pokemon_red_move_ref(move)
        mechanics = catalog.resolve_move(ref)
        if (
            catalog.recovery_attack_supported(ref)
            and mechanics.power > 0
            and mechanics.category in {"physical", "special"}
            and not mechanics.effect_flags & EXCLUDED_FLAGS
            and catalog.move_effect(ref) not in {"THRASH_PETAL_DANCE_EFFECT", "RAGE_EFFECT"}
        ):
            result.append(move)
    return tuple(result)


def _move_rows(catalog, ids: tuple[int, ...] | list[int]) -> list[dict]:
    return [
        {
            "move_ref": pokemon_red_move_ref(move),
            "pp": catalog.resolve_move(pokemon_red_move_ref(move)).max_pp,
        }
        for move in ids
    ]


def _family_score(
    catalog, actor: int, enemy: int, move_ids: tuple[int, ...], *, stat_ratio: float
) -> float:
    actor_types = catalog.resolve_species(pokemon_red_species_ref(actor)).types
    enemy_types = catalog.resolve_species(pokemon_red_species_ref(enemy)).types
    mechanics = [catalog.resolve_move(pokemon_red_move_ref(m)) for m in move_ids]
    effects = [catalog.type_effectiveness(m.type_name, enemy_types) for m in mechanics]
    categories = {m.category for m in mechanics}
    stabs = {m.type_name in actor_types for m in mechanics}
    accuracies = {m.accuracy for m in mechanics}
    return (
        4 * (len(categories) == 2)
        + 2 * len(set(effects))
        + 4 * (0 in effects)
        + 3 * (max(effects) > 1)
        + 2 * (min(effects) < 1)
        + 2 * (len(stabs) == 2)
        + min(3, len(accuracies))
        + 5 * any(m.priority for m in mechanics)
        + (stat_ratio < 0.8 or stat_ratio > 1.25)
    )


def _prior_pairs() -> set[tuple[int, int]]:
    plan = json.loads(DIAGNOSTIC.read_bytes())
    return {
        tuple(
            sorted(
                (
                    int(r["practice"]["actor_species_ref"][-3:]),
                    int(r["practice"]["opponent_species_ref"][-3:]),
                )
            )
        )
        for r in plan["recipes"]
    }


def matchup_families(cartridge, catalog) -> tuple[list[dict], set[tuple[int, int]]]:
    rng = random.Random(SEEDS["recipe"])
    used = _prior_pairs()
    families = []
    for index in range(48):
        level = (31, 37, 43, 49)[index % 4]
        opponent_level = level + (-3, 0, 3)[index % 3]
        pool = {
            s: legal_damage(cartridge, catalog, s, level)
            for s in cartridge.species_ids
            if s not in EXCLUDED_SPECIES
        }
        actors = sorted(s for s, moves in pool.items() if len(moves) >= 4)
        enemies = sorted(
            s
            for s in cartridge.species_ids
            if s not in EXCLUDED_SPECIES
            and len(legal_damage(cartridge, catalog, s, opponent_level)) >= 2
        )
        if not actors or not enemies:
            raise ValueError("input-only incompatibility: no eligible actors or opponents")
        best = None
        for _ in range(1200):
            actor = rng.choice(actors)
            enemy = rng.choice(enemies)
            pair = tuple(sorted((actor, enemy)))
            if actor == enemy or pair in used:
                continue
            moves = tuple(rng.sample(pool[actor], 4))
            own = cartridge.species(actor).neutral_stats(level)
            foe = cartridge.species(enemy).trainer_stats(opponent_level)
            ratio = own.attack / foe.defense
            score = _family_score(catalog, actor, enemy, moves, stat_ratio=ratio)
            # Fixed input-only jitter avoids a narrow repeated roster.
            score += rng.random() * 1.5
            if best is None or score > best[0]:
                best = (score, actor, enemy, moves)
        if best is None:
            raise ValueError("input-only incompatibility: fewer than 48 disjoint families")
        _, actor, enemy, moves = best
        used.add(tuple(sorted((actor, enemy))))
        own = cartridge.species(actor)
        foe = cartridge.species(enemy)
        own_hp = own.neutral_stats(level).max_hp
        foe_hp = foe.trainer_stats(opponent_level).max_hp
        practice = {
            "partition": "train",
            "battle_kind": "trainer",
            "actor_species_ref": pokemon_red_species_ref(actor),
            "actor_national_number": own.national_number,
            "actor_level": level,
            "actor_moves": _move_rows(catalog, moves),
            "opponent_species_ref": pokemon_red_species_ref(enemy),
            "opponent_national_number": foe.national_number,
            "opponent_level": opponent_level,
            "opponent_moves": _move_rows(
                catalog,
                tuple(rng.sample(legal_damage(cartridge, catalog, enemy, opponent_level), 2)),
            ),
            "opponent_party_count": 1,
        }
        role = "fit" if index < 32 else "holdout"
        contexts = (
            ("neutral", own_hp, foe_hp, StatusPracticeConditions()),
            (
                "burn",
                max(1, own_hp * 70 // 100),
                foe_hp,
                StatusPracticeConditions(player_status="burn"),
            ),
            (
                "stage",
                own_hp,
                max(1, foe_hp * 45 // 100),
                StatusPracticeConditions(player_accuracy=-2, opponent_status="paralysis"),
            ),
        )
        families.append(
            {
                "id": f"family-{index:02d}",
                "role": role,
                "actor_species_id": actor,
                "opponent_species_id": enemy,
                "moves": list(moves),
                "level": level,
                "source_index": index % 4,
                "contexts": [
                    {
                        "id": f"family-{index:02d}-{name}",
                        "family_id": f"family-{index:02d}",
                        "role": role,
                        "source_index": index % 4,
                        "conditions": asdict(conditions),
                        "practice": {
                            **practice,
                            "actor_hp": actor_hit_points,
                            "opponent_hp": foe_hit_points,
                        },
                    }
                    for name, actor_hit_points, foe_hit_points, conditions in contexts
                ],
            }
        )
    return families, used


def compact_rows(vectors) -> tuple[tuple[float, ...], ...]:
    rows = tuple(tuple(row[index] for index in FEATURE_INDICES) for row in vectors)
    if not rows or any(any(not math.isfinite(x) or not -1 <= x <= 1 for x in row) for row in rows):
        raise ValueError("compact feature range or finiteness differs")
    return rows


def ordered_legal_vectors(projected, legal_slots: tuple[int, ...]):
    if tuple(projected.candidate_slots) != (1, 2, 3, 4) or legal_slots != (1, 2, 3, 4):
        raise ValueError("four legal slots or slot order differs")
    return tuple(
        tuple(projected.candidate_vectors[projected.candidate_slots.index(slot)])
        for slot in legal_slots
    )


def validate_partitions(families: list[dict]) -> None:
    if len(families) != 48 or [f["role"] for f in families] != ["fit"] * 32 + ["holdout"] * 16:
        raise ValueError("fit/holdout split differs")
    pairs = [tuple(sorted((f["actor_species_id"], f["opponent_species_id"]))) for f in families]
    if len(set(pairs)) != 48:
        raise ValueError("unordered matchup family crosses split or duplicates")
    if any(
        len(f["contexts"]) != 3 or any(c["role"] != f["role"] for c in f["contexts"])
        for f in families
    ):
        raise ValueError("context family partition differs")


def assert_untouched_components(admitted, composed) -> None:
    for field in ("move", "control", "switch"):
        if getattr(composed, field).to_dict() != getattr(admitted, field).to_dict():
            raise ValueError(f"untouched {field} component changed")


def embed(head: TrainerHeadModel) -> TrainerHeadModel:
    if head.feature_names != FEATURES or head.schema_id != MOVE_SCHEMA_ID:
        raise ValueError("compact head schema differs")
    weights = np.zeros((len(MOVE_FEATURE_NAMES), head.weights1.shape[1]), dtype=np.float64)
    weights[list(FEATURE_INDICES)] = head.weights1
    return TrainerHeadModel(
        MOVE_SCHEMA_ID,
        MOVE_FEATURE_NAMES,
        weights,
        head.bias1,
        head.weights2,
        head.training_seed,
        head.training_objective,
    )


def assert_embedding(compact: TrainerHeadModel, full: TrainerHeadModel, vectors) -> None:
    compact_input = compact_rows(vectors)
    for method in ("scores", "probabilities"):
        a = getattr(compact, method)(compact_input)
        b = getattr(full, method)(vectors)
        if not np.allclose(a, b, rtol=0, atol=1e-10):
            raise ValueError(f"{method} embedding mismatch")
    if compact.predict_index(compact_input) != full.predict_index(vectors):
        raise ValueError("embedded choice differs")
    if any(
        np.any(full.weights1[i]) for i in range(len(MOVE_FEATURE_NAMES)) if i not in FEATURE_INDICES
    ):
        raise ValueError("excluded model column is nonzero")


def _team_moves(
    cartridge, catalog, species: int, level: int, rng: random.Random, *, status: bool
) -> list[dict]:
    damage = legal_damage(cartridge, catalog, species, level)
    if len(damage) < 2:
        raise ValueError("team member lacks two supported attacks")
    chosen = list(rng.sample(damage, min(3, len(damage))))
    if status:
        supported = {79, 86, 77, 109, 105, 156, 115, 28, 50}
        status_moves = [
            m
            for m in cartridge.species(species).teachable_moves_at_level(level)
            if m in supported and m not in chosen
        ]
        if status_moves:
            chosen.append(rng.choice(status_moves))
    return _move_rows(catalog, chosen[:4])


def team_recipes(cartridge, catalog, used_pairs: set[tuple[int, int]]) -> list[dict]:
    rng = random.Random(SEEDS["recipe"] + 1)
    eligible = sorted(
        s
        for s in cartridge.species_ids
        if s not in EXCLUDED_SPECIES and len(legal_damage(cartridge, catalog, s, 41)) >= 2
    )
    if len(eligible) < 20:
        raise ValueError("input-only incompatibility: team species inventory")
    result = []
    team_families = set()
    for index in range(24):
        own_count, foe_count = ((3, 3), (3, 6), (6, 6))[index // 8]
        for _ in range(10000):
            own = tuple(rng.sample(eligible, own_count))
            foe = tuple(rng.sample([s for s in eligible if s not in own], foe_count))
            signature = (tuple(sorted(own)), tuple(sorted(foe)))
            if signature in team_families or any(
                tuple(sorted((a, b))) in used_pairs for a in own for b in foe
            ):
                continue
            break
        else:
            raise ValueError("input-only incompatibility: 24 disjoint team rosters")
        team_families.add(signature)
        level = (37, 41, 45, 49)[index % 4]
        lead_hp = cartridge.species(own[0]).neutral_stats(level).max_hp
        status_available = False

        def reserve(species, slot, actor, level=level):
            nonlocal status_available
            moves = _team_moves(cartridge, catalog, species, level, rng, status=actor and slot == 2)
            status_available |= actor and any(
                catalog.resolve_move(m["move_ref"]).category == "status" for m in moves
            )
            return {
                "party_slot": slot,
                "species_ref": pokemon_red_species_ref(species),
                "national_number": cartridge.species(species).national_number,
                "level": level,
                "moves": moves,
            }

        actor_moves = _team_moves(cartridge, catalog, own[0], level, rng, status=True)
        status_available |= any(
            catalog.resolve_move(m["move_ref"]).category == "status" for m in actor_moves
        )
        practice = {
            "partition": "train",
            "battle_kind": "trainer",
            "actor_species_ref": pokemon_red_species_ref(own[0]),
            "actor_national_number": cartridge.species(own[0]).national_number,
            "actor_level": level,
            "actor_hp": 1 if index % 3 == 0 else lead_hp,
            "actor_moves": actor_moves,
            "party_reserves": [reserve(s, slot, True) for slot, s in enumerate(own[1:], 2)],
            "opponent_species_ref": pokemon_red_species_ref(foe[0]),
            "opponent_national_number": cartridge.species(foe[0]).national_number,
            "opponent_level": level,
            "opponent_hp": cartridge.species(foe[0]).trainer_stats(level).max_hp,
            "opponent_moves": _team_moves(cartridge, catalog, foe[0], level, rng, status=False),
            "opponent_reserves": [reserve(s, slot, False) for slot, s in enumerate(foe[1:], 2)],
            "opponent_party_count": foe_count,
        }
        result.append(
            {
                "id": f"team-{index:02d}",
                "role": "composition",
                "source_index": index % 4,
                "own_species": own,
                "opponent_species": foe,
                "roster": f"{own_count}v{foe_count}",
                "forced_switch_probe": index % 3 == 0,
                "status_available": status_available,
                "conditions": asdict(StatusPracticeConditions()),
                "practice": practice,
            }
        )
    return result


def coverage(families: list[dict], teams: list[dict], catalog, cartridge) -> dict:
    by_split = {}
    for role in ("fit", "holdout"):
        subset = [f for f in families if f["role"] == role]
        counts = Counter()
        actor_species, foe_species = set(), set()
        for family in subset:
            actor, enemy = family["actor_species_id"], family["opponent_species_id"]
            actor_species.add(actor)
            foe_species.add(enemy)
            ratio = cartridge.species(actor).base_stats[1] / cartridge.species(enemy).base_stats[2]
            ratio_bin = "low" if ratio < 0.8 else "high" if ratio > 1.25 else "middle"
            counts[f"stat_ratio_{ratio_bin}"] += 1
            actor_types = catalog.resolve_species(pokemon_red_species_ref(actor)).types
            enemy_types = catalog.resolve_species(pokemon_red_species_ref(enemy)).types
            counts[f"level_{family['level']}"] += 1
            for move in family["moves"]:
                m = catalog.resolve_move(pokemon_red_move_ref(move))
                effect = catalog.type_effectiveness(m.type_name, enemy_types)
                counts[m.category] += 1
                counts[
                    "immune"
                    if effect == 0
                    else "unfavorable"
                    if effect < 1
                    else "favorable"
                    if effect > 1
                    else "neutral"
                ] += 1
                counts["stab" if m.type_name in actor_types else "nonstab"] += 1
                counts["accuracy_below_one" if m.accuracy < 1 else "accuracy_one"] += 1
                counts["priority" if m.priority else "normal_priority"] += 1
        by_split[role] = {
            "families": len(subset),
            "configurations": len(subset) * 3,
            "root_counts": dict(Counter(f["source_index"] for f in subset)),
            "counts": dict(sorted(counts.items())),
            "actor_species": sorted(actor_species),
            "opponent_species": sorted(foe_species),
        }
    return {
        "splits": by_split,
        "overlapping_individual_species": sorted(
            (set(by_split["fit"]["actor_species"]) | set(by_split["fit"]["opponent_species"]))
            & (
                set(by_split["holdout"]["actor_species"])
                | set(by_split["holdout"]["opponent_species"])
            )
        ),
        "composition_rosters": dict(Counter(t["roster"] for t in teams)),
        "status_available_teams": sum(t["status_available"] for t in teams),
        "forced_switch_probe_teams": sum(t["forced_switch_probe"] for t in teams),
    }


def freeze(*, inspect_only: bool = False) -> dict:
    deadline_check()
    cartridge, catalog, sources, k, admitted = inputs()
    families, used_pairs = matchup_families(cartridge, catalog)
    validate_partitions(families)
    teams = team_recipes(cartridge, catalog, used_pairs)
    for row in [c for f in families for c in f["contexts"]] + teams:
        row["root"] = sources[row["source_index"]][1]["source_id"]
    report = coverage(families, teams, catalog, cartridge)
    from pokemon_red_completion.battle_practice_factory import BattlePracticeSpec

    for row in [c for f in families for c in f["contexts"]] + teams:
        source, receipt = sources[row["source_index"]]
        from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture

        capture = open_battle_scenario_capture(
            source / "source.state", source / "source.state.json"
        )
        BattlePracticeSpec.from_dict(
            {
                **row["practice"],
                "root_lineage_id": receipt["source_id"],
                "source_state_sha256": capture.manifest.state_sha256,
            }
        )
        StatusPracticeConditions(**row["conditions"])
    fingerprints = [sha_recipe(c) for f in families for c in f["contexts"]]
    if len(set(fingerprints)) != 144:
        raise ValueError("duplicate configuration fingerprint")
    if report["composition_rosters"] != {"3v3": 8, "3v6": 8, "6v6": 8}:
        raise ValueError("composition roster counts differ")
    if any(
        report["splits"][role]["counts"].get(key, 0) == 0
        for role in ("fit", "holdout")
        for key in (
            "physical",
            "special",
            "favorable",
            "unfavorable",
            "immune",
            "accuracy_below_one",
            "stab",
            "nonstab",
        )
    ):
        raise ValueError("input-only incompatibility: predeclared coverage absent")
    if inspect_only:
        return report
    if OUTPUT.exists():
        raise ValueError("output identity already exists")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("source must be committed before freeze")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    source_binding = {
        str(p.relative_to(ROOT)): sha(p)
        for p in (
            ROOT / "scripts/run_red_damage_proposal_overnight.py",
            ROOT / "scripts/run_red_status_curriculum.py",
            ROOT / "src/pokemon_red_completion/red_trainer_practice_head.py",
            ROOT / "src/pokemon_red_completion/red_trainer_practice_features.py",
        )
    }
    order_rng = random.Random(SEEDS["paired_order"])
    orders = [0] * 36 + [1] * 36
    order_rng.shuffle(orders)
    composition_orders = {
        f"{team['id']}:offset-{offset}": ("admitted", "candidate")
        if orders[index] == 0
        else ("candidate", "admitted")
        for index, (team, offset) in enumerate(
            (team, offset) for team in teams for offset in OFFSETS
        )
    }
    plan = {
        "schema": "pokemon.red.damage-proposal-overnight.v1",
        "created_at_utc": utc_now(),
        "source_commit": commit,
        "source_hashes": source_binding,
        "seeds": SEEDS,
        "feature_names": FEATURES,
        "feature_indices": FEATURE_INDICES,
        "split": {
            "fit_families": 32,
            "holdout_families": 16,
            "fit_configurations": 96,
            "holdout_configurations": 48,
            "upstream_train_roots": 4,
            "new_independent_roots": 0,
        },
        "families": families,
        "composition_teams": teams,
        "composition_orders": composition_orders,
        "coverage": report,
        "recipe_fingerprints": fingerprints,
        "baselines": {"K": lab.common._binding(K), "admitted": lab.common._binding(ADMITTED)},
        "inputs": {
            "rom": lab.common._binding(ROM),
            "diagnostic": lab.common._binding(DIAGNOSTIC),
            "sources": [lab.common._binding(p / "source.state.json") for p, _ in sources],
        },
        "outputs": {
            "private": str(OUTPUT),
            "workspace": str(WORKSPACE),
            "train_targets": str(OUTPUT / "train-targets.json"),
            "candidate": str(OUTPUT / "candidate-model.json"),
            "holdout": str(OUTPUT / "HOLDOUT_RESULT.json"),
            "composition": str(OUTPUT / "COMPOSITION_RESULT.json"),
        },
        "budgets": {
            "maximum_native_branches": 1728,
            "train_branches": 1152,
            "holdout_branches": 576,
            "composition_episodes": 144,
            "offsets": OFFSETS,
            "player_turns_per_damage_branch": 1,
            "episode_decisions": 80,
            "episode_frames": 120000,
            "episode_controller_actions": 5000,
            "episode_wall_seconds": 45,
            "composition_wall_seconds": 4500,
            "original_deadline_utc": json.loads(STATE.read_bytes())["deadline_at_utc"],
            "native_dispatch_cutoff_seconds": 27000,
        },
        "fit": {
            "attempts": 1,
            "hidden_units": 16,
            "epochs": 600,
            "learning_rate": 0.03,
            "seed": SEEDS["fit"],
            "objective": "expected_regret",
            "warm_start": False,
        },
        "holdout_gate": {
            "integrity_failures_max": 0,
            "measured_configurations": 48,
            "relative_mean_regret_improvement_min": 0.20,
            "absolute_mean_regret_improvement_min": 0.01,
            "coverage_slice_regression_max": 0.03,
            "family_regression_max": 0.15,
            "bootstrap_family_resamples": 2000,
        },
        "composition_gate": {
            "all_pairs_required": True,
            "integrity_failures_max": 0,
            "censored_increase_max": 0,
            "loss_increase_max": 0,
            "win_decrease_max": 0,
            "terminal_hp_strict_gain_min": 0.02,
            "turn_or_pp_common_win_increase_max_fraction": 0.10,
        },
        "retention_gate": {
            "supported_group_mean_regret_regression_max": 0.02,
            "mixed_units_separate": True,
        },
        "coverage_slices": (
            "level",
            "category",
            "effect",
            "accuracy",
            "stab",
            "context",
            "player_status",
            "actor_hp",
            "opponent_hp",
            "stat_ratio",
        ),
        "supported_domain": (
            "instantaneous single-hit ordinary damage with secondary status and priority"
        ),
        "excluded_mechanics": sorted(EXCLUDED_FLAGS),
        "forced_training_branches": True,
        "final_player_action": False,
        "promotions": 0,
    }
    OUTPUT.mkdir(mode=0o700)
    write_once(OUTPUT / "PLAN.json", plan)
    write_once(
        OUTPUT / "baseline-inventory.json",
        {
            "source_commit": commit,
            "source_hashes": source_binding,
            "baseline_hashes": {k: v["sha256"] for k, v in plan["baselines"].items()},
            "rom_sha256": sha(ROM),
            "source_roots": [r["source_id"] for _, r in sources],
            "protected_story_sha256": sha(
                PRIVATE
                / "goal-manager-v1/model141-earned-story-campaign-20260921-v1/stage-328/final.state"
            ),
            "protected_collection_sha256": sha(
                PRIVATE
                / "goal-manager-v1/model141-integrated-play-20260921-v1/step-006/terminal.state"
            ),
        },
    )
    state_update(
        unit="freeze",
        plan_sha256=sha(OUTPUT / "PLAN.json"),
        output=str(OUTPUT),
        phase="collect_train",
    )
    return report


def sha_recipe(row: dict) -> str:
    content = {"practice": row["practice"], "conditions": row["conditions"]}
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_plan() -> dict:
    plan = json.loads((OUTPUT / "PLAN.json").read_bytes())
    state = json.loads(STATE.read_bytes())
    if sha(OUTPUT / "PLAN.json") != state.get("plan_sha256"):
        raise ValueError("frozen plan hash differs")
    if (
        plan["source_commit"]
        != subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    ):
        raise ValueError("source commit differs from freeze")
    for relative, digest in plan["source_hashes"].items():
        if sha(ROOT / relative) != digest:
            raise ValueError(f"frozen source differs: {relative}")
    return plan


def _capture(args, row: dict, index: int, sources, cartridge, commit: str):
    directory = OUTPUT / row["id"]
    state_path = directory / "capture.state"
    manifest = directory / "capture.state.json"
    if state_path.exists() or manifest.exists() or directory.exists():
        if not (state_path.exists() and manifest.exists() and (directory / "setup.json").exists()):
            raise ValueError(f"interrupted materialization retained: {row['id']}")
        setup = json.loads((directory / "setup.json").read_bytes())
        if sha_recipe(setup["recipe"]) != sha_recipe(row):
            raise ValueError("materialized recipe differs from freeze")
        from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture

        return open_battle_scenario_capture(state_path, manifest)
    deadline_check(native=True)
    state_update(
        active_process={
            "unit": f"materialize:{row['id']}",
            "pid": os.getpid(),
            "started_at_utc": utc_now(),
        }
    )
    try:
        capture = lab.materialize(args, row, index, sources, cartridge, commit)
    except Exception as error:
        if directory.exists():
            write_once(
                directory / "materialization-failure.json",
                {"type": type(error).__name__, "error": str(error), "at_utc": utc_now()},
            )
        state_update(active_process=None, phase="failed")
        raise
    state_update(unit=f"materialize:{row['id']}", active_process=None)
    return capture


def _vectors(capture, cartridge) -> tuple[tuple[tuple[float, ...], ...], tuple[int, ...]]:
    with lab.PyBoyAdapter(ROM, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(capture.state_bytes)
        reader = lab.PokemonRedStateReader(emulator)
        encoder = lab.PokemonRedObservationEncoder(reader, True, cartridge.public_base_stats, True)
        raw = reader.read()
        prepared = lab.prepare_red_battle_scenario(encoder, raw, allow_status_moves=True)
        obs = encoder.snapshot_from_raw(raw).to_dict()
        projected = project_trainer_move_features(obs, prepared.features)
        slots = tuple(
            slot + 1
            for slot, legal in zip(
                prepared.features.slot_indices, prepared.features.legal_mask, strict=True
            )
            if legal
        )
        vectors = ordered_legal_vectors(projected, slots)
        if any(len(row) != 125 for row in vectors):
            raise ValueError("125-input move schema differs")
        lead = obs["features"]["party"]["lead"]
        move_rows = lead["moves"]
        if any(move_rows[s - 1]["pp"] <= 0 for s in slots):
            raise ValueError("positive PP inventory differs")
        compact_rows(vectors)
        return vectors, slots


def _branch(args, capture, model, cartridge, row: dict, offset: int, slot: int) -> dict:
    unit = f"{row['id']}:offset-{offset}:slot-{slot}"
    directory = OUTPUT / row["id"] / f"branch-{offset}-{slot}"
    if directory.exists():
        if (directory / "episode.json").exists() and (directory / "events").is_dir():
            if unit not in json.loads(STATE.read_bytes())["completed_units"]:
                raise ValueError(f"unclaimed existing branch {unit}")
            lab.verify_trainer_practice_event_log(directory / "events")
            episode = json.loads((directory / "episode.json").read_bytes())
        else:
            raise ValueError(f"interrupted or failed branch cannot replay: {unit}")
    else:
        deadline_check(native=True)
        state_update(active_process={"unit": unit, "pid": os.getpid(), "started_at_utc": utc_now()})
        try:
            episode = lab.play(
                args,
                capture,
                model,
                directory,
                cartridge,
                first_slot=slot,
                offset=offset,
                horizon=1,
            )
        except Exception:
            state_update(active_process=None, phase="failed")
            raise
        state_update(unit=unit, active_process=None)
    decisions = episode["decisions"]
    attacks = [d for d in decisions if d["kind"] == "attack"]
    if len(attacks) != 1 or attacks[0]["move_slot"] != slot:
        raise ValueError(f"forced attack did not yield one matching decision: {unit}")
    d = attacks[0]
    max_hp = d["observation"]["features"]["battle"]["opponent_max_hp"]
    if type(max_hp) is not int or max_hp <= 0:
        raise ValueError("opponent maximum HP unavailable")
    damage = (d["opponent_hp_before"] - d["opponent_hp_after"]) / max_hp
    if not 0 <= damage <= 1:
        raise ValueError("measured damage fraction differs")
    return {
        "unit": unit,
        "slot": slot,
        "offset": offset,
        "damage_fraction": damage,
        "opponent_max_hp": max_hp,
        "opponent_hp_before": d["opponent_hp_before"],
        "opponent_hp_after": d["opponent_hp_after"],
        "metrics": episode["metrics"],
        "stop_reason": episode["stop_reason"],
        "utility": lab.outcome_value(episode),
        "player_hp_before": d["state_before"]["party_hp"],
        "player_hp_after": d["state_after"]["party_hp"],
        "player_status_before": d["observation"]["features"]["battle"].get("player_status"),
        "episode_sha256": sha(directory / "episode.json"),
    }


def _collect_role(role: str) -> list[dict]:
    plan = load_plan()
    cartridge, _, sources, k, _ = inputs()
    args = argparse.Namespace(output=OUTPUT, rom=ROM)
    results = []
    families = [f for f in plan["families"] if f["role"] == role]
    for family in families:
        for row in family["contexts"]:
            deadline_check()
            target_path = OUTPUT / row["id"] / "target.json"
            if target_path.exists():
                target = json.loads(target_path.read_bytes())
                if target["role"] != role or target["recipe_sha256"] != sha_recipe(row):
                    raise ValueError("existing target differs from frozen recipe")
                results.append(target)
                continue
            capture = _capture(
                args, row, row["source_index"], sources, cartridge, plan["source_commit"]
            )
            vectors, slots = _vectors(capture, cartridge)
            branches = []
            for offset in OFFSETS:
                for slot in slots:
                    branches.append(_branch(args, capture, k, cartridge, row, offset, slot))
            values = tuple(
                fmean(b["damage_fraction"] for b in branches if b["slot"] == s) for s in slots
            )
            target = {
                "schema": "pokemon.red.damage-outcome-target.v1",
                "id": row["id"],
                "family_id": row["family_id"],
                "role": role,
                "root": capture.manifest.root_lineage_id,
                "capture_sha256": capture.manifest.state_sha256,
                "recipe_sha256": sha_recipe(row),
                "slots": slots,
                "vectors": vectors,
                "mean_damage": values,
                "branches": branches,
                "forced_training_actions": True,
                "learned_battle_actions": 0,
            }
            write_once(target_path, target)
            state_update(unit=f"target:{row['id']}")
            results.append(target)
            print(
                json.dumps({"target": row["id"], "role": role, "mean_damage": values}), flush=True
            )
    expected = 96 if role == "fit" else 48
    if len(results) != expected or any(len(r["branches"]) != 12 for r in results):
        raise ValueError("incomplete target inventory")
    return results


def collect_train_and_fit() -> dict:
    deadline_check()
    plan = load_plan()
    if (OUTPUT / "candidate-model.json").exists():
        raise ValueError("candidate already frozen; no second fit")
    rows = _collect_role("fit")
    if not (OUTPUT / "train-targets.json").exists():
        write_once(OUTPUT / "train-targets.json", rows)
        state_update(unit="train-targets", dataset_sha256=sha(OUTPUT / "train-targets.json"))
    else:
        if json.loads((OUTPUT / "train-targets.json").read_bytes()) != rows:
            raise ValueError("train target inventory differs")
    if json.loads(STATE.read_bytes())["fit_attempts"] != 0:
        raise ValueError("fit already attempted")
    examples = tuple(
        TrainerHeadExample(
            compact_rows(row["vectors"]),
            tied_best_indices(tuple(row["mean_damage"])),
            mean_returns=tuple(row["mean_damage"]),
        )
        for row in rows
    )
    state_update(fit_attempts=1, phase="fitting")
    try:
        compact = TrainerHeadModel.fit(
            schema_id=MOVE_SCHEMA_ID,
            feature_names=FEATURES,
            examples=examples,
            seed=SEEDS["fit"],
            hidden_units=16,
            epochs=600,
            learning_rate=0.03,
            initial_model=None,
            training_objective="expected_regret",
        )
        full = embed(compact)
        for row in rows:
            assert_embedding(compact, full, row["vectors"])
        restored = TrainerHeadModel.from_dict(
            full.to_dict(), schema_id=MOVE_SCHEMA_ID, feature_names=MOVE_FEATURE_NAMES
        )
        if restored.to_dict() != full.to_dict():
            raise ValueError("model serialization changes parameter values")
        _, _, _, _, admitted = inputs()
        composed = replace(admitted, damage_reference=full)
        assert_untouched_components(admitted, composed)
        write_once(OUTPUT / "compact-head.json", compact.to_dict())
        write_once(OUTPUT / "candidate-model.json", composed.to_dict())
        candidate_hash = sha(OUTPUT / "candidate-model.json")
        write_once(
            OUTPUT / "FIT_RECEIPT.json",
            {
                "fit_attempts": 1,
                "fit_completed": 1,
                "examples": len(examples),
                "train_dataset_sha256": sha(OUTPUT / "train-targets.json"),
                "compact_sha256": sha(OUTPUT / "compact-head.json"),
                "candidate_sha256": candidate_hash,
                "optimizer": plan["fit"],
                "embedded_match_absolute_tolerance": 1e-10,
                "serialization_exact": True,
                "untouched_components_exact": True,
                "frozen_before_holdout": True,
            },
        )
        state_update(unit="fit", fit_completed=1, candidate_sha256=candidate_hash, phase="holdout")
        return {"candidate_sha256": candidate_hash, "examples": len(examples)}
    except Exception as error:
        write_once(
            OUTPUT / "FIT_FAILURE.json",
            {"type": type(error).__name__, "error": str(error), "at_utc": utc_now()},
        )
        state_update(phase="failed")
        raise


def _slice_tags(row: dict, family: dict, cartridge, catalog) -> tuple[str, ...]:
    actor = family["actor_species_id"]
    enemy = family["opponent_species_id"]
    own_types = catalog.resolve_species(pokemon_red_species_ref(actor)).types
    foe_types = catalog.resolve_species(pokemon_red_species_ref(enemy)).types
    definitions = [catalog.resolve_move(pokemon_red_move_ref(m)) for m in family["moves"]]
    effects = [catalog.type_effectiveness(m.type_name, foe_types) for m in definitions]
    own_stats = cartridge.species(actor)
    foe_stats = cartridge.species(enemy)
    # Public base-stat ratio is available before outcomes and independent of DVs.
    ratio = own_stats.base_stats[1] / max(1, foe_stats.base_stats[2])
    context = row["id"].rsplit("-", 1)[1]
    tags = [
        f"level:{family['level']}",
        f"context:{context}",
        f"player_status:{row['conditions']['player_status']}",
        f"actor_hp:{'impaired' if context == 'burn' else 'full'}",
        f"opponent_hp:{'partial' if context == 'stage' else 'full'}",
        f"stat_ratio:{'low' if ratio < 0.8 else 'high' if ratio > 1.25 else 'middle'}",
    ]
    tags += [
        f"category:{category}"
        for category in ("physical", "special")
        if any(m.category == category for m in definitions)
    ]
    tags += [
        f"effect:{name}"
        for name, present in (
            ("immune", 0 in effects),
            ("unfavorable", any(0 < x < 1 for x in effects)),
            ("neutral", 1 in effects),
            ("favorable", any(x > 1 for x in effects)),
        )
        if present
    ]
    tags += [
        f"accuracy:{name}"
        for name, present in (
            ("imperfect", any(m.accuracy < 1 for m in definitions)),
            ("perfect", any(m.accuracy == 1 for m in definitions)),
        )
        if present
    ]
    tags += [
        f"stab:{name}"
        for name, present in (
            ("present", any(m.type_name in own_types for m in definitions)),
            ("absent", any(m.type_name not in own_types for m in definitions)),
        )
        if present
    ]
    return tuple(tags)


def _bootstrap_family_interval(configurations: list[dict]) -> list[float]:
    families = defaultdict(list)
    for item in configurations:
        families[item["family_id"]].append(item)
    if len(families) != 16 or any(len(v) != 3 for v in families.values()):
        raise ValueError("bootstrap family inventory differs")
    effects = [
        fmean(row["baseline_regret"] - row["candidate_regret"] for row in rows)
        for _, rows in sorted(families.items())
    ]
    rng = random.Random(SEEDS["bootstrap"])
    replicates = sorted(fmean(rng.choices(effects, k=len(effects))) for _ in range(2000))
    return [replicates[49], replicates[1949]]


def score_holdout(targets: list[dict], plan: dict, k, candidate) -> dict:
    cartridge, catalog, _, _, _ = inputs()
    family_by_id = {f["id"]: f for f in plan["families"]}
    configurations = []
    for row in targets:
        family = family_by_id[row["family_id"]]
        recipe = next(c for c in family["contexts"] if c["id"] == row["id"])
        vectors = tuple(tuple(v) for v in row["vectors"])
        values = tuple(row["mean_damage"])
        baseline_index = k.move.predict_index(vectors)
        candidate_index = candidate.damage_reference.predict_index(vectors)
        optimum = max(values)
        configurations.append(
            {
                "id": row["id"],
                "family_id": row["family_id"],
                "root": row["root"],
                "baseline_index": baseline_index,
                "candidate_index": candidate_index,
                "baseline_slot": row["slots"][baseline_index],
                "candidate_slot": row["slots"][candidate_index],
                "mean_damage": values,
                "baseline_regret": optimum - values[baseline_index],
                "candidate_regret": optimum - values[candidate_index],
                "best_indices": tied_best_indices(values),
                "tags": _slice_tags(recipe, family, cartridge, catalog),
                "baseline_scores": k.move.scores(vectors).tolist(),
                "candidate_scores": candidate.damage_reference.scores(vectors).tolist(),
                "target_sha256": sha(OUTPUT / row["id"] / "target.json"),
            }
        )
    baseline = [row["baseline_regret"] for row in configurations]
    fitted = [row["candidate_regret"] for row in configurations]
    by_family = defaultdict(list)
    for row in configurations:
        by_family[row["family_id"]].append(row)
    families = [
        {
            "id": family,
            "baseline_regret": fmean(r["baseline_regret"] for r in rows),
            "candidate_regret": fmean(r["candidate_regret"] for r in rows),
        }
        for family, rows in sorted(by_family.items())
    ]
    slices = {}
    for tag in sorted({tag for row in configurations for tag in row["tags"]}):
        rows = [row for row in configurations if tag in row["tags"]]
        slices[tag] = {
            "configurations": len(rows),
            "families": len({row["family_id"] for row in rows}),
            "baseline_regret": fmean(r["baseline_regret"] for r in rows),
            "candidate_regret": fmean(r["candidate_regret"] for r in rows),
        }
        slices[tag]["regression"] = slices[tag]["candidate_regret"] - slices[tag]["baseline_regret"]
    improvement = fmean(baseline) - fmean(fitted)
    failures = []
    if len(configurations) != 48:
        failures.append("held_configuration_count")
    if any(
        b["metrics"]["invalid_action_failures"] for target in targets for b in target["branches"]
    ):
        failures.append("illegal_action")
    if fmean(baseline) <= 0 or improvement < 0.01 or improvement < 0.20 * fmean(baseline):
        failures.append("mean_regret_improvement")
    if any(v["regression"] > 0.03 for v in slices.values()):
        failures.append("coverage_slice_regression")
    if any(f["candidate_regret"] - f["baseline_regret"] > 0.15 for f in families):
        failures.append("family_regression")
    return {
        "schema": "pokemon.red.damage-holdout-result.v1",
        "plan_sha256": sha(OUTPUT / "PLAN.json"),
        "candidate_sha256": sha(OUTPUT / "candidate-model.json"),
        "baseline_K_sha256": sha(K),
        "dataset_sha256": sha(OUTPUT / "holdout-targets.json"),
        "upstream_roots": 4,
        "new_independent_roots": 0,
        "configurations": configurations,
        "families": families,
        "coverage_slices": slices,
        "summary": {
            "configurations": len(configurations),
            "families": len(families),
            "native_branches": sum(len(t["branches"]) for t in targets),
            "baseline_mean_regret": fmean(baseline),
            "candidate_mean_regret": fmean(fitted),
            "baseline_median_regret": median(baseline),
            "candidate_median_regret": median(fitted),
            "baseline_worst_regret": max(baseline),
            "candidate_worst_regret": max(fitted),
            "absolute_mean_improvement": improvement,
            "relative_mean_improvement": improvement / fmean(baseline) if fmean(baseline) else None,
            "baseline_best_count": sum(
                r["baseline_index"] in r["best_indices"] for r in configurations
            ),
            "candidate_best_count": sum(
                r["candidate_index"] in r["best_indices"] for r in configurations
            ),
            "changed_choices": sum(
                r["baseline_index"] != r["candidate_index"] for r in configurations
            ),
            "paired_candidate_better": sum(
                r["candidate_regret"] < r["baseline_regret"] for r in configurations
            ),
            "paired_candidate_worse": sum(
                r["candidate_regret"] > r["baseline_regret"] for r in configurations
            ),
            "paired_ties": sum(
                r["candidate_regret"] == r["baseline_regret"] for r in configurations
            ),
            "family_cluster_bootstrap_absolute_improvement_95pct": _bootstrap_family_interval(
                configurations
            ),
            "bootstrap_conditional_on_four_reused_TRAIN_origins": True,
        },
        "integrity_or_gate_failures": failures,
        "pass_to_composition": not failures,
    }


def collect_and_score_holdout() -> dict:
    deadline_check()
    plan = load_plan()
    state = json.loads(STATE.read_bytes())
    if (
        state.get("candidate_sha256") is None
        or sha(OUTPUT / "candidate-model.json") != state["candidate_sha256"]
    ):
        raise ValueError("candidate was not frozen before holdout")
    if (OUTPUT / "HOLDOUT_RESULT.json").exists():
        raise ValueError("holdout already opened and scored")
    targets = _collect_role("holdout")
    write_once(OUTPUT / "holdout-targets.json", targets)
    _, _, _, k, _ = inputs()
    candidate = TrainerPracticeThreeHeadModel.from_dict(
        json.loads((OUTPUT / "candidate-model.json").read_bytes())
    )
    report = score_holdout(targets, plan, k, candidate)
    write_once(OUTPUT / "HOLDOUT_RESULT.json", report)
    state_update(
        unit="holdout",
        holdout_dataset_sha256=sha(OUTPUT / "holdout-targets.json"),
        holdout_pass=report["pass_to_composition"],
        phase="composition" if report["pass_to_composition"] else "failure_audit",
    )
    return report


def _composition_metrics(episode: dict, path: Path) -> dict:
    decisions = episode["decisions"]
    if not decisions:
        raise ValueError("composition episode has no retained decisions")
    before = decisions[0]["state_before"]
    after = decisions[-1]["state_after"]
    cap = sum(before["party_max_hp"])
    if cap <= 0:
        raise ValueError("composition starting HP capacity differs")
    if episode["teacher_queries"] or episode["metrics"]["teacher_interventions"]:
        raise ValueError("composition used teacher action")
    if episode["memory_write_actions"]:
        raise ValueError("composition actor wrote memory")
    seen = Counter()
    loops = 0
    for d in decisions:
        signature = (
            tuple(d["state_before"]["party_hp"]),
            tuple(tuple(row) for row in d["state_before"]["party_pp"]),
            d["state_before"]["opponent_hp"],
            d["kind"],
            d.get("move_slot"),
            d.get("party_slot"),
            d["state_before"].get("active_party_slot"),
            d["state_before"].get("opponent_party_position"),
        )
        seen[signature] += 1
        loops += seen[signature] > 1
    stop = episode["stop_reason"]
    return {
        "stop_reason": stop,
        "win": stop == "battle_won",
        "loss": stop == "party_defeated",
        "censored": stop not in {"battle_won", "party_defeated"},
        "opponents_defeated": episode["metrics"]["opponent_faints"],
        "own_faints": episode["metrics"]["party_faints"],
        "normalized_terminal_hp": sum(after["party_hp"]) / cap,
        "pp_spent": episode["metrics"]["party_pp_spent"],
        "decisions": episode["decision_count"],
        "turns": episode["player_turn_count"],
        "frames": episode["frames_executed"],
        "elapsed_seconds": episode["elapsed_ns"] / 1e9,
        "voluntary_switches": episode["action_counts"]["voluntary_switch"],
        "forced_switches": episode["action_counts"]["forced_switch"],
        "failed_or_suppressed_moves": episode["metrics"]["move_suppressed_or_failed"],
        "failed_move_executions": episode["failed_move_executions"],
        "repeat_state_action_loops": loops,
        "invalid_action_failures": episode["metrics"]["invalid_action_failures"],
        "episode_sha256": sha(path / "episode.json"),
        "decision_trace_path": str(path / "episode.json"),
    }


def _composition_arm(args, capture, model, cartridge, team: dict, offset: int, arm: str) -> dict:
    unit = f"{team['id']}:offset-{offset}:{arm}"
    path = OUTPUT / team["id"] / f"offset-{offset}-{arm}"
    if path.exists():
        if (path / "episode.json").exists() and unit in json.loads(STATE.read_bytes())[
            "completed_units"
        ]:
            lab.verify_trainer_practice_event_log(path / "events")
            episode = json.loads((path / "episode.json").read_bytes())
        else:
            raise ValueError(f"interrupted composition episode cannot replay: {unit}")
    else:
        deadline_check(native=True)
        state_update(active_process={"unit": unit, "pid": os.getpid(), "started_at_utc": utc_now()})
        try:
            episode = lab.play(
                args,
                capture,
                model,
                path,
                cartridge,
                offset=offset,
                learner_continuation=True,
                status=True,
            )
        except Exception:
            state_update(active_process=None, phase="failed")
            raise
        state_update(unit=unit, active_process=None)
    return _composition_metrics(episode, path)


def score_composition(pairs: list[dict], plan: dict, *, bindings: dict | None = None) -> dict:
    by_team = defaultdict(list)
    for pair in pairs:
        by_team[pair["team_id"]].append(pair)
    teams = []
    for team_id, rows in sorted(by_team.items()):
        teams.append(
            {
                "team_id": team_id,
                "roster": rows[0]["roster"],
                "offsets": len(rows),
                "admitted_wins": sum(r["admitted"]["win"] for r in rows),
                "candidate_wins": sum(r["candidate"]["win"] for r in rows),
                "admitted_terminal_hp": fmean(
                    r["admitted"]["normalized_terminal_hp"] for r in rows
                ),
                "candidate_terminal_hp": fmean(
                    r["candidate"]["normalized_terminal_hp"] for r in rows
                ),
            }
        )

    def total(arm, key):
        return sum(pair[arm][key] for pair in pairs)

    common = [pair for pair in pairs if pair["admitted"]["win"] and pair["candidate"]["win"]]
    efficiency = {}
    for key in ("turns", "pp_spent"):
        if common:
            base = fmean(p["admitted"][key] for p in common)
            candidate = fmean(p["candidate"][key] for p in common)
            efficiency[key] = {
                "admitted": base,
                "candidate": candidate,
                "increase_fraction": (candidate - base) / base if base else None,
            }
        else:
            efficiency[key] = {"unassessed": True}
    losses = []
    if len(pairs) != 72 or len(teams) != 24 or any(t["offsets"] != 3 for t in teams):
        losses.append("pair_inventory")
    if any(p[a]["invalid_action_failures"] for p in pairs for a in ("admitted", "candidate")):
        losses.append("illegal_action")
    if total("candidate", "censored") > total("admitted", "censored"):
        losses.append("censored_increase")
    if total("candidate", "loss") > total("admitted", "loss"):
        losses.append("loss_increase")
    if total("candidate", "win") < total("admitted", "win"):
        losses.append("win_decrease")
    hp_gain = fmean(
        p["candidate"]["normalized_terminal_hp"] - p["admitted"]["normalized_terminal_hp"]
        for p in pairs
    )
    if not (
        total("candidate", "win") > total("admitted", "win")
        or total("candidate", "opponents_defeated") > total("admitted", "opponents_defeated")
        or hp_gain >= 0.02
    ):
        losses.append("no_strict_gain")
    if not common:
        losses.append("common_win_efficiency_unassessed")
    elif any(
        efficiency[key]["increase_fraction"] is None or efficiency[key]["increase_fraction"] > 0.10
        for key in ("turns", "pp_spent")
    ):
        losses.append("common_win_efficiency_regression")
    return {
        "schema": "pokemon.red.damage-composition-result.v1",
        **(
            bindings
            if bindings is not None
            else {
                "plan_sha256": sha(OUTPUT / "PLAN.json"),
                "admitted_model_sha256": sha(ADMITTED),
                "candidate_model_sha256": sha(OUTPUT / "candidate-model.json"),
            }
        ),
        "upstream_train_roots": 4,
        "independent_new_roots": 0,
        "pairs": pairs,
        "team_aggregates": teams,
        "summary": {
            "teams": len(teams),
            "paired_offsets": len(pairs),
            "episodes": len(pairs) * 2,
            "admitted_wins": total("admitted", "win"),
            "candidate_wins": total("candidate", "win"),
            "admitted_losses": total("admitted", "loss"),
            "candidate_losses": total("candidate", "loss"),
            "admitted_censored": total("admitted", "censored"),
            "candidate_censored": total("candidate", "censored"),
            "admitted_opponents_defeated": total("admitted", "opponents_defeated"),
            "candidate_opponents_defeated": total("candidate", "opponents_defeated"),
            "mean_normalized_terminal_hp_gain": hp_gain,
            "common_wins": len(common),
            "common_win_efficiency": efficiency,
            "representative_complete_trace_paths": [
                pairs[index][arm]["decision_trace_path"]
                for index, arm in (
                    (0, "admitted"),
                    (0, "candidate"),
                    (len(pairs) // 2, "candidate"),
                    (len(pairs) - 1, "candidate"),
                )
            ],
        },
        "gate_failures": losses,
        "provisional_review_gate_passed": not losses,
        "production_authority_promoted": False,
    }


def collect_and_score_composition() -> dict:
    deadline_check()
    holdout = json.loads((OUTPUT / "HOLDOUT_RESULT.json").read_bytes())
    if not holdout["pass_to_composition"]:
        raise ValueError("failed holdout forbids native composition")
    if (OUTPUT / "COMPOSITION_RESULT.json").exists():
        raise ValueError("composition already scored")
    plan = load_plan()
    cartridge, _, sources, _, admitted = inputs()
    candidate = TrainerPracticeThreeHeadModel.from_dict(
        json.loads((OUTPUT / "candidate-model.json").read_bytes())
    )
    args = argparse.Namespace(output=OUTPUT, rom=ROM)
    started = time.monotonic()
    pairs = []
    for team in plan["composition_teams"]:
        capture = _capture(
            args, team, team["source_index"], sources, cartridge, plan["source_commit"]
        )
        for offset in OFFSETS:
            if time.monotonic() - started >= 4500:
                raise TimeoutError("composition wall ceiling")
            key = f"{team['id']}:offset-{offset}"
            order = plan["composition_orders"][key]
            results = {}
            for arm in order:
                if time.monotonic() - started >= 4500:
                    raise TimeoutError("composition wall ceiling")
                results[arm] = _composition_arm(
                    args,
                    capture,
                    admitted if arm == "admitted" else candidate,
                    cartridge,
                    team,
                    offset,
                    arm,
                )
            pair = {
                "team_id": team["id"],
                "roster": team["roster"],
                "root": capture.manifest.root_lineage_id,
                "offset": offset,
                "arm_order": order,
                **results,
            }
            write_once(OUTPUT / team["id"] / f"pair-{offset}.json", pair)
            state_update(unit=f"pair:{key}")
            pairs.append(pair)
            print(
                json.dumps(
                    {
                        "pair": key,
                        "admitted_win": results["admitted"]["win"],
                        "candidate_win": results["candidate"]["win"],
                    }
                ),
                flush=True,
            )
    report = score_composition(pairs, plan)
    write_once(OUTPUT / "COMPOSITION_RESULT.json", report)
    state_update(
        unit="composition", composition_pass=report["provisional_review_gate_passed"], phase="audit"
    )
    return report


def retention_audit() -> dict:
    """Read previously opened TRAIN results; keep damage and utility units distinct."""
    _, catalog, _, k, _ = inputs()
    candidate_path = OUTPUT / "candidate-model.json"
    if not candidate_path.exists():
        return {
            "gate": "unmet_no_candidate",
            "supported_domain_groups": {},
            "excluded_mechanic_groups": {},
            "new_native_runs": 0,
        }
    candidate = TrainerPracticeThreeHeadModel.from_dict(json.loads(candidate_path.read_bytes()))
    diagnostic_dir = PRIVATE / "red-damage-ranking-diagnostic-20260922-v1"
    diagnostic = json.loads((diagnostic_dir / "result.json").read_bytes())
    damage_rows = []
    for item in diagnostic["results"]:
        vectors = tuple(tuple(v) for v in item["vectors"])
        values = tuple(item["mean_damage"])
        base = max(values) - values[k.move.predict_index(vectors)]
        fitted = max(values) - values[candidate.damage_reference.predict_index(vectors)]
        damage_rows.append({"id": item["id"], "baseline_regret": base, "candidate_regret": fitted})
    corpus_path = PRIVATE / "red-trainer-J-canonical-20260920-v1/audited-targets.json"
    corpus = json.loads(corpus_path.read_bytes())
    classification = Counter()
    by_group = {}
    for group, records in corpus["retention"].items():
        classes = Counter()
        for record in records:
            moves = record["heads"]["move"]["choice_refs"]
            flags = []
            for ref in moves:
                if ":move:" not in ref:
                    flags.append("non_move_action")
                    continue
                slot = int(ref.rsplit(":", 1)[1])
                observed = record["observation"]["features"]["party"]["lead"]["moves"]
                if slot < 1 or slot > len(observed):
                    flags.append("unresolved_slot")
                    continue
                move_ref = observed[slot - 1].get("move_ref")
                if not isinstance(move_ref, str):
                    flags.append("unresolved_move")
                    continue
                if not catalog.recovery_attack_supported(move_ref):
                    flags.append("excluded_or_status")
                else:
                    mechanics = catalog.resolve_move(move_ref)
                    if mechanics.effect_flags & EXCLUDED_FLAGS:
                        flags.append("excluded_mechanic")
            category = "supported_damage_inventory" if not flags else "+".join(sorted(set(flags)))
            classes[category] += 1
            classification[category] += 1
        by_group[group] = {
            "records": len(records),
            "classification": dict(classes),
            "outcome_unit": "historical mixed battle utility",
            "comparable_foe_hp_damage_regret": False,
        }
    baseline = fmean(row["baseline_regret"] for row in damage_rows)
    fitted = fmean(row["candidate_regret"] for row in damage_rows)
    diagnostic_group = {
        "records": len(damage_rows),
        "outcome_unit": "foe maximum HP fraction",
        "baseline_mean_regret": baseline,
        "candidate_mean_regret": fitted,
        "regression": fitted - baseline,
        "historical_opened_TRAIN_not_unseen": True,
        "passes_0_02_regression_limit": fitted - baseline <= 0.02,
        "cases": damage_rows,
        "source_sha256": sha(diagnostic_dir / "result.json"),
    }
    # The old utility corpora cannot silently satisfy an HP-fraction threshold.
    return {
        "supported_domain_groups": {
            "prior_damage_diagnostic": diagnostic_group,
            "historical_utility_groups": by_group,
        },
        "excluded_mechanic_groups": dict(classification),
        "historical_corpus_sha256": sha(corpus_path),
        "gate": "unmet_missing_comparable_damage_groups"
        if diagnostic_group["passes_0_02_regression_limit"]
        else "failed_prior_damage_diagnostic_regression",
        "new_native_runs": 0,
        "mixed_units_kept_separate": True,
        "unsupported_domain_general_replacement_blocked": True,
    }


def failure_trace() -> dict:
    path = OUTPUT / "HOLDOUT_RESULT.json"
    if not path.exists():
        return {"status": "no_holdout", "cases": [], "next_experiment": None}
    holdout = json.loads(path.read_bytes())
    if holdout["pass_to_composition"]:
        return {"status": "holdout_passed", "cases": [], "next_experiment": None}
    from pokemon_red_completion.battle_semantics import BattleFeatureProjector

    catalog = lab.PokemonRedBattleCatalog()
    cases = []
    for row in sorted(holdout["configurations"], key=lambda r: (-r["candidate_regret"], r["id"]))[
        :5
    ]:
        target = json.loads((OUTPUT / row["id"] / "target.json").read_bytes())
        event_path = OUTPUT / row["id"] / "branch-0-1" / "episode.json"
        episode = json.loads(event_path.read_bytes())
        observation = episode["decisions"][0]["observation"]
        raw = BattleFeatureProjector(catalog).project(observation)
        projected = project_trainer_move_features(observation, raw)
        vectors = tuple(
            tuple(projected.candidate_vectors[projected.candidate_slots.index(slot)])
            for slot in target["slots"]
        )
        if vectors != tuple(tuple(v) for v in target["vectors"]):
            raise ValueError("failure-trace raw feature recomputation differs")
        candidate = TrainerPracticeThreeHeadModel.from_dict(
            json.loads((OUTPUT / "candidate-model.json").read_bytes())
        )
        _, _, _, k, _ = inputs()
        if (
            candidate.damage_reference.predict_index(vectors) != row["candidate_index"]
            or k.move.predict_index(vectors) != row["baseline_index"]
        ):
            raise ValueError("failure-trace choice recomputation differs")
        samples = {
            slot: [b["damage_fraction"] for b in target["branches"] if b["slot"] == slot]
            for slot in target["slots"]
        }
        cases.append(
            {
                "id": row["id"],
                "family_id": row["family_id"],
                "candidate_regret": row["candidate_regret"],
                "baseline_regret": row["baseline_regret"],
                "baseline_slot": row["baseline_slot"],
                "candidate_slot": row["candidate_slot"],
                "three_timing_samples_by_slot": samples,
                "feature_recomputation_exact": True,
                "choice_recomputation_exact": True,
                "sampling_noise_visible": any(len(set(v)) > 1 for v in samples.values()),
                "implementation_defect_detected": False,
            }
        )
    return {
        "status": "holdout_failed",
        "cases": cases,
        "next_experiment": (
            "A separately authorized, new-root damage-domain study of move-effect "
            "coverage and outcome variance; no refit or replay in this packet."
        ),
    }


def audit_saved() -> dict:
    deadline_check()
    plan = load_plan()
    from pokemon_red_completion.battle_semantics import BattleFeatureProjector

    catalog = lab.PokemonRedBattleCatalog()
    targets = []
    checks = Counter()
    failures = []
    for family in plan["families"]:
        for recipe in family["contexts"]:
            target_path = OUTPUT / recipe["id"] / "target.json"
            if not target_path.exists():
                continue
            target = json.loads(target_path.read_bytes())
            targets.append(target)
            if target["recipe_sha256"] != sha_recipe(recipe):
                failures.append(f"recipe:{recipe['id']}")
            if target["role"] != family["role"] or target["family_id"] != family["id"]:
                failures.append(f"partition:{recipe['id']}")
            if len(target["branches"]) != 12:
                failures.append(f"branches:{recipe['id']}")
            for branch in target["branches"]:
                episode_path = OUTPUT / recipe["id"] / f"branch-{branch['offset']}-{branch['slot']}"
                if (
                    not (episode_path / "episode.json").exists()
                    and not (episode_path / "failure.json").exists()
                ):
                    failures.append(f"missing_terminal:{branch['unit']}")
                    continue
                if (episode_path / "episode.json").exists():
                    episode = json.loads((episode_path / "episode.json").read_bytes())
                    lab.verify_trainer_practice_event_log(episode_path / "events")
                    decision = episode["decisions"][0]
                    max_hp = decision["observation"]["features"]["battle"]["opponent_max_hp"]
                    damage = (
                        decision["opponent_hp_before"] - decision["opponent_hp_after"]
                    ) / max_hp
                    if damage != branch["damage_fraction"]:
                        failures.append(f"damage:{branch['unit']}")
                    projected = project_trainer_move_features(
                        decision["observation"],
                        BattleFeatureProjector(catalog).project(decision["observation"]),
                    )
                    vector = tuple(
                        projected.candidate_vectors[projected.candidate_slots.index(branch["slot"])]
                    )
                    if vector != tuple(target["vectors"][branch["slot"] - 1]):
                        failures.append(f"features:{branch['unit']}")
                    checks["complete_episodes"] += 1
                else:
                    checks["explicit_failures"] += 1
            for slot in target["slots"]:
                actual = fmean(
                    b["damage_fraction"] for b in target["branches"] if b["slot"] == slot
                )
                if actual != target["mean_damage"][slot - 1]:
                    failures.append(f"target_mean:{recipe['id']}:{slot}")
            checks["targets"] += 1
    if len({t["id"] for t in targets}) != len(targets):
        failures.append("duplicate_target_ids")
    if len({t["capture_sha256"] for t in targets}) != len(targets):
        failures.append("duplicate_capture_states")
    if (OUTPUT / "candidate-model.json").exists():
        candidate = TrainerPracticeThreeHeadModel.from_dict(
            json.loads((OUTPUT / "candidate-model.json").read_bytes())
        )
        compact = TrainerHeadModel.from_dict(
            json.loads((OUTPUT / "compact-head.json").read_bytes()),
            schema_id=MOVE_SCHEMA_ID,
            feature_names=FEATURES,
        )
        for row in targets:
            assert_embedding(compact, candidate.damage_reference, row["vectors"])
        checks["prediction_rows"] = len(targets)
    retention = retention_audit()
    write_once(OUTPUT / "RETENTION_RESULT.json", retention)
    trace = failure_trace()
    write_once(OUTPUT / "FAILURE_TRACE.json", trace)
    report = {
        "schema": "pokemon.red.damage-audit.v1",
        "plan_sha256": sha(OUTPUT / "PLAN.json"),
        "source_commit": plan["source_commit"],
        "checks": dict(checks),
        "failures": failures,
        "fit_targets": sum(t["role"] == "fit" for t in targets),
        "holdout_targets": sum(t["role"] == "holdout" for t in targets),
        "completed_native_damage_branches": checks["complete_episodes"],
        "explicit_failed_native_damage_branches": checks["explicit_failures"],
        "retention_gate": retention["gate"],
        "independent_new_roots": 0,
        "promotion": False,
        "status": "passed" if not failures else "failed",
    }
    write_once(OUTPUT / "AUDIT.json", report)
    state_update(unit="audit", phase="closeout")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", choices=("inspect", "freeze", "collect-fit", "holdout", "composition", "audit")
    )
    args = parser.parse_args()
    action = {
        "inspect": lambda: freeze(inspect_only=True),
        "freeze": freeze,
        "collect-fit": collect_train_and_fit,
        "holdout": collect_and_score_holdout,
        "composition": collect_and_score_composition,
        "audit": audit_saved,
    }[args.phase]
    try:
        result = action()
    except Exception as error:
        if OUTPUT.exists():
            failure_path = OUTPUT / f"{args.phase}-failure.json"
            if not failure_path.exists():
                write_once(
                    failure_path,
                    {"type": type(error).__name__, "error": str(error), "at_utc": utc_now()},
                )
        raise
    print(
        json.dumps(
            result
            if args.phase == "inspect"
            else {
                key: value
                for key, value in result.items()
                if key
                not in {"configurations", "families", "pairs", "coverage_slices", "team_aggregates"}
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
