#!/usr/bin/env python3
"""Execute only pending items from one frozen Red battle-capture plan."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TypeAlias

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MATERIALIZER_PATH = PROJECT_ROOT / "scripts" / "materialize_battle_scenario_capture.py"
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from inventory_battle_scenario_source_venues import (  # noqa: E402
    BattleScenarioSourceInventoryError,
    _load_attempted_source_exclusions,
    _load_catalog,
    _open_all_catalog_train_roots,
    _require_state_bank,
)

from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    BattleScenarioCaptureError,
    open_battle_scenario_capture,
)
from pokemon_red_completion.battle_scenario_materialization_plan import (  # noqa: E402
    MANSION_VENUE_ID,
    ROUTE_11_VENUE_ID,
    BattleScenarioMaterializationAssignment,
    BattleScenarioMaterializationPlan,
    BattleScenarioMaterializationPlanError,
    parse_battle_scenario_materialization_plan,
)
from pokemon_red_completion.battle_scenario_materialization_plan_v2 import (  # noqa: E402
    BattleScenarioMaterializationAssignmentV2,
    BattleScenarioMaterializationCompletionPlan,
    BattleScenarioMaterializationPlanV2,
    BattleScenarioMaterializationPlanV2Error,
    RetainedBattleScenarioMaterializationCapture,
    parse_battle_scenario_materialization_completion_plan,
    parse_battle_scenario_materialization_plan_v2,
)
from pokemon_red_completion.battle_scenario_materialization_run import (  # noqa: E402
    FAILED,
    PENDING,
    STARTED,
    SUCCEEDED,
    BattleScenarioMaterializationRunError,
    BattleScenarioMaterializationRunIdentity,
    BattleScenarioMaterializationRunJournal,
    fail_battle_scenario_materialization_assignment,
    initialize_battle_scenario_materialization_run,
    parse_battle_scenario_materialization_run,
    require_battle_scenario_materialization_run_matches_plan,
    start_battle_scenario_materialization_assignment,
    succeed_battle_scenario_materialization_assignment,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.goal_manager_composition_qualification import (  # noqa: E402
    FreshCompositionQualificationError,
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    root_claim_is_available,
)
from pokemon_red_completion.observation import (  # noqa: E402
    BattleMenuPhase,
    MapId,
    PokemonRedStateReader,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_battle_scenario import (  # noqa: E402
    prepare_red_battle_scenario,
)
from pokemon_red_completion.red_trajectory import (  # noqa: E402
    PokemonRedObservationEncoder,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.runtime_identity import (  # noqa: E402
    build_runtime_identity,
    require_pyboy_import_origins,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAXIMUM_PLAN_BYTES = 8 * 1024 * 1024
_MAXIMUM_JOURNAL_BYTES = 2 * 1024 * 1024
_MAXIMUM_RECEIPT_BYTES = 512 * 1024
_MAXIMUM_MATERIALIZER_OUTPUT_BYTES = 2 * 1024 * 1024
_GITHUB_REPOSITORY = "PeteAndrews1289/pokemon-red-completion-agent"
_CI_WORKFLOW_NAME = "CI"
_MATERIALIZER_FAILURE_SCHEMA = (
    "pokemon-private-battle-scenario-materialization-failure-v1"
)
_MATERIALIZER_FAILURE_REASONS = frozenset(
    {
        "materialization_preflight_failed",
        "source_authentication_failed",
        "source_reauthentication_failed",
        "source_relocation_failed",
        "encounter_materialization_failed",
        "output_publication_failed",
        "materialization_internal_failure",
    }
)

BattleScenarioMaterializationAssignmentLike: TypeAlias = (
    BattleScenarioMaterializationAssignment | BattleScenarioMaterializationAssignmentV2
)
BattleScenarioMaterializationPlanLike: TypeAlias = (
    BattleScenarioMaterializationPlan
    | BattleScenarioMaterializationPlanV2
    | BattleScenarioMaterializationCompletionPlan
)


class BattleScenarioMaterializationRunnerError(RuntimeError):
    """Raised when the exact plan cannot continue without risking replay."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--exact-ci-run", type=int, required=True)
    parser.add_argument("--exact-ci-attempt", type=int, required=True)
    parser.add_argument("--state-bank", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--capture-directory", type=Path, required=True)
    parser.add_argument("--excluded-plan", type=Path, default=None)
    parser.add_argument("--excluded-run-journal", type=Path, default=None)
    parser.add_argument("--predecessor-plan", type=Path, default=None)
    parser.add_argument("--predecessor-run-journal", type=Path, default=None)
    parser.add_argument("--predecessor-capture-directory", type=Path, default=None)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--maximum-encounter-steps", type=int, default=512)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=None)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.maximum_encounter_steps < 1:
        raise BattleScenarioMaterializationRunnerError(
            "maximum encounter steps must be positive"
        )
    if args.speed is not None and not args.watch:
        raise BattleScenarioMaterializationRunnerError("--speed requires --watch")

    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    source_commit = _commit(args.expected_source_commit, "source")
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if (
        source.git_commit != source_commit
        or source_bundle != _sha256(args.expected_source_bundle_sha256, "source bundle")
    ):
        raise BattleScenarioMaterializationRunnerError(
            "published source identity differs"
        )
    _require_exact_green_ci_run(
        args.exact_ci_run,
        args.exact_ci_attempt,
        source_commit=source_commit,
    )

    runtime = build_runtime_identity()
    require_pyboy_import_origins(runtime)
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    capture_directory = _private_capture_directory(
        args.capture_directory,
        rom_path=rom_path,
    )
    plan_path = _private_existing_file(
        args.plan,
        parent=capture_directory,
        maximum_bytes=_MAXIMUM_PLAN_BYTES,
        subject="materialization plan",
    )
    plan = _read_plan(plan_path)
    if plan.plan_sha256 != _sha256(args.expected_plan_sha256, "plan"):
        raise BattleScenarioMaterializationRunnerError("materialization plan differs")
    if (
        plan.rom_sha256 != rom.sha256
        or plan.capture_directory_sha256
        != hashlib.sha256(str(capture_directory).encode("utf-8")).hexdigest()
    ):
        raise BattleScenarioMaterializationRunnerError(
            "materialization plan environment differs"
        )
    _require_plan_exclusions(args, plan=plan, rom_path=rom_path)

    catalog, registry = _load_exact_catalog(args, plan=plan)
    scan = _open_all_catalog_train_roots(
        _require_state_bank(args.state_bank),
        catalog=catalog,
        registry=registry,
    )
    if scan.missing_catalog_train_roots != 0:
        raise BattleScenarioMaterializationRunnerError(
            "complete catalog train state bank is required"
        )
    roots_by_sha256 = {
        item.binding.source_state_sha256: item for item in scan.roots
    }
    if any(
        item.candidate.source.source_state_sha256 not in roots_by_sha256
        or roots_by_sha256[item.candidate.source.source_state_sha256].binding
        != item.candidate.source
        for item in plan.assignments
    ):
        raise BattleScenarioMaterializationRunnerError(
            "frozen materialization source is unavailable"
        )

    materializer_sha256 = hashlib.sha256(MATERIALIZER_PATH.read_bytes()).hexdigest()
    identity = BattleScenarioMaterializationRunIdentity(
        plan_id=plan.plan_id,
        plan_sha256=plan.plan_sha256,
        source_commit=source_commit,
        source_bundle_sha256=source_bundle,
        materializer_sha256=materializer_sha256,
        runtime_identity_sha256=runtime.sha256,
        rom_sha256=rom.sha256,
        capture_directory_sha256=plan.capture_directory_sha256,
        context_catalog_sha256=catalog.catalog_sha256,
        registry_sha256=registry.registry_sha256,
        registry_source_commit=registry.execution.source_commit or "",
        exact_ci_run=args.exact_ci_run,
        exact_ci_attempt=args.exact_ci_attempt,
    )
    journal_path = _private_journal_path(args.journal, parent=capture_directory)
    receipt_path = _private_receipt_path(args.receipt, parent=capture_directory)
    if len({plan_path, journal_path, receipt_path}) != 3:
        raise BattleScenarioMaterializationRunnerError(
            "plan, journal, and receipt must be distinct"
        )

    registry_path = open_fixed_account_claim_registry()
    with _run_lease(journal_path):
        journal = _open_or_initialize_journal(
            journal_path,
            plan=plan,
            identity=identity,
        )
        journal = _reconcile_existing_entries(
            journal,
            plan=plan,
            capture_directory=capture_directory,
            journal_path=journal_path,
            rom_path=rom_path,
        )
        for assignment in plan.assignments:
            if journal.entries[assignment.ordinal].status != PENDING:
                continue
            with fixed_account_claim_registry_lease(registry_path, exclusive=False):
                if not root_claim_is_available(
                    registry_path,
                    assignment.candidate.source.root_consumption_sha256,
                ):
                    raise BattleScenarioMaterializationRunnerError(
                        "pending frozen source root is no longer available"
                    )
                _require_pending_outputs_absent(
                    assignment,
                    capture_directory=capture_directory,
                )
                journal = _execute_pending_assignment(
                    journal,
                    assignment=assignment,
                    journal_path=journal_path,
                    source_bytes=roots_by_sha256[
                        assignment.candidate.source.source_state_sha256
                    ].state_bytes,
                    capture_directory=capture_directory,
                    context_catalog=args.context_catalog,
                    registry_source_commit=args.registry_source_commit,
                    expected_registry_sha256=args.expected_registry_sha256,
                    expected_context_catalog_sha256=(
                        args.expected_context_catalog_sha256
                    ),
                    rom_path=rom_path,
                    maximum_encounter_steps=args.maximum_encounter_steps,
                    watch=args.watch,
                    speed=args.speed,
                )

        journal = _reconcile_existing_entries(
            _read_journal(journal_path),
            plan=plan,
            capture_directory=capture_directory,
            journal_path=journal_path,
            rom_path=rom_path,
        )
        receipt = journal.public_receipt()
        _publish_or_verify_receipt(receipt_path, receipt)
        return receipt


def _execute_pending_assignment(
    journal: BattleScenarioMaterializationRunJournal,
    *,
    assignment: BattleScenarioMaterializationAssignmentLike,
    journal_path: Path,
    source_bytes: bytes,
    capture_directory: Path,
    context_catalog: Path,
    registry_source_commit: str,
    expected_registry_sha256: str,
    expected_context_catalog_sha256: str,
    rom_path: Path,
    maximum_encounter_steps: int,
    watch: bool,
    speed: int | None,
) -> BattleScenarioMaterializationRunJournal:
    """Persist the consumed attempt before calling the controller-capable child."""

    journal = start_battle_scenario_materialization_assignment(
        journal,
        assignment.ordinal,
    )
    _replace_journal(journal_path, journal.canonical_bytes())
    try:
        materializer_receipt = _materialize_assignment(
            assignment,
            source_bytes=source_bytes,
            capture_directory=capture_directory,
            context_catalog=context_catalog,
            registry_source_commit=registry_source_commit,
            expected_registry_sha256=expected_registry_sha256,
            expected_context_catalog_sha256=expected_context_catalog_sha256,
            rom_path=rom_path,
            maximum_encounter_steps=maximum_encounter_steps,
            watch=watch,
            speed=speed,
        )
        state_sha256, manifest_sha256 = _authenticate_assignment_outputs(
            assignment,
            capture_directory=capture_directory,
            source_commit=journal.identity.source_commit,
            rom_path=rom_path,
        )
        _require_materializer_receipt(
            materializer_receipt,
            assignment=assignment,
            source_commit=journal.identity.source_commit,
            state_sha256=state_sha256,
            manifest_sha256=manifest_sha256,
        )
        journal = succeed_battle_scenario_materialization_assignment(
            journal,
            assignment.ordinal,
            state_sha256=state_sha256,
            manifest_sha256=manifest_sha256,
        )
    except Exception as error:
        journal = fail_battle_scenario_materialization_assignment(
            journal,
            assignment.ordinal,
            reason_code=_failure_reason(error),
        )
    _replace_journal(journal_path, journal.canonical_bytes())
    return journal


def _load_exact_catalog(
    args: argparse.Namespace,
    *,
    plan: BattleScenarioMaterializationPlanLike,
):  # type: ignore[no-untyped-def]
    provenances = {
        (
            item.source.catalog_sha256,
            item.source.registry_sha256,
            item.source.registry_source_commit,
        )
        for item in plan.inventory
    }
    expected = {
        (
            _sha256(args.expected_context_catalog_sha256, "context catalog"),
            _sha256(args.expected_registry_sha256, "registry"),
            _commit(args.registry_source_commit, "registry source"),
        )
    }
    if provenances != expected:
        raise BattleScenarioMaterializationRunnerError(
            "plan source provenance differs"
        )
    try:
        return _load_catalog(
            args.context_catalog,
            expected_catalog_sha256=args.expected_context_catalog_sha256,
            registry_source_commit=args.registry_source_commit,
            expected_registry_sha256=args.expected_registry_sha256,
        )
    except BattleScenarioSourceInventoryError as error:
        raise BattleScenarioMaterializationRunnerError(str(error)) from None


def _require_plan_exclusions(
    args: argparse.Namespace,
    *,
    plan: BattleScenarioMaterializationPlanLike,
    rom_path: Path,
) -> None:
    predecessor_arguments = (
        args.predecessor_plan,
        args.predecessor_run_journal,
        args.predecessor_capture_directory,
    )
    if isinstance(plan, BattleScenarioMaterializationCompletionPlan):
        if (
            args.excluded_plan is None
            or args.excluded_run_journal is None
            or any(item is None for item in predecessor_arguments)
        ):
            raise BattleScenarioMaterializationRunnerError(
                "completion predecessor and exhausted evidence are required"
            )
        attempted_sources = _require_completion_predecessor(
            plan,
            earliest_plan_path=args.excluded_plan,
            earliest_journal_path=args.excluded_run_journal,
            predecessor_plan_path=args.predecessor_plan,
            predecessor_journal_path=args.predecessor_run_journal,
            predecessor_capture_directory=args.predecessor_capture_directory,
            rom_path=rom_path,
        )
        if any(
            item.source.source_state_sha256 in attempted_sources
            for item in plan.inventory
        ):
            raise BattleScenarioMaterializationRunnerError(
                "completion plan reuses an attempted source"
            )
    elif isinstance(plan, BattleScenarioMaterializationPlanV2):
        if args.excluded_plan is None or args.excluded_run_journal is None:
            raise BattleScenarioMaterializationRunnerError(
                "V2 exhausted source evidence is required"
            )
        try:
            attempted_sources = _load_attempted_source_exclusions(
                args.excluded_plan,
                args.excluded_run_journal,
                expected_plan_sha256=plan.excluded_plan_sha256,
                expected_journal_sha256=plan.excluded_run_journal_sha256,
            )
        except BattleScenarioSourceInventoryError as error:
            raise BattleScenarioMaterializationRunnerError(str(error)) from None
        if any(
            item.source.source_state_sha256 in attempted_sources
            for item in plan.inventory
        ):
            raise BattleScenarioMaterializationRunnerError(
                "V2 materialization plan reuses an exhausted source"
            )
        if any(item is not None for item in predecessor_arguments):
            raise BattleScenarioMaterializationRunnerError(
                "V2 materialization plan cannot accept completion predecessor evidence"
            )
    elif (
        args.excluded_plan is not None
        or args.excluded_run_journal is not None
        or any(item is not None for item in predecessor_arguments)
    ):
        raise BattleScenarioMaterializationRunnerError(
            "V1 materialization plan cannot accept V2 exclusion evidence"
        )


def _require_completion_predecessor(
    plan: BattleScenarioMaterializationCompletionPlan,
    *,
    earliest_plan_path: Path,
    earliest_journal_path: Path,
    predecessor_plan_path: Path,
    predecessor_journal_path: Path,
    predecessor_capture_directory: Path,
    rom_path: Path,
) -> frozenset[str]:
    try:
        earliest_attempted = _load_attempted_source_exclusions(
            earliest_plan_path,
            earliest_journal_path,
            expected_plan_sha256=plan.earliest_excluded_plan_sha256,
            expected_journal_sha256=plan.earliest_excluded_run_journal_sha256,
        )
    except BattleScenarioSourceInventoryError as error:
        raise BattleScenarioMaterializationRunnerError(str(error)) from None
    predecessor_directory = _private_capture_directory(
        predecessor_capture_directory,
        rom_path=rom_path,
    )
    predecessor_plan = _read_plan(
        _private_existing_file(
            predecessor_plan_path,
            parent=predecessor_directory,
            maximum_bytes=_MAXIMUM_PLAN_BYTES,
            subject="predecessor materialization plan",
        )
    )
    if not isinstance(predecessor_plan, BattleScenarioMaterializationPlanV2):
        raise BattleScenarioMaterializationRunnerError(
            "completion predecessor plan differs"
        )
    predecessor_journal = _read_journal(
        _private_existing_file(
            predecessor_journal_path,
            parent=predecessor_directory,
            maximum_bytes=_MAXIMUM_JOURNAL_BYTES,
            subject="predecessor materialization journal",
        )
    )
    try:
        require_battle_scenario_materialization_run_matches_plan(
            predecessor_journal,
            predecessor_plan,
            predecessor_journal.identity,
        )
    except BattleScenarioMaterializationRunError as error:
        raise BattleScenarioMaterializationRunnerError(str(error)) from None
    if (
        predecessor_plan.plan_sha256 != plan.predecessor_plan_sha256
        or predecessor_journal.journal_sha256
        != plan.predecessor_run_journal_sha256
        or predecessor_plan.capture_directory_sha256
        != plan.predecessor_capture_directory_sha256
        or hashlib.sha256(str(predecessor_directory).encode("utf-8")).hexdigest()
        != plan.predecessor_capture_directory_sha256
        or predecessor_plan.excluded_plan_sha256
        != plan.earliest_excluded_plan_sha256
        or predecessor_plan.excluded_run_journal_sha256
        != plan.earliest_excluded_run_journal_sha256
        or any(
            entry.status not in {SUCCEEDED, FAILED}
            for entry in predecessor_journal.entries
        )
        or sum(entry.status == FAILED for entry in predecessor_journal.entries)
        != plan.predecessor_failure_count
    ):
        raise BattleScenarioMaterializationRunnerError(
            "completion predecessor binding differs"
        )
    retained = []
    predecessor_attempted = set(earliest_attempted)
    for assignment, entry in zip(
        predecessor_plan.assignments,
        predecessor_journal.entries,
        strict=True,
    ):
        predecessor_attempted.add(
            assignment.candidate.source.source_state_sha256
        )
        if entry.status != SUCCEEDED:
            continue
        state_sha256, manifest_sha256 = _authenticate_assignment_outputs(
            assignment,
            capture_directory=predecessor_directory,
            source_commit=predecessor_journal.identity.source_commit,
            rom_path=rom_path,
        )
        if (
            state_sha256 != entry.state_sha256
            or manifest_sha256 != entry.manifest_sha256
        ):
            raise BattleScenarioMaterializationRunnerError(
                "completion retained output binding differs"
            )
        retained.append(
            RetainedBattleScenarioMaterializationCapture(
                ordinal=assignment.ordinal,
                capture_id=assignment.capture_id,
                assignment_sha256=canonical_sha256(assignment.private_dict()),
                source_commit=predecessor_journal.identity.source_commit,
                source_state_sha256=(
                    assignment.candidate.source.source_state_sha256
                ),
                root_lineage_id=assignment.candidate.source.root_lineage_id,
                venue_id=assignment.selected_venue.venue_id,
                party_slot=assignment.party_slot,
                state_filename=assignment.state_filename,
                manifest_filename=assignment.manifest_filename,
                state_sha256=state_sha256,
                manifest_sha256=manifest_sha256,
            )
        )
    if tuple(retained) != plan.retained_successes:
        raise BattleScenarioMaterializationRunnerError(
            "completion retained capture catalog differs"
        )
    return frozenset(predecessor_attempted)


def _open_or_initialize_journal(
    path: Path,
    *,
    plan: BattleScenarioMaterializationPlanLike,
    identity: BattleScenarioMaterializationRunIdentity,
) -> BattleScenarioMaterializationRunJournal:
    if path.exists():
        journal = _read_journal(path)
        require_battle_scenario_materialization_run_matches_plan(
            journal,
            plan,
            identity,
        )
        return journal
    journal = initialize_battle_scenario_materialization_run(plan, identity)
    _write_new(path, journal.canonical_bytes())
    return _read_journal(path)


def _reconcile_existing_entries(
    journal: BattleScenarioMaterializationRunJournal,
    *,
    plan: BattleScenarioMaterializationPlanLike,
    capture_directory: Path,
    journal_path: Path,
    rom_path: Path,
) -> BattleScenarioMaterializationRunJournal:
    changed = False
    for assignment in plan.assignments:
        entry = journal.entries[assignment.ordinal]
        if entry.status == PENDING:
            _require_pending_outputs_absent(
                assignment,
                capture_directory=capture_directory,
            )
        elif entry.status == SUCCEEDED:
            state_sha256, manifest_sha256 = _authenticate_assignment_outputs(
                assignment,
                capture_directory=capture_directory,
                source_commit=journal.identity.source_commit,
                rom_path=rom_path,
            )
            if (
                state_sha256 != entry.state_sha256
                or manifest_sha256 != entry.manifest_sha256
            ):
                raise BattleScenarioMaterializationRunnerError(
                    "successful materialization output changed"
                )
        elif entry.status == STARTED:
            state_path, manifest_path = _assignment_paths(
                assignment,
                capture_directory=capture_directory,
            )
            if state_path.exists() and manifest_path.exists():
                state_sha256, manifest_sha256 = _authenticate_assignment_outputs(
                    assignment,
                    capture_directory=capture_directory,
                    source_commit=journal.identity.source_commit,
                    rom_path=rom_path,
                )
                journal = succeed_battle_scenario_materialization_assignment(
                    journal,
                    assignment.ordinal,
                    state_sha256=state_sha256,
                    manifest_sha256=manifest_sha256,
                )
                changed = True
        elif entry.status != FAILED:  # pragma: no cover - dataclass closes this
            raise AssertionError("unsupported journal state")
    if changed:
        _replace_journal(journal_path, journal.canonical_bytes())
    return journal


def _materialize_assignment(
    assignment: BattleScenarioMaterializationAssignmentLike,
    *,
    source_bytes: bytes,
    capture_directory: Path,
    context_catalog: Path,
    registry_source_commit: str,
    expected_registry_sha256: str,
    expected_context_catalog_sha256: str,
    rom_path: Path,
    maximum_encounter_steps: int,
    watch: bool,
    speed: int | None,
) -> Mapping[str, object]:
    descriptor, source_name = tempfile.mkstemp(
        prefix="pokemon-red-battle-source-",
        suffix=".state",
    )
    source_path = Path(source_name)
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, source_bytes)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        state_path, manifest_path = _assignment_paths(
            assignment,
            capture_directory=capture_directory,
        )
        command = [
            sys.executable,
            str(MATERIALIZER_PATH),
            "--source-state",
            str(source_path),
            "--context-catalog",
            str(context_catalog),
            "--expected-context-catalog-sha256",
            expected_context_catalog_sha256,
            "--registry-source-commit",
            registry_source_commit,
            "--expected-registry-sha256",
            expected_registry_sha256,
            "--party-slot",
            str(assignment.party_slot.party_slot),
            "--capture-id",
            assignment.capture_id,
            "--out-state",
            str(state_path),
            "--out-manifest",
            str(manifest_path),
            "--rom",
            str(rom_path),
            "--maximum-encounter-steps",
            str(maximum_encounter_steps),
        ]
        if isinstance(assignment, BattleScenarioMaterializationAssignmentV2):
            command.extend(
                (
                    "--expected-reachable-venue-id",
                    assignment.selected_venue.venue_id,
                )
            )
        if watch:
            command.append("--watch")
        if speed is not None:
            command.extend(("--speed", str(speed)))
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=False,
        )
        if (
            len(completed.stdout) > _MAXIMUM_MATERIALIZER_OUTPUT_BYTES
            or len(completed.stderr) > _MAXIMUM_MATERIALIZER_OUTPUT_BYTES
        ):
            raise BattleScenarioMaterializationRunnerError(
                "materializer_process_failed"
            )
        try:
            value = json.loads(completed.stdout.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise BattleScenarioMaterializationRunnerError(
                "materializer_receipt_invalid"
            ) from None
        if not isinstance(value, Mapping):
            raise BattleScenarioMaterializationRunnerError(
                "materializer_receipt_invalid"
            )
        if completed.returncode != 0:
            reason_code = value.get("reason_code")
            if (
                value.get("schema") != _MATERIALIZER_FAILURE_SCHEMA
                or value.get("status") != "failed_closed"
                or reason_code not in _MATERIALIZER_FAILURE_REASONS
                or value.get("private_path_fields") != 0
                or value.get("teacher_queries") != 0
                or value.get("move_choices_executed") != 0
                or value.get("root_claims_created") != 0
            ):
                raise BattleScenarioMaterializationRunnerError(
                    "materializer_process_failed"
                )
            raise BattleScenarioMaterializationRunnerError(str(reason_code))
        return value
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with suppress(OSError):
            source_path.unlink()


def _assignment_venue_id(
    assignment: BattleScenarioMaterializationAssignmentLike,
) -> str:
    if isinstance(assignment, BattleScenarioMaterializationAssignmentV2):
        return assignment.selected_venue.venue_id
    return assignment.candidate.venue_id


def _assignment_source_location(
    assignment: BattleScenarioMaterializationAssignmentLike,
) -> str:
    if isinstance(assignment, BattleScenarioMaterializationAssignmentV2):
        return assignment.selected_venue.source_location
    return assignment.candidate.source_location


def _assignment_minimum_encounter_level(
    assignment: BattleScenarioMaterializationAssignmentLike,
) -> int:
    if isinstance(assignment, BattleScenarioMaterializationAssignmentV2):
        return assignment.selected_venue.minimum_encounter_level
    return assignment.candidate.minimum_encounter_level


def _assignment_maximum_encounter_level(
    assignment: BattleScenarioMaterializationAssignmentLike,
) -> int:
    if isinstance(assignment, BattleScenarioMaterializationAssignmentV2):
        return assignment.selected_venue.maximum_encounter_level
    return assignment.candidate.maximum_encounter_level


def _require_materializer_receipt(
    receipt: Mapping[str, object],
    *,
    assignment: BattleScenarioMaterializationAssignmentLike,
    source_commit: str,
    state_sha256: str,
    manifest_sha256: str,
) -> None:
    source = assignment.candidate.source
    venue_id = _assignment_venue_id(assignment)
    source_location = _assignment_source_location(assignment)
    minimum_encounter_level = _assignment_minimum_encounter_level(assignment)
    maximum_encounter_level = _assignment_maximum_encounter_level(assignment)
    selected_venue_reauthenticated = isinstance(
        assignment,
        BattleScenarioMaterializationAssignmentV2,
    )
    candidate_count = receipt.get("candidate_count")
    supported_candidate_count = receipt.get("supported_candidate_count")
    if not _battle_candidate_cardinality_is_supported(
        candidate_count,
        supported_candidate_count,
    ):
        raise BattleScenarioMaterializationRunnerError(
            "materializer_candidate_cardinality_differs"
        )
    if (
        receipt.get("schema")
        != "pokemon-private-battle-scenario-materialization-receipt-v2"
        or receipt.get("status") != "ok"
        or receipt.get("capture_id") != assignment.capture_id
        or receipt.get("root_lineage_id") != source.root_lineage_id
        or receipt.get("partition") != "train"
        or receipt.get("source_commit") != source_commit
        or receipt.get("source_state_sha256") != source.source_state_sha256
        or receipt.get("source_slot_id") != source.source_slot_id
        or receipt.get("source_assignment_id") != source.source_assignment_id
        or receipt.get("source_context_id") != source.source_context_id
        or receipt.get("source_envelope_sha256") != source.source_envelope_sha256
        or receipt.get("root_consumption_sha256") != source.root_consumption_sha256
        or receipt.get("context_catalog_sha256") != source.catalog_sha256
        or receipt.get("registry_sha256") != source.registry_sha256
        or receipt.get("registry_source_commit") != source.registry_source_commit
        or receipt.get("state_sha256") != state_sha256
        or receipt.get("manifest_sha256") != manifest_sha256
        or receipt.get("venue_id") != venue_id
        or receipt.get("venue_minimum_encounter_level")
        != minimum_encounter_level
        or receipt.get("venue_maximum_encounter_level")
        != maximum_encounter_level
        or receipt.get("source_location") != source_location
        or receipt.get("party_slot") != assignment.party_slot.party_slot
        or receipt.get("teacher_queries") != 0
        or receipt.get("move_choices_executed") != 0
        or receipt.get("root_claims_created") != 0
        or receipt.get("caller_supplied_partition") is not False
        or receipt.get("caller_supplied_lineage") is not False
        or receipt.get("caller_supplied_source_location") is not False
        or receipt.get("selected_reachable_venue_reauthenticated")
        is not selected_venue_reauthenticated
        or receipt.get("private_path_fields") != 0
    ):
        raise BattleScenarioMaterializationRunnerError(
            "materializer_receipt_invalid"
        )


def _battle_candidate_cardinality_is_supported(
    candidate_count: object,
    supported_candidate_count: object,
) -> bool:
    """Share the learner's variable two-to-four action-menu contract."""

    return (
        type(candidate_count) is int  # noqa: E721
        and 2 <= candidate_count <= 4
        and type(supported_candidate_count) is int  # noqa: E721
        and 2 <= supported_candidate_count <= candidate_count
    )


def _authenticate_assignment_outputs(
    assignment: BattleScenarioMaterializationAssignmentLike,
    *,
    capture_directory: Path,
    source_commit: str,
    rom_path: Path,
) -> tuple[str, str]:
    state_path, manifest_path = _assignment_paths(
        assignment,
        capture_directory=capture_directory,
    )
    try:
        capture = open_battle_scenario_capture(state_path, manifest_path)
    except BattleScenarioCaptureError as error:
        raise BattleScenarioMaterializationRunnerError(
            "materialized_capture_cannot_be_authenticated"
        ) from error
    manifest = capture.manifest
    expected_map = {
        MANSION_VENUE_ID: int(MapId.POKEMON_MANSION_1F),
        ROUTE_11_VENUE_ID: int(MapId.ROUTE_11),
        "digletts_cave": int(MapId.DIGLETTS_CAVE),
    }[_assignment_venue_id(assignment)]
    if (
        manifest.capture_id != assignment.capture_id
        or manifest.root_lineage_id != assignment.candidate.source.root_lineage_id
        or manifest.partition.value != "train"
        or manifest.source_commit != source_commit
        or manifest.source_state_sha256
        != assignment.candidate.source.source_state_sha256
        or manifest.expected_map != expected_map
        or manifest.expected_battle_state != 1
    ):
        raise BattleScenarioMaterializationRunnerError(
            "materialized_capture_binding_differs"
        )
    try:
        with PyBoyAdapter(rom_path) as emulator:
            emulator.load_state_bytes(capture.state_bytes)
            reader = PokemonRedStateReader(emulator)
            raw = reader.read()
            menu = reader.read_battle_menu_state(raw)
            prepared = prepare_red_battle_scenario(
                PokemonRedObservationEncoder.from_state_reader(reader),
                raw,
            )
            if emulator.frame_count != 0 or emulator.pressed_buttons:
                raise BattleScenarioMaterializationRunnerError(
                    "materialized_capture_reopen_crossed_controller_boundary"
                )
    except BattleScenarioMaterializationRunnerError:
        raise
    except Exception as error:
        raise BattleScenarioMaterializationRunnerError(
            "materialized_capture_state_cannot_be_reopened"
        ) from error
    party_index = assignment.party_slot.party_slot - 1
    candidate_count = len(prepared.features.candidate_vectors)
    supported_candidate_count = sum(prepared.supported_candidate_mask)
    if (
        raw.map_id != expected_map
        or raw.battle_state != 1
        or raw.active_party_index != party_index
        or menu.phase is not BattleMenuPhase.MAIN
    ):
        raise BattleScenarioMaterializationRunnerError(
            "materialized_capture_policy_boundary_differs"
        )
    if prepared.initial_observation_sha256 != manifest.initial_observation_sha256:
        raise BattleScenarioMaterializationRunnerError(
            "materialized_capture_observation_differs"
        )
    if not _battle_candidate_cardinality_is_supported(
        candidate_count,
        supported_candidate_count,
    ):
        raise BattleScenarioMaterializationRunnerError(
            "materialized_capture_candidate_cardinality_differs"
        )
    if (
        raw.party_species_ids is None
        or raw.party_levels is None
        or party_index >= len(raw.party_species_ids)
        or party_index >= len(raw.party_levels)
        or raw.party_species_ids[party_index] != assignment.party_slot.species_id
        or raw.party_levels[party_index] != assignment.party_slot.level
    ):
        raise BattleScenarioMaterializationRunnerError(
            "materialized_capture_party_binding_differs"
        )
    return manifest.state_sha256, capture.manifest_sha256


def _require_pending_outputs_absent(
    assignment: BattleScenarioMaterializationAssignmentLike,
    *,
    capture_directory: Path,
) -> None:
    state_path, manifest_path = _assignment_paths(
        assignment,
        capture_directory=capture_directory,
    )
    if any(path.exists() or path.is_symlink() for path in (state_path, manifest_path)):
        raise BattleScenarioMaterializationRunnerError(
            "pending materialization output already exists"
        )


def _assignment_paths(
    assignment: BattleScenarioMaterializationAssignmentLike,
    *,
    capture_directory: Path,
) -> tuple[Path, Path]:
    state = (capture_directory / assignment.state_filename).resolve()
    manifest = (capture_directory / assignment.manifest_filename).resolve()
    if (
        state.parent != capture_directory
        or manifest.parent != capture_directory
        or state == manifest
    ):
        raise BattleScenarioMaterializationRunnerError(
            "materialization destination differs"
        )
    return state, manifest


def _private_capture_directory(path: Path, *, rom_path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
        observed = resolved.stat()
    except OSError:
        raise BattleScenarioMaterializationRunnerError(
            "capture directory cannot be authenticated"
        ) from None
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) & 0o077
        or resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved == rom_path.resolve().parent
    ):
        raise BattleScenarioMaterializationRunnerError(
            "capture directory cannot be authenticated"
        )
    return resolved


