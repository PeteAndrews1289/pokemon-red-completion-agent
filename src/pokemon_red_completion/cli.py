from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pokemon_red_completion.bootstrap import BootstrapError, run_bootstrap_smoke
from pokemon_red_completion.emulator import EmulatorError
from pokemon_red_completion.opening import (
    OpeningChapterError,
    OpeningChapterReport,
    OpeningProgress,
    run_opening_chapter,
)
from pokemon_red_completion.play import (
    QualifiedPlayError,
    QualifiedPlayProgress,
    QualifiedPlayReport,
    run_qualified_play,
)
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
    opening = subcommands.add_parser(
        "opening",
        help="Run the bounded clean-start teacher through a verified starter.",
    )
    opening.add_argument(
        "--rom",
        type=Path,
        help="Private ROM path; otherwise use POKEMON_RED_ROM.",
    )
    opening.add_argument(
        "--watch",
        action="store_true",
        help="Show a view-only local game window with human input disabled.",
    )
    opening.add_argument(
        "--speed",
        type=int,
        choices=(1, 2, 4),
        help="Watched playback speed; requires --watch and defaults to 2.",
    )
    play = subcommands.add_parser(
        "play",
        help="Run the qualified teacher from clean power-on through the Hall of Fame.",
    )
    play.add_argument(
        "--rom",
        type=Path,
        help="Private ROM path; otherwise use POKEMON_RED_ROM.",
    )
    play.add_argument(
        "--watch",
        action="store_true",
        help="Show a view-only local game window with human input disabled.",
    )
    play.add_argument(
        "--speed",
        type=int,
        choices=(1, 2, 4),
        help="Watched playback speed; requires --watch and defaults to 2.",
    )
    return parser


def _print_opening_progress(progress: OpeningProgress) -> None:
    print(
        f"[{progress.completed}/{progress.total}] {progress.label}",
        file=sys.stderr,
        flush=True,
    )


def _print_opening_summary(report: OpeningChapterReport) -> None:
    verified = len(report.verified_objectives)
    total = len(COMPLETION_QUEST)
    if report.next_objective is None:
        next_step = "All declared objectives verified"
    else:
        next_step = COMPLETION_QUEST.objective(report.next_objective).title
    print(
        f"Objectives: {verified}/{total} verified | Next: {next_step}",
        file=sys.stderr,
        flush=True,
    )


def _print_qualified_progress(progress: QualifiedPlayProgress) -> None:
    print(
        f"[{progress.completed}/{progress.total}] {progress.label}",
        file=sys.stderr,
        flush=True,
    )


def _print_qualified_summary(report: QualifiedPlayReport) -> None:
    verified = len(report.verified_objectives)
    total = len(COMPLETION_QUEST)
    if report.next_objective is None:
        next_step = "All declared objectives verified"
    else:
        next_step = COMPLETION_QUEST.objective(report.next_objective).title
    print(
        f"Objectives: {verified}/{total} verified | Next: {next_step}",
        file=sys.stderr,
        flush=True,
    )
    print(
        "Completion verified: Champion defeated and Hall of Fame entered.",
        file=sys.stderr,
        flush=True,
    )


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

    if (
        args.command in {"opening", "play"}
        and args.speed is not None
        and not args.watch
    ):
        parser.error("--speed requires --watch")

    try:
        rom_path = resolve_rom_path(args.rom)
        if args.command == "doctor":
            payload = verify_rom(rom_path).public_dict()
        elif args.command == "bootstrap":
            payload = run_bootstrap_smoke(rom_path).public_dict()
        elif args.command == "opening":
            report = run_opening_chapter(
                rom_path,
                watch=args.watch,
                speed=args.speed,
                progress=_print_opening_progress,
            )
            _print_opening_summary(report)
            payload = report.public_dict()
        else:
            qualified_report = run_qualified_play(
                rom_path,
                watch=args.watch,
                speed=args.speed,
                progress=_print_qualified_progress,
            )
            _print_qualified_summary(qualified_report)
            payload = qualified_report.public_dict()
    except (
        BootstrapError,
        EmulatorError,
        OpeningChapterError,
        QualifiedPlayError,
        RomValidationError,
    ) as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        print(
            "Stopped safely without saving. No success report was emitted.",
            file=sys.stderr,
            flush=True,
        )
        return 130
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
