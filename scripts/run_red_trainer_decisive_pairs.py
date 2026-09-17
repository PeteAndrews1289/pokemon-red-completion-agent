"""Follow the noisy pilot with four prospective one-foe type-contrast pairs.

Within each pair, the actor, moves, stats and opponent behavior stay fixed.
Only the opponent species changes. All captures are TRAIN and are measured at
the same five declared timing offsets; earlier contexts are read, not replayed.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import run_red_trainer_distinct_pilot as pilot

OPPONENT_PAIRS = (
    ((169, 74), (177, 7)),  # Pikachu: Geodude versus Squirtle.
    ((169, 74), (153, 1)),  # Squirtle: Geodude versus Bulbasaur.
    ((177, 7), (176, 4)),  # Bulbasaur: Squirtle versus Charmander.
    ((153, 1), (177, 7)),  # Charmander: Bulbasaur versus Squirtle.
)


def decisive_cases(
    templates: tuple[dict[str, object], ...],
) -> tuple[tuple[int, str, dict[str, object]], ...]:
    if len(templates) != 4:
        raise ValueError("decisive pilot needs four original MAIN templates")
    cases = []
    for root_index, template in enumerate(templates):
        for label, (species_id, national_number) in zip(
            ("a", "b"), OPPONENT_PAIRS[root_index], strict=True
        ):
            practice = deepcopy(template)
            practice["actor_hp"] = 80
            practice["actor_stats"] = {
                "max_hp": 100,
                "attack": 90,
                "defense": 80,
                "speed": 100,
                "special": 90,
            }
            practice["opponent_species_ref"] = f"pokemon.red.gb.us.rev0:species:{species_id:03d}"
            practice["opponent_national_number"] = national_number
            practice["opponent_level"] = 25
            practice["opponent_hp"] = 30
            practice["opponent_moves"] = [{"move_ref": "pokemon.red.gb.us.rev0:move:033", "pp": 35}]
            practice["opponent_party_count"] = 1
            practice.pop("opponent_reserves", None)
            cases.append((root_index, f"decisive-{label}", practice))
    return tuple(cases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--frozen-model", type=Path, required=True)
    parser.add_argument(
        "--main-template",
        dest="main_templates",
        type=Path,
        action="append",
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    print(
        json.dumps(
            pilot.run(
                parser.parse_args(),
                recipe_builder=decisive_cases,
                predecessor_contexts=36,
                result_schema="pokemon.red.trainer-decisive-pair-result.v1",
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
