"""Prospective cartridge-backed TRAIN coverage probe, never natural qualification.

Recipes use catalog mechanics and fixed randomness, not failed DEVELOPMENT
encounters. Both learned policies see the same predeclared three-on-three cases.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
from copy import deepcopy
from pathlib import Path

import materialize_red_teacher_battle_practice as materializer
import run_fresh_red_trainer_curriculum as common
import run_red_trainer_practice_model as player

from pokemon_red_completion.battle_scenario_capture import OBSERVATION_SCHEMA_V2
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge

ROOT = Path(__file__).resolve().parents[1]
MOVE = "pokemon.red.gb.us.rev0:move"
SPECIES = "pokemon.red.gb.us.rev0:species"
CANDIDATE_SHA = "36a141fb456e81412d47f9d167f34a7a05ef401f8be583b6a6888b4f4ae9eda5"
FROZEN_SHA = "9f2aa62d01b72217931a3fab4b60e69522734f69b7eeab43b90e46498c34cbbc"


def broad_recipes(cartridge, *, seed=2026091901, count=24):
    catalog = PokemonRedBattleCatalog()
    rng = random.Random(seed)
    cases = []
    for index in range(count):
        level = (16, 32, 48, 64)[index % 4]
        legal = {}
        for species in cartridge.species_ids:
            moves = [
                m
                for m in cartridge.species(species).teachable_moves_at_level(level)
                if catalog.recovery_attack_supported(f"{MOVE}:{m:03d}")
            ]
            if len(moves) >= 2:
                legal[species] = moves
        members = []
        for slot, species in enumerate(rng.sample(sorted(legal), 6)):
            info = cartridge.species(species)
            available = list(legal[species])
            rng.shuffle(available)
            chosen = available[:4]
            moves = [
                {
                    "move_ref": f"{MOVE}:{m:03d}",
                    "pp": catalog.resolve_move(f"{MOVE}:{m:03d}").max_pp,
                }
                for m in chosen
            ]
            members.append(
                {
                    "party_slot": slot % 3 + 1,
                    "species_ref": f"{SPECIES}:{species:03d}",
                    "national_number": info.national_number,
                    "level": level,
                    "moves": moves,
                }
            )
        actor, foe = members[0], members[3]
        actor_species = int(actor["species_ref"].rsplit(":", 1)[1])
        foe_species = int(foe["species_ref"].rsplit(":", 1)[1])
        cases.append(
            {
                "actor_species_ref": actor["species_ref"],
                "actor_national_number": actor["national_number"],
                "actor_level": level,
                "actor_moves": actor["moves"],
                "actor_hp": max(
                    1,
                    cartridge.species(actor_species).neutral_stats(level).max_hp
                    * (1 if index % 3 == 0 else 2)
                    // 2,
                ),
                "party_reserves": members[1:3],
                "opponent_species_ref": foe["species_ref"],
                "opponent_national_number": foe["national_number"],
                "opponent_level": level,
                "opponent_moves": foe["moves"],
                "opponent_hp": cartridge.species(foe_species).trainer_stats(level).max_hp,
                "opponent_party_count": 3,
                "opponent_reserves": members[4:],
                "battle_kind": "trainer",
                "partition": "train",
            }
        )
    return cases


def summarize(evaluations):
    totals = {}
    for arm in ("frozen", "candidate"):
        rows = [r for r in evaluations if r["arm"] == arm]
        totals[arm] = {
            "battles": len(rows),
            "wins": sum(r["battle_won"] for r in rows),
            "faints": sum(r["metrics"]["party_faints"] for r in rows),
            "hp_lost": sum(r["metrics"]["party_hp_lost"] for r in rows),
            "decisions": sum(r["decision_count"] for r in rows),
        }
    complete = len(evaluations) == 48 and all(
        r["stop_reason"] in {"battle_won", "party_defeated"}
        and r["teacher_queries"]
        == r["memory_write_actions"]
        == r["metrics"]["invalid_action_failures"]
        == 0
        for r in evaluations
    )
    gates = {
        "all_terminal_unassisted": complete,
        "wins_no_regression": totals["candidate"]["wins"] >= totals["frozen"]["wins"],
        "faints_no_regression": totals["candidate"]["faints"] <= totals["frozen"]["faints"],
    }
    return {
        "totals": totals,
        "gates": gates,
        "probe_passed": all(gates.values()),
        "authority_promotions": 0,
        "natural_qualified": False,
    }


def run(args):
    if (
        args.output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("broad probe requires new output and committed code")
    for path, digest in (
        (args.candidate, CANDIDATE_SHA),
        (args.frozen, FROZEN_SHA),
        (args.rom, player.ROM_SHA256),
    ):
        if common._binding(path)["sha256"] != digest:
            raise ValueError("declared broad probe input differs")
    result = json.loads((args.candidate.parent / "result.json").read_bytes())
    if not result["train_qualified"] or result["model"] != common._binding(args.candidate):
        raise ValueError("candidate is not TRAIN qualified")
    sources = common._source_rows(args.batch)
    recipes = broad_recipes(RedPracticeCartridge(args.rom.read_bytes()))
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    args.output.mkdir(mode=0o700, parents=True)
    declaration = {
        "source_commit": commit,
        "seed": 2026091901,
        "candidate": common._binding(args.candidate),
        "frozen": common._binding(args.frozen),
        "recipes": recipes,
        "offsets": [0],
        "max_decisions": 160,
        "maximum_frames": 240000,
        "partition": "train",
        "natural_qualification": False,
        "authority_promotions": 0,
        "gates": (
            "all runs terminal, candidate wins >= frozen, candidate faints <= frozen; "
            "no fitting on probe"
        ),
    }
    common._write(args.output / "plan.json", declaration)
    evaluations = []
    for index, unbound in enumerate(recipes):
        directory = args.output / f"case-{index:02d}"
        directory.mkdir(mode=0o700)
        source, receipt = sources[index % len(sources)]
        recipe = deepcopy(unbound)
        recipe.update(
            root_lineage_id=receipt["source_id"],
            source_state_sha256=common._binding(source / "source.state")["sha256"],
        )
        path = directory / "materialize-plan.json"
        common._write(
            path,
            {
                "schema": materializer.TRAINER_SCHEMA,
                "source_commit": commit,
                "rom": common._binding(args.rom),
                "source_state": common._binding(source / "source.state"),
                "source_capture_manifest": common._binding(source / "source.state.json"),
                "practice": recipe,
                "observation_schema": OBSERVATION_SCHEMA_V2,
                "output": str(directory / "materialized"),
            },
        )
        materializer.run(path, check_only=True)
        materializer.run(path)
        state = directory / "materialized/assisted.state"
        for arm, model in (("frozen", args.frozen), ("candidate", args.candidate)):
            path = directory / f"{arm}-plan.json"
            common._write(
                path,
                {
                    "schema": player.OUTCOME_SCHEMA,
                    "source_commit": commit,
                    "rom": common._binding(args.rom),
                    "outcome_model": common._binding(model),
                    "capture_state": common._binding(state),
                    "capture_manifest": common._binding(state.with_suffix(".state.json")),
                    "max_decisions": 160,
                    "maximum_frames": 240000,
                    "opening_idle_frames": 0,
                    "output": str(directory / arm),
                },
            )
            player.run(path)
            outcome = json.loads((directory / arm / "outcome.json").read_bytes())
            outcome = {
                k: v for k, v in outcome.items() if k not in ("decisions", "final_observation")
            }
            evaluations.append({"case": index, "arm": arm, **outcome})
            print(
                json.dumps(
                    {
                        "case": index,
                        "arm": arm,
                        "won": outcome["battle_won"],
                        "stop_reason": outcome["stop_reason"],
                    }
                ),
                flush=True,
            )
        common._write(args.output / "progress.json", {"evaluations": evaluations})
    summary = summarize(evaluations)
    common._write(args.output / "summary.json", {"evaluations": evaluations, **summary})
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "batch", "candidate", "frozen", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
