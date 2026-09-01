#!/usr/bin/env python3
"""Build one action-free seven-capture catalog across two immutable producers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from run_battle_scenario_materialization_plan import (  # noqa: E402
    BattleScenarioMaterializationRunnerError,
    _authenticate_assignment_outputs,
    _private_capture_directory,
)

from pokemon_red_completion.battle_scenario_capture_catalog import (  # noqa: E402
    BattleScenarioCaptureCatalogEntry,
    BattleScenarioCaptureCatalogError,
    BattleScenarioCaptureProducer,
    build_battle_scenario_capture_catalog,
    parse_battle_scenario_capture_catalog,
)
from pokemon_red_completion.battle_scenario_materialization_plan_v2 import (  # noqa: E402
    BattleScenarioMaterializationCompletionPlan,
    BattleScenarioMaterializationPlanV2,
    BattleScenarioMaterializationPlanV2Error,
    RetainedBattleScenarioMaterializationCapture,
    parse_battle_scenario_materialization_completion_plan,
    parse_battle_scenario_materialization_plan_v2,
)
from pokemon_red_completion.battle_scenario_materialization_run import (  # noqa: E402
    FAILED,
    SUCCEEDED,
    BattleScenarioMaterializationRunError,
    BattleScenarioMaterializationRunJournal,
    parse_battle_scenario_materialization_run,
    require_battle_scenario_materialization_run_matches_plan,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAXIMUM_PLAN_BYTES = 8 * 1024 * 1024
_MAXIMUM_JOURNAL_BYTES = 2 * 1024 * 1024
_MAXIMUM_CATALOG_BYTES = 2 * 1024 * 1024


class BattleScenarioCaptureCatalogBuildError(RuntimeError):
    """Raised when the seven inputs cannot be independently authenticated."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-id", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--predecessor-plan", type=Path, required=True)
    parser.add_argument("--expected-predecessor-plan-sha256", required=True)
    parser.add_argument("--predecessor-journal", type=Path, required=True)
    parser.add_argument("--expected-predecessor-journal-sha256", required=True)
    parser.add_argument("--predecessor-capture-directory", type=Path, required=True)
    parser.add_argument("--completion-plan", type=Path, required=True)
    parser.add_argument("--expected-completion-plan-sha256", required=True)
    parser.add_argument("--completion-journal", type=Path, required=True)
    parser.add_argument("--expected-completion-journal-sha256", required=True)
    parser.add_argument("--completion-capture-directory", type=Path, required=True)
    parser.add_argument("--out-catalog", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    source_commit = _commit(args.expected_source_commit, "builder source")
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if source.git_commit != source_commit or source_bundle != _sha256(
        args.expected_source_bundle_sha256, "builder source bundle"
    ):
        raise BattleScenarioCaptureCatalogBuildError("published catalog builder identity differs")

    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    predecessor_directory = _private_capture_directory(
        args.predecessor_capture_directory,
        rom_path=rom_path,
    )
    completion_directory = _private_capture_directory(
        args.completion_capture_directory,
        rom_path=rom_path,
    )
    if predecessor_directory == completion_directory:
        raise BattleScenarioCaptureCatalogBuildError("capture producer directories collapse")

    predecessor_plan = _read_predecessor_plan(
        args.predecessor_plan,
        parent=predecessor_directory,
        expected_sha256=args.expected_predecessor_plan_sha256,
    )
    predecessor_journal = _read_journal(
        args.predecessor_journal,
        parent=predecessor_directory,
        expected_sha256=args.expected_predecessor_journal_sha256,
    )
    completion_plan = _read_completion_plan(
        args.completion_plan,
        parent=completion_directory,
        expected_sha256=args.expected_completion_plan_sha256,
    )
    completion_journal = _read_journal(
        args.completion_journal,
        parent=completion_directory,
        expected_sha256=args.expected_completion_journal_sha256,
    )

    _require_terminal_producer(
        predecessor_plan,
        predecessor_journal,
        expected_successes=5,
        expected_failures=2,
        capture_directory=predecessor_directory,
    )
    _require_terminal_producer(
        completion_plan,
        completion_journal,
        expected_successes=2,
        expected_failures=0,
        capture_directory=completion_directory,
    )
    _require_completion_lineage(
        predecessor_plan,
        predecessor_journal,
        completion_plan,
    )

    predecessor_entries, retained = _catalog_entries(
        producer_id="predecessor",
        plan=predecessor_plan,
        journal=predecessor_journal,
        capture_directory=predecessor_directory,
        rom_path=rom_path,
    )
    completion_entries, _ = _catalog_entries(
        producer_id="completion",
        plan=completion_plan,
        journal=completion_journal,
        capture_directory=completion_directory,
        rom_path=rom_path,
    )
    if retained != completion_plan.retained_successes:
        raise BattleScenarioCaptureCatalogBuildError(
            "completion retained capture projection differs"
        )

    try:
        catalog = build_battle_scenario_capture_catalog(
            catalog_id=args.catalog_id,
            builder_source_commit=source_commit,
            builder_source_bundle_sha256=source_bundle,
            rom_sha256=rom.sha256,
            producers=(
                _producer(
                    "predecessor",
                    predecessor_journal,
                    successes=5,
                    failures=2,
                ),
                _producer(
                    "completion",
                    completion_journal,
                    successes=2,
                    failures=0,
                ),
            ),
            captures=(*predecessor_entries, *completion_entries),
        )
    except (BattleScenarioCaptureCatalogError, TypeError, ValueError) as error:
        raise BattleScenarioCaptureCatalogBuildError(str(error)) from None

    destination = _private_new_catalog(args.out_catalog, rom_path=rom_path)
    _write_exclusive(destination, catalog.canonical_bytes())
    reopened_payload = _read_owned_regular(
        destination,
        maximum_bytes=_MAXIMUM_CATALOG_BYTES,
        subject="capture catalog",
    )
    try:
        reopened = parse_battle_scenario_capture_catalog(reopened_payload)
    except BattleScenarioCaptureCatalogError as error:
        raise BattleScenarioCaptureCatalogBuildError(str(error)) from None
    if reopened != catalog:
        raise BattleScenarioCaptureCatalogBuildError(
            "capture catalog differs after independent reopen"
        )
    venue_counts: dict[str, int] = {}
    for item in catalog.captures:
        venue_counts[item.venue_id] = venue_counts.get(item.venue_id, 0) + 1
    return {
        "schema": "pokemon-red-battle-scenario-capture-catalog-receipt-v1",
        "status": "authenticated_action_free",
        "catalog_id": catalog.catalog_id,
        "catalog_sha256": catalog.catalog_sha256,
        "builder_source_commit": source_commit,
        "builder_source_bundle_sha256": source_bundle,
        "rom_sha256": rom.sha256,
        "producer_count": len(catalog.producers),
        "producer_commits_preserved": len({item.source_commit for item in catalog.producers}),
        "capture_count": len(catalog.captures),
        "unique_capture_ids": len({item.capture_id for item in catalog.captures}),
        "unique_source_roots": len({item.source_state_sha256 for item in catalog.captures}),
        "historical_failed_assignments": 2,
        "failed_assignments_admitted": 0,
        "venue_counts": dict(sorted(venue_counts.items())),
        "read_only_runtime_preparations": len(catalog.captures),
        "controller_actions": 0,
        "emulator_frames": 0,
        "root_claims_created": 0,
        "move_choices_executed": 0,
        "predictions_computed": 0,
        "outcomes_opened": 0,
        "model_fits": 0,
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "red_sealed_test_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }


def _producer(
    role: str,
    journal: BattleScenarioMaterializationRunJournal,
    *,
    successes: int,
    failures: int,
) -> BattleScenarioCaptureProducer:
    identity = journal.identity
    return BattleScenarioCaptureProducer(
        producer_id=role,
        role=role,
        plan_id=identity.plan_id,
        plan_sha256=identity.plan_sha256,
        run_journal_sha256=journal.journal_sha256,
        source_commit=identity.source_commit,
        source_bundle_sha256=identity.source_bundle_sha256,
        materializer_sha256=identity.materializer_sha256,
        runtime_identity_sha256=identity.runtime_identity_sha256,
        rom_sha256=identity.rom_sha256,
        capture_directory_sha256=identity.capture_directory_sha256,
        context_catalog_sha256=identity.context_catalog_sha256,
        registry_sha256=identity.registry_sha256,
        registry_source_commit=identity.registry_source_commit,
        exact_ci_run=identity.exact_ci_run,
        exact_ci_attempt=identity.exact_ci_attempt,
        successful_capture_count=successes,
        failed_assignment_count=failures,
    )


def _catalog_entries(
    *,
    producer_id: str,
    plan: BattleScenarioMaterializationPlanV2 | BattleScenarioMaterializationCompletionPlan,
    journal: BattleScenarioMaterializationRunJournal,
    capture_directory: Path,
    rom_path: Path,
) -> tuple[
    tuple[BattleScenarioCaptureCatalogEntry, ...],
    tuple[RetainedBattleScenarioMaterializationCapture, ...],
]:
    entries: list[BattleScenarioCaptureCatalogEntry] = []
    retained: list[RetainedBattleScenarioMaterializationCapture] = []
    for assignment, run_entry in zip(
        plan.assignments,
        journal.entries,
        strict=True,
    ):
        if run_entry.status == FAILED:
            continue
        if run_entry.status != SUCCEEDED:
            raise BattleScenarioCaptureCatalogBuildError("capture producer journal is not terminal")
        try:
            state_sha256, manifest_sha256 = _authenticate_assignment_outputs(
                assignment,
                capture_directory=capture_directory,
                source_commit=journal.identity.source_commit,
                rom_path=rom_path,
            )
        except BattleScenarioMaterializationRunnerError:
            raise BattleScenarioCaptureCatalogBuildError(
                "capture output cannot be independently authenticated"
            ) from None
        if state_sha256 != run_entry.state_sha256 or manifest_sha256 != run_entry.manifest_sha256:
            raise BattleScenarioCaptureCatalogBuildError(
                "capture output differs from its terminal journal"
            )
        venue_id = assignment.selected_venue.venue_id
        assignment_sha256 = canonical_sha256(assignment.private_dict())
        entries.append(
            BattleScenarioCaptureCatalogEntry(
                ordinal=len(entries),
                producer_id=producer_id,
                producer_ordinal=assignment.ordinal,
                capture_id=assignment.capture_id,
                assignment_sha256=assignment_sha256,
                source_state_sha256=(assignment.candidate.source.source_state_sha256),
                root_lineage_id=assignment.candidate.source.root_lineage_id,
                venue_id=venue_id,
                party_slot=assignment.party_slot,
                state_filename=assignment.state_filename,
                manifest_filename=assignment.manifest_filename,
                state_sha256=state_sha256,
                manifest_sha256=manifest_sha256,
            )
        )
        retained.append(
            RetainedBattleScenarioMaterializationCapture(
                ordinal=assignment.ordinal,
                capture_id=assignment.capture_id,
                assignment_sha256=assignment_sha256,
                source_commit=journal.identity.source_commit,
                source_state_sha256=(assignment.candidate.source.source_state_sha256),
                root_lineage_id=assignment.candidate.source.root_lineage_id,
                venue_id=venue_id,
                party_slot=assignment.party_slot,
                state_filename=assignment.state_filename,
                manifest_filename=assignment.manifest_filename,
                state_sha256=state_sha256,
                manifest_sha256=manifest_sha256,
            )
        )
    return tuple(entries), tuple(retained)


def _require_terminal_producer(
    plan: BattleScenarioMaterializationPlanV2 | BattleScenarioMaterializationCompletionPlan,
    journal: BattleScenarioMaterializationRunJournal,
    *,
    expected_successes: int,
    expected_failures: int,
    capture_directory: Path,
) -> None:
    try:
        require_battle_scenario_materialization_run_matches_plan(
            journal,
            plan,
            journal.identity,
        )
    except BattleScenarioMaterializationRunError as error:
        raise BattleScenarioCaptureCatalogBuildError(str(error)) from None
    observed_directory_sha256 = hashlib.sha256(str(capture_directory).encode("utf-8")).hexdigest()
    if (
        plan.capture_directory_sha256 != observed_directory_sha256
        or journal.identity.capture_directory_sha256 != observed_directory_sha256
        or sum(item.status == SUCCEEDED for item in journal.entries) != expected_successes
        or sum(item.status == FAILED for item in journal.entries) != expected_failures
        or any(item.status not in {SUCCEEDED, FAILED} for item in journal.entries)
    ):
        raise BattleScenarioCaptureCatalogBuildError(
            "capture producer terminal denominator differs"
        )


def _require_completion_lineage(
    predecessor_plan: BattleScenarioMaterializationPlanV2,
    predecessor_journal: BattleScenarioMaterializationRunJournal,
    completion_plan: BattleScenarioMaterializationCompletionPlan,
) -> None:
    predecessor_attempted = {
        item.candidate.source.source_state_sha256 for item in predecessor_plan.assignments
    }
    completion_sources = {
        item.candidate.source.source_state_sha256 for item in completion_plan.assignments
    }
    if (
        completion_plan.predecessor_plan_sha256 != predecessor_plan.plan_sha256
        or completion_plan.predecessor_run_journal_sha256 != predecessor_journal.journal_sha256
        or completion_plan.predecessor_capture_directory_sha256
        != predecessor_plan.capture_directory_sha256
        or completion_plan.predecessor_failure_count != 2
        or predecessor_attempted.intersection(completion_sources)
    ):
        raise BattleScenarioCaptureCatalogBuildError("completion producer lineage differs")


def _read_predecessor_plan(
    path: Path,
    *,
    parent: Path,
    expected_sha256: str,
) -> BattleScenarioMaterializationPlanV2:
    payload = _read_input(
        path,
        parent=parent,
        maximum_bytes=_MAXIMUM_PLAN_BYTES,
        subject="predecessor plan",
        expected_sha256=expected_sha256,
    )
    try:
        return parse_battle_scenario_materialization_plan_v2(payload)
    except BattleScenarioMaterializationPlanV2Error as error:
        raise BattleScenarioCaptureCatalogBuildError(str(error)) from None


def _read_completion_plan(
    path: Path,
    *,
    parent: Path,
    expected_sha256: str,
) -> BattleScenarioMaterializationCompletionPlan:
    payload = _read_input(
        path,
        parent=parent,
        maximum_bytes=_MAXIMUM_PLAN_BYTES,
        subject="completion plan",
        expected_sha256=expected_sha256,
    )
    try:
        return parse_battle_scenario_materialization_completion_plan(payload)
    except BattleScenarioMaterializationPlanV2Error as error:
        raise BattleScenarioCaptureCatalogBuildError(str(error)) from None


def _read_journal(
    path: Path,
    *,
    parent: Path,
    expected_sha256: str,
) -> BattleScenarioMaterializationRunJournal:
    payload = _read_input(
        path,
        parent=parent,
        maximum_bytes=_MAXIMUM_JOURNAL_BYTES,
        subject="producer journal",
        expected_sha256=expected_sha256,
    )
    try:
        return parse_battle_scenario_materialization_run(payload)
    except BattleScenarioMaterializationRunError as error:
        raise BattleScenarioCaptureCatalogBuildError(str(error)) from None


def _read_input(
    path: Path,
    *,
    parent: Path,
    maximum_bytes: int,
    subject: str,
    expected_sha256: str,
) -> bytes:
    if path.is_symlink():
        raise BattleScenarioCaptureCatalogBuildError(f"{subject} is unavailable")
    resolved = path.resolve()
    if resolved.parent != parent:
        raise BattleScenarioCaptureCatalogBuildError(f"{subject} is unavailable")
    payload = _read_owned_regular(
        resolved,
        maximum_bytes=maximum_bytes,
        subject=subject,
    )
    if hashlib.sha256(payload).hexdigest() != _sha256(expected_sha256, subject):
        raise BattleScenarioCaptureCatalogBuildError(f"{subject} digest differs")
    return payload


def _private_new_catalog(path: Path, *, rom_path: Path) -> Path:
    parent = path.parent.resolve(strict=True)
    try:
        observed = parent.stat()
    except OSError:
        raise BattleScenarioCaptureCatalogBuildError("catalog destination is unavailable") from None
    destination = path.resolve()
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) & 0o077
        or parent.is_relative_to(PROJECT_ROOT.resolve())
        or parent == rom_path.resolve().parent
        or destination.parent != parent
        or destination.exists()
        or destination.is_symlink()
    ):
        raise BattleScenarioCaptureCatalogBuildError("catalog destination is unavailable")
    return destination