def _private_existing_file(
    path: Path,
    *,
    parent: Path,
    maximum_bytes: int,
    subject: str,
) -> Path:
    resolved = path.resolve()
    if resolved.parent != parent:
        raise BattleScenarioMaterializationRunnerError(f"{subject} is unavailable")
    _read_owned_regular(resolved, maximum_bytes=maximum_bytes, subject=subject)
    return resolved


def _private_journal_path(path: Path, *, parent: Path) -> Path:
    resolved = path.resolve()
    if resolved.parent != parent or resolved.is_symlink():
        raise BattleScenarioMaterializationRunnerError("run journal is unavailable")
    if resolved.exists():
        _read_owned_regular(
            resolved,
            maximum_bytes=_MAXIMUM_JOURNAL_BYTES,
            subject="run journal",
        )
    return resolved


def _private_receipt_path(path: Path, *, parent: Path) -> Path:
    resolved = path.resolve()
    if resolved.parent != parent or resolved.is_symlink():
        raise BattleScenarioMaterializationRunnerError("run receipt is unavailable")
    if resolved.exists():
        _read_owned_regular(
            resolved,
            maximum_bytes=_MAXIMUM_RECEIPT_BYTES,
            subject="run receipt",
        )
    return resolved


def _read_plan(path: Path) -> BattleScenarioMaterializationPlanLike:
    payload = _read_owned_regular(
        path,
        maximum_bytes=_MAXIMUM_PLAN_BYTES,
        subject="materialization plan",
    )
    try:
        return parse_battle_scenario_materialization_plan(payload)
    except BattleScenarioMaterializationPlanError:
        pass
    try:
        return parse_battle_scenario_materialization_plan_v2(payload)
    except BattleScenarioMaterializationPlanV2Error:
        pass
    try:
        return parse_battle_scenario_materialization_completion_plan(payload)
    except BattleScenarioMaterializationPlanV2Error as error:
        raise BattleScenarioMaterializationRunnerError(str(error)) from None


