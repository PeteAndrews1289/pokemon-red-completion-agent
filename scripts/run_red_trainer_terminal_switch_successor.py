"""Prospective two-action terminal HP pairs with competent reserve attacks."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import run_red_trainer_terminal_hp_pairs as pilot

MOVE = "pokemon.red.gb.us.rev0:move"


def successor_cases(
    templates: tuple[dict[str, object], ...],
) -> tuple[tuple[int, str, dict[str, object]], ...]:
    if len(templates) != 2:
        raise ValueError("successor needs two frozen matchup templates")
    reserve = templates[0].get("party_reserves")
    if not isinstance(reserve, list) or not reserve:
        raise ValueError("successor needs a Squirtle reserve template")
    # Each supported reserve move can damage the one opponent effectively.
    stronger_reserve = deepcopy(reserve[0])
    stronger_reserve["moves"] = [
        {"move_ref": f"{MOVE}:057", "pp": 15},  # Surf
        {"move_ref": f"{MOVE}:061", "pp": 20},  # BubbleBeam
    ]
    cases = []
    for root_index, name, practice in pilot.terminal_hp_cases(templates):
        practice["party_reserves"] = [deepcopy(stronger_reserve)]
        if root_index == 3:
            practice["actor_moves"] = [
                {"move_ref": f"{MOVE}:053", "pp": 15},  # Flamethrower
                {"move_ref": f"{MOVE}:052", "pp": 25},  # Ember
            ]
        cases.append((root_index, name, practice))
    return tuple(cases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--frozen-model", type=Path, required=True)
    parser.add_argument("--template", dest="templates", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(pilot.run(
        parser.parse_args(), recipe_builder=successor_cases,
        matched_choices="opening_move_one_vs_switch_two",
    ), sort_keys=True))


if __name__ == "__main__":
    main()
