from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from collections.abc import Sequence
from contextlib import nullcontext
from dataclasses import asdict, replace
from pathlib import Path

from pokemon_red_completion import __version__
from pokemon_red_completion.battle_model import CURRENT_BATTLE_FEATURE_SCHEMA_ID
from pokemon_red_completion.battle_plan import RED_BATTLE_PLAN_IDS
from pokemon_red_completion.battle_schedule import BattleScheduleError
from pokemon_red_completion.bootstrap import (
    DEFAULT_NEW_GAME_TIMING,
    BootstrapError,
    run_bootstrap_smoke,
)
from pokemon_red_completion.collection_ledger import (
    CollectionCampaignIdentity,
    CollectionLedgerError,
    CollectionOutcomeLedger,
    CollectionSlot,
    find_dry_run_qualification,
    publish_dry_run_qualification,
    require_dry_run_qualification,
)
from pokemon_red_completion.collection_protocol import (
    BATTLE_PLAN_ROSTER_SCHEMA,
    BATTLE_START_MAX_OFFSET_FRAMES,
    BATTLE_START_SCHEDULE_DERIVATION,
    BATTLE_START_SCHEDULE_SCHEMA,
    BattleStartOffset,
    BattleStartSchedule,
    CollectionAssignment,
    CollectionExecution,
    CollectionProtocolError,
    CollectionRegistry,
    ScheduleDryRun,
    battle_start_offsets_sha256,
    collection_document_sha256,
    committed_source_bundle_sha256,
    load_committed_collection_registry,
    objective_graph_document,
    teacher_behavior_configuration,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import EmulatorError
from pokemon_red_completion.learned_battle_policy import (
    LearnedBattlePolicyError,
    load_battle_model_artifact,
)
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
    PrivateArtifactRoot,
    initialize_private_root,
    open_private_root,
)
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_trajectory import (
    POKEMON_BATTLE_MOVE_SKILL_ID,
    POKEMON_CORE_ONTOLOGY_ID,
    POKEMON_RED_ADAPTER_ID,
    POKEMON_RED_GAME_ID,
    POKEMON_RED_QUALIFIED_TEACHER_POLICY_ID,
)
from pokemon_red_completion.rom import RomValidationError, resolve_rom_path, verify_rom
from pokemon_red_completion.route import COMPLETION_QUEST, completion_route_payload
from pokemon_red_completion.runtime_identity import (
    RuntimeIdentityError,
    build_runtime_identity,
)
from pokemon_red_completion.schedule_audit import (
    ScheduleAttestationError,
    audit_schedule_attestations,
)
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
    collection = subcommands.add_parser(
        "collection",
        help="Inspect the immutable held-out collection campaign.",
    )
    collection_commands = collection.add_subparsers(
        dest="collection_command",
        required=True,
    )
    collection_status = collection_commands.add_parser(
        "status",
        help="Reconcile power-loss artifacts and print a path-free slot ledger.",
    )
    collection_status.add_argument(
        "--private-root",
        type=Path,
        required=True,
        help="Explicit absolute path to the initialized private artifact root.",
    )
    collection_status.add_argument(
        "--rom",
        type=Path,
        help="Private ROM path; otherwise use POKEMON_RED_ROM.",
    )
    learn = subcommands.add_parser(
        "learn",
        help="Train or inspect private learned-policy artifacts.",
    )
    learn_commands = learn.add_subparsers(dest="learn_command", required=True)
    learn_battle = learn_commands.add_parser(
        "battle",
        help="Build the transferable battle move-ranking specialist.",
    )
    learn_battle_commands = learn_battle.add_subparsers(
        dest="learn_battle_command",
        required=True,
    )
    learn_battle_train = learn_battle_commands.add_parser(
        "train",
        help="Train the battle ranker from an integrity-checked private episode.",
    )
    learn_battle_train.add_argument(
        "--private-root",
        type=Path,
        required=True,
        help="Explicit absolute path to the initialized private artifact root.",
    )
    learn_battle_train.add_argument(
        "--episode-id",
        required=True,
        help="Safe identifier of the completed private teacher episode.",
    )
    learn_battle_train.add_argument(
        "--diagnostic",
        action="store_true",
        help="Acknowledge that one unassigned lineage cannot support a held-out claim.",
    )
    learn_battle_train.add_argument(
        "--folds",
        type=int,
        default=5,
        help="Whole-battle diagnostic fold count (default: 5).",
    )
    learn_battle_train.add_argument(
        "--epochs",
        type=int,
        default=300,
        help="Deterministic optimizer epochs (default: 300).",
    )
    learn_battle_train.add_argument(
        "--seed",
        type=int,
        default=1289,
        help="Deterministic training seed (default: 1289).",
    )
    learn_battle_fit = learn_battle_commands.add_parser(
        "fit",
        help="Fit from all authenticated train roots and select on validation roots.",
    )
    learn_battle_fit.add_argument(
        "--private-root",
        type=Path,
        required=True,
        help="Explicit absolute path to the initialized private artifact root.",
    )
    learn_battle_fit.add_argument(
        "--rom",
        type=Path,
        help="Private ROM path; otherwise use POKEMON_RED_ROM.",
    )
    learn_battle_fit.add_argument(
        "--epochs",
        type=int,
        default=300,
        help="Frozen deterministic optimizer epochs (default: 300).",
    )
    learn_battle_fit.add_argument(
        "--seed",
        type=int,
        default=1289,
        help="Frozen deterministic training seed (default: 1289).",
    )
    learn_battle_correct = learn_battle_commands.add_parser(
        "correct",
        help="Refit a battle model with authenticated live teacher corrections.",
    )
    learn_battle_correct.add_argument(
        "--private-root",
        type=Path,
        required=True,
        help="Explicit absolute path to the initialized private artifact root.",
    )
    learn_battle_correct.add_argument(
        "--base-model",
        type=Path,
        required=True,
        help="Authenticated model.jsonl used to collect the corrections.",
    )
    learn_battle_correct.add_argument(
        "--corrections",
        type=Path,
        required=True,
        help="Completed private battle-correction artifact directory.",
    )
    learn_battle_correct.add_argument(
        "--train-episode",
        action="append",
        required=True,
        help="Authenticated historical train episode ID; repeat exactly five times.",
    )
    learn_battle_correct.add_argument(
        "--validation-episode",
        action="append",
        required=True,
        help="Authenticated historical validation episode ID; repeat exactly twice.",
    )
    learn_battle_correct.add_argument(
        "--correction-repetitions",
        type=int,
        default=8,
        help="Training weight for each live correction (default: 8).",
    )
    learn_battle_correct.add_argument(
        "--epochs",
        type=int,
        default=300,
        help="Deterministic optimizer epochs (default: 300).",
    )
    learn_battle_correct.add_argument(
        "--seed",
        type=int,
        default=1289,
        help="Deterministic training seed (default: 1289).",
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
    play.add_argument(
        "--battle-model",
        type=Path,
        help="Deploy an authenticated model.jsonl artifact for live battle choices.",
    )
    play.add_argument(
        "--battle-confidence-threshold",
        type=float,
        default=0.5,
        help="Use the routed teacher below this learned-policy confidence (default: 0.5).",
    )
    play.add_argument(
        "--allow-model-disagreement",
        action="store_true",
        help="Evaluation mode: execute confident model choices even when the teacher disagrees.",
    )
    play.add_argument(
        "--battle-corrections-root",
        type=Path,
        help=(
            "Write live low-confidence and disagreement labels to an initialized "
            "private external artifact root; requires --battle-model."
        ),
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
    recording_mode = record.add_mutually_exclusive_group()
    recording_mode.add_argument(
        "--collection-run",
        help=(
            "Declared run ID from the committed held-out collection registry; "
            "omit for an unassigned diagnostic recording."
        ),
    )
    recording_mode.add_argument(
        "--schedule-dry-run",
        action="store_true",
        help=(
            "Run the fixed unassigned 71-battle schedule rehearsal without "
            "consuming a held-out collection slot."
        ),
    )
    recording_mode.add_argument(
        "--diagnostic-schedule-seed",
        type=int,
        help=(
            "Run one uncounted arbitrary battle-timing schedule for robustness "
            "diagnostics without publishing a qualification or touching a campaign ledger."
        ),
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


def _collection_slots(registry: CollectionRegistry) -> tuple[CollectionSlot, ...]:
    """Derive the exact single-attempt ledger roster from the frozen registry."""

    slots: list[CollectionSlot] = []
    for run in registry.runs:
        assignment = registry.assignment(run.run_id)
        slots.append(
            CollectionSlot(
                assignment_id=assignment.assignment_id,
                episode_id=assignment.episode_id,
                root_lineage_id=assignment.root_lineage_id,
                run_id=assignment.run_id,
                partition=assignment.partition,
                harness_seed=assignment.harness_seed,
                schedule_sha256=assignment.schedule_sha256,
                offsets=assignment.offsets,
                battle_count=len(assignment.offsets),
                collection_ordinal=assignment.collection_slot_ordinal,
                collection_total=assignment.declared_collection_slots,
                partition_ordinal=assignment.partition_slot_ordinal,
                partition_total=assignment.declared_partition_slots,
            )
        )
    return tuple(slots)


def _diagnostic_schedule(seed: int) -> tuple[tuple[BattleStartOffset, ...], str]:
    """Expand one explicitly uncounted pre-registration robustness schedule."""

    if type(seed) is not int or not 0 <= seed <= (1 << 64) - 1:  # noqa: E721
        raise ValueError("diagnostic schedule seed must be an unsigned 64-bit integer")
    battle_roster_sha256 = collection_document_sha256(
        {
            "battle_plan_ids": list(RED_BATTLE_PLAN_IDS),
            "schema": BATTLE_PLAN_ROSTER_SCHEMA,
        }
    )
    schedule = BattleStartSchedule(
        battle_plan_ids=RED_BATTLE_PLAN_IDS,
        battle_roster_sha256=battle_roster_sha256,
        derivation=BATTLE_START_SCHEDULE_DERIVATION,
        max_offset_frames=BATTLE_START_MAX_OFFSET_FRAMES,
        schema=BATTLE_START_SCHEDULE_SCHEMA,
    )
    offsets = schedule.offsets(seed)
    return offsets, schedule.schedule_sha256(seed)


def _attach_diagnostic_schedule_metadata(
    metadata: dict[str, object],
    *,
    seed: int,
    offsets: tuple[BattleStartOffset, ...],
    schedule_sha256: str,
) -> None:
    """Describe a schedule-fuzzing episode without granting evaluation status."""

    configuration = metadata.get("configuration")
    collection = metadata.get("collection")
    if not isinstance(configuration, dict) or not isinstance(collection, dict):
        raise TypeError("diagnostic metadata lacks configuration or collection blocks")
    configuration["battle_start_schedule"] = {
        "offsets": [offset.public_dict() for offset in offsets],
        "purpose": "pre_registration_robustness_diagnostic",
        "schedule_sha256": schedule_sha256,
        "schema": BATTLE_START_SCHEDULE_SCHEMA,
    }
    metadata["configuration_sha256"] = canonical_sha256(configuration)
    collection.update(
        {
            "attempt": {"counted": False},
            "harness_seed": seed,
            "perturbation_schedule": "diagnostic_battle_start_offsets",
            "purpose": "pre_registration_robustness_diagnostic",
            "schedule": {
                "schedule_sha256": schedule_sha256,
                "schema": BATTLE_START_SCHEDULE_SCHEMA,
            },
            "seed_protocol": "explicit_diagnostic_harness_seed",
        }
    )


def _campaign_identity(
    registry: CollectionRegistry,
    metadata: dict[str, object],
) -> CollectionCampaignIdentity:
    """Bind private campaign accounting to the exact runtime and ROM identities."""

    rom_identity = metadata.get("rom_identity")
    source = metadata.get("source")
    if not isinstance(rom_identity, dict):
        raise CollectionLedgerError("recording metadata has no ROM identity")
    if not isinstance(source, dict):
        raise CollectionLedgerError("recording metadata has no source identity")
    runtime_sha256 = metadata.get("runtime_sha256")
    if not isinstance(runtime_sha256, str):
        raise CollectionLedgerError("recording metadata has no runtime identity")
    return CollectionCampaignIdentity(
        collection_id=registry.collection_id,
        registry_sha256=registry.registry_sha256,
        source_commit=str(source.get("git_commit")),
        source_bundle_sha256=registry.execution.source_bundle_sha256,
        behavior_configuration_sha256=(registry.execution.behavior_configuration_sha256),
        objective_graph_sha256=registry.execution.objective_graph_sha256,
        teacher_execution_sha256=registry.execution.teacher_execution_sha256,
        runtime_sha256=runtime_sha256,
        rom_sha1=str(rom_identity.get("sha1")),
        rom_sha256=str(rom_identity.get("sha256")),
    )


def _capture_private_recording(
    private_root: PrivateArtifactRoot,
    *,
    rom_path: Path,
    episode_id: str,
    metadata: dict[str, object],
    watch: bool,
    speed: int | None,
    battle_start_offsets: tuple[BattleStartOffset, ...] | None,
) -> tuple[QualifiedPlayReport, dict[str, object]]:
    writer = private_root.begin_episode(episode_id)
    with writer:
        trajectory_sink = EpisodeTrajectorySink(
            writer,
            episode_id=episode_id,
            game_id=POKEMON_RED_GAME_ID,
        )
        trajectory_sink.write_episode_header(metadata=metadata)
        report = run_qualified_play(
            rom_path,
            watch=watch,
            speed=speed,
            progress=_print_qualified_progress,
            trajectory_sink=trajectory_sink,
            trajectory_episode_id=episode_id,
            battle_start_offsets=battle_start_offsets,
        )
    if battle_start_offsets is not None:
        audit_schedule_attestations(
            private_root.open_episode(episode_id),
            episode_id=episode_id,
            offsets=battle_start_offsets,
            schedule_sha256=battle_start_offsets_sha256(battle_start_offsets),
        )
    return report, writer.summary.public_dict()


def _recording_metadata(
    rom_path: Path,
    *,
    episode_id: str,
    watch: bool,
    speed: int | None,
    assignment: CollectionAssignment | None = None,
    execution: CollectionExecution | None = None,
    schedule_dry_run: ScheduleDryRun | None = None,
) -> dict[str, object]:
    if assignment is not None and schedule_dry_run is not None:
        raise ValueError("assignment and schedule_dry_run are mutually exclusive")
    if assignment is not None and (
        not isinstance(assignment, CollectionAssignment) or episode_id != assignment.episode_id
    ):
        raise ValueError("assignment must match the planned episode identity")
    if schedule_dry_run is not None and not isinstance(schedule_dry_run, ScheduleDryRun):
        raise TypeError("schedule_dry_run must be a ScheduleDryRun")
    if (assignment is not None or schedule_dry_run is not None) and not isinstance(
        execution,
        CollectionExecution,
    ):
        raise ValueError("scheduled recording requires a frozen execution contract")
    source = detect_source_identity(REPOSITORY_ROOT, include_untracked=True)
    require_clean_source(source)
    if assignment is not None or schedule_dry_run is not None:
        if execution.source_commit is None:
            raise EvaluationIdentityError(
                "Scheduled collection requires a registry loaded from one exact commit."
            )
        if source.git_commit != execution.source_commit:
            raise EvaluationIdentityError(
                "The source commit changed after the collection registry was loaded."
            )
        require_published_source(REPOSITORY_ROOT, source)
    fingerprint = verify_rom(rom_path)
    runtime_identity = build_runtime_identity()
    pyboy_version = runtime_identity.pyboy_distribution_version

    behavior_configuration = teacher_behavior_configuration(
        pyboy_version=pyboy_version,
        new_game_timing=asdict(DEFAULT_NEW_GAME_TIMING),
        opening_timing=asdict(DEFAULT_OPENING_TIMING),
        play_timing=asdict(DEFAULT_QUALIFIED_PLAY_TIMING),
        pret_pokered_commit=PRET_POKERED_COMMIT,
    )
    behavior_configuration_sha256 = collection_document_sha256(behavior_configuration)
    route = completion_route_payload()
    objective_graph_sha256 = collection_document_sha256(objective_graph_document(route))
    source_bundle_sha256: str | None = None
    if execution is not None:
        source_bundle_sha256 = committed_source_bundle_sha256(
            REPOSITORY_ROOT,
            revision=(execution.source_commit if execution.source_commit is not None else "HEAD"),
        )
        working_bundle_sha256 = working_source_bundle_sha256(REPOSITORY_ROOT)
        if (
            behavior_configuration_sha256 != execution.behavior_configuration_sha256
            or behavior_configuration != execution.behavior_configuration_dict()
            or objective_graph_sha256 != execution.objective_graph_sha256
            or source_bundle_sha256 != execution.source_bundle_sha256
            or working_bundle_sha256 != execution.source_bundle_sha256
        ):
            raise EvaluationIdentityError(
                "The local teacher execution does not match the frozen collection contract."
            )
        if assignment is not None or schedule_dry_run is not None:
            current_source = detect_source_identity(
                REPOSITORY_ROOT,
                include_untracked=True,
            )
            require_clean_source(current_source)
            if current_source != source:
                raise EvaluationIdentityError(
                    "The source identity changed while preparing collection."
                )

    runtime = runtime_identity.public_dict()
    configuration = {
        "schema": "qualified-teacher-configuration-v2",
        "behavior_configuration": behavior_configuration,
        "behavior_configuration_sha256": behavior_configuration_sha256,
        "presentation": {
            "watch": watch,
            "speed": speed if watch else 0,
        },
    }
    scheduled_offsets = (
        assignment.offsets
        if assignment is not None
        else schedule_dry_run.offsets
        if schedule_dry_run is not None
        else None
    )
    if scheduled_offsets is not None:
        schedule_sha256 = (
            assignment.schedule_sha256
            if assignment is not None
            else schedule_dry_run.schedule_sha256
        )
        configuration["battle_start_schedule"] = {
            "offsets": [offset.public_dict() for offset in scheduled_offsets],
            "schedule_sha256": schedule_sha256,
            "schema": BATTLE_START_SCHEDULE_SCHEMA,
        }
        if assignment is not None:
            configuration["battle_start_schedule"].update(
                {
                    "assignment_id": assignment.assignment_id,
                    "registry_sha256": assignment.registry_sha256,
                }
            )
        else:
            configuration["battle_start_schedule"].update(
                {
                    "dry_run_id": schedule_dry_run.dry_run_id,
                    "purpose": "schedule_integration_dry_run",
                    "registry_sha256": schedule_dry_run.registry_sha256,
                    "teacher_execution_sha256": (execution.teacher_execution_sha256),
                }
            )
    if assignment is None:
        if schedule_dry_run is None:
            collection: dict[str, object] = {
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
            }
        else:
            collection = {
                "assistance_class": "teacher",
                "attempt": {"counted": False},
                "dry_run_id": schedule_dry_run.dry_run_id,
                "execution": {
                    "behavior_configuration_sha256": (execution.behavior_configuration_sha256),
                    "objective_graph_sha256": execution.objective_graph_sha256,
                    "source_bundle_sha256": execution.source_bundle_sha256,
                    "teacher_execution_sha256": (execution.teacher_execution_sha256),
                },
                "harness_seed": schedule_dry_run.harness_seed,
                "human_input": False,
                "perturbation_schedule": "fixed_schedule_integration_dry_run",
                "purpose": "schedule_integration_dry_run",
                "registry_sha256": schedule_dry_run.registry_sha256,
                "save_restore_used": False,
                "schedule": {
                    "schedule_sha256": schedule_dry_run.schedule_sha256,
                    "schema": BATTLE_START_SCHEDULE_SCHEMA,
                },
                "seed_protocol": "committed_diagnostic_harness_seed",
                "start_type": "clean_power_on",
            }
        split: dict[str, object] = {
            "partition": "unassigned",
            "regime": "within_game",
            "root_lineage_id": episode_id,
        }
    else:
        assignment_metadata = assignment.metadata_dict()
        split_value = assignment_metadata.pop("split")
        if not isinstance(split_value, dict):
            raise TypeError("assignment split metadata must be a mapping")
        split = split_value
        collection = {
            "assistance_class": "teacher",
            "start_type": "clean_power_on",
            "human_input": False,
            "save_restore_used": False,
            "perturbation_schedule": "preregistered_battle_start_offsets",
            "seed_protocol": "committed_harness_seed",
            **assignment_metadata,
        }
        configuration["assignment_configuration_sha256"] = collection_document_sha256(
            {
                "assignment_id": assignment.assignment_id,
                "behavior_configuration_sha256": (assignment.behavior_configuration_sha256),
                "schedule_sha256": assignment.schedule_sha256,
                "schema": "pokemon-red-assignment-configuration-v1",
            }
        )
    return {
        "adapter_id": POKEMON_RED_ADAPTER_ID,
        "ontology_id": POKEMON_CORE_ONTOLOGY_ID,
        "policy": {
            "actor": "deterministic_teacher",
            "policy_id": POKEMON_RED_QUALIFIED_TEACHER_POLICY_ID,
            "source_version": __version__,
        },
        "source": source.public_dict(),
        "source_bundle_sha256": source_bundle_sha256,
        "runtime": runtime,
        "runtime_sha256": runtime_identity.sha256,
        "rom_identity": fingerprint.public_dict(),
        "objective_graph_sha256": objective_graph_sha256,
        "configuration": configuration,
        "configuration_sha256": canonical_sha256(configuration),
        "collection": collection,
        "split": split,
    }


def _run_battle_learning(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> dict[str, object]:
    """Run the optional learning stack without making NumPy a base CLI dependency."""

    if args.learn_battle_command == "fit":
        return _run_preassigned_battle_learning(parser, args)
    if args.learn_battle_command == "correct":
        return _run_corrected_battle_learning(parser, args)
    if not args.diagnostic:
        parser.error(
            "The current single-lineage trainer requires --diagnostic; "
            "it cannot produce held-out evidence."
        )
    try:
        from pokemon_red_completion.battle_dataset import (
            BattleDatasetError,
            BattleDecisionProvenance,
            load_battle_episode,
        )
        from pokemon_red_completion.battle_model import BattleModelValidationError
        from pokemon_red_completion.battle_semantics import (
            BattleFeatureError,
            BattleFeatureProjector,
        )
        from pokemon_red_completion.battle_training import (
            BattleTrainingConfig,
            BattleTrainingError,
            train_diagnostic_battle_ranker,
        )
        from pokemon_red_completion.red_battle_catalog import (
            PRET_POKERED_COMMIT as BATTLE_CATALOG_SOURCE_COMMIT,
        )
        from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
    except ModuleNotFoundError as error:
        if error.name == "numpy":
            parser.error('Battle learning requires the optional "learning" dependencies.')
        raise

    try:
        source = detect_source_identity(REPOSITORY_ROOT, include_untracked=True)
        require_clean_source(source)
        registry = load_committed_collection_registry(REPOSITORY_ROOT)
        if any(
            registry.assignment(run.run_id).episode_id == args.episode_id for run in registry.runs
        ):
            raise BattleTrainingError(
                "This diagnostic command cannot open a preregistered collection episode."
            )
        private_root = open_private_root(
            args.private_root,
            repository_root=REPOSITORY_ROOT,
        )
        reader = private_root.open_episode(args.episode_id)
        projector = BattleFeatureProjector(PokemonRedBattleCatalog())
        dataset = load_battle_episode(
            reader,
            projector,
            required_provenance=BattleDecisionProvenance(
                actor="deterministic_teacher",
                policy_id=POKEMON_RED_QUALIFIED_TEACHER_POLICY_ID,
                skill_id=POKEMON_BATTLE_MOVE_SKILL_ID,
            ),
        )
        if dataset.partition != "unassigned":
            raise BattleTrainingError(
                "This diagnostic command accepts only unassigned episodes; "
                "preassigned train, validation, and test episodes are sealed from this lane."
            )
        if dataset.episode_qualified:
            raise BattleTrainingError(
                "This command is diagnostic-only; use battle fit after the declared train and "
                "validation roots complete."
            )
        config = BattleTrainingConfig(
            seed=args.seed,
            folds=args.folds,
            epochs=args.epochs,
        )
        result = train_diagnostic_battle_ranker(dataset, config=config)
        artifact_id = f"red-battle-ranker-{uuid.uuid4().hex}"
        writer = private_root.begin_artifact(artifact_id, kind="battle_model")
        with writer:
            writer.append(
                "model",
                {
                    "record_type": "battle_model",
                    "model": result.model.to_dict(),
                    "model_sha256": result.model_sha256,
                    "source": source.public_dict(),
                    "source_episode_manifest_sha256": dataset.manifest_sha256,
                },
            )
            writer.append(
                "training",
                {
                    "record_type": "battle_training",
                    "catalog": {
                        "game": "pokemon_red_us_rev0",
                        "pret_pokered_commit": BATTLE_CATALOG_SOURCE_COMMIT,
                    },
                    "configuration": config.public_dict(),
                    "dataset": dataset.public_summary(),
                },
            )
            writer.append(
                "metrics",
                {
                    "record_type": "battle_diagnostic_metrics",
                    "receipt": result.public_receipt(),
                },
            )
        payload = result.public_receipt()
        payload["source"] = source.public_dict()
        payload["private_artifact"] = writer.summary.public_dict()
        return payload
    except (
        BattleDatasetError,
        BattleFeatureError,
        BattleModelValidationError,
        BattleTrainingError,
        CollectionProtocolError,
        EvaluationIdentityError,
        PrivateArtifactError,
    ) as error:
        parser.error(
            _public_error_message(
                error,
                private_paths=(args.private_root,),
            )
        )
    except OSError:
        parser.error("Private learning input/output failed; no model was published.")
    raise AssertionError("argparse error unexpectedly returned")


def _run_preassigned_battle_learning(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> dict[str, object]:
    """Authenticate the frozen campaign and fit without opening its test rows."""

    try:
        from pokemon_red_completion.battle_dataset import (
            BattleDatasetError,
            BattleDecisionProvenance,
            BattleEpisodeDataset,
            load_battle_episode,
        )
        from pokemon_red_completion.battle_model import BattleModelValidationError
        from pokemon_red_completion.battle_semantics import (
            BattleFeatureError,
            BattleFeatureProjector,
        )
        from pokemon_red_completion.battle_training import (
            BattleTrainingConfig,
            BattleTrainingError,
            train_preassigned_battle_ranker,
        )
        from pokemon_red_completion.red_battle_catalog import (
            PRET_POKERED_COMMIT as BATTLE_CATALOG_SOURCE_COMMIT,
        )
        from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
    except ModuleNotFoundError as error:
        if error.name == "numpy":
            parser.error('Battle learning requires the optional "learning" dependencies.')
        raise

    rom_path: Path | None = None
    try:
        rom_path = resolve_rom_path(args.rom)
        source = detect_source_identity(REPOSITORY_ROOT, include_untracked=True)
        require_clean_source(source)
        registry = load_committed_collection_registry(REPOSITORY_ROOT)
        slots = _collection_slots(registry)
        train_slots = tuple(slot for slot in slots if slot.partition == "train")
        validation_slots = tuple(slot for slot in slots if slot.partition == "validation")
        test_slots = tuple(slot for slot in slots if slot.partition == "test")
        if (len(train_slots), len(validation_slots), len(test_slots)) != (5, 2, 5):
            raise BattleTrainingError(
                "The frozen campaign must declare five train, two validation, and five test roots."
            )
        first_assignment = registry.assignment(registry.runs[0].run_id)
        metadata = _recording_metadata(
            rom_path,
            episode_id=first_assignment.episode_id,
            watch=False,
            speed=None,
            assignment=first_assignment,
            execution=registry.execution,
        )
        identity = _campaign_identity(registry, metadata)
        private_root = open_private_root(
            args.private_root,
            repository_root=REPOSITORY_ROOT,
        )
        projector = BattleFeatureProjector(PokemonRedBattleCatalog())
        provenance = BattleDecisionProvenance(
            actor="deterministic_teacher",
            policy_id=POKEMON_RED_QUALIFIED_TEACHER_POLICY_ID,
            skill_id=POKEMON_BATTLE_MOVE_SKILL_ID,
        )
        datasets: dict[str, BattleEpisodeDataset] = {}
        with private_root.collection_session(registry.collection_id) as session:
            if (
                find_dry_run_qualification(
                    private_root,
                    identity,
                    registry.schedule_dry_run,
                )
                is None
            ):
                raise BattleTrainingError(
                    "The exact 71-battle schedule rehearsal is not qualified."
                )
            ledger = CollectionOutcomeLedger.open_existing(
                store=private_root,
                session=session,
                identity=identity,
                slots=slots,
            )
            if ledger is None:
                raise BattleTrainingError("The frozen collection campaign has not started.")
            outcomes = {outcome.slot.assignment_id: outcome for outcome in ledger.reconcile()}
            if any(slot.assignment_id in outcomes for slot in test_slots):
                raise BattleTrainingError(
                    "The test partition must remain unopened until the model is frozen."
                )
            for slot in (*train_slots, *validation_slots):
                outcome = outcomes.get(slot.assignment_id)
                if (
                    outcome is None
                    or outcome.status != "complete"
                    or outcome.episode_manifest_sha256 is None
                ):
                    raise BattleTrainingError(
                        "Every declared train and validation root must complete before fitting."
                    )
                dataset = load_battle_episode(
                    private_root.open_episode(slot.episode_id),
                    projector,
                    required_provenance=provenance,
                )
                if (
                    dataset.episode_id != slot.episode_id
                    or dataset.root_lineage_id != slot.root_lineage_id
                    or dataset.partition != slot.partition
                    or dataset.regime != "within_game"
                    or dataset.manifest_sha256 != outcome.episode_manifest_sha256
                ):
                    raise BattleTrainingError(
                        "A loaded battle dataset contradicts its authenticated campaign slot."
                    )
                datasets[slot.assignment_id] = dataset

        config = BattleTrainingConfig(
            seed=args.seed,
            epochs=args.epochs,
        )
        result = train_preassigned_battle_ranker(
            tuple(datasets[slot.assignment_id] for slot in train_slots),
            tuple(datasets[slot.assignment_id] for slot in validation_slots),
            config=config,
        )
        artifact_id = f"red-battle-candidate-{uuid.uuid4().hex}"
        writer = private_root.begin_artifact(artifact_id, kind="battle_model")
        with writer:
            writer.append(
                "model",
                {
                    "record_type": "battle_model_candidate",
                    "model": result.model.to_dict(),
                    "model_sha256": result.model_sha256,
                    "source": source.public_dict(),
                    "collection_id": registry.collection_id,
                    "registry_sha256": registry.registry_sha256,
                    "corpus_manifest_roster_sha256": (result.corpus_manifest_roster_sha256),
                },
            )
            writer.append(
                "training",
                {
                    "record_type": "battle_preassigned_training",
                    "catalog": {
                        "game": "pokemon_red_us_rev0",
                        "pret_pokered_commit": BATTLE_CATALOG_SOURCE_COMMIT,
                    },
                    "configuration": config.public_dict(split_unit="preassigned_root_lineage"),
                    "collection_id": registry.collection_id,
                    "registry_sha256": registry.registry_sha256,
                    "scope": result.public_receipt()["scope"],
                },
            )
            writer.append(
                "metrics",
                {
                    "record_type": "battle_preassigned_validation_metrics",
                    "receipt": result.public_receipt(),
                },
            )
        payload = result.public_receipt()
        payload["source"] = source.public_dict()
        payload["registry_sha256"] = registry.registry_sha256
        payload["private_artifact"] = writer.summary.public_dict()
        return payload
    except (
        BattleDatasetError,
        BattleFeatureError,
        BattleModelValidationError,
        BattleTrainingError,
        CollectionLedgerError,
        CollectionProtocolError,
        EvaluationIdentityError,
        PrivateArtifactError,
        RomValidationError,
        RuntimeIdentityError,
        ScheduleAttestationError,
    ) as error:
        parser.error(
            _public_error_message(
                error,
                private_paths=(args.private_root, rom_path),
            )
        )
    except OSError:
        parser.error("Private learning input/output failed; no model was published.")
    raise AssertionError("argparse error unexpectedly returned")


def _run_corrected_battle_learning(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> dict[str, object]:
    """Refit on the historical train roots plus authenticated live corrections."""

    try:
        from pokemon_red_completion.battle_corrections import (
            BattleCorrectionError,
            load_battle_correction_artifact,
        )
        from pokemon_red_completion.battle_dataset import (
            BattleDatasetError,
            BattleDecisionProvenance,
            BattleEpisodeDataset,
            load_battle_episode,
        )
        from pokemon_red_completion.battle_model import BattleModelValidationError
        from pokemon_red_completion.battle_semantics import (
            BattleFeatureError,
            BattleFeatureProjector,
        )
        from pokemon_red_completion.battle_training import (
            BattleTrainingConfig,
            BattleTrainingError,
            train_preassigned_battle_ranker,
        )
        from pokemon_red_completion.red_battle_catalog import (
            PRET_POKERED_COMMIT as BATTLE_CATALOG_SOURCE_COMMIT,
        )
        from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
    except ModuleNotFoundError as error:
        if error.name == "numpy":
            parser.error('Battle learning requires the optional "learning" dependencies.')
        raise

    try:
        if (
            len(args.train_episode) != 5
            or len(set(args.train_episode)) != 5
            or len(args.validation_episode) != 2
            or len(set(args.validation_episode)) != 2
            or set(args.train_episode) & set(args.validation_episode)
        ):
            raise BattleTrainingError(
                "Correction training requires five unique train and two unique validation roots."
            )
        if (
            type(args.correction_repetitions) is not int  # noqa: E721
            or not 1 <= args.correction_repetitions <= 64
        ):
            raise BattleTrainingError("correction repetitions must be between one and 64")
        source = detect_source_identity(REPOSITORY_ROOT, include_untracked=True)
        require_clean_source(source)
        private_root = open_private_root(
            args.private_root,
            repository_root=REPOSITORY_ROOT,
        )
        base_model = load_battle_model_artifact(args.base_model)
        base_model_sha256 = hashlib.sha256(
            base_model.to_json().encode("ascii")
        ).hexdigest()
        corrections = load_battle_correction_artifact(args.corrections)
        if corrections.source_model_sha256 != base_model_sha256:
            raise BattleTrainingError(
                "The correction corpus was collected from a different base model."
            )
        projector = BattleFeatureProjector(PokemonRedBattleCatalog())
        provenance = BattleDecisionProvenance(
            actor="deterministic_teacher",
            policy_id=POKEMON_RED_QUALIFIED_TEACHER_POLICY_ID,
            skill_id=POKEMON_BATTLE_MOVE_SKILL_ID,
        )

        def load_partition(
            episode_ids: Sequence[str],
            partition: str,
        ) -> tuple[BattleEpisodeDataset, ...]:
            datasets = tuple(
                load_battle_episode(
                    private_root.open_episode(episode_id),
                    projector,
                    required_provenance=provenance,
                )
                for episode_id in episode_ids
            )
            if any(
                dataset.partition != partition or not dataset.episode_qualified
                for dataset in datasets
            ):
                raise BattleTrainingError(
                    f"Every correction-training {partition} episode must be qualified."
                )
            return datasets

        train_datasets = load_partition(args.train_episode, "train")
        validation_datasets = load_partition(args.validation_episode, "validation")
        weighted_corrections = corrections.examples * args.correction_repetitions
        augmented_first = replace(
            train_datasets[0],
            examples=train_datasets[0].examples + weighted_corrections,
        )
        config = BattleTrainingConfig(seed=args.seed, epochs=args.epochs)
        result = train_preassigned_battle_ranker(
            (augmented_first, *train_datasets[1:]),
            validation_datasets,
            config=config,
        )
        artifact_id = f"red-battle-corrected-{uuid.uuid4().hex}"
        writer = private_root.begin_artifact(artifact_id, kind="battle_model")
        with writer:
            writer.append(
                "model",
                {
                    "record_type": "battle_model_candidate",
                    "model": result.model.to_dict(),
                    "model_sha256": result.model_sha256,
                    "source": source.public_dict(),
                    "base_model_sha256": base_model_sha256,
                    "correction_manifest_sha256": corrections.manifest_sha256,
                },
            )
            writer.append(
                "training",
                {
                    "record_type": "battle_correction_training",
                    "catalog": {
                        "game": "pokemon_red_us_rev0",
                        "pret_pokered_commit": BATTLE_CATALOG_SOURCE_COMMIT,
                    },
                    "configuration": {
                        **config.public_dict(split_unit="preassigned_root_lineage"),
                        "correction_repetitions": args.correction_repetitions,
                    },
                    "historical_train_decisions": sum(
                        len(dataset.examples) for dataset in train_datasets
                    ),
                    "correction_decisions": len(corrections.examples),
                    "weighted_correction_decisions": len(weighted_corrections),
                    "historical_validation_decisions": sum(
                        len(dataset.examples) for dataset in validation_datasets
                    ),
                },
            )
            writer.append(
                "metrics",
                {
                    "record_type": "battle_correction_validation_metrics",
                    "receipt": result.public_receipt(),
                    "corrections": corrections.public_summary(),
                    "promotion_eligible": False,
                    "reason": "iterative_corrections_require_fresh_rollout_evaluation",
                },
            )
        payload = result.public_receipt()
        payload["schema"] = "battle-imitation-correction-training-v1"
        payload["corrections"] = corrections.public_summary()
        payload["base_model_sha256"] = base_model_sha256
        payload["qualification"] = {
            "promotion_eligible": False,
            "held_out_validation": True,
            "learned_policy_rollout": False,
            "reasons": ["fresh_model_assisted_rollout_required"],
        }
        payload["source"] = source.public_dict()
        payload["private_artifact"] = writer.summary.public_dict()
        return payload
    except (
        BattleCorrectionError,
        BattleDatasetError,
        BattleFeatureError,
        BattleModelValidationError,
        BattleTrainingError,
        EvaluationIdentityError,
        LearnedBattlePolicyError,
        PrivateArtifactError,
    ) as error:
        parser.error(
            _public_error_message(
                error,
                private_paths=(args.private_root, args.base_model, args.corrections),
            )
        )
    except OSError:
        parser.error("Private correction training failed; no model was published.")
    raise AssertionError("argparse error unexpectedly returned")


def main(arguments: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(arguments)
    if args.command == "route":
        payload = completion_route_payload()
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

    if args.command == "learn":
        payload = _run_battle_learning(parser, args)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command in {"opening", "play", "record"} and args.speed is not None and not args.watch:
        parser.error("--speed requires --watch")

    rom_path: Path | None = None
    try:
        rom_path = resolve_rom_path(args.rom)
        if args.command == "collection":
            registry = load_committed_collection_registry(REPOSITORY_ROOT)
            assignment = registry.assignment(registry.runs[0].run_id)
            metadata = _recording_metadata(
                rom_path,
                episode_id=assignment.episode_id,
                watch=False,
                speed=None,
                assignment=assignment,
                execution=registry.execution,
            )
            private_root = open_private_root(
                args.private_root,
                repository_root=REPOSITORY_ROOT,
            )
            slots = _collection_slots(registry)
            identity = _campaign_identity(registry, metadata)
            with private_root.collection_session(registry.collection_id) as session:
                dry_run_qualification = find_dry_run_qualification(
                    private_root,
                    identity,
                    registry.schedule_dry_run,
                )
                ledger = CollectionOutcomeLedger.open_existing(
                    store=private_root,
                    session=session,
                    identity=identity,
                    slots=slots,
                )
                receipt = ledger.public_receipt() if ledger is not None else None
            payload = {
                "schema": "pokemon-red-collection-status-v1",
                "campaign_started": receipt is not None,
                "collection_id": registry.collection_id,
                "registry_sha256": registry.registry_sha256,
                "declared_slots": len(slots),
                "dry_run_qualified": dry_run_qualification is not None,
                "dry_run_qualification": (
                    dry_run_qualification.public_dict()
                    if dry_run_qualification is not None
                    else None
                ),
                "counts": (
                    receipt["counts"]
                    if receipt is not None
                    else {
                        "complete": 0,
                        "failed": 0,
                        "interrupted": 0,
                        "invalid": 0,
                        "pending": len(slots),
                    }
                ),
                "ledger": receipt,
            }
        elif args.command == "doctor":
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
            if args.battle_corrections_root is not None and args.battle_model is None:
                parser.error("--battle-corrections-root requires --battle-model")
            battle_model = (
                load_battle_model_artifact(args.battle_model)
                if args.battle_model is not None
                else None
            )
            correction_writer = None
            correction_summary = None
            if args.battle_corrections_root is not None:
                correction_root = open_private_root(
                    args.battle_corrections_root,
                    repository_root=REPOSITORY_ROOT,
                )
                correction_writer = correction_root.begin_artifact(
                    f"red-battle-corrections-{uuid.uuid4().hex}",
                    kind="battle_corrections",
                )
            with correction_writer if correction_writer is not None else nullcontext():
                if correction_writer is not None:
                    assert battle_model is not None
                    correction_writer.append(
                        "metadata",
                        {
                            "record_type": "battle_correction_run",
                            "schema_version": 1,
                            "model_id": battle_model.model_id,
                            "model_sha256": hashlib.sha256(
                                battle_model.to_json().encode("ascii")
                            ).hexdigest(),
                            "feature_schema_id": CURRENT_BATTLE_FEATURE_SCHEMA_ID,
                            "feature_count": len(battle_model.feature_names),
                            "confidence_threshold": args.battle_confidence_threshold,
                            "teacher_agreement_required": not args.allow_model_disagreement,
                        },
                    )
                qualified_report = run_qualified_play(
                    rom_path,
                    watch=args.watch,
                    speed=args.speed,
                    progress=_print_qualified_progress,
                    battle_model=battle_model,
                    battle_model_confidence_threshold=args.battle_confidence_threshold,
                    require_battle_model_teacher_agreement=not args.allow_model_disagreement,
                    battle_correction_sink=(
                        (lambda record: correction_writer.append("corrections", record))
                        if correction_writer is not None
                        else None
                    ),
                )
                if correction_writer is not None:
                    qualified_public = qualified_report.public_dict()
                    correction_writer.append(
                        "summary",
                        {
                            "record_type": "battle_correction_summary",
                            "schema_version": 1,
                            "battle_policy": qualified_report.battle_policy_report,
                            "game_complete": bool(qualified_public.get("game_complete")),
                        },
                    )
            if correction_writer is not None:
                correction_summary = correction_writer.summary.public_dict()
            _print_qualified_summary(qualified_report)
            payload = qualified_report.public_dict()
            if correction_summary is not None:
                payload["battle_corrections"] = correction_summary
        else:
            assignment = None
            schedule_dry_run = None
            registry = None
            diagnostic_offsets = None
            diagnostic_schedule_sha256 = None
            if args.collection_run is not None or args.schedule_dry_run:
                registry = load_committed_collection_registry(REPOSITORY_ROOT)
            if args.collection_run is not None and registry is not None:
                assignment = registry.assignment(args.collection_run)
            elif args.schedule_dry_run and registry is not None:
                schedule_dry_run = registry.schedule_dry_run
            elif args.diagnostic_schedule_seed is not None:
                diagnostic_offsets, diagnostic_schedule_sha256 = _diagnostic_schedule(
                    args.diagnostic_schedule_seed
                )
            episode_id = (
                assignment.episode_id
                if assignment is not None
                else (
                    f"red-dry-run-{uuid.uuid4().hex}"
                    if schedule_dry_run is not None
                    else (
                        f"red-schedule-diagnostic-{uuid.uuid4().hex}"
                        if diagnostic_offsets is not None
                        else f"red-teacher-{uuid.uuid4().hex}"
                    )
                )
            )
            metadata = _recording_metadata(
                rom_path,
                episode_id=episode_id,
                watch=args.watch,
                speed=args.speed,
                assignment=assignment,
                execution=(registry.execution if registry is not None else None),
                schedule_dry_run=schedule_dry_run,
            )
            if diagnostic_offsets is not None:
                if diagnostic_schedule_sha256 is None:
                    raise RuntimeError("diagnostic schedule digest is unavailable")
                _attach_diagnostic_schedule_metadata(
                    metadata,
                    seed=args.diagnostic_schedule_seed,
                    offsets=diagnostic_offsets,
                    schedule_sha256=diagnostic_schedule_sha256,
                )
            private_root = open_private_root(
                args.private_root,
                repository_root=REPOSITORY_ROOT,
            )
            battle_start_offsets = (
                assignment.offsets
                if assignment is not None
                else schedule_dry_run.offsets
                if schedule_dry_run is not None
                else diagnostic_offsets
            )
            dry_run_qualification = None
            if assignment is not None and registry is not None:
                slots = _collection_slots(registry)
                slot = slots[assignment.collection_slot_ordinal - 1]
                if slot.assignment_id != assignment.assignment_id:
                    raise CollectionLedgerError(
                        "collection slot does not match the selected assignment"
                    )
                identity = _campaign_identity(registry, metadata)
                with private_root.collection_session(registry.collection_id) as session:
                    require_dry_run_qualification(
                        private_root,
                        identity,
                        registry.schedule_dry_run,
                    )
                    ledger = CollectionOutcomeLedger.open_or_seal(
                        store=private_root,
                        session=session,
                        identity=identity,
                        slots=slots,
                    )
                    ledger.reconcile()
                    ledger.require_pending(slot)
                    report_completed = False
                    try:
                        qualified_report, episode_summary = _capture_private_recording(
                            private_root,
                            rom_path=rom_path,
                            episode_id=episode_id,
                            metadata=metadata,
                            watch=args.watch,
                            speed=args.speed,
                            battle_start_offsets=battle_start_offsets,
                        )
                        report_completed = True
                    finally:
                        outcome = ledger.reconcile_slot(slot)
                    if report_completed and (
                        outcome is None or outcome.status != "complete" or not outcome.game_complete
                    ):
                        raise CollectionLedgerError(
                            "completed collection run failed outcome verification"
                        )
            elif schedule_dry_run is not None and registry is not None:
                identity = _campaign_identity(registry, metadata)
                with private_root.collection_session(registry.collection_id):
                    qualified_report, episode_summary = _capture_private_recording(
                        private_root,
                        rom_path=rom_path,
                        episode_id=episode_id,
                        metadata=metadata,
                        watch=args.watch,
                        speed=args.speed,
                        battle_start_offsets=battle_start_offsets,
                    )
                    dry_run_qualification = publish_dry_run_qualification(
                        private_root,
                        identity,
                        schedule_dry_run,
                        episode_id,
                    )
            else:
                qualified_report, episode_summary = _capture_private_recording(
                    private_root,
                    rom_path=rom_path,
                    episode_id=episode_id,
                    metadata=metadata,
                    watch=args.watch,
                    speed=args.speed,
                    battle_start_offsets=battle_start_offsets,
                )
            _print_qualified_summary(qualified_report)
            public_play = qualified_report.public_dict()
            payload = {
                "schema": "private-trajectory-recording-v1",
                "status": "ok",
                "game_complete": bool(public_play.get("game_complete")),
                "episode": episode_summary,
            }
            if dry_run_qualification is not None:
                payload["dry_run_qualification"] = dry_run_qualification.public_dict()
    except (
        BootstrapError,
        BattleScheduleError,
        CollectionLedgerError,
        CollectionProtocolError,
        EmulatorError,
        EvaluationIdentityError,
        LearnedBattlePolicyError,
        OpeningChapterError,
        PrivateArtifactError,
        QualifiedPlayError,
        RomValidationError,
        RuntimeIdentityError,
        ScheduleAttestationError,
    ) as error:
        parser.error(
            _public_error_message(
                error,
                private_paths=(
                    rom_path,
                    getattr(args, "rom", None),
                    getattr(args, "private_root", None),
                    getattr(args, "battle_corrections_root", None),
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
