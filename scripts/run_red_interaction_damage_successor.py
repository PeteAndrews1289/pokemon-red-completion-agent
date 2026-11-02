"""Single-use balanced TRAIN damage fit and configuration comparison."""

from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from itertools import product
from pathlib import Path
from statistics import fmean

import numpy as np
import run_red_crossed_damage_diagnostic as crossed
import run_red_damage_proposal_overnight as old
from audit_red_damage_proposal_overnight import classify_retention_record

from pokemon_red_completion.battle_practice_factory import BattlePracticeSpec
from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_damage_interaction_head import (
    SEED as FIT_SEED,
)
from pokemon_red_completion.red_damage_interaction_head import (
    fit_damage_interaction_head,
    project_damage_interactions,
)
from pokemon_red_completion.red_trainer_practice_episode import (
    RedTrainerPracticeEpisodeError,
    validate_opening_idle_frames,
)
from pokemon_red_completion.red_trainer_practice_features import project_trainer_move_features

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = old.PRIVATE / "red-interaction-damage-successor-20260923-v1"
CROSSED = old.PRIVATE / "red-crossed-damage-diagnostic-20260923-v1"
SEED = 23092321
LEVELS = (31, 37, 43, 49)
OFFSETS = tuple(range(0, 36, 4))
MAX_ELAPSED = 2700
V2_OFFSETS = (0, 1, 3, 4, 6, 7, 9, 10, 12)


def experiment_config(version: int) -> tuple[Path, int, tuple[int, ...], set[tuple[int, int]]]:
    if version == 1:
        return OUTPUT, SEED, OFFSETS, set()
    if version != 2:
        raise ValueError("unknown damage experiment version")
    prior = json.loads((OUTPUT / "PLAN.json").read_bytes())
    excluded = {tuple(sorted((f["actor"], f["enemy"]))) for f in prior["inventory"]["families"]}
    if len(excluded) != 40:
        raise ValueError("V1 exclusion inventory differs")
    return (
        old.PRIVATE / "red-interaction-damage-successor-20260923-v2",
        23092322,
        V2_OFFSETS,
        excluded,
    )


def validate_offsets(offsets: tuple[int, ...]) -> None:
    """Use the native contract before any inputs or execution identity are opened."""
    if len(offsets) != 9 or len(set(offsets)) != 9:
        raise ValueError("opening timing offsets exceed native trainer bound")
    for offset in offsets:
        try:
            validate_opening_idle_frames(offset)
        except RedTrainerPracticeEpisodeError as error:
            raise ValueError("opening timing offsets exceed native trainer bound") from error


def _prior_pairs() -> set[tuple[int, int]]:
    previous = json.loads((old.OUTPUT / "PLAN.json").read_bytes())
    crossed_plan = json.loads((CROSSED / "PLAN.json").read_bytes())
    pairs = old._prior_pairs() | {
        tuple(sorted((f["actor_species_id"], f["opponent_species_id"])))
        for f in previous["families"]
    }
    pairs |= {
        tuple(
            sorted(
                (
                    int(r["practice"]["actor_species_ref"][-3:]),
                    int(r["practice"]["opponent_species_ref"][-3:]),
                )
            )
        )
        for r in crossed_plan["recipes"]
    }
    return pairs


def _proxy(
    catalog,
    own,
    foe,
    actor_id: int,
    foe_id: int,
    moves: tuple[int, ...],
    level: int,
    foe_level: int,
) -> tuple[float, float]:
    own_stats = own.neutral_stats(level)
    foe_stats = foe.neutral_stats(foe_level)
    types = catalog.resolve_species(old.pokemon_red_species_ref(actor_id)).types
    foe_types = catalog.resolve_species(old.pokemon_red_species_ref(foe_id)).types
    values = {"physical": [], "special": []}
    for move in moves:
        mechanics = catalog.resolve_move(old.pokemon_red_move_ref(move))
        stat = (
            own_stats.attack / foe_stats.defense
            if mechanics.category == "physical"
            else own_stats.special / foe_stats.special
        )
        values[mechanics.category].append(
            mechanics.power
            * mechanics.accuracy
            * (1.5 if mechanics.type_name in types else 1)
            * catalog.type_effectiveness(mechanics.type_name, foe_types)
            * stat
        )
    return max(values["physical"]), max(values["special"])


