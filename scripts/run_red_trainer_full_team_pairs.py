"""Measure eight TRAIN-only five-on-five HP contrasts from four fresh origins.

The two cases per origin differ only in actor lead HP. Species, moves, levels,
reserves, opponent order and timing offsets remain identical within each pair.
Earlier 44 contexts are authenticated without replay. DEVELOPMENT is unopened.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import run_red_trainer_distinct_pilot as pilot

MOVE = "pokemon.red.gb.us.rev0:move"
SPECIES = "pokemon.red.gb.us.rev0:species"
EXTRA_ACTOR_SPECIES = (
    ((176, 4, ((52, 25), (10, 35))), (169, 74, ((88, 15), (33, 35)))),
    ((176, 4, ((52, 25), (10, 35))), (169, 74, ((88, 15), (33, 35)))),
    ((84, 25, ((85, 15), (98, 30))), (169, 74, ((88, 15), (33, 35)))),
    ((177, 7, ((55, 25), (33, 35))), (169, 74, ((88, 15), (33, 35)))),
)
EXTRA_OPPONENT_SPECIES = (
    ((153, 1, ((22, 10), (33, 35))), (176, 4, ((52, 25), (10, 35)))),
    ((84, 25, ((85, 15), (98, 30))), (153, 1, ((22, 10), (33, 35)))),
    ((177, 7, ((55, 25), (33, 35))), (176, 4, ((52, 25), (10, 35)))),
    ((169, 74, ((88, 15), (33, 35))), (177, 7, ((55, 25), (33, 35)))),
)


def _reserve(slot: int, definition: tuple[int, int, tuple[tuple[int, int], ...]]) -> dict:
    species, national, moves = definition
    return {
        "party_slot": slot,
        "species_ref": f"{SPECIES}:{species:03d}",
        "national_number": national,
        "level": 32,
        "moves": [{"move_ref": f"{MOVE}:{move:03d}", "pp": pp} for move, pp in moves],
    }


def full_team_cases(
    templates: tuple[dict[str, object], ...],
) -> tuple[tuple[int, str, dict[str, object]], ...]:
    if len(templates) != 4:
        raise ValueError("full-team pilot needs four original MAIN templates")
    cases = []
    for root_index, template in enumerate(templates):
        base = deepcopy(template)
        actor_reserves = base.get("party_reserves")
        enemy_reserves = base.get("opponent_reserves")
        if (
            not isinstance(actor_reserves, list)
            or len(actor_reserves) != 2
            or not isinstance(enemy_reserves, list)
            or len(enemy_reserves) != 2
        ):
            raise ValueError("full-team pair needs two original reserves per side")
        base["party_reserves"] = actor_reserves + [
            _reserve(slot, definition)
            for slot, definition in enumerate(EXTRA_ACTOR_SPECIES[root_index], 4)
        ]
        base["opponent_reserves"] = enemy_reserves + [
            _reserve(slot, definition)
            for slot, definition in enumerate(EXTRA_OPPONENT_SPECIES[root_index], 4)
        ]
        base["opponent_party_count"] = 5
        base["opponent_species_ref"] = f"{SPECIES}:106"
        base["opponent_national_number"] = 66
        base["opponent_level"] = 35
        base["opponent_hp"] = 80
        base["opponent_moves"] = [
            {"move_ref": f"{MOVE}:002", "pp": 25},
            {"move_ref": f"{MOVE}:067", "pp": 20},
        ]
        for label, hp in (("healthy", template["actor_hp"]), ("critical", 8)):
            practice = deepcopy(base)
            practice["actor_hp"] = hp
            cases.append((root_index, label, practice))
    return tuple(cases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--frozen-model", type=Path, required=True)
    parser.add_argument(
        "--main-template", dest="main_templates", type=Path, action="append", required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    print(
        json.dumps(
            pilot.run(
                parser.parse_args(),
                recipe_builder=full_team_cases,
                predecessor_contexts=44,
                result_schema="pokemon.red.trainer-full-team-pair-result.v1",
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
