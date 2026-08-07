"""Run the Mansion training block alone, from a captured state.

This is what the capture is for. Twelve runs in one session each spent about
six minutes replaying 275 checkpoints to reach the same thirty seconds of game,
and every one was iterating on a single menu. Loading a state reaches that menu
in about a second.

It is not a substitute for a full run. A captured state is a real starting
point -- actual memory, not a fake's idea of it -- but it is *one* starting
point, and a change that works from here still has to survive the route
arriving here on its own. Iterate here, confirm with ``cli play``.

Usage::

    POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <path>.state
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.observation import PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.opening import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.red_party import PokemonRedPartyReader  # noqa: E402
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="a captured state file")
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument(
        "--swap-only",
        action="store_true",
        help="exercise just the party swap rather than the whole training block",
    )
    args = parser.parse_args(argv)

    emulator = PyBoyAdapter(resolve_rom_path(args.rom))
    emulator.start()
    try:
        emulator.load_state(args.state)
        reader = PokemonRedStateReader(emulator)
        actions = CountingExecutor(
            FrameSafeExecutor(emulator, DEFAULT_NEW_GAME_TIMING.controller_timing())
        )
        party_reader = PokemonRedPartyReader(emulator)

        raw = reader.read()
        party = party_reader.read()
        print(f"resumed on map {raw.map_id} at {(raw.player_x, raw.player_y)!r}")
        described = tuple(
            f"{hex(species)}@{level}"
            for species, level in zip(party.species_ids(), party.levels, strict=True)
        )
        print(f"party: {described}")

        if args.swap_only:
            return _replay_swap(actions, reader, emulator, party_reader)
        return _replay_training(actions, reader, emulator)
    finally:
        emulator.close()


def _replay_swap(actions, reader, emulator, party_reader) -> int:
    """Swap the party's first two slots and report what happened.

    The narrowest possible exercise of the menu that has cost the most runs.
    """

    from pokemon_red_completion.red_team_training import swap_field_party_slots

    before = party_reader.read().species_ids()
    print(f"\nswapping slots 1 and 2 of {tuple(hex(s) for s in before)}")
    try:
        swap_field_party_slots(
            actions,
            reader,
            emulator,
            first_index=0,
            second_index=1,
            label="replay swap",
            hideout_timing=None,
        )
    except Exception as error:  # noqa: BLE001 - the failure is the output
        print(f"\nFAILED: {error}")
        return 1
    after = party_reader.read().species_ids()
    print(f"result: {tuple(hex(s) for s in after)}")
    swapped = after[0] == before[1] and after[1] == before[0]
    print("swap succeeded" if swapped else "swap did not do what was asked")
    return 0 if swapped else 1


def _replay_training(actions, reader, emulator) -> int:
    """Run the Mansion balancing block exactly as ``blaine`` calls it."""

    from pokemon_red_completion import blaine

    print("\nrunning the Mansion balancing block")
    try:
        report, battles, heals = blaine.run_red_team_balancing(
            actions,
            reader,
            emulator,
            policy=blaine.MANSION_TEAM_POLICY,
            venues=(blaine.DIGLETTS_CAVE_TRAINING_VENUE, blaine.MANSION_TRAINING_VENUE),
            intent=blaine.MANSION_BALANCED_TEAM_TRAINING_INTENT,
            flee_timing=blaine.MANSION_TRAINING_FLEE_TIMING,
            hideout_timing=blaine.DEFAULT_HIDEOUT_TIMING,
            flee_func=blaine._flee,
            volatile_enemy_species=blaine.MANSION_VOLATILE_ENEMY_SPECIES,
            escort_enemy_species=blaine.MANSION_ESCORT_ENEMY_SPECIES,
            max_consecutive_flees=blaine.MANSION_MAX_CONSECUTIVE_FLEES,
            cancel_interval=blaine.MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
            report_label="replay training",
            checkpoint_count=blaine.BLAINE_CHECKPOINT_COUNT,
        )
    except Exception as error:  # noqa: BLE001 - the failure is the output
        print(f"\nFAILED: {type(error).__name__}: {error}")
        traceback.print_exc(limit=3)
        return 1
    print(f"\nfinished: battles={battles}, healing_trips={heals}, report={report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
