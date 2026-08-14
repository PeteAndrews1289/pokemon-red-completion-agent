#!/usr/bin/env python3
"""Run a complete private Red goal-context preflight or frozen collection batch."""

from __future__ import annotations

import argparse
import json
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalogError,
    open_goal_manager_context_capture,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_dataset import (
    GoalManagerDatasetError,
    load_assigned_goal_manager_episode,
)
from pokemon_red_completion.goal_manager_preflight import (
    GoalManagerPreflightError,
    parse_goal_manager_preflight,
)
from pokemon_red_completion.goal_manager_protocol import (
    GoalManagerCollectionRegistry,
    GoalManagerProtocolError,
    load_committed_goal_manager_registry,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    open_private_root,
)
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    load_red_goal_context_profile,
)
from pokemon_red_completion.rom import RomValidationError, resolve_rom_path, verify_rom

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_SCRIPT = PROJECT_ROOT / "scripts" / "preflight_goal_manager_context.py"
REHEARSAL_SCRIPT = PROJECT_ROOT / "scripts" / "rehearse_goal_manager_context.py"
COLLECTION_SCRIPT = PROJECT_ROOT / "scripts" / "collect_goal_manager_context.py"
PLAN_SCHEMA = "pokemon-red-private-goal-manager-context-plan-v1"
_MAX_PLAN_BYTES = 2 * 1024 * 1024


class GoalManagerContextBatchError(RuntimeError):
    """Raised before a private batch can cross its declared stage boundary."""


@dataclass(frozen=True, slots=True)
class _PlanEntry:
    slot_id: str
    state: Path
    envelope: Path
    profile: Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=("preflight", "rehearse", "collect"),
        required=True,
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--preflight-root", type=Path)
    parser.add_argument("--context-catalog", type=Path)
    parser.add_argument("--private-root", type=Path)
    return parser


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _load_plan(
    path: Path,
    registry: GoalManagerCollectionRegistry,
) -> tuple[_PlanEntry, ...]:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise GoalManagerContextBatchError("private context plan must remain external")
    try:
        payload = resolved.read_bytes()
    except OSError:
        raise GoalManagerContextBatchError("private context plan is unavailable") from None
    if not payload or len(payload) > _MAX_PLAN_BYTES:
        raise GoalManagerContextBatchError("private context plan size is invalid")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise GoalManagerContextBatchError("private context plan is not canonical JSON") from None
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise GoalManagerContextBatchError("private context plan is not canonical JSON")
    if set(value) != {"entries", "registry_sha256", "schema", "source_commit"}:
        raise GoalManagerContextBatchError("private context plan fields differ")
    if (
        value.get("schema") != PLAN_SCHEMA
        or value.get("registry_sha256") != registry.registry_sha256
        or value.get("source_commit") != registry.execution.source_commit
    ):
        raise GoalManagerContextBatchError("private context plan identity differs")
    raw_entries = value.get("entries")
    if not isinstance(raw_entries, list):
        raise GoalManagerContextBatchError("private context plan entries must be a list")
    entries: list[_PlanEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict) or set(raw) != {
            "envelope",
            "profile",
            "slot_id",
            "state",
        }:
            raise GoalManagerContextBatchError("private context plan entry differs")
        if any(not isinstance(raw.get(key), str) for key in raw):
            raise GoalManagerContextBatchError("private context plan entry value is invalid")
        entries.append(
            _PlanEntry(
                slot_id=str(raw["slot_id"]),
                state=Path(str(raw["state"])),
                envelope=Path(str(raw["envelope"])),
                profile=Path(str(raw["profile"])),
            )
        )
    expected = tuple(slot.slot_id for slot in registry.slots)
    if tuple(entry.slot_id for entry in entries) != expected:
        raise GoalManagerContextBatchError(
            "private context plan must cover every slot in registry order"
        )
    path_groups = {
        "state": tuple(entry.state for entry in entries),
        "envelope": tuple(entry.envelope for entry in entries),
        "profile": tuple(entry.profile for entry in entries),
    }
    for subject, paths in path_groups.items():
        resolved_paths = tuple(path.resolve() for path in paths)
        if (
            any(not path.is_absolute() for path in paths)
            or len(set(paths)) != len(paths)
            or len(set(resolved_paths)) != len(resolved_paths)
        ):
            raise GoalManagerContextBatchError(
                f"private context plan {subject} paths must be absolute and unique"
            )
    return tuple(entries)