def _read_journal(path: Path) -> BattleScenarioMaterializationRunJournal:
    payload = _read_owned_regular(
        path,
        maximum_bytes=_MAXIMUM_JOURNAL_BYTES,
        subject="run journal",
    )
    try:
        return parse_battle_scenario_materialization_run(payload)
    except BattleScenarioMaterializationRunError as error:
        raise BattleScenarioMaterializationRunnerError(str(error)) from None


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
            or stat.S_IMODE(opened.st_mode) & 0o077
            or not 1 <= opened.st_size <= maximum_bytes
        ):
            raise OSError("unsafe private file")
        payload = b""
        while len(payload) < opened.st_size:
            chunk = os.read(descriptor, opened.st_size - len(payload))
            if not chunk:
                raise OSError("private file changed")
            payload += chunk
        after = os.fstat(descriptor)
        if (
            after.st_dev != opened.st_dev
            or after.st_ino != opened.st_ino
            or after.st_mode != opened.st_mode
            or after.st_nlink != opened.st_nlink
            or after.st_uid != opened.st_uid
            or after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
        ):
            raise OSError("private file changed")
        return payload
    except OSError:
        raise BattleScenarioMaterializationRunnerError(
            f"{subject} cannot be authenticated"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _write_new(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    created = False
    try:
        descriptor = os.open(path, flags, 0o600)
        created = True
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _fsync_directory(path.parent)
    except OSError:
        if created:
            with suppress(OSError):
                path.unlink()
        raise BattleScenarioMaterializationRunnerError(
            "private run artifact could not be retained durably"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _replace_journal(path: Path, payload: bytes) -> None:
    _read_owned_regular(
        path,
        maximum_bytes=_MAXIMUM_JOURNAL_BYTES,
        subject="run journal",
    )
    temporary = path.with_name(f".{path.name}.next")
    if temporary.exists() or temporary.is_symlink():
        raise BattleScenarioMaterializationRunnerError(
            "run journal transition is ambiguous"
        )
    _write_new(temporary, payload)
    try:
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError:
        raise BattleScenarioMaterializationRunnerError(
            "run journal transition could not be retained durably"
        ) from None


def _publish_or_verify_receipt(path: Path, receipt: Mapping[str, object]) -> None:
    payload = _canonical_payload(receipt)
    if path.exists():
        if _read_owned_regular(
            path,
            maximum_bytes=_MAXIMUM_RECEIPT_BYTES,
            subject="run receipt",
        ) != payload:
            raise BattleScenarioMaterializationRunnerError("run receipt differs")
        return
    _write_new(path, payload)


@contextmanager
def _run_lease(journal_path: Path) -> Iterator[None]:
    lock_path = journal_path.with_name(f".{journal_path.name}.lock")
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) & 0o077
        ):
            raise OSError("unsafe run lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except BlockingIOError:
        raise BattleScenarioMaterializationRunnerError(
            "another materialization runner holds the journal"
        ) from None
    except OSError:
        raise BattleScenarioMaterializationRunnerError(
            "run journal lease is unavailable"
        ) from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def _require_exact_green_ci_run(
    exact_ci_run: int,
    exact_ci_attempt: int,
    *,
    source_commit: str,
) -> Mapping[str, object]:
    if (
        type(exact_ci_run) is not int  # noqa: E721
        or exact_ci_run <= 0
        or type(exact_ci_attempt) is not int  # noqa: E721
        or exact_ci_attempt <= 0
    ):
        raise BattleScenarioMaterializationRunnerError("exact_ci_identity_differs")
    try:
        completed = subprocess.run(
            (
                "gh",
                "run",
                "view",
                str(exact_ci_run),
                "--repo",
                _GITHUB_REPOSITORY,
                "--json",
                "attempt,conclusion,databaseId,event,headBranch,headSha,status,url,workflowName",
            ),
            cwd=PROJECT_ROOT,
            env={**os.environ, "GH_PROMPT_DISABLED": "1"},
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        value = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        raise BattleScenarioMaterializationRunnerError(
            "exact_ci_cannot_be_authenticated"
        ) from None
    if (
        completed.returncode != 0
        or not isinstance(value, Mapping)
        or value.get("databaseId") != exact_ci_run
        or value.get("attempt") != exact_ci_attempt
        or value.get("headSha") != source_commit
        or value.get("status") != "completed"
        or value.get("conclusion") != "success"
        or value.get("event") != "push"
        or value.get("headBranch") != "main"
        or value.get("workflowName") != _CI_WORKFLOW_NAME
        or value.get("url")
        != f"https://github.com/{_GITHUB_REPOSITORY}/actions/runs/{exact_ci_run}"
    ):
        raise BattleScenarioMaterializationRunnerError("exact_ci_differs")
    return value


def _failure_reason(error: Exception) -> str:
    if isinstance(error, BattleScenarioMaterializationRunnerError):
        text = str(error)
        if re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,95}", text):
            return text
    return "materialization_failed"


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("write made no progress")
        offset += written


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _canonical_payload(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("ascii")


def _commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise BattleScenarioMaterializationRunnerError(f"{subject} commit differs")
    return value


def _sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleScenarioMaterializationRunnerError(f"{subject} digest differs")
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = _run(args)
    except (
        BattleScenarioMaterializationRunnerError,
        BattleScenarioMaterializationRunError,
        FreshCompositionQualificationError,
    ) as error:
        print(
            json.dumps(
                {
                    "schema": "pokemon.red-battle-scenario-materialization-run-failure.v1",
                    "status": "failed_closed",
                    "reason": _failure_reason(error),
                    "private_path_fields": 0,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
