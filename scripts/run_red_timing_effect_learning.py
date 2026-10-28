"""One prospective TRAIN-only timing/condition effect experiment; no actor promotion."""

import argparse
import json
import subprocess
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path

import run_red_measured_effect_learning as measured
import run_red_status_curriculum as lab
from qualify_red_status_effect_trace import play_one
from red_status_root_coverage import crossed_recipes

SEED = 2026092207
SCHEMA = "pokemon.red.timing-effect-learning.v1"
ORDERS = ("actor_first", "opponent_first")
SPEED = measured.COMPACT_STATUS_NAMES.index("choice.player_speed_margin")


def timing_case(template, cartridge, order):
    """Choose native, priority-zero opponents from metadata, never measured outcomes."""
    if order not in ORDERS:
        raise ValueError("unknown turn order")
    row = deepcopy(template)
    p = row["practice"]
    catalog = lab.PokemonRedBattleCatalog()
    own = cartridge.species(int(p["actor_species_ref"].rsplit(":", 1)[1])).neutral_stats(
        p["actor_level"])
    own_types = catalog.resolve_species(p["actor_species_ref"]).types
    variant = int(row["id"].split("-")[-2])
    target = (.15, .60, .35)[variant] * (1 if order == "actor_first" else -1)
    options = []
    for delta in (0, -4, 4, -8, 8):
        level = p["actor_level"] + delta
        for species in cartridge.species_ids:
            enemy = cartridge.species(species)
            stats = enemy.trainer_stats(level)
            margin = own.speed / stats.speed - 1
            if (not .10 <= abs(margin) <= .80 or (margin > 0) != (order == "actor_first")
                    or stats.attack > 1.5 * own.defense or stats.special > 1.5 * own.special):
                continue
            for move in enemy.teachable_moves_at_level(level):
                ref = lab.pokemon_red_move_ref(move)
                semantic = catalog.resolve_move(ref)
                if (catalog.move_effect(ref) == "NO_ADDITIONAL_EFFECT"
                        and 35 <= semantic.power <= 60 and semantic.priority == 0
                        and semantic.accuracy >= .95
                        and 0 < catalog.type_effectiveness(semantic.type_name, own_types) <= 1):
                    options.append((abs(margin-target), abs(delta), species, move, level, margin))
    if not options:
        raise ValueError("no prospective native timing opponent")
    _, _, species, move, level, margin = min(options)
    enemy = cartridge.species(species)
    ref = lab.pokemon_red_move_ref(move)
    p.update(opponent_species_ref=f"pokemon.red.gb.us.rev0:species:{species:03d}",
             opponent_national_number=enemy.national_number, opponent_level=level,
             opponent_hp=enemy.trainer_stats(level).max_hp,
             opponent_moves=[{"move_ref": ref, "pp": catalog.resolve_move(ref).max_pp}])
    if row["family"] == "confusion":
        p["actor_hp"] = own.max_hp
    if row["family"] == "rest" and row["contrast"] == 0:
        row["conditions"]["player_status"] = "burn"
    row.update(id=f"timing-{SEED}-{row['id']}-{order}", order=order,
               planned_speed_margin=margin)
    return row


def recipes(cartridge, roots):
    cases = [timing_case(row, cartridge, order)
             for row in crossed_recipes(cartridge, roots, seed=SEED)
             if row["family"] in measured.FAMILIES and row["contrast"] in (0, 1)
             for order in ORDERS]
    if (len(cases) != 84 or len({r["id"] for r in cases}) != 84 or
            sum(r["role"] == "train" for r in cases) != 72):
        raise ValueError("timing packet size differs")
    return cases


