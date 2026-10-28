"""Disjoint later-turn qualification, one selector fit and unchanged native TRAIN gate."""

import argparse
import subprocess
import time
from copy import copy
from pathlib import Path

import run_red_effect_selector_combination as combined
from qualify_red_status_effect_trace import play_one
from red_status_root_coverage import crossed_recipes
from run_red_status_sequence_curriculum import capture_intermediate
from run_red_timing_effect_learning import timing_case

from pokemon_red_completion.red_balanced_status_features import project_balanced_status_moves

EFFECT_SHA = "8ac8c2d5376ebf0f6e9d31c3852c5b89b6dfd18ea87ab583c4606a6d5dde4105"
OLD_PLAN_SHA = "e788f80fe6f5046498cb9a32a44e0a25eb1fb2a11cbe6b4f6c768b59c825338c"
OLD_RESULT_SHA = "a3b62c68397e144ef8f1881469dcbdd84f1a04f246a24e4a88c02c4f4cb26368"
CELLS = {("heal", 0), ("heal", 1), ("rest", 0), ("confusion", 0), ("confusion", 1)}
PRIMER_SEED = 2026092213
FRESH_SEED = 2026092221
PREPARATION_PLAN_SHA = "959d9315cdeff36a1778070d0d545f1140c3768a03820171fba02a6af58e1493"
PREPARATION_RESULT_SHA = "1ee214a275efb88f8086706213c1f864caf2ff41a2b8fbb16224de0c652138cd"


def fresh_native_recipes(cartridge, roots):
    """Ten second-turn cells, not replacement draws from the failed qualification."""
    catalog = combined.lab.PokemonRedBattleCatalog()
    rows = []
    for template in crossed_recipes(cartridge, roots, seed=FRESH_SEED):
        family, contrast = template["family"], template["contrast"]
        variant = int(template["id"].split("-")[-2])
        if ((family, contrast) not in CELLS or variant not in (0, 1) or
                template["source_index"] != variant):
            continue
        # Occupied-confusion diagnostics act first. Fainting before a move stays
        # valid battle evidence but cannot measure conditional effect application.
        order = "opponent_first" if (family == "heal" and contrast == 1) else "actor_first"
        row = timing_case(template, cartridge, order)
        row["id"] = f"native-later-{FRESH_SEED}-{family}-{variant}-{contrast}"
        row["primer_move"] = 105 if family == "heal" else (
            109 if family == "confusion" and contrast == 1 else 92)
        if family == "confusion":
            row["effect_conditions"]["opponent_confusion_turns"] = 0
        # Toxic is a legal non-damaging setup action; no need for it to succeed.
        # It leaves clear confusion clear and lets opposing damage create injury.
        if row["primer_move"] == 92:
            p = row["practice"]
            actor = cartridge.species(int(p["actor_species_ref"].rsplit(":", 1)[1]))
            if 92 not in actor.teachable_moves_at_level(p["actor_level"]):
                raise ValueError("prospective actor cannot legally learn primer Toxic")
            ref = combined.lab.pokemon_red_move_ref(92)
            if not any(m["move_ref"] == ref for m in p["actor_moves"]):
                p["actor_moves"].append({"move_ref": ref, "pp": catalog.resolve_move(ref).max_pp})
        rows.append(row)
    if len(rows) != 10:
        raise ValueError("fresh later curriculum must contain ten fixed cases")
    return rows


def all_consumed_bindings(root):
    consumed = consumed_bindings(root)
    folder = root / "red-timing-selector-preparation-20260922-v1/combination"
    bind = combined.lab.common._binding
    if (bind(folder / "plan.json")["sha256"] != PREPARATION_PLAN_SHA or
            bind(folder / "result.json")["sha256"] != PREPARATION_RESULT_SHA):
        raise ValueError("failed preparation bindings differ")
    for row in combined.loop.load(folder / "plan.json")["later_cases"]:
        consumed.append({k: row[k] for k in ("capture_id", "manifest_sha256", "state_sha256")})
    return consumed


def primer_recipes(cartridge, roots):
    templates = crossed_recipes(cartridge, roots, seed=PRIMER_SEED)
    cases = []
    for index in (0, 1):
        template = next(r for r in templates if r["family"] == "heal" and r["contrast"] == 1
                        and r["source_index"] == index and
                        r["id"].endswith(f"-heal-{index}-1"))
        row = timing_case(template, cartridge, "opponent_first")
        row["id"] = f"selector-primer-{PRIMER_SEED}-{index}"
        cases.append(row)
    return cases