def _read_owned_regular(path: Path, *, maximum_bytes: int, subject: str) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        named = path.lstat()
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            named.st_dev != opened.st_dev
            or named.st_ino != opened.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) & 0o022
            or not 1 <= opened.st_size <= maximum_bytes
        ):
            raise OSError("unsafe private file")
        payload = os.read(descriptor, opened.st_size + 1)
        if len(payload) != opened.st_size:
            raise OSError("private file changed while opening")
        return payload
    except OSError:
        raise BattleScenarioCaptureCatalogBuildError(f"{subject} is unavailable") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short private write")
            view = view[written:]
        os.fsync(descriptor)
    except OSError:
        raise BattleScenarioCaptureCatalogBuildError(
            "capture catalog could not be retained"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleScenarioCaptureCatalogBuildError(f"{subject} digest differs")
    return value


def _commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise BattleScenarioCaptureCatalogBuildError(f"{subject} commit differs")
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = _run(args)
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema": ("pokemon-red-battle-scenario-capture-catalog-failure-v1"),
                    "status": "failed_closed",
                    "reason_code": ("capture_catalog_authentication_failed"),
                    "failure_type": type(error).__name__,
                    "controller_actions": 0,
                    "emulator_frames": 0,
                    "outcomes_opened": 0,
                    "model_fits": 0,
                    "private_path_fields": 0,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
