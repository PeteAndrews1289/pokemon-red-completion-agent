#!/usr/bin/env python3
"""Run all open Red validation contexts in shadow or causal manager mode."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameSafeExecutor
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
    open_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_promotion import (
    authenticate_goal_manager_candidate,
    authenticate_goal_manager_shadow_receipt,
    build_goal_manager_promotion_receipt,
    load_committed_goal_manager_promotion_plan,
)
from pokemon_red_completion.goal_manager_promotion_runtime import (
    GoalManagerPromotionContextResult,
    evaluate_goal_manager_promotion_context,
    summarize_goal_manager_promotion_results,
)
from pokemon_red_completion.goal_manager_protocol import GoalManagerCollectionRegistry
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.provenance import (
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    load_red_goal_context_profile,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PLAN_SCHEMA = "pokemon-red-private-goal-manager-context-plan-v1"
_MAX_PRIVATE_PLAN_BYTES = 2 * 1024 * 1024
_MAX_RECEIPT_BYTES = 4 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class GoalManagerPromotionRunError(RuntimeError):
    """Raised before private inputs can become a promotion claim."""


@dataclass(frozen=True, slots=True)
class _PlanEntry:
    slot_id: str
    state: Path
    envelope: Path
    profile: Path


@dataclass(frozen=True, slots=True)
class _ValidatedEntry:
    plan: _PlanEntry
    capture: GoalManagerContextCapture
    profile: RedGoalContextProfile


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("shadow", "causal"), required=True)
    parser.add_argument("--private-plan", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--fit-summary", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--shadow-receipt", type=Path)
    parser.add_argument("--shadow-receipt-sha256")
    return parser


def _load_private_plan(
    path: Path,
    registry: GoalManagerCollectionRegistry,
) -> tuple[_PlanEntry, ...]:
    resolved = path.resolve()
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        raise GoalManagerPromotionRunError("private context plan is unavailable") from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or resolved.is_relative_to(PROJECT_ROOT.resolve())
        or not payload
        or len(payload) > _MAX_PRIVATE_PLAN_BYTES
    ):
        raise GoalManagerPromotionRunError("private context plan is invalid")
    document = _canonical_document(payload, subject="private context plan")
    if set(document) != {"entries", "registry_sha256", "schema", "source_commit"}:
        raise GoalManagerPromotionRunError("private context plan fields differ")
    if (
        document.get("schema") != PRIVATE_PLAN_SCHEMA
        or document.get("registry_sha256") != registry.registry_sha256
        or document.get("source_commit") != registry.execution.source_commit
    ):
        raise GoalManagerPromotionRunError("private context plan identity differs")
    rows = document.get("entries")
    if not isinstance(rows, list):
        raise GoalManagerPromotionRunError("private context plan entries are invalid")
    entries: list[_PlanEntry] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "envelope",
            "profile",
            "slot_id",
            "state",
        }:
            raise GoalManagerPromotionRunError("private context plan entry differs")
        if any(not isinstance(value, str) for value in row.values()):
            raise GoalManagerPromotionRunError("private context plan entry is invalid")
        entries.append(
            _PlanEntry(
                slot_id=str(row["slot_id"]),
                state=Path(str(row["state"])),
                envelope=Path(str(row["envelope"])),
                profile=Path(str(row["profile"])),
            )
        )
    expected_slots = tuple(slot.slot_id for slot in registry.slots)
    if tuple(entry.slot_id for entry in entries) != expected_slots:
        raise GoalManagerPromotionRunError(
            "private context plan must cover the historical registry in order"
        )
    for subject, paths in {
        "state": tuple(entry.state for entry in entries),
        "envelope": tuple(entry.envelope for entry in entries),
        "profile": tuple(entry.profile for entry in entries),
    }.items():
        resolved_paths = tuple(item.resolve() for item in paths)
        if (
            any(not item.is_absolute() for item in paths)
            or len(set(paths)) != len(paths)
            or len(set(resolved_paths)) != len(resolved_paths)
        ):
            raise GoalManagerPromotionRunError(
                f"private context plan {subject} paths must be absolute and unique"
            )
    return tuple(entries)


def _validate_open_contexts(
    entries: tuple[_PlanEntry, ...],
    *,
    candidate,  # type: ignore[no-untyped-def]
    rom_path: Path,
) -> tuple[_ValidatedEntry, ...]:
    validation_slots = {
        slot.slot_id for slot in candidate.registry.slots if slot.partition == "validation"
    }
    selected = tuple(entry for entry in entries if entry.slot_id in validation_slots)
    if len(selected) != candidate.plan.validation_examples:
        raise GoalManagerPromotionRunError("open validation context coverage differs")
    repository = PROJECT_ROOT.resolve()
    rom_parent = rom_path.resolve().parent
    state_digests: set[str] = set()
    envelope_digests: set[str] = set()
    result: list[_ValidatedEntry] = []
    for entry in selected:
        for private_path in (entry.state, entry.envelope, entry.profile):
            resolved = private_path.resolve()
            try:
                metadata = private_path.lstat()
            except OSError:
                raise GoalManagerPromotionRunError(
                    "an open validation input is unavailable"
                ) from None
            if (
                private_path.is_symlink()
                or not stat.S_ISREG(metadata.st_mode)
                or resolved.is_relative_to(repository)
                or resolved.parent == rom_parent
            ):
                raise GoalManagerPromotionRunError(
                    "an open validation input location is invalid"
                )
        capture = open_goal_manager_context_capture(entry.state, entry.envelope)
        profile = load_red_goal_context_profile(entry.profile)
        context = candidate.catalog.entry(entry.slot_id)
        if (
            capture.capture_id != entry.slot_id
            or profile.profile_id != entry.slot_id
            or capture.capture_id != context.capture_id
            or capture.state_sha256 != context.state_sha256
            or capture.envelope_sha256 != context.envelope_sha256
            or capture.state_sha256 in state_digests
            or capture.envelope_sha256 in envelope_digests
        ):
            raise GoalManagerPromotionRunError(
                "an open validation input differs from the frozen catalog"
            )
        state_digests.add(capture.state_sha256)
        envelope_digests.add(capture.envelope_sha256)
        result.append(_ValidatedEntry(entry, capture, profile))
    expected_order = tuple(
        slot.slot_id for slot in candidate.registry.slots if slot.partition == "validation"
    )
    if tuple(item.plan.slot_id for item in result) != expected_order:
        raise GoalManagerPromotionRunError("validation context order differs")
    return tuple(result)


def _external_regular(path: Path, *, rom_path: Path, subject: str) -> Path:
    resolved = path.resolve()
    try:
        metadata = path.lstat()
    except OSError:
        raise GoalManagerPromotionRunError(f"{subject} is unavailable") from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved.parent == rom_path.resolve().parent
    ):
        raise GoalManagerPromotionRunError(f"{subject} location is invalid")
    return resolved


def _new_external_receipt(path: Path, *, rom_path: Path) -> Path:
    resolved = path.resolve()
    if (
        resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved.parent == rom_path.resolve().parent
        or not resolved.parent.is_dir()
        or resolved.exists()
        or resolved.name.startswith(".")
    ):
        raise GoalManagerPromotionRunError(
            "promotion receipt must use a new external path"
        )
    return resolved


def _protected_digests(paths: tuple[Path, ...]) -> tuple[tuple[Path, str], ...]:
    return tuple((path, hashlib.sha256(path.read_bytes()).hexdigest()) for path in paths)


def _require_unchanged(protected: tuple[tuple[Path, str], ...]) -> None:
    try:
        changed = any(
            hashlib.sha256(path.read_bytes()).hexdigest() != expected
            for path, expected in protected
        )
    except OSError:
        changed = True
    if changed:
        raise GoalManagerPromotionRunError("promotion changed a protected input")


def _write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        with suppress(OSError):
            path.unlink()
        raise


def _run(args: argparse.Namespace) -> tuple[dict[str, object], Path]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    plan, evaluation_commit = load_committed_goal_manager_promotion_plan(PROJECT_ROOT)
    if source.git_commit != evaluation_commit:
        raise GoalManagerPromotionRunError("working source differs from the promotion plan")

    rom_path = resolve_rom_path(args.rom)
    verify_rom(rom_path)
    destination = _new_external_receipt(args.out, rom_path=rom_path)
    catalog_path = _external_regular(
        args.context_catalog,
        rom_path=rom_path,
        subject="context catalog",
    )
    model_path = _external_regular(args.model, rom_path=rom_path, subject="model")
    summary_path = _external_regular(
        args.fit_summary,
        rom_path=rom_path,
        subject="fit summary",
    )
    candidate = authenticate_goal_manager_candidate(
        repository_root=PROJECT_ROOT,
        plan=plan,
        context_catalog_path=catalog_path,
        model_path=model_path,
        fit_summary_path=summary_path,
    )
    entries = _load_private_plan(args.private_plan, candidate.registry)
    validated = _validate_open_contexts(entries, candidate=candidate, rom_path=rom_path)

    shadow_digest: str | None = None
    shadow_path: Path | None = None
    if args.mode == "causal":
        if args.shadow_receipt is None or args.shadow_receipt_sha256 is None:
            raise GoalManagerPromotionRunError(
                "causal evaluation requires an authenticated shadow receipt"
            )
        shadow_path = _external_regular(
            args.shadow_receipt,
            rom_path=rom_path,
            subject="shadow receipt",
        )
        shadow_payload = shadow_path.read_bytes()
        if len(shadow_payload) > _MAX_RECEIPT_BYTES:
            raise GoalManagerPromotionRunError("shadow receipt is too large")
        shadow_digest = authenticate_goal_manager_shadow_receipt(
            shadow_payload,
            expected_sha256=args.shadow_receipt_sha256,
            candidate=candidate,
        )
    elif args.shadow_receipt is not None or args.shadow_receipt_sha256 is not None:
        raise GoalManagerPromotionRunError(
            "shadow evaluation cannot consume prior shadow evidence"
        )

    protected_paths = (
        args.private_plan.resolve(),
        catalog_path,
        model_path,
        summary_path,
        rom_path.resolve(),
        *(path for item in validated for path in (
            item.plan.state,
            item.plan.envelope,
            item.plan.profile,
        )),
        *((shadow_path,) if shadow_path is not None else ()),
    )
    protected = _protected_digests(protected_paths)
    adjacent_before = rom_adjacent_artifacts(rom_path)
    results: list[GoalManagerPromotionContextResult] = []
    try:
        for item in validated:
            assignment = candidate.registry.assignment(item.plan.slot_id)
            with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
                emulator.load_state_bytes(item.capture.state_bytes)
                reader = PokemonRedStateReader(emulator)
                runtime = build_red_goal_context_runtime(
                    profile=item.profile,
                    capture=item.capture,
                    emulator=emulator,
                    reader=reader,
                )
                controller = FrameSafeExecutor(
                    emulator,
                    DEFAULT_NEW_GAME_TIMING.controller_timing(),
                )
                results.append(
                    evaluate_goal_manager_promotion_context(
                        mode=args.mode,
                        assignment=assignment,
                        capture=item.capture,
                        context_catalog=candidate.catalog,
                        adapter=runtime.adapter,
                        action_delegate=controller,
                        enumerator_factory=runtime.enumerator,
                        model=candidate.model,
                        confidence_threshold=plan.minimum_live_confidence,
                    )
                )
    finally:
        _require_unchanged(protected)
        if rom_adjacent_artifacts(rom_path) != adjacent_before:
            raise GoalManagerPromotionRunError(
                "promotion created a ROM-adjacent artifact"
            )

    batch = summarize_goal_manager_promotion_results(
        mode=args.mode,
        planned_contexts=len(validated),
        results=tuple(results),
    )
    receipt = build_goal_manager_promotion_receipt(
        candidate=candidate,
        batch=batch,
        evaluation_source_commit=evaluation_commit,
        evaluation_source_bundle_sha256=working_source_bundle_sha256(PROJECT_ROOT),
        prior_shadow_receipt_sha256=shadow_digest,
        shadow_prerequisite_passed=shadow_digest is not None,
    )
    payload = _canonical_line(receipt)
    if len(payload) > _MAX_RECEIPT_BYTES:
        raise GoalManagerPromotionRunError("promotion receipt is too large")
    _write_exclusive(destination, payload)
    return receipt, destination


def _canonical_document(payload: bytes, *, subject: str) -> dict[str, object]:
    if not payload or len(payload) > _MAX_PRIVATE_PLAN_BYTES:
        raise GoalManagerPromotionRunError(f"{subject} size is invalid")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise GoalManagerPromotionRunError(f"{subject} is not canonical JSON") from None
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise GoalManagerPromotionRunError(f"{subject} is not canonical JSON")
    return value


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


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        receipt, destination = _run(args)
    except Exception:
        parser.error("Goal-manager promotion failed closed; private paths were withheld.")
    gates = receipt.get("gates")
    passed = isinstance(gates, dict) and gates.get("passed") is True
    print(
        json.dumps(
            {
                "mode": receipt["mode"],
                "status": receipt["status"],
                "receipt_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "evaluated_contexts": receipt["audit"]["evaluated_contexts"],
                "agreements": receipt["audit"]["agreements"],
                "successful_contexts": receipt["audit"]["successful_contexts"],
                "minimum_confidence": receipt["audit"]["minimum_confidence"],
                "sealed_test_captures_opened": 0,
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
