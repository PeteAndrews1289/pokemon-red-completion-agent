from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from pokemon_red_completion.rom import resolve_rom_path, verify_rom
from pokemon_red_completion.route import COMPLETION_QUEST


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pokemon-red-completion",
        description="Inspect the completion-first Pokémon Red agent foundation.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("route", help="Print the validated high-level completion route.")
    doctor = subcommands.add_parser("doctor", help="Verify the private ROM identity.")
    doctor.add_argument("--rom", type=Path, help="Private ROM path; otherwise use POKEMON_RED_ROM.")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
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

    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    print(json.dumps(fingerprint.public_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
