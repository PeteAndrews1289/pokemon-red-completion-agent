from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from pokemon_red_completion.bootstrap import BootstrapError, run_bootstrap_smoke
from pokemon_red_completion.emulator import EmulatorError
from pokemon_red_completion.rom import RomValidationError, resolve_rom_path, verify_rom
from pokemon_red_completion.route import COMPLETION_QUEST


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pokemon-red-completion",
        description="Run and inspect the completion-first Pokémon Red agent.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("route", help="Print the validated high-level completion route.")
    doctor = subcommands.add_parser("doctor", help="Verify the private ROM identity.")
    doctor.add_argument("--rom", type=Path, help="Private ROM path; otherwise use POKEMON_RED_ROM.")
    bootstrap = subcommands.add_parser(
        "bootstrap",
        help="Run a clean-power-on, headless bedroom and movement smoke test.",
    )
    bootstrap.add_argument(
        "--rom",
        type=Path,
        help="Private ROM path; otherwise use POKEMON_RED_ROM.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(arguments)
    if args.command == "route":
        payload = [
            {
                "id": objective.id,
                "title": objective.title,
                "specialist": objective.specialist.value,
                "prerequisites": sorted(objective.prerequisites),
                "completion_facts": sorted(objective.completion_facts),
            }
            for objective in COMPLETION_QUEST.topological_order()
        ]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    try:
        rom_path = resolve_rom_path(args.rom)
        if args.command == "doctor":
            payload = verify_rom(rom_path).public_dict()
        else:
            payload = run_bootstrap_smoke(rom_path).public_dict()
    except (BootstrapError, EmulatorError, RomValidationError) as error:
        parser.error(str(error))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