def derive_later_row(capture, folder, recipe, episode, primer_binding, *, target_slot=None):
    if episode["stop_reason"] != "player_turn_budget" or len(episode["decisions"]) != 1:
        raise ValueError("primer did not reach a later decision")
    observation = episode["final_observation"]
    lab = combined.lab
    view = project_balanced_status_moves(observation,
        lab.BattleFeatureProjector(lab.PokemonRedBattleCatalog()).project(observation))
    family, condition = recipe.get("family", "heal"), recipe.get("contrast", 1)
    slot = episode["decisions"][0]["move_slot"] if target_slot is None else target_slot
    vector = view.candidate_vectors[view.candidate_slots.index(slot)]
    flag_name = "choice.already_confused" if family == "confusion" else "choice.heal_full_hp"
    if (vector[combined.N.index(flag_name)] != condition or
            vector[combined.N.index("choice.player_asleep")] or
            not vector[combined.N.index("choice.effect." + family)]):
        raise ValueError("primer missed its awake effect/condition cell; no replacement")
    return {"capture": str(folder), "state_name": "intermediate.state",
            "manifest_sha256": capture.manifest_sha256,
            "state_sha256": capture.manifest.state_sha256,
            "capture_id": capture.manifest.capture_id, "root": recipe["root"],
            "family": family, "asleep": False, "slot": slot, "vector": list(vector),
            "primer": primer_binding}


def prepare_primers(args, frozen, sources, cartridge, commit, recipes):
    """Forced TRAIN setup turn only; no memory intervention after the opening capture."""
    lab, rows = combined.lab, []
    args.output.mkdir(mode=0o700)
    for recipe in recipes:
        capture = lab.materialize(args, recipe, recipe["source_index"], sources, cartridge, commit)
        directory = args.output / recipe["id"]
        primer_move = recipe.get("primer_move", 105)
        slot = next(i+1 for i, m in enumerate(recipe["practice"]["actor_moves"])
                    if m["move_ref"] == lab.pokemon_red_move_ref(primer_move))
        episode = play_one(args, capture, frozen, directory / "primer", cartridge, slot,
                           traced=False, allow_terminal=True)
        folder = directory / (recipe["id"] + "-later")
        folder.mkdir(mode=0o700)
        later = capture_intermediate(args, directory / "primer/final.state", folder,
                                     recipe["root"], commit, cartridge)
        if later is None:
            raise ValueError("primer ended without a usable later decision; no replacement")
        target_ref = lab.pokemon_red_move_ref(lab.FAMILIES[recipe["family"]])
        target_slot = next(i+1 for i, m in enumerate(recipe["practice"]["actor_moves"])
                          if m["move_ref"] == target_ref)
        row = derive_later_row(later, folder, recipe, episode,
            lab.common._binding(directory / "primer/episode.json"), target_slot=target_slot)
        lab.write(directory / "derived-later.json", row)
        rows.append(row)
    return rows


def consumed_bindings(root):
    folder = root / "red-effect-selector-combination-20260922-v1"
    bind = combined.lab.common._binding
    if (bind(folder / "plan.json")["sha256"] != OLD_PLAN_SHA or
            bind(folder / "result.json")["sha256"] != OLD_RESULT_SHA):
        raise ValueError("consumed qualification identity differs")
    old = combined.loop.load(folder / "plan.json")["later_cases"]
    consumed = []
    for row in old:
        path = Path(row["capture"])
        c = combined.loop.open_battle_scenario_capture(path / "capture.state",
                                                     path / "capture.state.json")
        if (c.manifest_sha256 != row["manifest_sha256"] or
                c.manifest.capture_id != row["capture_id"]):
            raise ValueError("consumed source differs")
        consumed.append({"manifest_sha256": c.manifest_sha256,
                         "state_sha256": c.manifest.state_sha256,
                         "capture_id": c.manifest.capture_id})
    if len(consumed) != 12:
        raise ValueError("expected twelve consumed diagnostics")
    return consumed


def select_unused(cells, sleepers, consumed):
    if set(cells) != CELLS:
        raise ValueError("pre-action condition inventory differs")
    identity_keys = ("manifest_sha256", "state_sha256", "capture_id")
    used = {k: {r[k] for r in consumed} for k in identity_keys}
    chosen, coverage = [], {}

    def select(pool, cap):
        result = []
        for row in sorted(pool, key=lambda r: (r["capture_id"], r["manifest_sha256"])):
            if any(row[k] in used[k] for k in identity_keys):
                continue
            result.append(dict(row))
            for k in identity_keys:
                used[k].add(row[k])
            if len(result) == cap:
                break
        return result

    for family, condition in sorted(CELLS):
        rows = select(cells[(family, condition)], 2)
        if not rows:
            raise ValueError(f"no unused state for {family}:{condition}")
        coverage[f"{family}:{condition}"] = len(rows)
        chosen.extend(rows)
    if len(chosen) < 8:
        raise ValueError("fewer than eight unused awake states")
    chosen.extend(select(sleepers, 2))
    for i, row in enumerate(chosen):
        row["id"] = f"timing-later-effect-{i:02d}"
    return chosen, coverage