def build_recipes(
    cartridge, catalog, sources, *, seed=SEED, excluded_pairs=frozenset()
) -> tuple[list[dict], dict]:
    rng = random.Random(seed)
    used = _prior_pairs() | set(excluded_pairs)
    rows = []
    families = []
    for role, count in (("fit", 24), ("comparison", 16)):
        coverage = Counter()
        for index in range(count):
            level = LEVELS[index % 4]
            foe_level = level + (-3, 0, 3)[index % 3]
            pool = {
                s: old.legal_damage(cartridge, catalog, s, level)
                for s in cartridge.species_ids
                if s not in old.EXCLUDED_SPECIES
            }
            foe_pool = {s: old.legal_damage(cartridge, catalog, s, foe_level) for s in pool}
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
            enemies = sorted(s for s in foe_pool if len(foe_pool[s]) >= 2)
            favored = "physical" if (index // 4) % 2 == 0 else "special"
            options = []
            for _ in range(4000):
                actor, enemy = rng.choice(actors), rng.choice(enemies)
                if actor == enemy or tuple(sorted((actor, enemy))) in used:
                    continue
                moves = tuple(rng.sample(physical[actor], 2) + rng.sample(special[actor], 2))
                own, foe = cartridge.species(actor), cartridge.species(enemy)
                p, s = _proxy(catalog, own, foe, actor, enemy, moves, level, foe_level)
                preferred, alternative = (p, s) if favored == "physical" else (s, p)
                if preferred <= 0 or preferred < 1.25 * alternative:
                    continue
                foe_types = catalog.resolve_species(old.pokemon_red_species_ref(enemy)).types
                mechanics = [catalog.resolve_move(old.pokemon_red_move_ref(m)) for m in moves]
                effects = [catalog.type_effectiveness(m.type_name, foe_types) for m in mechanics]
                flags = {
                    "immune": 0 in effects,
                    "unfavorable": any(0 < x < 1 for x in effects),
                    "favorable": any(x > 1 for x in effects),
                    "accurate": any(m.accuracy == 1 for m in mechanics),
                    "imperfect": any(m.accuracy < 1 for m in mechanics),
                }
                ratio = own.base_stats[1] / max(1, foe.base_stats[2])
                ratio_bin = "low" if ratio < 0.8 else "high" if ratio > 1.25 else "middle"
                flags["ratio:" + ratio_bin] = True
                novelty = sum(10 for key, present in flags.items() if present and not coverage[key])
                distinct = (
                    8
                    if not any(
                        f["actor"] == actor and f["role"] == role and f["favored"] == favored
                        for f in families
                    )
                    else 0
                )
                score = (
                    novelty
                    + distinct
                    + old._family_score(catalog, actor, enemy, moves, stat_ratio=ratio)
                    + rng.random()
                )
                options.append((score, actor, enemy, moves, p, s, flags, ratio_bin))
            if not options:
                raise ValueError("balanced curriculum has no eligible fresh family")
            _, actor, enemy, moves, p, s, flags, ratio_bin = max(options, key=lambda o: o[0])
            used.add(tuple(sorted((actor, enemy))))
            coverage.update(key for key, present in flags.items() if present)
            own, foe = cartridge.species(actor), cartridge.species(enemy)
            foe_moves = tuple(rng.sample(foe_pool[enemy], 2))
            own_hp = own.neutral_stats(level).max_hp
            foe_hp = foe.trainer_stats(foe_level).max_hp
            family_id = f"{role}-{index:02d}"
            source_index = (index // 4 + index % 4) % 4
            base = {
                "partition": "train",
                "battle_kind": "trainer",
                "actor_species_ref": old.pokemon_red_species_ref(actor),
                "actor_national_number": own.national_number,
                "actor_level": level,
                "actor_moves": old._move_rows(catalog, moves),
                "opponent_species_ref": old.pokemon_red_species_ref(enemy),
                "opponent_national_number": foe.national_number,
                "opponent_level": foe_level,
                "opponent_moves": old._move_rows(catalog, foe_moves),
                "opponent_party_count": 1,
            }
            contexts = (
                ("neutral", own_hp, foe_hp, old.StatusPracticeConditions()),
                (
                    "burn",
                    max(1, own_hp * 70 // 100),
                    foe_hp,
                    old.StatusPracticeConditions(player_status="burn"),
                ),
                (
                    "stage",
                    own_hp,
                    max(1, foe_hp * 45 // 100),
                    old.StatusPracticeConditions(player_accuracy=-2, opponent_status="paralysis"),
                ),
            )
            for name, hp, enemy_hp, conditions in contexts:
                rows.append(
                    {
                        "id": f"{family_id}-{name}",
                        "family_id": family_id,
                        "role": role,
                        "context": name,
                        "favored": favored,
                        "ratio_bin": ratio_bin,
                        "source_index": source_index,
                        "root": sources[source_index][1]["source_id"],
                        "conditions": asdict(conditions),
                        "practice": {**base, "actor_hp": hp, "opponent_hp": enemy_hp},
                    }
                )
            families.append(
                {
                    "id": family_id,
                    "role": role,
                    "actor": actor,
                    "enemy": enemy,
                    "favored": favored,
                    "source_index": source_index,
                    "level": level,
                    "physical_proxy": p,
                    "special_proxy": s,
                    "flags": flags,
                }
            )
        for flag in ("immune", "unfavorable", "favorable", "accurate", "imperfect"):
            if not coverage[flag]:
                raise ValueError(f"{role} input coverage lacks {flag}")
        if sum(bool(coverage["ratio:" + b]) for b in ("low", "middle", "high")) < 2:
            raise ValueError(f"{role} input coverage lacks stat-ratio diversity")
    validate_plan(rows, families, sources, excluded_pairs=excluded_pairs)
    return rows, {
        "families": families,
        "joint_root_level": {
            role: {
                f"root-{r}-level-{level}": sum(
                    f["role"] == role and f["source_index"] == r and f["level"] == level
                    for f in families
                )
                for r, level in product(range(4), LEVELS)
            }
            for role in ("fit", "comparison")
        },
    }


def validate_plan(rows, families, sources, *, excluded_pairs=frozenset()) -> None:
    if len(rows) != 120 or len(families) != 40 or len({r["id"] for r in rows}) != 120:
        raise ValueError("balanced plan cardinality or identity differs")
    pairs = [tuple(sorted((f["actor"], f["enemy"]))) for f in families]
    if len(set(pairs)) != 40 or set(pairs) & (_prior_pairs() | set(excluded_pairs)):
        raise ValueError("balanced family split or historical exclusion differs")
    for role, n in (("fit", 24), ("comparison", 16)):
        subset = [f for f in families if f["role"] == role]
        if len(subset) != n or Counter(f["favored"] for f in subset) != {
            "physical": n // 2,
            "special": n // 2,
        }:
            raise ValueError("favored physical/special split differs")
        for favored in ("physical", "special"):
            if len({f["actor"] for f in subset if f["favored"] == favored}) < 4:
                raise ValueError("favored category has fewer than four actors")
        grid = Counter((f["source_index"], f["level"]) for f in subset)
        if (
            set(grid) != set(product(range(4), LEVELS))
            or max(grid.values()) - min(grid.values()) > 1
        ):
            raise ValueError("source by level crossing differs")
        for f in subset:
            related = [r for r in rows if r["family_id"] == f["id"]]
            if (
                len(related) != 3
                or {r["context"] for r in related} != {"neutral", "burn", "stage"}
                or any(
                    r["source_index"] != f["source_index"]
                    or r["root"] != sources[f["source_index"]][1]["source_id"]
                    or r["role"] != f["role"]
                    or r["favored"] != f["favored"]
                    or r["practice"]["actor_level"] != f["level"]
                    or int(r["practice"]["actor_species_ref"][-3:]) != f["actor"]
                    or int(r["practice"]["opponent_species_ref"][-3:]) != f["enemy"]
                    for r in related
                )
            ):
                raise ValueError("family context/root partition differs")


def _source_pins() -> dict[str, str]:
    paths = [
        Path(__file__),
        Path(old.__file__),
        Path(crossed.__file__),
        Path(old.lab.__file__),
        ROOT / "scripts/run_red_trainer_practice_model.py",
        ROOT / "scripts/run_fresh_red_trainer_curriculum.py",
        ROOT / "scripts/audit_red_damage_proposal_overnight.py",
    ]
    paths.extend((ROOT / "src").rglob("*.py"))
    return {str(p.relative_to(ROOT)): old.sha(p) for p in paths}


def preflight(*, version=1):
    _, seed, offsets, exclusions = experiment_config(version)
    validate_offsets(offsets)
    cartridge, catalog, sources, k, admitted = old.inputs()
    if len(sources) != 4 or old.sha(old.ROM) != old.lab.common.ROM_SHA256:
        raise ValueError("TRAIN source or cartridge binding differs")
    rows, inventory = build_recipes(
        cartridge, catalog, sources, seed=seed, excluded_pairs=exclusions
    )
    for row in rows:
        source = sources[row["source_index"]][0]
        capture = open_battle_scenario_capture(
            source / "source.state", source / "source.state.json"
        )
        BattlePracticeSpec.from_dict(
            {
                **row["practice"],
                "root_lineage_id": row["root"],
                "source_state_sha256": capture.manifest.state_sha256,
            }
        )
        old.StatusPracticeConditions(**row["conditions"])
        categories = Counter(
            catalog.resolve_move(move["move_ref"]).category
            for move in row["practice"]["actor_moves"]
        )
        if categories != {"physical": 2, "special": 2}:
            raise ValueError("practice categories differ from balanced recipe")
        for side in ("actor", "opponent"):
            spec = row["practice"]
            species = int(spec[f"{side}_species_ref"][-3:])
            legal = old.legal_damage(cartridge, catalog, species, spec[f"{side}_level"])
            if any(int(move["move_ref"][-3:]) not in legal for move in spec[f"{side}_moves"]):
                raise ValueError("practice move is unsupported at its own battler level")
    historical_train = json.loads((old.OUTPUT / "train-targets.json").read_bytes())
    for record in historical_train:
        project_damage_interactions(record["vectors"])
    return cartridge, catalog, sources, k, admitted, rows, inventory


def _deadline(start):
    if time.monotonic() - start >= MAX_ELAPSED:
        raise TimeoutError("bounded native damage experiment exceeded45minutes")


def _measure(args, row, sources, cartridge, k, commit, start, *, offsets=OFFSETS):
    _deadline(start)
    capture = old.lab.materialize(args, row, row["source_index"], sources, cartridge, commit)
    if capture.manifest.root_lineage_id != row["root"]:
        raise ValueError("materialized root differs from prospectively frozen recipe")
    vectors, slots = old._vectors(capture, cartridge)
    if slots != (1, 2, 3, 4):
        raise ValueError("damaging action mask differs")
    project_damage_interactions(vectors)
    catalog = old.lab.PokemonRedBattleCatalog()
    branches = []
    for offset, slot in product(offsets, slots):
        _deadline(start)
        directory = args.output / row["id"] / f"branch-{offset}-{slot}"
        episode = old.lab.play(
            args, capture, k, directory, cartridge, first_slot=slot, offset=offset, horizon=1
        )
        attacks = [d for d in episode["decisions"] if d["kind"] == "attack"]
        if len(attacks) != 1 or attacks[0]["move_slot"] != slot or len(episode["decisions"]) != 1:
            raise ValueError("forced branch did not take its claimed action")
        decision = attacks[0]
        observed = decision["observation"]
        projection = project_trainer_move_features(
            observed, BattleFeatureProjector(catalog).project(observed)
        )
        if (
            tuple(projection.candidate_slots) != slots
            or not np.allclose(projection.candidate_vectors, vectors, rtol=0, atol=1e-12)
            or decision["legal_move_slots"] != [1, 2, 3, 4]
        ):
            raise ValueError("actual branch features or legality differ")
        battle = observed["features"]["battle"]
        if (
            decision["opponent_hp_before"] != row["practice"]["opponent_hp"]
            or observed["features"]["party"]["lead"]["hp"] != row["practice"]["actor_hp"]
        ):
            raise ValueError("materialized HP differs")
        cap = battle["opponent_max_hp"]
        damage = (decision["opponent_hp_before"] - decision["opponent_hp_after"]) / cap
        if not 0 <= damage <= 1:
            raise ValueError("measured foe-max-HP damage target differs")
        terminal = json.loads((directory / "final-state.json").read_bytes())
        if (
            old.sha(directory / "final.state") != terminal["state_sha256"]
            or not 0 < terminal["completed_actions"] <= terminal["attempted_actions"] <= 5000
            or terminal["frame_delta"] > 120000
            or terminal["wall_elapsed_seconds"] > 45
        ):
            raise ValueError("native terminal or hard budget differs")
        branches.append(
            {
                "slot": slot,
                "offset": offset,
                "damage_fraction": damage,
                "opponent_max_hp": cap,
                "stop_reason": episode["stop_reason"],
                "player_hp_before": decision["state_before"]["party_hp"],
                "player_hp_after": decision["state_after"]["party_hp"],
                "party_pp_spent": episode["metrics"]["party_pp_spent"],
                "invalid_action_failures": episode["metrics"]["invalid_action_failures"],
                "episode_sha256": old.sha(directory / "episode.json"),
                "terminal_sha256": terminal["state_sha256"],
                "actual_actions": terminal["completed_actions"],
                "attempted_actions": terminal["attempted_actions"],
                "actual_frames": terminal["frame_delta"],
            }
        )
    values = tuple(
        fmean(b["damage_fraction"] for b in branches if b["slot"] == slot) for slot in slots
    )
    target = {
        "id": row["id"],
        "family_id": row["family_id"],
        "role": row["role"],
        "context": row["context"],
        "favored": row["favored"],
        "source_index": row["source_index"],
        "level": row["practice"]["actor_level"],
        "ratio_bin": row["ratio_bin"],
        "root": row["root"],
        "capture_sha256": capture.manifest.state_sha256,
        "recipe_sha256": old.sha_recipe(row),
        "slots": slots,
        "vectors": vectors,
        "mean_damage": values,
        "branches": branches,
        "forced_training_actions": True,
        "learned_native_actions": 0,
    }
    old.write_once(args.output / row["id"] / "target.json", target)
    return target


def _costs(rows) -> dict:
    branches = [b for row in rows for b in row["branches"]]
    return {
        "native_branches": len(branches),
        "controller_actions": sum(b["actual_actions"] for b in branches),
        "attempted_controller_actions": sum(b["attempted_actions"] for b in branches),
        "frames": sum(b["actual_frames"] for b in branches),
        "stops": dict(Counter(b["stop_reason"] for b in branches)),
        "invalid_actions": sum(b["invalid_action_failures"] for b in branches),
    }


def _evaluate(
    rows, k_head, candidate_head, *, expected, branches_per_case, target_root=OUTPUT
) -> dict:
    if len(rows) != expected or any(len(r["branches"]) != branches_per_case for r in rows):
        raise ValueError("evaluation inventory is incomplete")
    checked = []
    for row in rows:
        values = tuple(row["mean_damage"])
        vectors = tuple(tuple(v) for v in row["vectors"])
        if len(values) != 4 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in values):
            raise ValueError("evaluation returns are not bounded damage")
        base, learned = k_head.predict_index(vectors), candidate_head.predict_index(vectors)
        best = max(values)
        target_file = target_root / row["id"] / "target.json"
        physical_at = old.MOVE_FEATURE_NAMES.index("move.category.physical")
        special_at = old.MOVE_FEATURE_NAMES.index("move.category.special")
        checked.append(
            {
                "id": row["id"],
                "family_id": row["family_id"],
                "root": row.get("source_index"),
                "level": row.get("level"),
                "context": row.get("context", row["id"].rsplit("-", 1)[-1]),
                "favored": row.get("favored"),
                "ratio_bin": row.get("ratio_bin"),
                "baseline_slot": base + 1,
                "candidate_slot": learned + 1,
                "baseline_regret": best - values[base],
                "candidate_regret": best - values[learned],
                "baseline_exact_best": abs(best - values[base]) <= 1e-12,
                "candidate_exact_best": abs(best - values[learned]) <= 1e-12,
                "baseline_near_best": best - values[base] <= 0.02,
                "candidate_near_best": best - values[learned] <= 0.02,
                "physical_best": any(
                    vectors[i][physical_at] == 1 and values[i] >= best - 1e-12 for i in range(4)
                ),
                "special_best": any(
                    vectors[i][special_at] == 1 and values[i] >= best - 1e-12 for i in range(4)
                ),
                "target_sha256": old.sha(target_file),
            }
        )
    return {
        "cases": checked,
        "baseline_mean_regret": fmean(r["baseline_regret"] for r in checked),
        "candidate_mean_regret": fmean(r["candidate_regret"] for r in checked),
        "baseline_exact_best": sum(r["baseline_exact_best"] for r in checked),
        "candidate_exact_best": sum(r["candidate_exact_best"] for r in checked),
        "baseline_near_best": sum(r["baseline_near_best"] for r in checked),
        "candidate_near_best": sum(r["candidate_near_best"] for r in checked),
    }


def score_comparison(rows, recipes, k_head, candidate_head, *, target_root=OUTPUT):
    evaluated = _evaluate(
        rows, k_head, candidate_head, expected=48, branches_per_case=36, target_root=target_root
    )
    recipe_by_id = {r["id"]: r for r in recipes}
    for record in evaluated["cases"]:
        record["level"] = recipe_by_id[record["id"]]["practice"]["actor_level"]
    groups = defaultdict(list)
    for case in evaluated["cases"]:
        for tag in (
            f"root:{case['root']}",
            f"level:{case['level']}",
            f"context:{case['context']}",
            f"stat_ratio:{case['ratio_bin']}",
            f"favored:{case['favored']}",
        ):
            groups[tag].append(case)
    slices = {
        tag: {
            "configurations": len(cases),
            "baseline_regret": fmean(x["baseline_regret"] for x in cases),
            "candidate_regret": fmean(x["candidate_regret"] for x in cases),
            "regression": fmean(x["candidate_regret"] - x["baseline_regret"] for x in cases),
        }
        for tag, cases in sorted(groups.items())
    }
    families = defaultdict(list)
    for case in evaluated["cases"]:
        families[case["family_id"]].append(case)
    family_regressions = {
        name: fmean(c["candidate_regret"] - c["baseline_regret"] for c in cases)
        for name, cases in sorted(families.items())
    }
    rng = np.random.default_rng(23092322)
    family_improvements = -np.asarray(list(family_regressions.values()))
    bootstrap = rng.choice(family_improvements, size=(2000, len(family_improvements))).mean(axis=1)
    improvement = evaluated["baseline_mean_regret"] - evaluated["candidate_mean_regret"]
    failures = []
    if (
        evaluated["baseline_mean_regret"] <= 0
        or improvement < 0.01
        or improvement < 0.2 * evaluated["baseline_mean_regret"]
    ):
        failures.append("mean_regret_improvement")
    if any(s["regression"] > 0.03 for s in slices.values()):
        failures.append("coverage_slice_regression")
    if any(value > 0.15 for value in family_regressions.values()):
        failures.append("family_regression")
    if any(s["regression"] > 1e-12 for name, s in slices.items() if name.startswith("root:")):
        failures.append("root_mean_improvement")
    if any(b["invalid_action_failures"] for r in rows for b in r["branches"]):
        failures.append("illegal_action")
    evaluated.update(
        {
            "slices": slices,
            "family_regressions": family_regressions,
            "absolute_improvement": improvement,
            "relative_improvement": improvement / evaluated["baseline_mean_regret"]
            if evaluated["baseline_mean_regret"]
            else None,
            "failures": failures,
            "gate_passed": not failures,
            "family_cluster_uncertainty": {
                "resamples": 2000,
                "seed": 23092322,
                "mean_regret_improvement_95_percentile_interval": np.quantile(
                    bootstrap, (0.025, 0.975)
                ).tolist(),
                "interpretation": (
                    "descriptive; shared roots and correlated timing offsets limit independence"
                ),
            },
        }
    )
    return evaluated


def score_retention(prior_rows, k_head, candidate_head) -> dict:
    evaluated = _evaluate(
        prior_rows,
        k_head,
        candidate_head,
        expected=96,
        branches_per_case=12,
        target_root=old.OUTPUT,
    )
    groups = {
        "all": evaluated["cases"],
        "physical_best": [r for r in evaluated["cases"] if r["physical_best"]],
        "special_best": [r for r in evaluated["cases"] if r["special_best"]],
    }
    scores = {
        name: {
            "configurations": len(cases),
            "baseline_regret": fmean(r["baseline_regret"] for r in cases),
            "candidate_regret": fmean(r["candidate_regret"] for r in cases),
            "regression": fmean(r["candidate_regret"] - r["baseline_regret"] for r in cases),
        }
        for name, cases in groups.items()
        if cases
    }
    corpus = old.PRIVATE / "red-trainer-J-canonical-20260920-v1/audited-targets.json"
    historical = json.loads(corpus.read_bytes())
    catalog = old.lab.PokemonRedBattleCatalog()
    classes = {
        name: dict(Counter(classify_retention_record(r, catalog) for r in records))
        for name, records in historical["retention"].items()
    }
    count = sum(sum(group.values()) for group in classes.values())
    if count != 936:
        raise ValueError("historical retention record population changed")
    return {
        "comparable_damage": scores,
        "gate_passed": len(scores) == 3 and all(v["regression"] <= 0.02 for v in scores.values()),
        "historical_records_classified": count,
        "historical_classification": classes,
        "historical_utility_unit": "battle utility; not foe HP damage",
        "historical_corpus_sha256": old.sha(corpus),
        "old_train_target_sha256": old.sha(old.OUTPUT / "train-targets.json"),
    }


def run(*, preflight_only=False, version=1):
    output, seed, offsets, exclusions = experiment_config(version)
    if output.exists():
        raise ValueError("new single-use output identity already exists")
    cartridge, catalog, sources, k, admitted, rows, inventory = preflight(version=version)
    if preflight_only:
        print(
            json.dumps(
                {
                    "preflight": "ready",
                    "families": len(inventory["families"]),
                    "joint_root_level": inventory["joint_root_level"],
                }
            )
        )
        return
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("native plan requires clean committed source")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    source_pins = _source_pins()
    protected = [
        old.ROM,
        old.K,
        old.ADMITTED,
        old.OUTPUT / "PLAN.json",
        old.OUTPUT / "train-targets.json",
        old.OUTPUT / "holdout-targets.json",
        CROSSED / "PLAN.json",
        CROSSED / "RESULT.json",
        old.PRIVATE
        / "goal-manager-v1/model141-earned-story-campaign-20260921-v1/stage-328/final.state",
        old.PRIVATE
        / "goal-manager-v1/model141-integrated-play-20260921-v1/step-006/terminal.state",
    ]
    if version == 2:
        protected.extend(
            OUTPUT / name for name in ("PLAN.json", "FAILURE.json", "AUDIT_FAILURE.json")
        )
    protected.extend(
        source / name for source, _ in sources for name in ("source.state", "source.state.json")
    )
    protected.append(old.PRIVATE / "red-trainer-J-canonical-20260920-v1/audited-targets.json")
    pins = {str(path): old.sha(path) for path in protected}
    plan = {
        "schema": f"pokemon.red.interaction-damage-successor.v{version}",
        "source_commit": commit,
        "source_hashes": source_pins,
        "protected_inputs": pins,
        "rows": rows,
        "inventory": inventory,
        "seed": seed,
        "additional_excluded_pairs": sorted(exclusions),
        "fit_seed": FIT_SEED,
        "fits_max": 1,
        "fit_families": 24,
        "comparison_families": 16,
        "branches_max": 4320,
        "offsets": offsets,
        "elapsed_budget_seconds": MAX_ELAPSED,
        "ridge": 0.001,
        "regret_relative_improvement_min": 0.2,
        "regret_absolute_improvement_min": 0.01,
        "slice_regression_max": 0.03,
        "family_regression_max": 0.15,
        "root_regression_max": 0,
        "retention_regression_max": 0.02,
        "native_fits": 0,
        "learned_battle_actions": 0,
        "classification": "configuration development on reused TRAIN origins",
    }
    output.mkdir(mode=0o700)
    old.write_once(output / "PLAN.json", plan)
    args = argparse.Namespace(output=output, rom=old.ROM)
    start = time.monotonic()
    completed = []
    try:
        for row in rows:
            if row["role"] == "comparison":
                break
            target = _measure(args, row, sources, cartridge, k, commit, start, offsets=offsets)
            completed.append(target)
            print(json.dumps({"fit_configurations": len(completed), "id": row["id"]}), flush=True)
        if len(completed) != 72:
            raise ValueError("TRAIN fit inventory differs")
        old.write_once(output / "FIT_TARGETS.json", completed)
        old.write_once(
            output / "FIT_CLAIM.json",
            {
                "fit_attempts": 1,
                "plan_sha256": old.sha(output / "PLAN.json"),
                "fit_targets_sha256": old.sha(output / "FIT_TARGETS.json"),
            },
        )
        fit_model = fit_damage_interaction_head(
            [(row["vectors"], row["mean_damage"]) for row in completed],
            train_dataset_sha256=old.sha(output / "FIT_TARGETS.json"),
        )
        candidate = replace(admitted, damage_reference=fit_model)
        old.assert_untouched_components(admitted, candidate)
        if (
            old.TrainerPracticeThreeHeadModel.from_dict(candidate.to_dict()).to_dict()
            != candidate.to_dict()
        ):
            raise ValueError("candidate model does not round trip exactly")
        old.write_once(output / "candidate-model.json", candidate.to_dict())
        old.write_once(
            output / "FIT_RECEIPT.json",
            {
                "fit_attempts": 1,
                "fit_completed": 1,
                "train_configurations": 72,
                "fit_targets_sha256": old.sha(output / "FIT_TARGETS.json"),
                "candidate_sha256": old.sha(output / "candidate-model.json"),
                "optimizer": "single closed-form pairwise ridge solve, lambda=0.001",
                "untouched_components_exact": True,
                "frozen_before_comparison": True,
            },
        )
        print(
            json.dumps(
                {"fit_completed": 1, "candidate_sha256": old.sha(output / "candidate-model.json")}
            ),
            flush=True,
        )
        comparison = []
        for row in rows:
            if row["role"] != "comparison":
                continue
            target = _measure(args, row, sources, cartridge, k, commit, start, offsets=offsets)
            comparison.append(target)
            print(
                json.dumps({"comparison_configurations": len(comparison), "id": row["id"]}),
                flush=True,
            )
        old.write_once(output / "COMPARISON_TARGETS.json", comparison)
        baseline = k.move
        held = score_comparison(comparison, rows, baseline, fit_model, target_root=output)
        retention = score_retention(
            json.loads((old.OUTPUT / "train-targets.json").read_bytes()), baseline, fit_model
        )
        decision = (
            "screen_passed_for_astra_review"
            if held["gate_passed"] and retention["gate_passed"]
            else "rejected"
        )
        result = {
            "schema": f"pokemon.red.interaction-damage-result.v{version}",
            "decision": decision,
            "fit_attempts": 1,
            "fit_completed": 1,
            "fit": {"configurations": 72, **_costs(completed)},
            "comparison": {
                "configurations": 48,
                **_costs(comparison),
                "gate_passed": held["gate_passed"],
                "failures": held["failures"],
                "baseline_mean_regret": held["baseline_mean_regret"],
                "candidate_mean_regret": held["candidate_mean_regret"],
                "absolute_improvement": held["absolute_improvement"],
                "relative_improvement": held["relative_improvement"],
                "baseline_exact_best": held["baseline_exact_best"],
                "candidate_exact_best": held["candidate_exact_best"],
                "baseline_near_best": held["baseline_near_best"],
                "candidate_near_best": held["candidate_near_best"],
                "slices": held["slices"],
                "family_regressions": held["family_regressions"],
                "family_cluster_uncertainty": held["family_cluster_uncertainty"],
            },
            "retention": retention,
            "candidate_sha256": old.sha(output / "candidate-model.json"),
            "plan_sha256": old.sha(output / "PLAN.json"),
            "comparison_targets_sha256": old.sha(output / "COMPARISON_TARGETS.json"),
            "forced_training_actions": 4320,
            "learned_native_actions": 0,
            "promotions": 0,
            "story_inputs": 0,
            "elapsed_seconds": time.monotonic() - start,
            "protected_inputs_unchanged": all(
                old.sha(Path(path)) == digest for path, digest in pins.items()
            ),
            "source_unchanged": all(
                old.sha(ROOT / path) == digest for path, digest in source_pins.items()
            ),
        }
        if not result["protected_inputs_unchanged"] or not result["source_unchanged"]:
            raise ValueError("protected input or source changed during experiment")
        old.write_once(output / "COMPARISON_RESULT.json", held)
        old.write_once(output / "RESULT.json", result)
        print(
            json.dumps(
                {
                    "decision": decision,
                    "fit": result["fit"],
                    "comparison": {
                        k: v
                        for k, v in result["comparison"].items()
                        if k not in ("slices", "family_regressions")
                    },
                    "retention_passed": retention["gate_passed"],
                }
            ),
            flush=True,
        )
    except BaseException as error:
        old.write_once(
            output / "FAILURE.json",
            {
                "type": type(error).__name__,
                "message": str(error),
                "completed_configurations": len(completed),
                "elapsed_seconds": time.monotonic() - start,
                "fit_claimed": (output / "FIT_CLAIM.json").exists(),
            },
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--version", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    run(preflight_only=args.preflight, version=args.version)