def timing_evidence(row, recipe, episode, trace):
    """Setup order is checked against observable native-stat speed, not a target label."""
    margin = row["features"][SPEED]
    expected = max(-1., min(1., recipe["planned_speed_margin"]))
    if abs(margin - expected) > 1e-12 or (margin > 0) != (recipe["order"] == "actor_first"):
        raise ValueError("observed speed differs from planned native order")
    step = episode["decisions"][0]
    own = step["observation"]["features"]["party"]["lead"]
    if own["hp"] != recipe["practice"]["actor_hp"]:
        raise ValueError("decision HP differs from prospective setup")
    records = [r for r in trace["records"] if r["before"]["turn"] == 0 and
               r["before"]["move"] == lab.FAMILIES[recipe["family"]]]
    entry_hp = records[0]["before"]["player_hp"] if len(records) == 1 else None
    return {"order": recipe["order"], "visible_speed_margin": margin,
            "decision_hp": own["hp"], "effect_entry_hp": entry_hp,
            "damage_before_effect": entry_hp is not None and entry_hp < own["hp"],
            "basis": "native_stats_and_priority_zero;hp_change_inside_authenticated_trace"}


def require_timing_support(rows, roots):
    measured.support(rows, roots)
    counts = Counter()
    for row in rows:
        order = row["timing"]["order"]
        if order not in ORDERS or row["family"] not in measured.FAMILIES:
            raise ValueError("unsupported timing cell")
        margin = row["features"][SPEED]
        if (abs(margin) < .099999 or (margin > 0) != (order == "actor_first") or
                margin != row["timing"]["visible_speed_margin"]):
            raise ValueError("missing observed turn-order coverage")
        index = measured.COMPACT_STATUS_NAMES.index(measured.CONDITION[row["family"]])
        condition = row["features"][index]
        if condition not in (0., 1.):
            raise ValueError("invalid condition feature")
        if row["evidence"]["kind"] == "observed":
            counts[(row["root"], row["family"], order, int(condition))] += 1
    required = {(root, family, order, condition) for root in roots
                for family in measured.FAMILIES for order in ORDERS for condition in (0, 1)}
    if set(counts) != required:
        raise ValueError("missing observed timing/condition cells")
    full_hp_index = measured.COMPACT_STATUS_NAMES.index("choice.heal_full_hp")
    for root in roots:
        for family in ("heal", "rest"):
            if not any(r["root"] == root and r["family"] == family and
                       r["features"][full_hp_index] == 1
                       and r["timing"]["order"] == "opponent_first"
                       and r["timing"]["damage_before_effect"]
                       and r["evidence"]["kind"] == "observed"
                       and r["evidence"]["application_success"] == 1 for r in rows):
                raise ValueError(f"missing measured full-HP timing reversal: {root}:{family}")
    return {"observed_cells": len(counts), "counts": {":".join(map(str, k)): v
                                                    for k, v in sorted(counts.items())}}


def fit_once(rows, roots):
    require_timing_support(rows, roots)
    return measured.fit_once(rows, roots)


