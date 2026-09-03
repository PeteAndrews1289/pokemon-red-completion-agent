#!/usr/bin/env python3
"""Materialize a crash-safe batch of frozen natural Red battle scenarios."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_repeatable_battle_scenario_runtime import (  # noqa: E402
    materialize_repeatable_red_battle_scenario,
)
from pokemon_red_completion.red_repeatable_battle_scenario_source import (  # noqa: E402
    inspect_repeatable_red_battle_source,
)
from pokemon_red_completion.repeatable_battle_scenario_factory import (  # noqa: E402
    RepeatableBattleScenarioAssignment,
    parse_repeatable_battle_scenario_plan,
)
from pokemon_red_completion.repeatable_battle_source_catalog import (  # noqa: E402
    RepeatableBattleSourceCatalog,
    parse_repeatable_battle_source_catalog,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402

_JOURNAL_SCHEMA = "pokemon-private-repeatable-battle-materialization-journal-v1"
_SUMMARY_SCHEMA = "pokemon.red.battle.repeatable-materialization-progress.v1"


class RepeatableBattleScenarioBatchError(RuntimeError):
    """Raised when a batch cannot preserve frozen identity or crash semantics."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--source-catalog", type=Path, required=True)
    parser.add_argument("--expected-source-catalog-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument(
        "--partition",
        choices=(ScenarioPartition.TRAIN.value, ScenarioPartition.DEVELOPMENT.value),
        required=True,
    )
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--limit", type=int, default=0, help="zero runs every pending assignment")
    parser.add_argument("--maximum-encounter-steps", type=int, default=512)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=None)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.limit < 0:
        raise RepeatableBattleScenarioBatchError("batch limit cannot be negative")
    if args.speed is not None and not args.watch:
        raise RepeatableBattleScenarioBatchError("--speed requires --watch")
    _require_external_directory(args.output_dir)
    _require_external_parent(args.journal)
    _require_external_parent(args.progress)
    if len({args.journal.resolve(), args.progress.resolve()}) != 2:
        raise RepeatableBattleScenarioBatchError("journal and progress outputs must differ")

    plan_payload = _read_available(args.private_plan, subject="private plan")
    catalog_payload = _read_bound(
        args.source_catalog,
        args.expected_source_catalog_sha256,
        subject="source catalog",
    )
    plan = parse_repeatable_battle_scenario_plan(plan_payload)
    if plan.sha256 != args.expected_plan_sha256:
        raise RepeatableBattleScenarioBatchError("private plan digest differs")
    catalog = parse_repeatable_battle_source_catalog(catalog_payload)
    partition = ScenarioPartition(args.partition)
    assignments = plan.partition_assignments(partition)
    _require_catalog_bindings(assignments, catalog)

    source_identity = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source_identity)
    require_published_source(PROJECT_ROOT, source_identity)
    if source_identity.git_commit is None:  # pragma: no cover - clean source owns this
        raise AssertionError("published batch source lacks a commit")
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    rom_bytes = rom_path.read_bytes()
    expected_journal = _new_journal(
        assignments,
        plan_sha256=args.expected_plan_sha256,
        catalog_sha256=args.expected_source_catalog_sha256,
        source_commit=source_identity.git_commit,
        partition=partition,
    )

    lock_path = args.journal.with_name(f"{args.journal.name}.lock")
    with _exclusive_lock(lock_path):
        if args.journal.exists():
            journal = _load_journal(args.journal, expected_journal)
        else:
            journal = expected_journal
            _write_atomic(args.journal, _payload(journal), require_absent=True, mode=0o600)
        _validate_retained_outputs(journal, output_dir=args.output_dir)
        _publish_progress(
            args.progress,
            journal,
            rom_sha256=rom.sha256,
            require_absent=not args.progress.exists(),
        )

        attempted_this_run = 0
        for index, assignment in enumerate(assignments):
            row = journal["assignments"][index]
            if row["status"] != "pending":
                continue
            if args.limit and attempted_this_run >= args.limit:
                break
            state_path, manifest_path = _output_paths(args.output_dir, assignment)
            if state_path.exists() or manifest_path.exists():
                raise RepeatableBattleScenarioBatchError(
                    "pending assignment output already exists"
                )
            row["status"] = "started"
            row["attempted"] = True
            _write_atomic(args.journal, _payload(journal), require_absent=False, mode=0o600)
            _publish_progress(args.progress, journal, rom_sha256=rom.sha256)
            attempted_this_run += 1
            spec = catalog.source(assignment.source_id)
            try:
                source_bytes = spec.state_path.read_bytes()

                def session_factory() -> PyBoyAdapter:
                    return PyBoyAdapter(
                        rom_path,
                        watch=args.watch,
                        speed=args.speed,
                    )

                source = inspect_repeatable_red_battle_source(
                    source_bytes,
                    source_id=spec.source_id,
                    source_lineage_id=spec.source_lineage_id,
                    partition=spec.partition,
                    source_commit=spec.source_commit,
                    session_factory=session_factory,
                )
                result = materialize_repeatable_red_battle_scenario(
                    source,
                    assignment,
                    source_bytes,
                    rom_bytes=rom_bytes,
                    materializer_source_commit=source_identity.git_commit,
                    session_factory=session_factory,
                    maximum_encounter_steps=args.maximum_encounter_steps,
                )
                _write_new_private(state_path, result.state_bytes)
                _write_new_private(manifest_path, result.manifest_payload)
            except Exception as error:
                reason = str(error) or type(error).__name__
                bounded_reason = reason[:2000]
                row.update(
                    {
                        "status": "failed",
                        "error_type": type(error).__name__,
                        "reason": bounded_reason,
                        "reason_sha256": hashlib.sha256(
                            bounded_reason.encode("utf-8", errors="replace")
                        ).hexdigest(),
                    }
                )
            else:
                row.update(
                    {
                        "status": "succeeded",
                        "state_sha256": hashlib.sha256(result.state_bytes).hexdigest(),
                        "manifest_sha256": hashlib.sha256(
                            result.manifest_payload
                        ).hexdigest(),
                    }
                )
            _write_atomic(args.journal, _payload(journal), require_absent=False, mode=0o600)
            progress = _publish_progress(args.progress, journal, rom_sha256=rom.sha256)
            print(
                json.dumps({"event": "scenario_terminal", **progress}, sort_keys=True),
                flush=True,
            )
        return _progress(journal, rom_sha256=rom.sha256)


