"""Digest-bound, read-only battle risk review; no emulator or policy changes."""

import argparse
import json
from pathlib import Path

from pokemon_red_completion.battle_choice_review import review_battle_choices
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = review_battle_choices(
        args.episode.read_bytes(), expected_sha256=args.sha256, catalog=PokemonRedBattleCatalog()
    )
    # Never replace an earlier diagnosis or an input episode.
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"decision_count": report["decision_count"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