def evaluate(rows, roots, fit):
    if any(r["role"] != "holdout" for r in rows) or set(roots) & set(fit["train_roots"]):
        raise ValueError("evaluation requires disjoint reserved rows")
    support = require_timing_support(rows, roots)
    all_rows = measured.metrics(rows, fit)
    groups = {"family:" + family: measured.metrics([r for r in rows if r["family"] == family], fit)
              for family in measured.FAMILIES}
    groups.update({"order:" + order: measured.metrics(
        [r for r in rows if r["timing"]["order"] == order], fit) for order in ORDERS})
    passed = (all_rows["brier"] <= .125 and
              all_rows["brier"] <= .9 * all_rows["constant_brier"] and
              all(m["brier"] <= m["constant_brier"] for m in groups.values()))
    return {"support": support, "overall": all_rows, "groups": groups,
            "diagnostic_pass": passed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "rom", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new output and committed source required")
    frozen_path = args.root / "red-trainer-J-canonical-20260920-v1/candidate-model.json"
    if (lab.common._binding(args.rom)["sha256"] != lab.common.ROM_SHA256 or
            lab.common._binding(frozen_path)["sha256"] != lab.K_SHA):
        raise ValueError("cartridge or frozen K differs")
    frozen = lab.TrainerPracticeThreeHeadModel.from_dict(json.loads(frozen_path.read_bytes()))
    sources = sorted(lab.common._source_rows(args.root / "red-fresh-trainer-train-batch-20260917"),
                     key=lambda p: p[1]["source_id"])
    roots = [r["source_id"] for _, r in sources]
    if set(roots) != set(frozen.train_root_ids):
        raise ValueError("TRAIN ancestry differs")
    cartridge = lab.RedPracticeCartridge(args.rom.read_bytes())
    cases = recipes(cartridge, roots)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "plan.json", {"schema": SCHEMA, "source_commit": commit,
        "seed": SEED, "cases": cases, "rom": lab.common._binding(args.rom),
        "sources": [lab.common._binding(p / "source.state.json") for p, _ in sources],
        "frozen": lab.common._binding(frozen_path), "max_episodes": 84, "max_frames": 420000,
        "max_minutes": 90, "max_fits": 1, "feature_names": measured.COMPACT_STATUS_NAMES,
        "max_iterations": 500, "l2_coefficient": .001, "ftol": 1e-12,
        "held_root": roots[-1], "actor_promotions": 0,
        "gate": "coverage;held_brier<=.125;<=.9*train_prevalence_baseline;"
                "no_family_or_order_regression"})
    started, episodes, frames, fits, rows = time.monotonic(), 0, 0, 0, []

    def collect(role):
        nonlocal episodes, frames
        for recipe in cases:
            if recipe["role"] != role:
                continue
            if time.monotonic() - started > 5400 or episodes >= 84 or frames >= 420000:
                raise TimeoutError("timing packet budget exhausted")
            capture = lab.materialize(args, recipe, recipe["source_index"], sources,
                                      cartridge, commit)
            selected_ref = lab.pokemon_red_move_ref(lab.FAMILIES[recipe["family"]])
            slot = next(i+1 for i, m in enumerate(recipe["practice"]["actor_moves"])
                        if m["move_ref"] == selected_ref)
            episodes += 1
            directory = args.output / recipe["id"] / "traced"
            episode = play_one(args, capture, frozen, directory, cartridge, slot,
                               traced=True, allow_terminal=True)
            frames += episode["frames_executed"]
            if frames > 420000 or time.monotonic() - started > 5400:
                raise TimeoutError("timing packet budget exhausted after retained turn")
            row = measured.authenticate_row(directory, capture, recipe, allow_terminal=True)
            trace = json.loads((directory / "effect-trace.json").read_bytes())
            row["timing"] = timing_evidence(row, recipe, episode, trace)
            lab.write(args.output / recipe["id"] / "measured.json", row)
            rows.append(row)
            print(json.dumps({"case": recipe["id"], "label": row["evidence"]}), flush=True)

    try:
        collect("train")
        lab.write(args.output / "training.json", {"rows": rows})
        support = require_timing_support(rows, roots[:-1])
        lab.write(args.output / "support.json", support)
        fits += 1
        fit = fit_once(rows, roots[:-1])
        fit["training"] = lab.common._binding(args.output / "training.json")
        lab.write(args.output / "fit.json", fit)
        if not fit["success"]:
            raise ValueError("single fit failed; no reserved cases opened")
        binding = lab.common._binding(args.output / "fit.json")
        collect("holdout")
        lab.write(args.output / "inventory.json", {"rows": rows})
        result = evaluate([r for r in rows if r["role"] == "holdout"], roots[-1:], fit)
        if binding != lab.common._binding(args.output / "fit.json"):
            raise ValueError("effect predictor changed during evaluation")
        lab.write(args.output / "result.json", {"schema": SCHEMA, "episodes": episodes,
            "frames": frames, "seconds": time.monotonic() - started, "fits": fits,
            "fit": binding, "inventory": lab.common._binding(args.output / "inventory.json"),
            "train": measured.metrics([r for r in rows if r["role"] == "train"], fit),
            "held": result, "label_kinds": dict(Counter(r["evidence"]["kind"] for r in rows)),
            "learned_battle_choices": 0, "actor_promotions": 0, "natural_transfer": False})
    except Exception as exc:
        lab.write(args.output / "failure.json", {"type": type(exc).__name__, "error": str(exc),
            "episodes_started": episodes, "completed_frames": frames, "measured_rows": len(rows),
            "fits_started": fits})
        raise


if __name__ == "__main__":
    main()
