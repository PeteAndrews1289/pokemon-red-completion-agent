"""Read-only admission report for one authenticated TRAIN trainer-choice set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.red_trainer_practice_admission import (
    inspect_trainer_practice_choices,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("choices", type=Path)
    args = parser.parse_args()
    capture = open_battle_scenario_capture(args.state, args.manifest)
    document = json.loads(args.choices.read_bytes())
    print(json.dumps(inspect_trainer_practice_choices(capture, document), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