def _require_catalog_bindings(
    assignments: tuple[RepeatableBattleScenarioAssignment, ...],
    catalog: RepeatableBattleSourceCatalog,
) -> None:
    for assignment in assignments:
        spec = catalog.source(assignment.source_id)
        if (
            spec.source_lineage_id != assignment.source_lineage_id
            or spec.partition is not assignment.partition
            or spec.source_commit != assignment.source_commit
        ):
            raise RepeatableBattleScenarioBatchError(
                "source catalog differs from a frozen assignment"
            )


def _new_journal(
    assignments: tuple[RepeatableBattleScenarioAssignment, ...],
    *,
    plan_sha256: str,
    catalog_sha256: str,
    source_commit: str,
    partition: ScenarioPartition,
) -> dict[str, Any]:
    return {
        "schema": _JOURNAL_SCHEMA,
        "plan_sha256": plan_sha256,
        "source_catalog_sha256": catalog_sha256,
        "materializer_source_commit": source_commit,
        "partition": partition.value,
        "assignments": [
            {
                "ordinal": ordinal,
                "scenario_id": assignment.scenario_id,
                "semantic_setup_sha256": assignment.semantic_setup_sha256,
                "source_lineage_id": assignment.source_lineage_id,
                "status": "pending",
                "attempted": False,
                "state_sha256": None,
                "manifest_sha256": None,
                "error_type": None,
                "reason": None,
                "reason_sha256": None,
            }
            for ordinal, assignment in enumerate(assignments, start=1)
        ],
    }