def require_observed_cells(qualification):
    observed = set()
    for row in qualification["rows"]:
        if row["asleep_before_choice"] or row["evidence"]["kind"] != "observed":
            continue
        family = row["family"]
        name = "choice.already_confused" if family == "confusion" else "choice.heal_full_hp"
        flag = row["features"][combined.COMPACT_STATUS_NAMES.index(name)]
        observed.add((family, int(flag)))
    return {"observed_cells": sorted(f"{f}:{c}" for f, c in observed),
            "passed": observed == CELLS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "rom", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--fresh-native", action="store_true",
                        help="separate prospective packet; requires the owner's new run approval")
    args = parser.parse_args()
    began = time.monotonic()
    lab = combined.lab
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new packet and committed source required")
    consumed = (all_consumed_bindings if args.fresh_native else consumed_bindings)(args.root)
    frozen_path = args.root / "red-trainer-J-canonical-20260920-v1/candidate-model.json"
    effect_path = args.root / "red-timing-effect-learning-20260922-v1/fit.json"
    if (lab.common._binding(args.rom)["sha256"] != lab.common.ROM_SHA256 or
            lab.common._binding(frozen_path)["sha256"] != lab.K_SHA or
            lab.common._binding(effect_path)["sha256"] != EFFECT_SHA):
        raise ValueError("frozen primer inputs differ")
    frozen = combined.model(frozen_path)
    sources = sorted(lab.common._source_rows(args.root / "red-fresh-trainer-train-batch-20260917"),
                     key=lambda pair: pair[1]["source_id"])
    roots = [receipt["source_id"] for _, receipt in sources]
    if set(roots) != set(frozen.train_root_ids):
        raise ValueError("primer TRAIN ancestry differs")
    cartridge = lab.RedPracticeCartridge(args.rom.read_bytes())
    recipes = (fresh_native_recipes if args.fresh_native else primer_recipes)(cartridge, roots)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "preparation-plan.json", {"source_commit": commit,
        "primer_seed": FRESH_SEED if args.fresh_native else PRIMER_SEED,
        "fresh_native": args.fresh_native, "recipes": recipes, "consumed": consumed,
        "rom": lab.common._binding(args.rom), "frozen": lab.common._binding(frozen_path),
        "effect": lab.common._binding(effect_path),
        "sources": [lab.common._binding(p / "source.state.json") for p, _ in sources],
        "max_primer_episodes": len(recipes), "max_total_episodes": 140 + len(recipes),
        "max_total_frames": 15420000 + len(recipes)*5000, "max_fits": 1, "max_minutes": 90,
        "post_primer_memory_interventions": 0, "replacement_cases": 0})
    primer_args = copy(args)
    primer_args.output = args.output / "primers"
    try:
        derived = prepare_primers(primer_args, frozen, sources, cartridge, commit, recipes)
    except Exception as exc:
        lab.write(args.output / "failure.json", {"type": type(exc).__name__, "error": str(exc),
            "stage": "native_later_state_preparation", "fits": 0})
        raise
    lab.write(args.output / "derived-later.json", derived)

    def select(inputs):
        if args.fresh_native:
            cells, sleepers = {cell: [] for cell in CELLS}, []
            for row, recipe in zip(derived, recipes, strict=True):
                cells[(recipe["family"], recipe["contrast"])].append(row)
        else:
            cells, sleepers = combined.later_inventory(inputs)
            cells[("heal", 1)].extend(derived)
        return select_unused(cells, sleepers, consumed)

    run_args = copy(args)
    run_args.output = args.output / "combination"
    combined.run(run_args, effect_relative="red-timing-effect-learning-20260922-v1/fit.json",
        effect_sha=EFFECT_SHA, select=select, extra_later_gate=require_observed_cells,
        started_at=began,
        protocol={"schema": "pokemon.red.timing-selector-preparation.v1",
                  "consumed": consumed, "old_plan_sha256": OLD_PLAN_SHA,
                  "old_result_sha256": OLD_RESULT_SHA,
                  "preparation": lab.common._binding(args.output / "preparation-plan.json"),
                  "derived": lab.common._binding(args.output / "derived-later.json"),
                  "minimum_awake_labels": 8, "maximum_brier": .125,
                  "all_five_observed_cells_required": True,
                  "refits": 0, "campaign_access": False})


if __name__ == "__main__":
    main()
