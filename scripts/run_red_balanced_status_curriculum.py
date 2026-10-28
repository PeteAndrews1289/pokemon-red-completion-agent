"""One prospectively balanced, outcome-trained status comparison; no live promotion."""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from statistics import fmean

import numpy as np
import run_red_status_curriculum as lab
from run_red_status_sequence_curriculum import capture_intermediate

from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_balanced_status_features import (
    BALANCED_STATUS_NAMES,
    BALANCED_STATUS_SCHEMA,
    COMPACT_STATUS_NAMES,
    project_balanced_status_moves,
)
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_status_battle_features import STATUS_MOVE_NAMES, status_choice_slots
from pokemon_red_completion.red_status_practice import StatusPracticeConditions
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel
from pokemon_red_completion.red_trainer_practice_returns import tied_best_indices
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder

SEED = 2026092123
OFFSETS = (0, 4, 8)


def balanced_recipes(cartridge, *, seed=SEED):
    """Balance starting conditions, never selected outcomes or winning species."""
    catalog, rng, rows = PokemonRedBattleCatalog(), random.Random(seed), []
    identities = set()
    for family, move_id in lab.FAMILIES.items():
        for variant, level in enumerate((32, 44, 40)):
            pool = {}
            for species in cartridge.species_ids:
                damage = [m for m in cartridge.species(species).teachable_moves_at_level(level)
                          if catalog.recovery_attack_supported(pokemon_red_move_ref(m))
                          and 35 <= catalog.resolve_move(pokemon_red_move_ref(m)).power <= 80
                          and not catalog.resolve_move(pokemon_red_move_ref(m)).effect_flags
                          & {"multi_hit", "drain"}]
                if len(damage) >= 2:
                    pool[species] = damage
            actors = [s for s in pool if move_id in
                      cartridge.species(s).teachable_moves_at_level(level)]
            for _ in range(1000):
                actor = rng.choice(sorted(actors))
                enemy = rng.choice(sorted(pool))
                actor_moves = rng.sample(pool[actor], 2) + [move_id]
                enemy_moves = rng.sample(pool[enemy], 2)
                rng.shuffle(actor_moves)
                key = (actor, enemy, tuple(sorted(actor_moves)), tuple(sorted(enemy_moves)))
                foe_types = catalog.resolve_species(pokemon_red_species_ref(enemy)).types
                # Ordinary (nonimmune) contrasts before a separate immune case.
                if (key in identities or (family == "poison" and "poison" in foe_types)
                        or (family == "paralysis" and "ground" in foe_types)):
                    continue
                actor_types = catalog.resolve_species(pokemon_red_species_ref(actor)).types
                if not any(catalog.type_effectiveness(
                    catalog.resolve_move(pokemon_red_move_ref(m)).type_name, foe_types
                ) > 0 for m in actor_moves if m != move_id):
                    continue
                if not any(catalog.type_effectiveness(
                    catalog.resolve_move(pokemon_red_move_ref(m)).type_name, actor_types
                ) > 0 for m in enemy_moves):
                    continue
                identities.add(key)
                break
            else:
                raise ValueError("could not prospectively construct a diverse matchup")

            def moves(ids):
                return [{"move_ref": pokemon_red_move_ref(m),
                         "pp": catalog.resolve_move(pokemon_red_move_ref(m)).max_pp} for m in ids]

            a = cartridge.species(actor)
            base = {
                "actor_species_ref": pokemon_red_species_ref(actor),
                "actor_national_number": a.national_number,
                "actor_level": level,
                "actor_moves": moves(actor_moves),
                "opponent_level": level,
                "opponent_party_count": 1,
                "battle_kind": "trainer", "partition": "train",
            }
            for contrast in range(4):
                foe = enemy
                foe_moves = enemy_moves
                conditions = StatusPracticeConditions()
                own_ratio, foe_ratio = ((75, 100), (100, 100), (75, 8), (35, 85))[contrast]
                if contrast == 1:
                    if family in {"sleep", "paralysis", "poison"}:
                        conditions = replace(conditions, opponent_status="paralysis")
                    elif family == "accuracy":
                        conditions = replace(conditions, opponent_accuracy=-6)
                if contrast == 3:
                    if family in {"poison", "paralysis"}:
                        immune_type = "poison" if family == "poison" else "ground"
                        immune_pool = [s for s in pool if immune_type in
                                       catalog.resolve_species(pokemon_red_species_ref(s)).types]
                        foe = rng.choice(sorted(immune_pool))
                        foe_moves = rng.sample(pool[foe], 2)
                    elif family == "rest":
                        conditions = replace(conditions, player_status="burn")
                    elif family == "heal":
                        conditions = replace(conditions, player_status="poison")
                e = cartridge.species(foe)
                rows.append({
                    "id": f"balanced-{family}-{variant}-{contrast}",
                    "family": family, "contrast": contrast,
                    "role": "holdout" if variant == 2 else "train",
                    "native_followup": variant < 2 and contrast == 0,
                    "conditions": asdict(conditions),
                    "practice": {**deepcopy(base),
                        "actor_hp": max(1, a.neutral_stats(level).max_hp * own_ratio // 100),
                        "opponent_species_ref": pokemon_red_species_ref(foe),
                        "opponent_national_number": e.national_number,
                        "opponent_moves": moves(foe_moves),
                        "opponent_hp": max(1, e.trainer_stats(level).max_hp * foe_ratio // 100)},
                })
    return rows


def context_view(args, capture, cartridge, frozen):
    with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(capture.state_bytes)
        reader = PokemonRedStateReader(emulator)
        encoder = PokemonRedObservationEncoder(reader, True, cartridge.public_base_stats, True)
        raw = reader.read()
        prepared = prepare_red_battle_scenario(encoder, raw, allow_status_moves=True)
        obs = encoder.snapshot_from_raw(raw).to_dict()
        projected = project_balanced_status_moves(obs, prepared.features)
        legal = tuple(s + 1 for s, ok in zip(
            prepared.features.slot_indices, prepared.features.legal_mask, strict=True) if ok)
        slots = status_choice_slots(projected, legal, frozen.move)
        if len(slots) != 2:
            raise ValueError("balanced case needs exactly one status and one damage alternative")
        return slots, [projected.candidate_vectors[projected.candidate_slots.index(s)]
                       for s in slots]


def collect(args, capture, directory, cartridge, frozen, check_deadline):
    slots, vectors = context_view(args, capture, cartridge, frozen)
    returns = {s: [] for s in slots}
    for offset in OFFSETS:
        for slot in slots:
            check_deadline()
            result = lab.play(args, capture, frozen, directory / f"branch-{offset}-{slot}",
                              cartridge, first_slot=slot, offset=offset, horizon=8)
            obs = result["decisions"][0]["observation"]
            actual = project_balanced_status_moves(
                obs, BattleFeatureProjector(PokemonRedBattleCatalog()).project(obs))
            observed = [actual.candidate_vectors[actual.candidate_slots.index(s)] for s in slots]
            if vectors != observed:
                raise ValueError("matched branch features differ")
            returns[slot].append(lab.outcome_value(result))
    target = {"role": "train", "root": capture.manifest.root_lineage_id,
              "capture_id": capture.manifest.capture_id, "slots": slots, "vectors": vectors,
              "returns": [fmean(returns[s]) for s in slots], "timing_returns": returns}
    lab.write(directory / "target.json", target)
    return target


def fit_selector(targets, frozen, *, epochs=1800, temperature=3, seed=SEED,
                 training_objective="cross_entropy", initial=None):
    examples = []
    for target in targets:
        if target["role"] != "train":
            raise ValueError("withheld outcome cannot enter fit")
        returns = tuple(target["returns"])
        logits = np.asarray(returns) * temperature
        weights = np.exp(logits - logits.max())
        examples.append(TrainerHeadExample(
            tuple(tuple(v[len(STATUS_MOVE_NAMES):]) for v in target["vectors"]),
            tied_best_indices(returns), tuple(weights / weights.sum()), returns))
    compact_initial = None
    if initial is not None:
        if (initial.move.schema_id != BALANCED_STATUS_SCHEMA
                or np.count_nonzero(initial.move.weights1[:len(STATUS_MOVE_NAMES)])):
            raise ValueError("warm start requires a compact-only status model")
        compact_initial = TrainerHeadModel(
            "pokemon.core.battle.status-selector.compact.v1", COMPACT_STATUS_NAMES,
            initial.move.weights1[len(STATUS_MOVE_NAMES):], initial.move.bias1,
            initial.move.weights2, seed, initial.move.training_objective)
    compact = TrainerHeadModel.fit(
        schema_id="pokemon.core.battle.status-selector.compact.v1",
        feature_names=COMPACT_STATUS_NAMES, examples=examples, seed=seed,
        hidden_units=16, epochs=epochs, learning_rate=0.03,
        training_objective=training_objective, initial_model=compact_initial)
    weights = np.zeros((len(BALANCED_STATUS_NAMES), 16))
    weights[len(STATUS_MOVE_NAMES):] = compact.weights1
    head = TrainerHeadModel(BALANCED_STATUS_SCHEMA, BALANCED_STATUS_NAMES, weights,
                            compact.bias1, compact.weights2, seed, training_objective)
    candidate = replace(frozen, move=head, damage_reference=frozen.move,
                        train_capture_ids=(*frozen.train_capture_ids,
                                           *(t["capture_id"] for t in targets)))
    regrets = {"baseline": [], "candidate": []}
    for target in targets:
        damage = next(i for i, row in enumerate(target["vectors"])
                      if row[STATUS_MOVE_NAMES.index("move.category.status")] == 0)
        chosen = head.predict_index(target["vectors"])
        for key, index in (("baseline", damage), ("candidate", chosen)):
            regrets[key].append(max(target["returns"]) - target["returns"][index])
    return candidate, {k + "_regret": fmean(v) for k, v in regrets.items()}


def choice_diagnostics(episode):
    rows = []
    for step in episode["decisions"]:
        if step["kind"] != "attack":
            continue
        obs = step["observation"]
        projected = project_balanced_status_moves(
            obs, BattleFeatureProjector(PokemonRedBattleCatalog()).project(obs))
        index = projected.candidate_slots.index(step["move_slot"])
        values = dict(zip(BALANCED_STATUS_NAMES, projected.candidate_vectors[index], strict=True))
        if not values["choice.status"]:
            continue
        concerns = [name for name in (
            "major_status_occupied", "poison_type_immune", "electric_paralysis_type_immune",
            "already_confused", "accuracy_floor", "heal_full_hp") if values[f"choice.{name}"]]
        rows.append({"decision": step["decision_index"] if "decision_index" in step else len(rows),
                     "slot": step["move_slot"], "concerns": concerns,
                     "effect": [f for f in lab.FAMILIES if values[f"choice.effect.{f}"]]})
    return rows


def run(args):
    if args.output.exists() or subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new output and committed code required")
    if (lab.common._binding(args.frozen)["sha256"] != lab.K_SHA
            or lab.common._binding(args.rom)["sha256"] != lab.common.ROM_SHA256):
        raise ValueError("frozen model or cartridge differs")
    frozen = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.frozen.read_bytes()))
    sources = lab.common._source_rows(args.batch)
    if {receipt["source_id"] for _, receipt in sources} != set(frozen.train_root_ids):
        raise ValueError("declared TRAIN ancestry differs")
    cartridge = RedPracticeCartridge(args.rom.read_bytes())
    rows = balanced_recipes(cartridge)
    assert len(rows) == 96 and sum(r["role"] == "train" for r in rows) == 64
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    started = time.monotonic()

    def check_deadline():
        if time.monotonic() - started > 3600:
            raise TimeoutError("frozen 60-minute experiment deadline")

    lab.write(args.output / "plan.json", {
        "source_commit": commit, "seed": SEED, "recipes": rows,
        "frozen": lab.common._binding(args.frozen), "rom": lab.common._binding(args.rom),
        "sources": [lab.common._binding(p / "source.state.json") for p, _ in sources],
        "offsets": OFFSETS, "branch_turns": 8, "max_episodes": 560,
        "max_fits": 1, "epochs": 1800, "learning_rate": 0.03, "hidden_units": 16,
        "feature_schema": BALANCED_STATUS_SCHEMA, "fitted_features": COMPACT_STATUS_NAMES,
        "independent_heldout_roots": 0, "authority_promotions": 0,
        "gates": {"wins_no_regression": True, "useful_status_choice_required": True,
                  "invalid_actions": 0, "concerning_status_selections": 0},
    })
    targets, censored = [], []
    try:
        for i, row in enumerate(rows):
            if row["role"] != "train":
                continue
            check_deadline()
            capture = lab.materialize(args, row, i, sources, cartridge, commit)
            directory = args.output / row["id"]
            target = collect(args, capture, directory, cartridge, frozen, check_deadline)
            targets.append(target)
            print(json.dumps({"context": row["id"], "returns": target["returns"]}), flush=True)
            if not row["native_followup"]:
                continue
            slot = next(i + 1 for i, move in enumerate(row["practice"]["actor_moves"])
                        if move["move_ref"] == pokemon_red_move_ref(lab.FAMILIES[row["family"]]))
            check_deadline()
            result = lab.play(args, capture, frozen, directory / "opening", cartridge,
                              first_slot=slot, horizon=1)
            destination = args.output / (row["id"] + "-post")
            destination.mkdir(mode=0o700)
            post = capture_intermediate(args, directory / "opening/final.state", destination,
                                        capture.manifest.root_lineage_id, commit, cartridge)
            if post is None:
                censored.append({"case": row["id"], "stop": result["stop_reason"]})
            else:
                targets.append(collect(args, post, destination, cartridge, frozen, check_deadline))
        lab.write(args.output / "collection.json", {"contexts": len(targets), "censored": censored})
        check_deadline()
        candidate, regret = fit_selector(targets, frozen)
        lab.write(args.output / "candidate-model.json", candidate.to_dict())
        lab.write(args.output / "fit.json", {
            "fits": 1, "examples": len(targets), **regret,
            "candidate": lab.common._binding(args.output / "candidate-model.json"),
            "damage_reference_equal": canonical_sha256(candidate.damage_reference.to_dict())
            == canonical_sha256(frozen.move.to_dict())})
        evaluations = []
        for i, row in enumerate(rows):
            if row["role"] != "holdout":
                continue
            check_deadline()
            capture = lab.materialize(args, row, i, sources, cartridge, commit)
            for arm, model, status in (("frozen", frozen, False), ("candidate", candidate, True)):
                check_deadline()
                episode = lab.play(args, capture, model, args.output / row["id"] / arm,
                                   cartridge, status=status)
                result = {"case": row["id"], "arm": arm, "won": episode["battle_won"],
                          "stop": episode["stop_reason"], "metrics": episode["metrics"],
                          "decisions": episode["decision_count"],
                          "return": lab.outcome_value(episode),
                          "status_choices": choice_diagnostics(episode) if status else []}
                evaluations.append(result)
                print(json.dumps(result), flush=True)
        wins = {arm: sum(e["won"] for e in evaluations if e["arm"] == arm)
                for arm in ("frozen", "candidate")}
        concerns = sum(bool(c["concerns"]) for e in evaluations if e["arm"] == "candidate"
                       for c in e["status_choices"])
        # A paired win/resource advantage, not mere status use, is needed for usefulness.
        baselines = {e["case"]: e for e in evaluations if e["arm"] == "frozen"}
        useful = sum(e["won"] and e["return"] > baselines[e["case"]]["return"] + 0.05
                     and any(not c["concerns"] for c in e["status_choices"])
                     for e in evaluations if e["arm"] == "candidate")
        lab.write(args.output / "result.json", {
            "evaluations": evaluations, "wins": wins, "fits": 1,
            "concerning_status_selections": concerns, "improved_won_cases_with_status": useful,
            "bounded_screen_passed": wins["candidate"] >= wins["frozen"] and concerns == 0
            and useful > 0, "authority_promotions": 0, "independent_heldout_roots": 0,
            "natural_qualified": False, "elapsed_seconds": time.monotonic() - started})
    except Exception as error:
        lab.write(args.output / "failure.json", {"type": type(error).__name__, "error": str(error)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "batch", "frozen", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
