#!/usr/bin/env python3
"""Show the honest Red completion-aware party-learning readiness gate."""

from __future__ import annotations

import argparse
import json
import stat
import sys
import time
import webbrowser
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.party_development_readiness_dashboard import (  # noqa: E402
    party_development_readiness_dashboard_snapshot,
)
from pokemon_red_completion.private_artifacts import PRIVATE_ROOT_SENTINEL  # noqa: E402
from pokemon_red_completion.progress_dashboard import (  # noqa: E402
    DASHBOARD_DEFAULT_PORT,
    DashboardSnapshot,
    DashboardState,
    ProgressDashboardError,
    ProgressDashboardServer,
)

EVIDENCE_PATH = (
    PROJECT_ROOT / "docs" / "evidence" / "party-development-v2-readiness-2026-08-16.json"
)
V4_EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-party-development-pp-materialization-v4-preflight-2026-08-16.json"
)
V4_EVIDENCE_SCHEMA = "pokemon.red.party-development-pp-materialization-v4-preflight-evidence.v1"
# Keep the readiness view separate from both the historical Pokémon dashboard
# (8765) and an existing local dashboard already using 8766 on the owner host.
DEFAULT_READINESS_PORT = DASHBOARD_DEFAULT_PORT + 2
_LIVE_STREAM_MAX_BYTES = 1024 * 1024
_LIVE_PARTITIONS = ("train", "development")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_READINESS_PORT)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--private-artifact-root", type=Path)
    parser.add_argument("--partition", choices=_LIVE_PARTITIONS, default="train")
    return parser


def _load_evidence() -> dict[str, object]:
    value = json.loads(EVIDENCE_PATH.read_text(encoding="ascii"))
    if not isinstance(value, dict):
        raise ProgressDashboardError("party-development readiness evidence must be a JSON object")
    return value


def _load_v4_evidence() -> dict[str, object]:
    value = json.loads(V4_EVIDENCE_PATH.read_text(encoding="ascii"))
    if not isinstance(value, dict):
        raise ProgressDashboardError("PP v4 preflight evidence must be a JSON object")
    return value


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ProgressDashboardError(f"PP v4 {key.replace('_', ' ')} is invalid")
    return value


def _current_snapshot(
    readiness: Mapping[str, object],
    v4_evidence: Mapping[str, object],
):
    base = party_development_readiness_dashboard_snapshot(readiness)
    if (
        v4_evidence.get("schema") != V4_EVIDENCE_SCHEMA
        or v4_evidence.get("status") != "ready_for_one_partition_owner_authorization"
    ):
        raise ProgressDashboardError("PP v4 preflight evidence is unsupported")
    source = _mapping(v4_evidence, "execution_source")
    packet = _mapping(v4_evidence, "immutable_packet")
    preflight = _mapping(v4_evidence, "read_only_preflight")
    audit = _mapping(v4_evidence, "independent_audit")
    authorization = _mapping(v4_evidence, "authorization")
    source_commit = source.get("git_commit")
    ci_run = source.get("github_ci_run")
    ci_attempt = source.get("github_ci_attempt")
    plan_file_sha256 = packet.get("private_plan_file_sha256")
    maximum_battles = packet.get("maximum_completed_battles")
    minimum_headroom = packet.get("minimum_battle_headroom")
    if (
        not isinstance(source_commit, str)
        or len(source_commit) != 40
        or not isinstance(ci_run, int)
        or isinstance(ci_run, bool)
        or ci_run <= 0
        or not isinstance(ci_attempt, int)
        or isinstance(ci_attempt, bool)
        or ci_attempt <= 0
        or source.get("github_ci_conclusion") != "success"
        or not isinstance(plan_file_sha256, str)
        or len(plan_file_sha256) != 64
        or maximum_battles != 32
        or minimum_headroom != 5
        or preflight.get("train_status") != "ready_authorization_required"
        or preflight.get("development_status") != "ready_authorization_required"
        or preflight.get("controller_actions") != 0
        or preflight.get("teacher_queries") != 0
        or preflight.get("model_predictions") != 0
        or preflight.get("learner_outcomes_opened") != 0
        or preflight.get("materializations_completed") != 0
        or audit.get("verdict") != "approve_request_for_exactly_one_named_partition"
        or authorization.get("granted") is not False
        or authorization.get("authorized_partition") is not None
    ):
        raise ProgressDashboardError("PP v4 readiness evidence is inconsistent")

    retained_events = tuple(
        event
        for event in base.events
        if not event.startswith("Per-source hard bounds") and not event.startswith("Next:")
    )
    return replace(
        base,
        message=(
            "V4 is frozen and both natural middle-PP sources pass read-only preflight. "
            "Claude approved asking for one partition; train still requires exact owner authority."
        ),
        location="Natural PP preparation gate · train authorization pending",
        events=(
            (
                f"V4 packet verified · source {source_commit[:7]} · CI {ci_run} "
                f"attempt {ci_attempt} · plan {plan_file_sha256[:8]}…"
            ),
            "Read-only preflights 2/2 · Claude APPROVE to ask · controller actions 0",
            *retained_events,
            (
                f"Per-source hard bounds · battles {maximum_battles} · minimum headroom "
                f"{minimum_headroom} · encounter steps 10000 · actions 250000 · frames 5000000"
            ),
            (
                "Next: exact owner authorization for train once; development remains separate, "
                "then freeze and review the 8+6 catalog"
            ),
        ),
    )


