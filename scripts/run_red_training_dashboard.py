#!/usr/bin/env python3
"""Run one clean-power Red teacher-supervised model evaluation with a live dashboard."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import uuid
import webbrowser
from contextlib import suppress
from pathlib import Path

from pokemon_red_completion.battle_semantics import FEATURE_NAMES
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.learned_battle_policy import load_battle_model_artifact
from pokemon_red_completion.play import QualifiedPlayReport, run_qualified_play
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.progress_dashboard import (
    DASHBOARD_DEFAULT_PORT,
    DashboardState,
    ProgressDashboardServer,
)
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_training_dashboard import RED_TRAINING_COMPONENTS
from pokemon_red_completion.red_training_runtime import RedTrainingDashboardTracker
from pokemon_red_completion.rom import resolve_rom_path
from pokemon_red_completion.training_candidate_model import (
    canonical_training_candidate_model_sha256,
    load_training_candidate_model,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATTLE_CONFIDENCE_THRESHOLD = 0.39994808298904233


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--battle-model", type=Path, required=True)
    parser.add_argument("--training-candidate-model", type=Path, required=True)
    parser.add_argument("--training-candidate-file-sha256", required=True)
    parser.add_argument("--corrections-root", type=Path, required=True)
    parser.add_argument(
        "--battle-confidence-threshold",
        type=float,
        default=DEFAULT_BATTLE_CONFIDENCE_THRESHOLD,
    )
    parser.add_argument("--port", type=int, default=DASHBOARD_DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--hold-seconds",
        type=int,
        default=0,
        help="Keep the final dashboard open for N seconds; zero waits for Ctrl-C.",
    )
    args = parser.parse_args(argv)
    if not 0.0 <= args.battle_confidence_threshold <= 1.0:
        parser.error("--battle-confidence-threshold must be between zero and one")
    if args.hold_seconds < 0:
        parser.error("--hold-seconds must be non-negative")

    source = detect_source_identity(REPOSITORY_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(REPOSITORY_ROOT, source)
    rom_path = resolve_rom_path(args.rom)
    battle_model = load_battle_model_artifact(args.battle_model)
    training_candidate_model = load_training_candidate_model(
        args.training_candidate_model,
        expected_sha256=args.training_candidate_file_sha256,
    )
    battle_model_sha256 = hashlib.sha256(
        battle_model.to_json().encode("ascii")
    ).hexdigest()
    training_candidate_model_sha256 = canonical_training_candidate_model_sha256(
        training_candidate_model
    )
    expected = {component.name: component.model_sha256 for component in RED_TRAINING_COMPONENTS}
    if battle_model_sha256 != expected["Battle move ranker"]:
        raise EvaluationIdentityError("battle model is not the frozen Red player v1 candidate")
    if training_candidate_model_sha256 != expected["Team-development ranker"]:
        raise EvaluationIdentityError(
            "training candidate model is not the frozen Red player v1 candidate"
        )
    if tuple(battle_model.feature_names) != FEATURE_NAMES:
        raise EvaluationIdentityError("battle model feature schema is not the live Red schema")

    private_root = open_private_root(
        args.corrections_root,
        repository_root=REPOSITORY_ROOT,
    )
    writer = private_root.begin_artifact(
        f"red-player-v1-shadow-corrections-{uuid.uuid4().hex}",
        kind="battle_corrections",
    )
    state = DashboardState()
    tracker = RedTrainingDashboardTracker(state)
    report: QualifiedPlayReport | None = None
    failure_type: str | None = None
    failure_message_sha256: str | None = None
    failure_snapshot: dict[str, object] | None = None

    with ProgressDashboardServer(state, port=args.port) as dashboard:
        _emit(
            {
                "schema": "pokemon-red-player-v1-dashboard-start-v1",
                "status": "ready",
                "url": dashboard.url,
                "view_only": True,
                "teacher_disagreement_authority": True,
                "team_model_authority": False,
                "goal_and_destination_authority": False,
                "red_sealed_destinations_opened": 0,
                "crystal_contexts_opened": 0,
                "source": source.public_dict(),
            }
        )
        if not args.no_browser:
            webbrowser.open(dashboard.url)
        tracker.start()
        try:
            with writer:
                try:
                    writer.append(
                        "metadata",
                        {
                            "record_type": "red_player_v1_shadow_run",
                            "schema_version": 1,
                            "source": source.public_dict(),
                            "battle_model_sha256": battle_model_sha256,
                            "training_candidate_model_sha256": (
                                training_candidate_model_sha256
                            ),
                            "battle_feature_schema_id": (
                                "pokemon.core.battle.move-ranker.v3"
                            ),
                            "battle_confidence_threshold": (
                                args.battle_confidence_threshold
                            ),
                            "teacher_agreement_required": True,
                            "training_candidate_authority": False,
                            "goal_manager_authority": False,
                            "destination_ranker_authority": False,
                        },
                    )
                    with PyBoyAdapter(
                        rom_path,
                        frame_observer=tracker.frame_observer,
                    ) as emulator:
                        report = run_qualified_play(
                            rom_path,
                            battle_model=battle_model,
                            battle_model_confidence_threshold=(
                                args.battle_confidence_threshold
                            ),
                            require_battle_model_teacher_agreement=True,
                            require_teacher_free_battle_policy=False,
                            battle_correction_sink=(
                                lambda record: writer.append("corrections", record)
                            ),
                            battle_policy_progress_sink=tracker.on_battle_policy,
                            training_candidate_model=training_candidate_model,
                            training_candidate_model_file_sha256=(
                                args.training_candidate_file_sha256
                            ),
                            execute_training_candidate_model=False,
                            training_candidate_progress_sink=tracker.on_team_policy,
                            progress=tracker.on_progress,
                            _emulator=emulator,
                        )
                    writer.append(
                        "summary",
                        {
                            "record_type": "red_player_v1_shadow_summary",
                            "schema_version": 1,
                            "battle_policy": report.battle_policy_report,
                            "training_candidate_policy": (
                                report.training_candidate_policy_report
                            ),
                            "game_complete": report.passed,
                        },
                    )
                except (Exception, KeyboardInterrupt, SystemExit) as error:
                    failure_type = type(error).__name__
                    failure_message_sha256 = _exception_message_sha256(error)
                    failure_snapshot = tracker.diagnostic_snapshot()
                    # Preserve the original emulator/runtime failure if diagnostic
                    # retention itself encounters an I/O or validation error.
                    with suppress(Exception):
                        writer.append(
                            "failure",
                            _private_failure_record(
                                error=error,
                                snapshot=failure_snapshot,
                            ),
                        )
                    raise
        except (Exception, KeyboardInterrupt, SystemExit) as error:
            failure_type = failure_type or type(error).__name__
            failure_message_sha256 = (
                failure_message_sha256 or _exception_message_sha256(error)
            )
            failure_snapshot = failure_snapshot or tracker.diagnostic_snapshot()
            tracker.fail_run(exception_type=failure_type)
        else:
            assert report is not None
            tracker.pass_run(report)

        receipt = _receipt(
            source=source.public_dict(),
            report=report,
            failure_type=failure_type,
            failure_message_sha256=failure_message_sha256,
            failure_snapshot=failure_snapshot,
            correction_artifact=writer.summary.public_dict(),
            battle_model_sha256=battle_model_sha256,
            training_candidate_model_sha256=training_candidate_model_sha256,
            battle_confidence_threshold=args.battle_confidence_threshold,
        )
        _emit(receipt)
        _hold_dashboard(args.hold_seconds)
    return 0 if report is not None and report.passed else 2


def _receipt(
    *,
    source: dict[str, str | bool],
    report: QualifiedPlayReport | None,
    failure_type: str | None,
    failure_message_sha256: str | None,
    failure_snapshot: dict[str, object] | None,
    correction_artifact: dict[str, object],
    battle_model_sha256: str,
    training_candidate_model_sha256: str,
    battle_confidence_threshold: float,
) -> dict[str, object]:
    battle_policy = report.battle_policy_report if report is not None else None
    team_policy = report.training_candidate_policy_report if report is not None else None
    collection = (
        report.collection_progress.public_dict()
        if report is not None and report.collection_progress is not None
        else None
    )
    passed = report is not None and report.passed
    return {
        "schema": "pokemon-red-player-v1-shadow-evaluation-v1",
        "status": "passed_shadow_evaluation" if passed else "failed_shadow_evaluation",
        "claim": (
            "One clean-power Red run evaluated learned battle and team-development heads under "
            "teacher supervision; it is not an end-to-end autonomous-player claim."
        ),
        "source": source,
        "models": {
            "battle_move_canonical_sha256": battle_model_sha256,
            "team_development_canonical_sha256": training_candidate_model_sha256,
        },
        "authority": {
            "battle_move": "teacher_supervised",
            "team_development": "shadow_only",
            "goal_manager": "offline",
            "destination_ranker": "offline",
        },
        "configuration": {
            "battle_confidence_threshold": battle_confidence_threshold,
            "clean_power": True,
            "save_on_exit": False,
        },
        "run": {
            "game_complete": passed,
            "frames_executed": report.frames_executed if report is not None else None,
            "actions_executed": report.actions_executed if report is not None else None,
            "controller_released": report.controller_released if report is not None else None,
            "failure_type": failure_type,
            "failure_message_sha256": failure_message_sha256,
            "last_verified": failure_snapshot,
        },
        "battle_policy": battle_policy,
        "training_candidate_policy": team_policy,
        "collection_progress": collection,
        "correction_artifact": correction_artifact,
        "promotion_eligible": False,
        "red_sealed_destinations_opened": 0,
        "crystal_contexts_opened": 0,
        "private_path_fields": 0,
    }


def _private_failure_record(
    *,
    error: BaseException,
    snapshot: dict[str, object],
) -> dict[str, object]:
    message = str(error)
    retained_message = _path_free_exception_message(message)
    return {
        "record_type": "red_player_v1_shadow_failure",
        "schema_version": 2,
        "exception_type": type(error).__name__,
        "exception_message": retained_message,
        "exception_message_retained_exactly": retained_message == message,
        "exception_message_redacted": retained_message != message,
        "exception_message_sha256": _exception_message_sha256(error),
        "last_verified": snapshot,
    }


def _exception_message_sha256(error: BaseException) -> str:
    return hashlib.sha256(str(error).encode("utf-8")).hexdigest()


_PRIVATE_PATH_TOKEN = re.compile(
    r"(?i)(?:file:(?://)?[^\s'\"]+|(?<![\w])~(?:[/\\][^\s'\"]*)?"
    r"|(?<![\w])(?:\.{1,2}[/\\][^\s'\"]+"
    r"|(?=[^\s'\"]*[a-z_.-])(?:[a-z0-9_.-]+[/\\])+[^\s'\"]+)"
    r"|(?<![\w])/(?:[^\s'\"]+)|(?<![\w])[a-z]:[/\\][^\s'\"]+"
    r"|\\\\[^\s'\"]+)"
)


def _path_free_exception_message(message: str) -> str:
    """Retain diagnostic text while replacing path-bearing tokens."""

    return _PRIVATE_PATH_TOKEN.sub("[private-path]", message)


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, allow_nan=False, indent=2, sort_keys=True), flush=True)


def _hold_dashboard(seconds: int) -> None:
    try:
        if seconds == 0:
            while True:
                time.sleep(0.5)
        else:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                time.sleep(min(0.5, deadline - time.monotonic()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        _emit(
            {
                "schema": "pokemon-red-player-v1-dashboard-error-v1",
                "status": "blocked",
                "reason": type(error).__name__,
                "message_sha256": _exception_message_sha256(error),
                "private_path_fields": 0,
            }
        )
        raise SystemExit(2) from None
