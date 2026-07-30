from __future__ import annotations

import argparse
import json
import platform
import sys
import uuid
from collections.abc import Sequence
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pokemon_red_completion import __version__
from pokemon_red_completion.bootstrap import (
    DEFAULT_NEW_GAME_TIMING,
    BootstrapError,
    run_bootstrap_smoke,
)
from pokemon_red_completion.emulator import EmulatorError
from pokemon_red_completion.opening import (
    DEFAULT_OPENING_TIMING,
    PRET_POKERED_COMMIT,
    OpeningChapterError,
    OpeningChapterReport,
    OpeningProgress,
    run_opening_chapter,
)
from pokemon_red_completion.play import (
    DEFAULT_QUALIFIED_PLAY_TIMING,
    QualifiedPlayError,
    QualifiedPlayProgress,
    QualifiedPlayReport,
    run_qualified_play,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    initialize_private_root,
    open_private_root,
)
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
)
from pokemon_red_completion.red_trajectory import (
    POKEMON_CORE_ONTOLOGY_ID,
    POKEMON_RED_ADAPTER_ID,
    POKEMON_RED_GAME_ID,
    POKEMON_RED_QUALIFIED_TEACHER_POLICY_ID,
)
from pokemon_red_completion.rom import RomValidationError, resolve_rom_path, verify_rom
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.trajectory_io import EpisodeTrajectorySink

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RECORDING_SERIES_ID = "red-teacher-nominal-v1"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pokemon-red-completion",
        description="Run and inspect the completion-first Pokémon Red agent.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("route", help="Print the validated high-level completion route.")
    private_data = subcommands.add_parser(
        "private-data",
        help="Initialize private external storage for trajectory data.",
    )
    private_data_commands = private_data.add_subparsers(
        dest="private_data_command",
        required=True,
    )
    private_data_init = private_data_commands.add_parser(
        "init",
        help="Mark an existing external directory as the private trajectory root.",
    )
    private_data_init.add_argument(
        "--private-root",
        type=Path,
        required=True,
        help="Explicit absolute path to an existing external directory.",
    )
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
    record = subcommands.add_parser(
        "record",
        help="Record a qualified Hall of Fame teacher run to private external storage.",
    )
    record.add_argument(
        "--private-root",
        type=Path,
        required=True,
        help="Explicit absolute path to an initialized private external directory.",
    )
    record.add_argument(
        "--rom",
        type=Path,
        help="Private ROM path; otherwise use POKEMON_RED_ROM.",
    )
    record.add_argument(
        "--watch",
        action="store_true",
        help="Show a view-only local game window with human input disabled.",
    )
    record.add_argument(
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


def _public_error_message(
    error: Exception,
    *,
    private_paths: Sequence[Path | None],
) -> str:
    message = str(error)
    for path in private_paths:
        if path is not None:
            message = message.replace(str(path), "<private>")
    if isinstance(error, RomValidationError) and message.startswith("ROM file does not exist:"):
        return "Private ROM file does not exist."
    return message


def _completion_route_payload() -> list[dict[str, object]]:
    return [
        {
            "id": objective.id,
            "title": objective.title,
            "specialist": objective.specialist.value,
            "prerequisites": sorted(objective.prerequisites),
            "completion_facts": sorted(objective.completion_facts),
        }
        for objective in COMPLETION_QUEST.topological_order()
    ]


def _recording_metadata(
    rom_path: Path,
    *,
    episode_id: str,
    watch: bool,
    speed: int | None,
) -> dict[str, object]:
    source = detect_source_identity(REPOSITORY_ROOT, include_untracked=True)
    require_clean_source(source)
    fingerprint = verify_rom(rom_path)
    try:
        pyboy_version = version("pyboy")
    except PackageNotFoundError:
        pyboy_version = "unavailable"

    configuration = {
        "schema": "qualified-teacher-configuration-v1",
        "pret_pokered_commit": PRET_POKERED_COMMIT,
        "new_game_timing": asdict(DEFAULT_NEW_GAME_TIMING),
        "opening_timing": asdict(DEFAULT_OPENING_TIMING),
        "play_timing": asdict(DEFAULT_QUALIFIED_PLAY_TIMING),
        "emulator": {
            "human_input": False,
            "save_on_exit": False,
            "watch": watch,
            "speed": speed if watch else 0,
        },
    }
    route = _completion_route_payload()
    return {
        "adapter_id": POKEMON_RED_ADAPTER_ID,
        "ontology_id": POKEMON_CORE_ONTOLOGY_ID,
        "policy": {
            "actor": "deterministic_teacher",
            "policy_id": POKEMON_RED_QUALIFIED_TEACHER_POLICY_ID,
            "source_version": __version__,
        },
        "source": source.public_dict(),
        "runtime": {
            "python_version": platform.python_version(),
            "emulator_name": "PyBoy",
            "emulator_version": pyboy_version,
        },
        "rom_identity": fingerprint.public_dict(),
        "objective_graph_sha256": canonical_sha256(route),
        "configuration": configuration,
        "configuration_sha256": canonical_sha256(configuration),
        "collection": {
            "assistance_class": "teacher",
            "start_type": "clean_power_on",
            "human_input": False,
            "save_restore_used": False,
            "perturbation_schedule": "none",
            "seed_protocol": "native_power_on_rng",
            "attempt": {
                "counted": True,
                "series_id": RECORDING_SERIES_ID,
            },
        },
        "split": {
            "partition": "unassigned",
            "regime": "within_game",
            "root_lineage_id": episode_id,
        },
    }


def main(arguments: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(arguments)
    if args.command == "route":
        payload = _completion_route_payload()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if args.command == "private-data":
        try:
            initialize_private_root(
                args.private_root,
                repository_root=REPOSITORY_ROOT,
            )
        except PrivateArtifactError as error:
            parser.error(
                _public_error_message(
                    error,
                    private_paths=(args.private_root,),
                )
            )
        print(
            json.dumps(
                {
                    "schema": "private-root-init-v1",
                    "status": "ready",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command in {"opening", "play", "record"} and args.speed is not None and not args.watch:
        parser.error("--speed requires --watch")

    rom_path: Path | None = None
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
        elif args.command == "play":
            qualified_report = run_qualified_play(
                rom_path,
                watch=args.watch,
                speed=args.speed,
                progress=_print_qualified_progress,
            )
            _print_qualified_summary(qualified_report)
            payload = qualified_report.public_dict()
        else:
            episode_id = f"red-teacher-{uuid.uuid4().hex}"
            metadata = _recording_metadata(
                rom_path,
                episode_id=episode_id,
                watch=args.watch,
                speed=args.speed,
            )
            private_root = open_private_root(
                args.private_root,
                repository_root=REPOSITORY_ROOT,
            )
            writer = private_root.begin_episode(episode_id)
            with writer:
                trajectory_sink = EpisodeTrajectorySink(
                    writer,
                    episode_id=episode_id,
                    game_id=POKEMON_RED_GAME_ID,
                )
                trajectory_sink.write_episode_header(metadata=metadata)
                qualified_report = run_qualified_play(
                    rom_path,
                    watch=args.watch,
                    speed=args.speed,
                    progress=_print_qualified_progress,
                    trajectory_sink=trajectory_sink,
                    trajectory_episode_id=episode_id,
                )
            _print_qualified_summary(qualified_report)
            public_play = qualified_report.public_dict()
            payload = {
                "schema": "private-trajectory-recording-v1",
                "status": "ok",
                "game_complete": bool(public_play.get("game_complete")),
                "episode": writer.summary.public_dict(),
            }
    except (
        BootstrapError,
        EmulatorError,
        EvaluationIdentityError,
        OpeningChapterError,
        PrivateArtifactError,
        QualifiedPlayError,
        RomValidationError,
    ) as error:
        parser.error(
            _public_error_message(
                error,
                private_paths=(
                    rom_path,
                    getattr(args, "rom", None),
                    getattr(args, "private_root", None),
                ),
            )
        )
    except OSError:
        parser.error("Private storage or ROM input/output failed; no episode was published.")
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
