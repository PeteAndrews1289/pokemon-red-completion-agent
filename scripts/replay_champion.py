"""Run the Champion from a private captured pre-chapter state.

This is a diagnostic harness for downstream League regression work. It is not
a substitute for a clean-power completion: use it to iterate at the battle
boundary, then qualify the exact source with ``pokemon-red-completion play``.

Usage::

    POKEMON_RED_ROM=<path> python scripts/replay_champion.py --state <path>.state
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.champion import run_champion_chapter  # noqa: E402
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.observation import PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.opening import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="private pre-Champion state")
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    args = parser.parse_args(argv)

    emulator = PyBoyAdapter(resolve_rom_path(args.rom))
    emulator.start()
    try:
        emulator.load_state(args.state)
        reader = PokemonRedStateReader(emulator)
        executor = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        try:
            report = run_champion_chapter(emulator, reader, executor)
        except Exception as error:  # noqa: BLE001 - the diagnostic is the output
            print(f"FAILED: {type(error).__name__}: {error}", file=sys.stderr)
            traceback.print_exc(limit=5)
            return 1
        public = report.public_dict()
        print(
            json.dumps(
                {
                    "status": public["status"],
                    "verification": public["verification"],
                    "participation": public["participation"],
                    "resources": public["resources"],
                    "terminal": public["terminal"],
                    "turns": public["turns"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    finally:
        emulator.close()


if __name__ == "__main__":
    raise SystemExit(main())