def _validated_inputs(
    entries: tuple[_PlanEntry, ...],
    *,
    rom_path: Path,
) -> None:
    repository = PROJECT_ROOT.resolve()
    rom_parent = rom_path.resolve().parent
    state_digests: set[str] = set()
    envelope_digests: set[str] = set()
    for entry in entries:
        for path in (entry.state, entry.envelope, entry.profile):
            resolved = path.resolve()
            try:
                metadata = path.lstat()
            except OSError:
                raise GoalManagerContextBatchError(
                    "a private context input is unavailable"
                ) from None
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or resolved.is_relative_to(repository)
                or resolved.parent == rom_parent
            ):
                raise GoalManagerContextBatchError("a private context input location is invalid")
        capture = open_goal_manager_context_capture(entry.state, entry.envelope)
        profile = load_red_goal_context_profile(entry.profile)
        if capture.capture_id != entry.slot_id or profile.profile_id != entry.slot_id:
            raise GoalManagerContextBatchError(
                "private capture or profile identity differs from its slot"
            )
        if capture.state_sha256 in state_digests or capture.envelope_sha256 in envelope_digests:
            raise GoalManagerContextBatchError("private context plan repeats a capture")
        state_digests.add(capture.state_sha256)
        envelope_digests.add(capture.envelope_sha256)


def _external_directory(path: Path | None, *, empty: bool) -> Path:
    if path is None:
        raise GoalManagerContextBatchError("the selected batch stage is missing an output root")
    resolved = path.resolve()
    if not resolved.is_dir() or resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise GoalManagerContextBatchError("private batch root must be an external directory")
    if empty and any(resolved.iterdir()):
        raise GoalManagerContextBatchError("preflight batch root must be empty")
    return resolved


def _invoke(command: list[str], *, slot_id: str) -> dict[str, object]:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise GoalManagerContextBatchError(f"private batch stopped at public slot {slot_id}")
    try:
        summary = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise GoalManagerContextBatchError(
            f"private batch received an invalid summary at public slot {slot_id}"
        ) from None
    if not isinstance(summary, dict):
        raise GoalManagerContextBatchError(
            f"private batch received an invalid summary at public slot {slot_id}"
        )
    return summary


def _preflight(
    entries: tuple[_PlanEntry, ...],
    registry: GoalManagerCollectionRegistry,
    *,
    rom_path: Path,
    output_root: Path,
) -> dict[str, object]:
    for entry in entries:
        destination = output_root / f"{entry.slot_id}.json"
        _invoke(
            [
                sys.executable,
                str(PREFLIGHT_SCRIPT),
                "--slot-id",
                entry.slot_id,
                "--state",
                str(entry.state),
                "--envelope",
                str(entry.envelope),
                "--profile",
                str(entry.profile),
                "--out",
                str(destination),
                "--rom",
                str(rom_path),
            ],
            slot_id=entry.slot_id,
        )
        assignment = registry.assignment(entry.slot_id)
        receipt = parse_goal_manager_preflight(destination.read_bytes(), assignment)
        if not receipt.passed:
            raise GoalManagerContextBatchError(
                f"private preflight did not pass at public slot {entry.slot_id}"
            )
    return {
        "schema": "pokemon-red-goal-manager-preflight-batch-summary-v1",
        "planned_contexts": len(entries),
        "passed_contexts": len(entries),
        "actions_executed": 0,
        "episodes_created": 0,
        "status": "complete",
        "private_path_fields": 0,
    }


def _rehearse(
    entries: tuple[_PlanEntry, ...],
    registry: GoalManagerCollectionRegistry,
    *,
    rom_path: Path,
    context_catalog: Path | None,
) -> dict[str, object]:
    if context_catalog is None:
        raise GoalManagerContextBatchError("rehearsal requires a frozen context catalog")
    catalog = parse_goal_manager_context_catalog(context_catalog.read_bytes(), registry)
    for entry in entries:
        context = catalog.entry(entry.slot_id)
        capture = open_goal_manager_context_capture(entry.state, entry.envelope)
        if (
            capture.capture_id != context.capture_id
            or capture.state_sha256 != context.state_sha256
            or capture.envelope_sha256 != context.envelope_sha256
        ):
            raise GoalManagerContextBatchError(
                "private rehearsal input differs from the frozen catalog"
            )

    actions_executed = 0
    frames_executed = 0
    for entry in entries:
        summary = _invoke(
            [
                sys.executable,
                str(REHEARSAL_SCRIPT),
                "--slot-id",
                entry.slot_id,
                "--state",
                str(entry.state),
                "--envelope",
                str(entry.envelope),
                "--profile",
                str(entry.profile),
                "--context-catalog",
                str(context_catalog),
                "--rom",
                str(rom_path),
            ],
            slot_id=entry.slot_id,
        )
        execution = summary.get("execution")
        if (
            summary.get("status") != "passed_uncounted_rehearsal"
            or summary.get("counted") is not False
            or summary.get("episode_created") is not False
            or not isinstance(execution, dict)
            or execution.get("status") != "succeeded"
            or type(execution.get("actions_executed")) is not int
            or type(execution.get("frames_executed")) is not int
        ):
            raise GoalManagerContextBatchError(
                f"private batch received an invalid rehearsal at public slot {entry.slot_id}"
            )
        actions_executed += int(execution["actions_executed"])
        frames_executed += int(execution["frames_executed"])
    return {
        "schema": "pokemon-red-goal-manager-rehearsal-batch-summary-v1",
        "planned_contexts": len(entries),
        "passed_contexts": len(entries),
        "actions_executed": actions_executed,
        "frames_executed": frames_executed,
        "episodes_created": 0,
        "counted": False,
        "status": "complete",
        "private_path_fields": 0,
    }