def _require_monitor_root(path: Path | None) -> Path | None:
    if path is None:
        return None
    if not path.is_absolute():
        raise ProgressDashboardError("dashboard private artifact root must be absolute")
    try:
        metadata = path.lstat()
        sentinel = (path / PRIVATE_ROOT_SENTINEL).lstat()
    except OSError:
        raise ProgressDashboardError("dashboard private artifact root is unavailable") from None
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(sentinel.st_mode)
        or stat.S_ISLNK(sentinel.st_mode)
    ):
        raise ProgressDashboardError("dashboard private artifact root is invalid")
    return path


def _artifact_directory(root: Path, partition: str) -> Path | None:
    if partition not in _LIVE_PARTITIONS:
        raise ProgressDashboardError("dashboard PP partition is invalid")
    artifact_id = f"red-party-pp-materialization-v1-{partition}"
    existing: list[Path] = []
    for candidate in (
        root / f"{artifact_id}.partial",
        root / artifact_id,
        root / f"{artifact_id}.failed.partial",
    ):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise ProgressDashboardError("dashboard PP artifact cannot be inspected") from None
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise ProgressDashboardError("dashboard PP artifact is invalid")
        existing.append(candidate)
    if len(existing) > 1:
        raise ProgressDashboardError("dashboard PP artifact identity is ambiguous")
    return existing[0] if existing else None