def _load_journal(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    try:
        journal = json.loads(path.read_text("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise RepeatableBattleScenarioBatchError("materialization journal is invalid") from None
    if not isinstance(journal, dict) or set(journal) != set(expected):
        raise RepeatableBattleScenarioBatchError("materialization journal fields differ")
    for name in (
        "schema",
        "plan_sha256",
        "source_catalog_sha256",
        "materializer_source_commit",
        "partition",
    ):
        if journal.get(name) != expected[name]:
            raise RepeatableBattleScenarioBatchError(
                "materialization journal identity differs"
            )
    rows = journal.get("assignments")
    expected_rows = expected["assignments"]
    if not isinstance(rows, list) or len(rows) != len(expected_rows):
        raise RepeatableBattleScenarioBatchError("materialization journal roster differs")
    mutable = {
        "status",
        "attempted",
        "state_sha256",
        "manifest_sha256",
        "error_type",
        "reason",
        "reason_sha256",
    }
    for row, expected_row in zip(rows, expected_rows, strict=True):
        if not isinstance(row, dict) or set(row) != set(expected_row):
            raise RepeatableBattleScenarioBatchError("materialization journal row differs")
        if any(row[name] != expected_row[name] for name in set(row) - mutable):
            raise RepeatableBattleScenarioBatchError("materialization journal roster differs")
        status = row["status"]
        if status not in {"pending", "started", "succeeded", "failed"}:
            raise RepeatableBattleScenarioBatchError("materialization journal status differs")
        if row["attempted"] is not (status != "pending"):
            raise RepeatableBattleScenarioBatchError("materialization journal attempt flag differs")
        _require_status_payload(row)
    return journal


def _require_status_payload(row: dict[str, Any]) -> None:
    status = row["status"]
    state_sha256 = row["state_sha256"]
    manifest_sha256 = row["manifest_sha256"]
    error_type = row["error_type"]
    reason = row["reason"]
    reason_sha256 = row["reason_sha256"]
    if status in {"pending", "started"}:
        if any(
            value is not None
            for value in (
                state_sha256,
                manifest_sha256,
                error_type,
                reason,
                reason_sha256,
            )
        ):
            raise RepeatableBattleScenarioBatchError(
                "unfinished materialization journal row has a result"
            )
    elif status == "succeeded":
        if (
            not _is_sha256(state_sha256)
            or not _is_sha256(manifest_sha256)
            or error_type is not None
            or reason is not None
            or reason_sha256 is not None
        ):
            raise RepeatableBattleScenarioBatchError(
                "successful materialization journal result is invalid"
            )
    elif (
        state_sha256 is not None
        or manifest_sha256 is not None
        or not isinstance(error_type, str)
        or not error_type
        or len(error_type) > 160
        or not isinstance(reason, str)
        or not reason
        or len(reason) > 2000
        or not _is_sha256(reason_sha256)
        or hashlib.sha256(reason.encode("utf-8", errors="replace")).hexdigest()
        != reason_sha256
    ):
        raise RepeatableBattleScenarioBatchError(
            "failed materialization journal result is invalid"
        )


def _validate_retained_outputs(journal: dict[str, Any], *, output_dir: Path) -> None:
    for row in journal["assignments"]:
        scenario_id = row["scenario_id"]
        state_path = output_dir / f"{scenario_id}.state"
        manifest_path = output_dir / f"{scenario_id}.state.json"
        if row["status"] == "succeeded":
            if (
                _sha256_or_none(state_path) != row["state_sha256"]
                or _sha256_or_none(manifest_path) != row["manifest_sha256"]
            ):
                raise RepeatableBattleScenarioBatchError(
                    "retained successful output differs from its journal"
                )
        elif row["status"] == "pending" and (state_path.exists() or manifest_path.exists()):
            raise RepeatableBattleScenarioBatchError(
                "pending assignment has an unjournaled output"
            )


def _progress(journal: dict[str, Any], *, rom_sha256: str) -> dict[str, object]:
    rows = journal["assignments"]
    counts = {
        status: sum(row["status"] == status for row in rows)
        for status in ("pending", "started", "succeeded", "failed")
    }
    completed = counts["succeeded"] + counts["failed"] + counts["started"]
    return {
        "schema": _SUMMARY_SCHEMA,
        "partition": journal["partition"],
        "plan_sha256": journal["plan_sha256"],
        "source_catalog_sha256": journal["source_catalog_sha256"],
        "materializer_source_commit": journal["materializer_source_commit"],
        "rom_sha256": rom_sha256,
        "total": len(rows),
        "completed": completed,
        **counts,
        "completion_fraction": completed / len(rows),
        "outcomes": 0,
        "model_fits": 0,
        "model_predictions": 0,
        "teacher_queries": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }


def _publish_progress(
    path: Path,
    journal: dict[str, Any],
    *,
    rom_sha256: str,
    require_absent: bool = False,
) -> dict[str, object]:
    progress = _progress(journal, rom_sha256=rom_sha256)
    _write_atomic(path, _payload(progress), require_absent=require_absent, mode=0o600)
    return progress


def _read_bound(path: Path, expected_sha256: str, *, subject: str) -> bytes:
    payload = _read_available(path, subject=subject)
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise RepeatableBattleScenarioBatchError(f"{subject} digest differs")
    return payload


def _read_available(path: Path, *, subject: str) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError:
        raise RepeatableBattleScenarioBatchError(f"{subject} is unavailable") from None
    return payload


def _require_external_directory(path: Path) -> None:
    if path.resolve().is_relative_to(PROJECT_ROOT.resolve()) or not path.is_dir():
        raise RepeatableBattleScenarioBatchError(
            "materialization output directory must be an existing private directory"
        )


def _require_external_parent(path: Path) -> None:
    if path.resolve().is_relative_to(PROJECT_ROOT.resolve()) or not path.parent.is_dir():
        raise RepeatableBattleScenarioBatchError(
            "materialization journal outputs must remain in an existing private directory"
        )


def _output_paths(
    output_dir: Path,
    assignment: RepeatableBattleScenarioAssignment,
) -> tuple[Path, Path]:
    state = output_dir / f"{assignment.scenario_id}.state"
    return state, state.with_suffix(".state.json")


def _sha256_or_none(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _payload(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def _write_new_private(path: Path, payload: bytes) -> None:
    _write_file(path, payload, flags=os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode=0o600)


def _write_atomic(path: Path, payload: bytes, *, require_absent: bool, mode: int) -> None:
    if require_absent and path.exists():
        raise RepeatableBattleScenarioBatchError("private output already exists")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    _write_file(
        temporary,
        payload,
        flags=os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        mode=mode,
    )
    try:
        if require_absent and path.exists():
            raise RepeatableBattleScenarioBatchError("private output already exists")
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_file(path: Path, payload: bytes, *, flags: int, mode: int) -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            flags | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("private output write made no progress")
            offset += written
        os.fsync(descriptor)
    except OSError:
        raise RepeatableBattleScenarioBatchError(
            "private batch output could not be retained"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _exclusive_lock(path: Path):  # type: ignore[no-untyped-def]
    descriptor = os.open(
        path,
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RepeatableBattleScenarioBatchError(
                "another materialization batch owns this journal"
            ) from None
        yield
    finally:
        os.close(descriptor)


def main() -> int:
    args = _parser().parse_args()
    try:
        result = _run(args)
    except (RepeatableBattleScenarioBatchError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "failed", "reason": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
