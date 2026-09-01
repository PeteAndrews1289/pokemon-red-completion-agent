#!/usr/bin/env python3
"""Freeze an additive Red battle-capture tranche around retained successes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from freeze_battle_scenario_materialization_plan import (  # noqa: E402
    BattleScenarioMaterializationFreezeError,
    _private_new_plan,
    _write_exclusive,
)
from freeze_battle_scenario_materialization_plan_v2 import (  # noqa: E402
    BattleScenarioMaterializationFreezeV2Error,
    _candidate_from_loaded_root,
    _private_capture_directory_v2,
    _read_private_plan_v2,
    _require_new_assignment_outputs_v2,
)
from inventory_battle_scenario_source_venues import (  # noqa: E402
    BattleScenarioSourceInventoryError,
    _CatalogTrainRootScan,
    _load_attempted_source_exclusions,
    _load_catalog,
    _observe_root,
    _open_all_catalog_train_roots,
    _require_state_bank,
)
from run_battle_scenario_materialization_plan import (  # noqa: E402
    _authenticate_assignment_outputs,
    _private_existing_file,
    _read_journal,
    _read_plan,
)

from pokemon_red_completion.battle_scenario_materialization_plan_v2 import (  # noqa: E402
    BattleScenarioMaterializationCompletionPlan,
    BattleScenarioMaterializationPlanV2,
    BattleScenarioMaterializationPlanV2Error,
    RetainedBattleScenarioMaterializationCapture,
    build_battle_scenario_materialization_completion_plan,
)
from pokemon_red_completion.battle_scenario_materialization_run import (  # noqa: E402
    FAILED,
    SUCCEEDED,
    BattleScenarioMaterializationRunError,
    require_battle_scenario_materialization_run_matches_plan,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.goal_manager_composition_qualification import (  # noqa: E402
    FreshCompositionQualificationError,
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.runtime_identity import (  # noqa: E402
    build_runtime_identity,
    require_pyboy_import_origins,
)

_MAXIMUM_PLAN_BYTES = 8 * 1024 * 1024
_MAXIMUM_JOURNAL_BYTES = 2 * 1024 * 1024


class BattleScenarioMaterializationCompletionFreezeError(RuntimeError):
    """Raised before an additive private plan can drift or replace history."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--state-bank", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--earliest-excluded-plan", type=Path, required=True)
    parser.add_argument("--expected-earliest-excluded-plan-sha256", required=True)
    parser.add_argument("--earliest-excluded-run-journal", type=Path, required=True)
    parser.add_argument(
        "--expected-earliest-excluded-run-journal-sha256",
        required=True,
    )
    parser.add_argument("--predecessor-capture-directory", type=Path, required=True)
    parser.add_argument("--predecessor-plan", type=Path, required=True)
    parser.add_argument("--expected-predecessor-plan-sha256", required=True)
    parser.add_argument("--predecessor-run-journal", type=Path, required=True)
    parser.add_argument("--expected-predecessor-run-journal-sha256", required=True)
    parser.add_argument("--capture-directory", type=Path, required=True)
    parser.add_argument("--out-plan", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if (
        source.git_commit != args.expected_source_commit
        or source_bundle != args.expected_source_bundle_sha256
    ):
        raise BattleScenarioMaterializationCompletionFreezeError(
            "published source identity differs"
        )
    runtime = build_runtime_identity()
    require_pyboy_import_origins(runtime)
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    capture_directory = _private_capture_directory_v2(
        args.capture_directory,
        rom_path=rom_path,
    )
    predecessor_directory = _private_capture_directory_v2(
        args.predecessor_capture_directory,
        rom_path=rom_path,
    )
    if capture_directory == predecessor_directory:
        raise BattleScenarioMaterializationCompletionFreezeError(
            "additive and predecessor capture directories must differ"
        )
    destination = _private_new_plan(
        args.out_plan,
        capture_directory=capture_directory,
    )

    try:
        catalog, registry = _load_catalog(
            args.context_catalog,
            expected_catalog_sha256=args.expected_context_catalog_sha256,
            registry_source_commit=args.registry_source_commit,
            expected_registry_sha256=args.expected_registry_sha256,
        )
        scan = _open_all_catalog_train_roots(
            _require_state_bank(args.state_bank),
            catalog=catalog,
            registry=registry,
        )
        earliest_attempted = _load_attempted_source_exclusions(
            args.earliest_excluded_plan,
            args.earliest_excluded_run_journal,
            expected_plan_sha256=args.expected_earliest_excluded_plan_sha256,
            expected_journal_sha256=(
                args.expected_earliest_excluded_run_journal_sha256
            ),
        )
    except BattleScenarioSourceInventoryError as error:
        raise BattleScenarioMaterializationCompletionFreezeError(str(error)) from None
    if scan.missing_catalog_train_roots != 0:
        raise BattleScenarioMaterializationCompletionFreezeError(
            "complete catalog train state bank is required"
        )

    predecessor_plan = _read_private_plan_v2(
        _private_existing_file(
            args.predecessor_plan,
            parent=predecessor_directory,
            maximum_bytes=_MAXIMUM_PLAN_BYTES,
            subject="predecessor materialization plan",
        )
    )
    predecessor_journal = _read_journal(
        _private_existing_file(
            args.predecessor_run_journal,
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
        raise BattleScenarioMaterializationCompletionFreezeError(str(error)) from None
    if (
        predecessor_plan.plan_sha256 != args.expected_predecessor_plan_sha256
        or predecessor_journal.journal_sha256
        != args.expected_predecessor_run_journal_sha256
        or predecessor_plan.rom_sha256 != rom.sha256
        or predecessor_plan.excluded_plan_sha256
        != args.expected_earliest_excluded_plan_sha256
        or predecessor_plan.excluded_run_journal_sha256
        != args.expected_earliest_excluded_run_journal_sha256
        or predecessor_plan.capture_directory_sha256
        != hashlib.sha256(str(predecessor_directory).encode("utf-8")).hexdigest()
        or any(
            entry.status not in {SUCCEEDED, FAILED}
            for entry in predecessor_journal.entries
        )
    ):
        raise BattleScenarioMaterializationCompletionFreezeError(
            "terminal predecessor binding differs"
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
            raise BattleScenarioMaterializationCompletionFreezeError(
                "retained predecessor output differs"
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
    failure_count = sum(
        entry.status == FAILED for entry in predecessor_journal.entries
    )
    if not retained or failure_count < 1:
        raise BattleScenarioMaterializationCompletionFreezeError(
            "terminal predecessor does not require additive completion"
        )

    successor_scan = _CatalogTrainRootScan(
        roots=tuple(
            root
            for root in scan.roots
            if root.binding.source_state_sha256 not in predecessor_attempted
        ),
        state_files_hashed=scan.state_files_hashed,
        matching_state_file_copies=scan.matching_state_file_copies,
        missing_catalog_train_roots=scan.missing_catalog_train_roots,
    )
    registry_path = open_fixed_account_claim_registry()
    try:
        plan, claim_available_roots = _freeze_under_shared_lease(
            scan=successor_scan,
            registry_path=registry_path,
            rom_path=rom_path,
            plan_id=args.plan_id,
            source_commit=args.expected_source_commit,
            source_bundle_sha256=source_bundle,
            rom_sha256=rom.sha256,
            capture_directory=capture_directory,
            predecessor_plan=predecessor_plan,
            predecessor_journal_sha256=predecessor_journal.journal_sha256,
            predecessor_failure_count=failure_count,
            retained_successes=tuple(retained),
            destination=destination,
        )
    except (
        BattleScenarioMaterializationFreezeError,
        BattleScenarioMaterializationFreezeV2Error,
        BattleScenarioMaterializationPlanV2Error,
        BattleScenarioSourceInventoryError,
        FreshCompositionQualificationError,
    ) as error:
        raise BattleScenarioMaterializationCompletionFreezeError(str(error)) from None

    reopened = _read_private_completion_plan(destination)
    if reopened != plan:
        raise BattleScenarioMaterializationCompletionFreezeError(
            "retained completion plan differs after reopen"
        )
    selected_counts = Counter(
        assignment.selected_venue.venue_id for assignment in plan.assignments
    )
    total_counts = Counter(item.venue_id for item in plan.retained_successes)
    total_counts.update(selected_counts)
    return {
        "schema": "pokemon-red-battle-scenario-materialization-completion-freeze-receipt-v1",
        "status": "prospective_unexecuted_additive_completion_frozen",
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "selection_policy_sha256": plan.selection_policy_sha256,
        "source_commit": source.git_commit,
        "source_bundle_sha256": source_bundle,
        "runtime_identity_sha256": runtime.sha256,
        "rom_sha256": rom.sha256,
        "context_catalog_sha256": catalog.catalog_sha256,
        "registry_sha256": registry.registry_sha256,
        "registry_source_commit": registry.execution.source_commit,
        "catalog_train_roots": len(scan.roots),
        "excluded_attempted_source_roots": len(predecessor_attempted),
        "successor_candidate_train_roots": len(successor_scan.roots),
        "claim_available_train_roots": claim_available_roots,
        "eligible_candidate_root_count": len(plan.inventory),
        "retained_successful_capture_count": len(plan.retained_successes),
        "retained_terminal_failure_count": plan.predecessor_failure_count,
        "new_assignment_count": len(plan.assignments),
        "combined_capture_count_if_complete": (
            len(plan.retained_successes) + len(plan.assignments)
        ),
        "new_assignment_venue_counts": dict(sorted(selected_counts.items())),
        "combined_venue_counts": dict(sorted(total_counts.items())),
        "retried_assignments": 0,
        "reclassified_failed_assignments": 0,
        "replacement_slots_inside_predecessor": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "battle_captures_created": 0,
        "outcomes_opened": 0,
        "model_predictions": 0,
        "model_fits": 0,
        "teacher_queries": 0,
        "sealed_red_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "full_game_replays": 0,
        "authority_promoted": False,
        "private_identity_fields": 0,
        "private_path_fields": 0,
    }


def _freeze_under_shared_lease(
    *,
    scan: _CatalogTrainRootScan,
    registry_path: Path,
    rom_path: Path,
    plan_id: str,
    source_commit: str,
    source_bundle_sha256: str,
    rom_sha256: str,
    capture_directory: Path,
    predecessor_plan: BattleScenarioMaterializationPlanV2,
    predecessor_journal_sha256: str,
    predecessor_failure_count: int,
    retained_successes: tuple[RetainedBattleScenarioMaterializationCapture, ...],
    destination: Path,
) -> tuple[BattleScenarioMaterializationCompletionPlan, int]:
    with (
        fixed_account_claim_registry_lease(registry_path, exclusive=False),
        PyBoyAdapter(rom_path) as emulator,
    ):
        candidates = []
        claim_available_roots = 0
        for root in scan.roots:
            observed = _observe_root(
                root,
                emulator=emulator,
                registry_path=registry_path,
            )
            claim_available_roots += int(observed.claim_available)
            if not observed.reachable_venue_allocation_eligible:
                continue
            candidates.append(
                _candidate_from_loaded_root(
                    root.binding,
                    expected_venue_ids=observed.eligible_venue_ids,
                    emulator=emulator,
                )
            )
        if emulator.frame_count != 0 or emulator.pressed_buttons:
            raise BattleScenarioMaterializationCompletionFreezeError(
                "completion freeze crossed the controller boundary"
            )
        plan = build_battle_scenario_materialization_completion_plan(
            plan_id=plan_id,
            source_commit=source_commit,
            source_bundle_sha256=source_bundle_sha256,
            rom_sha256=rom_sha256,
            capture_directory_sha256=hashlib.sha256(
                str(capture_directory).encode("utf-8")
            ).hexdigest(),
            earliest_excluded_plan_sha256=predecessor_plan.excluded_plan_sha256,
            earliest_excluded_run_journal_sha256=(
                predecessor_plan.excluded_run_journal_sha256
            ),
            predecessor_plan_sha256=predecessor_plan.plan_sha256,
            predecessor_run_journal_sha256=predecessor_journal_sha256,
            predecessor_capture_directory_sha256=(
                predecessor_plan.capture_directory_sha256
            ),
            predecessor_failure_count=predecessor_failure_count,
            retained_successes=retained_successes,
            candidates=candidates,
        )
        _require_new_assignment_outputs_v2(
            plan,  # type: ignore[arg-type]
            capture_directory=capture_directory,
            plan_destination=destination,
        )
        _write_exclusive(destination, plan.canonical_bytes())
    return plan, claim_available_roots


def _read_private_completion_plan(
    path: Path,
) -> BattleScenarioMaterializationCompletionPlan:
    plan = _read_plan(path)
    if not isinstance(plan, BattleScenarioMaterializationCompletionPlan):
        raise BattleScenarioMaterializationCompletionFreezeError(
            "completion plan cannot be reopened"
        )
    return plan


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(_run(args), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
