"""Run the Mansion training block alone, from a captured state.

The point of the capture is this script. Twelve runs in one session each spent
about six minutes replaying 275 checkpoints to reach the same thirty seconds of
game, and every one of them was iterating on a single menu. Loading a state
puts us at that menu directly.

This is not a substitute for a full run. A state captured mid-route is a real
starting point -- actual memory, not a fake's idea of it -- but it is one
starting point, and a change that works from here still has to survive the
route reaching here on its own. Use this to iterate, then confirm with
``cli play``.

Usage::

    POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <path>.state
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.observation import PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.red_party import PokemonRedPartyReader  # noqa: E402
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="a captured state file")
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    args = parser.parse_args(argv)

    emulator = PyBoyAdapter(resolve_rom_path(args.rom))
    emulator.start()
    try:
        emulator.load_state(args.state)
        reader = PokemonRedStateReader(emulator)
        raw = reader.read()
        party = PokemonRedPartyReader(emulator).read()

        print(f"resumed on map {raw.map_id} at {(raw.player_x, raw.player_y)!r}")
        print(f"party levels: {party.levels}")
        print(f"party species: {tuple(hex(s) for s in party.species_ids())}")

        from pokemon_red_completion.blaine import (
            DIGLETTS_CAVE_TRAINING_VENUE,
            MANSION_TRAINING_VENUE,
        )

        for venue in (MANSION_TRAINING_VENUE, DIGLETTS_CAVE_TRAINING_VENUE):
            print(f"venue available: {venue.describe()}")
        return 0
    finally:
        emulator.close()


if __name__ == "__main__":
    raise SystemExit(main())