def _collect(
    entries: tuple[_PlanEntry, ...],
    registry: GoalManagerCollectionRegistry,
    *,
    rom_path: Path,
    context_catalog: Path | None,
    private_root_path: Path | None,
) -> dict[str, object]:
    if context_catalog is None or private_root_path is None:
        raise GoalManagerContextBatchError("collection requires a catalog and private root")
    catalog = parse_goal_manager_context_catalog(context_catalog.read_bytes(), registry)
    store = open_private_root(private_root_path, repository_root=PROJECT_ROOT)
    completed: set[str] = set()
    for entry in entries:
        assignment = registry.assignment(entry.slot_id)
        context = catalog.entry(entry.slot_id)
        capture = open_goal_manager_context_capture(entry.state, entry.envelope)
        if (
            capture.capture_id != context.capture_id
            or capture.state_sha256 != context.state_sha256
            or capture.envelope_sha256 != context.envelope_sha256
        ):
            raise GoalManagerContextBatchError(
                "private collection input differs from the frozen catalog"
            )
        state = store.inspect_episode_state(assignment.episode_id)
        if state.status == "complete":
            load_assigned_goal_manager_episode(
                store.open_episode(assignment.episode_id),
                assignment,
                context_catalog=catalog,
            )
            completed.add(entry.slot_id)
        elif state.status != "absent":
            raise GoalManagerContextBatchError(
                f"one-shot episode is not runnable at public slot {entry.slot_id}"
            )
    resumed = len(completed)
    for entry in entries:
        if entry.slot_id in completed:
            continue
        _invoke(
            [
                sys.executable,
                str(COLLECTION_SCRIPT),
                "--slot-id",
                entry.slot_id,
                "--state",
                str(entry.state),
                "--envelope",
                str(entry.envelope),
                "--profile",
                str(entry.profile),
                "--context-catalog",
                str(context_catalog),
                "--private-root",
                str(private_root_path),
                "--rom",
                str(rom_path),
            ],
            slot_id=entry.slot_id,
        )
        assignment = registry.assignment(entry.slot_id)
        load_assigned_goal_manager_episode(
            store.open_episode(assignment.episode_id),
            assignment,
            context_catalog=catalog,
        )
        completed.add(entry.slot_id)
    return {
        "schema": "pokemon-red-goal-manager-collection-batch-summary-v1",
        "planned_contexts": len(entries),
        "completed_contexts": len(completed),
        "resumed_contexts": resumed,
        "status": "complete",
        "private_path_fields": 0,
    }


def _run(args: argparse.Namespace) -> dict[str, object]:
    registry = load_committed_goal_manager_registry(PROJECT_ROOT)
    rom_path = resolve_rom_path(args.rom)
    verify_rom(rom_path)
    entries = _load_plan(args.plan, registry)
    _validated_inputs(entries, rom_path=rom_path)
    if args.stage == "preflight":
        if args.context_catalog is not None or args.private_root is not None:
            raise GoalManagerContextBatchError(
                "preflight does not accept collection-stage inputs"
            )
        return _preflight(
            entries,
            registry,
            rom_path=rom_path,
            output_root=_external_directory(args.preflight_root, empty=True),
        )
    if args.stage == "rehearse":
        if args.preflight_root is not None or args.private_root is not None:
            raise GoalManagerContextBatchError(
                "rehearsal does not accept preflight or collection output roots"
            )
        return _rehearse(
            entries,
            registry,
            rom_path=rom_path,
            context_catalog=args.context_catalog,
        )
    if args.preflight_root is not None:
        raise GoalManagerContextBatchError(
            "collection does not accept a preflight output root"
        )
    return _collect(
        entries,
        registry,
        rom_path=rom_path,
        context_catalog=args.context_catalog,
        private_root_path=args.private_root,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        summary = _run(args)
    except (
        GoalManagerContextBatchError,
        GoalManagerContextCatalogError,
        GoalManagerDatasetError,
        GoalManagerPreflightError,
        GoalManagerProtocolError,
        PrivateArtifactError,
        RedGoalContextProfileError,
        RomValidationError,
        OSError,
    ):
        parser.error("Goal-manager private batch failed closed; private paths were withheld.")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