def _latest_stream_record(
    directory: Path,
    stream: str,
    *,
    expected_record_type: str,
) -> dict[str, object] | None:
    path = directory / f"{stream}.jsonl"
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        raise ProgressDashboardError("dashboard PP stream cannot be inspected") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_size > _LIVE_STREAM_MAX_BYTES
    ):
        raise ProgressDashboardError("dashboard PP stream is invalid")
    try:
        payload = path.read_bytes()
    except OSError:
        raise ProgressDashboardError("dashboard PP stream cannot be read") from None
    lines = payload.split(b"\n")
    if payload and not payload.endswith(b"\n"):
        lines = lines[:-1]
    for line in reversed(lines):
        if not line:
            continue
        try:
            value = json.loads(line.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProgressDashboardError("dashboard PP stream record is invalid") from None
        if not isinstance(value, dict):
            raise ProgressDashboardError("dashboard PP stream record is invalid")
        if value.get("record_type") != expected_record_type or value.get("schema_version") != 1:
            raise ProgressDashboardError("dashboard PP stream record is unsupported")
        return value
    return None


def _live_artifact_record(
    root: Path,
    partition: str,
) -> tuple[str, dict[str, object] | None]:
    directory = _artifact_directory(root, partition)
    if directory is None:
        return "waiting", None
    failure = _latest_stream_record(
        directory,
        "failure",
        expected_record_type="party_development_pp_materialization_failure",
    )
    if failure is not None:
        return "failed", failure
    terminal = _latest_stream_record(
        directory,
        "terminal",
        expected_record_type="party_development_pp_materialization_terminal",
    )
    if terminal is not None:
        return "passed", terminal
    progress = _latest_stream_record(
        directory,
        "progress",
        expected_record_type="party_development_pp_materialization_progress",
    )
    if progress is not None:
        return "running", progress
    return "claimed", None


def _record_count(record: Mapping[str, object], key: str) -> int:
    value = record.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise ProgressDashboardError(f"dashboard PP {key.replace('_', ' ')} is invalid")
    return value


def _live_snapshot(
    base: DashboardSnapshot,
    *,
    partition: str,
    status: str,
    record: Mapping[str, object] | None,
    train_prepared: bool = False,
) -> DashboardSnapshot:
    label = partition.title()
    if status == "waiting":
        return base
    if status == "claimed":
        return replace(
            base,
            run_status="running",
            message=(
                f"{label} output identity is durably claimed. Waiting for the first "
                "path-free battle progress receipt."
            ),
            location=f"{label} natural PP preparation · starting",
            events=(
                f"{label} one-shot artifact claimed · no progress receipt yet",
                *base.events[:23],
            ),
        )
    if record is None:
        raise ProgressDashboardError("dashboard PP live record is missing")
    if status == "failed":
        return replace(
            base,
            run_status="failed",
            message=(
                f"{label} preparation stopped fail-closed. The private receipt retains the "
                "failure; this dashboard exposes no private path or game identity."
            ),
            location=f"{label} natural PP preparation · failed",
            events=(
                f"{label} preparation failed closed · no retry inferred by dashboard",
                *base.events[:23],
            ),
        )

    battles = _record_count(record, "battles_completed")
    encounter_steps = _record_count(record, "encounter_steps")
    actions = _record_count(record, "controller_actions")
    frames = _record_count(record, "frames_executed")
    protected_counts = tuple(
        _record_count(record, key)
        for key in (
            "candidate_menus_constructed",
            "learner_outcomes_opened",
            "teacher_queries",
            "model_predictions",
        )
    )
    if battles > 32 or encounter_steps > 10_000 or actions > 250_000 or frames > 5_000_000:
        raise ProgressDashboardError("dashboard PP progress exceeds its frozen bounds")
    if any(protected_counts):
        raise ProgressDashboardError("dashboard PP progress opened a prohibited context")
    current_pp = _record_count(
        record, "current_total_pp" if status == "running" else "final_total_pp"
    )
    maximum_pp = _record_count(record, "maximum_total_pp")
    if maximum_pp == 0 or current_pp > maximum_pp:
        raise ProgressDashboardError("dashboard PP total is invalid")
    if status == "passed":
        if (
            record.get("partition") != partition
            or record.get("final_pp_bin") != "middle"
            or any(
                _record_count(record, key)
                for key in (
                    "faints",
                    "new_persistent_statuses",
                    "heals",
                    "party_switches",
                    "captures",
                    "storage_accesses",
                    "model_updates",
                )
            )
        ):
            raise ProgressDashboardError("dashboard PP terminal state is inconsistent")
        retained_events = tuple(
            event
            for event in base.events
            if not event.startswith("Natural middle-PP preparations")
            and not event.startswith("Next:")
        )
        if partition == "train":
            preparation_event = (
                "Natural middle-PP preparations 1/2 · train complete · "
                "development authorization absent"
            )
            next_event = (
                "Next: separately authorize development once; if accepted, re-inventory both "
                "states and freeze the 8+6 menus"
            )
        elif train_prepared:
            preparation_event = (
                "Natural middle-PP preparations 2/2 · train and development complete"
            )
            next_event = (
                "Next: re-inventory both accepted states and freeze the exact 8+6 menus before "
                "opening any outcome"
            )
        else:
            preparation_event = "Development middle-PP preparation complete · train not reconciled"
            next_event = (
                "Next: reconcile the train receipt before claiming 2/2 or freezing the 8+6 menus"
            )
        return replace(
            base,
            run_status="passed",
            stage_progress=1.0,
            actions=actions,
            frame_count=frames,
            message=(
                f"{label} natural middle-PP state completed: {battles} battles, "
                f"{current_pp}/{maximum_pp} total PP, zero learner outcomes."
            ),
            location=f"{label} natural PP preparation · complete",
            events=(
                f"{label} PP state complete · battles {battles} · steps {encounter_steps} · "
                f"actions {actions} · frames {frames}",
                preparation_event,
                *retained_events[:21],
                next_event,
            ),
        )
    if status != "running":
        raise ProgressDashboardError("dashboard PP live status is unsupported")
    return replace(
        base,
        run_status="running",
        stage_progress=min(battles / 32, 0.99),
        actions=actions,
        frame_count=frames,
        message=(
            f"{label} preparation is running: {battles}/32 battle cap, "
            f"{current_pp}/{maximum_pp} total PP, no teacher/model/outcome access."
        ),
        location=f"{label} natural PP preparation · battle {battles}/32",
        events=(
            f"{label} live progress · battles {battles} · steps {encounter_steps} · "
            f"actions {actions} · frames {frames}",
            *base.events[:23],
        ),
    )


def _development_gate_snapshot(
    base: DashboardSnapshot,
    train_terminal: Mapping[str, object],
) -> DashboardSnapshot:
    accepted_train = _live_snapshot(
        base,
        partition="train",
        status="passed",
        record=train_terminal,
    )
    return replace(
        accepted_train,
        run_status="waiting",
        stage_progress=0.5,
        actions=0,
        frame_count=0,
        message=(
            "Train's natural middle-PP state is accepted. Development passes read-only "
            "preflight and requires its own exact owner authorization."
        ),
        location="Natural PP preparation gate · development authorization pending",
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.duration_seconds < 0:
        raise ProgressDashboardError("dashboard duration must be non-negative")
    evidence = _load_evidence()
    v4_evidence = _load_v4_evidence()
    preparation_base = _current_snapshot(evidence, v4_evidence)
    monitor_root = _require_monitor_root(args.private_artifact_root)
    completed_train = False
    train_live_record: tuple[str, dict[str, object] | None] | None = None
    base_snapshot = preparation_base
    if monitor_root is not None:
        train_live_record = _live_artifact_record(monitor_root, "train")
        completed_train = train_live_record[0] == "passed"
        if args.partition == "development" and completed_train:
            if train_live_record[1] is None:  # pragma: no cover - live reader owns this invariant
                raise ProgressDashboardError("dashboard train terminal is missing")
            base_snapshot = _development_gate_snapshot(
                preparation_base,
                train_live_record[1],
            )
    initial_live_record: tuple[str, dict[str, object] | None] | None = None
    initial_snapshot = base_snapshot
    if monitor_root is not None:
        initial_live_record = (
            train_live_record
            if args.partition == "train"
            else _live_artifact_record(monitor_root, args.partition)
        )
        if initial_live_record is None:  # pragma: no cover - branch above always assigns it
            raise AssertionError("dashboard live record disappeared")
        initial_snapshot = _live_snapshot(
            base_snapshot,
            partition=args.partition,
            status=initial_live_record[0],
            record=initial_live_record[1],
            train_prepared=completed_train,
        )
    state = DashboardState(initial_snapshot)
    with ProgressDashboardServer(state, port=args.port) as dashboard:
        print(
            json.dumps(
                {
                    "schema": "pokemon-party-development-v2-readiness-dashboard-v1",
                    "url": dashboard.url,
                    "view_only": True,
                    "venue_priors": 2,
                    "reserved_roots": "8 train / 6 development",
                    "pp_materializations": "1/2" if completed_train else "0/2",
                    "read_only_preflights": "2/2",
                    "independent_audit": "approve_to_request_one_partition",
                    "authorization_pending": "development" if completed_train else "train",
                    "maximum_completed_battles": 32,
                    "minimum_battle_headroom": 5,
                    "frozen_menus": 0,
                    "outcome_collection_progress": "0/14",
                    "model_fit": False,
                    "teacher_queries": 0,
                    "controller_actions": initial_snapshot.actions,
                    "sealed_red_cases_opened": 0,
                    "crystal_cases_opened": 0,
                    "authority_promoted": False,
                    "private_path_fields": 0,
                    "live_progress_monitor": monitor_root is not None,
                    "live_game_frame": False,
                },
                sort_keys=True,
            )
        )
        if not args.no_browser:
            webbrowser.open(dashboard.url)
        started = time.monotonic()
        previous_live_record = initial_live_record
        try:
            while args.duration_seconds == 0 or time.monotonic() - started < args.duration_seconds:
                if monitor_root is not None:
                    live_record = _live_artifact_record(monitor_root, args.partition)
                    if live_record != previous_live_record:
                        state.publish(
                            _live_snapshot(
                                base_snapshot,
                                partition=args.partition,
                                status=live_record[0],
                                record=live_record[1],
                                train_prepared=completed_train,
                            )
                        )
                        previous_live_record = live_record
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
