#!/usr/bin/env python3
"""Build one authenticated action-free catalog from a terminal V2 development run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from run_battle_scenario_materialization_plan import (  # noqa: E402
    BattleScenarioMaterializationRunnerError,
    _authenticate_assignment_outputs,
    _private_capture_directory,
)

from pokemon_red_completion.battle_scenario_development_capture_catalog import (  # noqa: E402
    BattleScenarioDevelopmentCaptureCatalogError,
    BattleScenarioDevelopmentCaptureEntry,
    BattleScenarioDevelopmentCaptureProducer,
    build_battle_scenario_development_capture_catalog,
    parse_battle_scenario_development_capture_catalog,
)
from pokemon_red_completion.battle_scenario_materialization_plan_v2 import (  # noqa: E402
    BattleScenarioMaterializationPlanV2Error,
    parse_battle_scenario_materialization_plan_v2,
)
from pokemon_red_completion.battle_scenario_materialization_run import (  # noqa: E402
    SUCCEEDED,
    BattleScenarioMaterializationRunError,
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
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAXIMUM_PLAN_BYTES = 8 * 1024 * 1024
_MAXIMUM_JOURNAL_BYTES = 2 * 1024 * 1024
_MAXIMUM_CATALOG_BYTES = 4 * 1024 * 1024


class BattleScenarioDevelopmentCaptureCatalogBuildError(RuntimeError):
    """Raised before unauthenticated development outputs can enter a catalog."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-id", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--expected-journal-sha256", required=True)
    parser.add_argument("--capture-directory", type=Path, required=True)
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
        args.expected_source_bundle_sha256,
        "builder source bundle",
    ):
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(
            "published development catalog builder identity differs"
        )

    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    capture_directory = _private_capture_directory(
        args.capture_directory,
        rom_path=rom_path,
    )
    plan_payload = _read_input(
        args.plan,
        parent=capture_directory,
        maximum_bytes=_MAXIMUM_PLAN_BYTES,
        subject="development plan",
        expected_sha256=args.expected_plan_sha256,
    )
    try:
        plan = parse_battle_scenario_materialization_plan_v2(plan_payload)
    except BattleScenarioMaterializationPlanV2Error as error:
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(str(error)) from None
    expected_journal_path = (
        capture_directory / f"battle-materialization-{plan.plan_sha256}.journal.json"
    )
    if args.journal.is_symlink() or args.journal.resolve() != expected_journal_path:
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(
            "development journal is not bound to its plan"
        )
    journal_payload = _read_input(
        args.journal,
        parent=capture_directory,
        maximum_bytes=_MAXIMUM_JOURNAL_BYTES,
        subject="development journal",
        expected_sha256=args.expected_journal_sha256,
    )
    try:
        journal = parse_battle_scenario_materialization_run(journal_payload)
        require_battle_scenario_materialization_run_matches_plan(
            journal,
            plan,
            journal.identity,
        )
    except BattleScenarioMaterializationRunError as error:
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(str(error)) from None

    observed_directory_sha256 = hashlib.sha256(str(capture_directory).encode("utf-8")).hexdigest()
    partitions = {item.source.partition for item in plan.inventory} | {
        item.candidate.source.partition for item in plan.assignments
    }
    if (
        partitions != {ScenarioPartition.DEVELOPMENT}
        or len(plan.assignments) != 8
        or len(journal.entries) != 8
        or any(item.status != SUCCEEDED for item in journal.entries)
        or plan.rom_sha256 != rom.sha256
        or journal.identity.rom_sha256 != rom.sha256
        or plan.capture_directory_sha256 != observed_directory_sha256
        or journal.identity.capture_directory_sha256 != observed_directory_sha256
    ):
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(
            "development producer terminal denominator differs"
        )

    entries: list[BattleScenarioDevelopmentCaptureEntry] = []
    for assignment, run_entry in zip(plan.assignments, journal.entries, strict=True):
        try:
            state_sha256, manifest_sha256 = _authenticate_assignment_outputs(
                assignment,
                capture_directory=capture_directory,
                source_commit=journal.identity.source_commit,
                rom_path=rom_path,
            )
        except BattleScenarioMaterializationRunnerError:
            raise BattleScenarioDevelopmentCaptureCatalogBuildError(
                "development output cannot be independently authenticated"
            ) from None
        if state_sha256 != run_entry.state_sha256 or manifest_sha256 != run_entry.manifest_sha256:
            raise BattleScenarioDevelopmentCaptureCatalogBuildError(
                "development output differs from its terminal journal"
            )
        entries.append(
            BattleScenarioDevelopmentCaptureEntry(
                ordinal=assignment.ordinal,
                capture_id=assignment.capture_id,
                assignment_sha256=canonical_sha256(assignment.private_dict()),
                source_state_sha256=assignment.candidate.source.source_state_sha256,
                root_lineage_id=assignment.candidate.source.root_lineage_id,
                venue_id=assignment.selected_venue.venue_id,
                party_slot=assignment.party_slot,
                state_filename=assignment.state_filename,
                manifest_filename=assignment.manifest_filename,
                state_sha256=state_sha256,
                manifest_sha256=manifest_sha256,
            )
        )

    identity = journal.identity
    try:
        catalog = build_battle_scenario_development_capture_catalog(
            catalog_id=args.catalog_id,
            builder_source_commit=source_commit,
            builder_source_bundle_sha256=source_bundle,
            producer=BattleScenarioDevelopmentCaptureProducer(
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
            ),
            captures=entries,
        )
    except (BattleScenarioDevelopmentCaptureCatalogError, TypeError, ValueError) as error:
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(str(error)) from None

    destination = _private_new_catalog(args.out_catalog, rom_path=rom_path)
    _write_exclusive(destination, catalog.canonical_bytes())
    reopened_payload = _read_owned_regular(
        destination,
        maximum_bytes=_MAXIMUM_CATALOG_BYTES,
        subject="development catalog",
    )
    try:
        reopened = parse_battle_scenario_development_capture_catalog(reopened_payload)
    except BattleScenarioDevelopmentCaptureCatalogError as error:
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(str(error)) from None
    if reopened != catalog:
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(
            "development catalog differs after independent reopen"
        )
    return {
        "schema": "pokemon-red-battle-scenario-development-capture-catalog-receipt-v1",
        "status": "authenticated_action_free",
        "catalog_id": catalog.catalog_id,
        "catalog_sha256": catalog.catalog_sha256,
        "plan_sha256": identity.plan_sha256,
        "run_journal_sha256": journal.journal_sha256,
        "source_commit": identity.source_commit,
        "source_bundle_sha256": identity.source_bundle_sha256,
        "builder_source_commit": source_commit,
        "builder_source_bundle_sha256": source_bundle,
        "rom_sha256": rom.sha256,
        "capture_count": len(catalog.captures),
        "unique_source_roots": len({item.source_state_sha256 for item in catalog.captures}),
        "venue_counts": dict(sorted(Counter(item.venue_id for item in catalog.captures).items())),
        "controller_actions": 0,
        "emulator_frames": 0,
        "outcomes_opened": 0,
        "predictions_computed": 0,
        "model_fits": 0,
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "red_sealed_test_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }


def _read_input(
    path: Path,
    *,
    parent: Path,
    maximum_bytes: int,
    subject: str,
    expected_sha256: str,
) -> bytes:
    if path.is_symlink() or path.resolve().parent != parent:
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(f"{subject} is unavailable")
    payload = _read_owned_regular(
        path.resolve(),
        maximum_bytes=maximum_bytes,
        subject=subject,
    )
    if hashlib.sha256(payload).hexdigest() != _sha256(expected_sha256, subject):
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(f"{subject} digest differs")
    return payload


def _private_new_catalog(path: Path, *, rom_path: Path) -> Path:
    parent = path.parent.resolve(strict=True)
    destination = path.resolve()
    observed = parent.stat()
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) & 0o077
        or parent.is_relative_to(PROJECT_ROOT.resolve())
        or parent == rom_path.resolve().parent
        or destination.parent != parent
        or destination.exists()
        or path.is_symlink()
    ):
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(
            "development catalog destination is unavailable"
        )
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
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(
            f"{subject} is unavailable"
        ) from None
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
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(
            "development catalog could not be retained"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(f"{subject} digest differs")
    return value


def _commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise BattleScenarioDevelopmentCaptureCatalogBuildError(f"{subject} commit differs")
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = _run(args)
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema": "pokemon-red-battle-scenario-development-capture-catalog-failure-v1",
                    "status": "failed_closed",
                    "reason_code": "development_capture_catalog_authentication_failed",
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
