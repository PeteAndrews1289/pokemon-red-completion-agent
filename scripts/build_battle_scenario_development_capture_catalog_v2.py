#!/usr/bin/env python3
"""Build one path-free development catalog across seven-plus-one producers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_battle_scenario_capture_catalog import (  # noqa: E402
    BattleScenarioCaptureCatalogBuildError,
    _catalog_entries,
    _private_new_catalog,
    _read_completion_plan,
    _read_journal,
    _read_owned_regular,
    _read_predecessor_plan,
    _require_terminal_producer,
    _write_exclusive,
)
from run_battle_scenario_materialization_plan import (  # noqa: E402
    _private_capture_directory,
)

from pokemon_red_completion.battle_scenario_development_capture_catalog import (  # noqa: E402
    BattleScenarioDevelopmentCaptureCatalogError,
    BattleScenarioDevelopmentCaptureEntryV2,
    BattleScenarioDevelopmentCaptureProducerV2,
    build_battle_scenario_development_capture_catalog_v2,
    parse_battle_scenario_development_capture_catalog,
)
from pokemon_red_completion.battle_scenario_materialization_plan_v2 import (  # noqa: E402
    BattleScenarioMaterializationCompletionPlan,
    BattleScenarioMaterializationPlanV2,
)
from pokemon_red_completion.battle_scenario_materialization_run import (  # noqa: E402
    BattleScenarioMaterializationRunJournal,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402

_MAXIMUM_CATALOG_BYTES = 4 * 1024 * 1024


class BattleScenarioDevelopmentCaptureCatalogV2BuildError(RuntimeError):
    """Raised before mixed development provenance can enter a catalog."""


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


def _producer(
    role: str,
    journal: BattleScenarioMaterializationRunJournal,
    *,
    successes: int,
    failures: int,
) -> BattleScenarioDevelopmentCaptureProducerV2:
    identity = journal.identity
    return BattleScenarioDevelopmentCaptureProducerV2(
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
        completion_plan.partition.value != "development"
        or completion_plan.predecessor_plan_sha256 != predecessor_plan.plan_sha256
        or completion_plan.predecessor_run_journal_sha256
        != predecessor_journal.journal_sha256
        or completion_plan.predecessor_capture_directory_sha256
        != predecessor_plan.capture_directory_sha256
        or completion_plan.predecessor_failure_count != 1
        or predecessor_attempted.intersection(completion_sources)
    ):
        raise BattleScenarioDevelopmentCaptureCatalogV2BuildError(
            "development completion lineage differs"
        )


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    source_commit = source.git_commit
    if (
        not isinstance(source_commit, str)
        or source_commit != args.expected_source_commit
        or source_bundle != args.expected_source_bundle_sha256
    ):
        raise BattleScenarioDevelopmentCaptureCatalogV2BuildError(
            "published development catalog builder identity differs"
        )
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
        raise BattleScenarioDevelopmentCaptureCatalogV2BuildError(
            "development producer directories collapse"
        )
    try:
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
            expected_successes=7,
            expected_failures=1,
            capture_directory=predecessor_directory,
        )
        _require_terminal_producer(
            completion_plan,
            completion_journal,
            expected_successes=1,
            expected_failures=0,
            capture_directory=completion_directory,
        )
        _require_completion_lineage(predecessor_plan, predecessor_journal, completion_plan)
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
    except BattleScenarioCaptureCatalogBuildError as error:
        raise BattleScenarioDevelopmentCaptureCatalogV2BuildError(str(error)) from None
    if retained != completion_plan.retained_successes:
        raise BattleScenarioDevelopmentCaptureCatalogV2BuildError(
            "development retained capture projection differs"
        )
    entries = tuple(
        BattleScenarioDevelopmentCaptureEntryV2(
            ordinal=item.ordinal,
            capture_id=item.capture_id,
            assignment_sha256=item.assignment_sha256,
            source_state_sha256=item.source_state_sha256,
            root_lineage_id=item.root_lineage_id,
            venue_id=item.venue_id,
            party_slot=item.party_slot,
            state_filename=item.state_filename,
            manifest_filename=item.manifest_filename,
            state_sha256=item.state_sha256,
            manifest_sha256=item.manifest_sha256,
            producer_id=item.producer_id,
            producer_ordinal=item.producer_ordinal,
        )
        for item in (*predecessor_entries, *completion_entries)
    )
    try:
        catalog = build_battle_scenario_development_capture_catalog_v2(
            catalog_id=args.catalog_id,
            builder_source_commit=source_commit,
            builder_source_bundle_sha256=source_bundle,
            rom_sha256=rom.sha256,
            producers=(
                _producer("predecessor", predecessor_journal, successes=7, failures=1),
                _producer("completion", completion_journal, successes=1, failures=0),
            ),
            captures=entries,
        )
        destination = _private_new_catalog(args.out_catalog, rom_path=rom_path)
        _write_exclusive(destination, catalog.canonical_bytes())
        reopened = parse_battle_scenario_development_capture_catalog(
            _read_owned_regular(
                destination,
                maximum_bytes=_MAXIMUM_CATALOG_BYTES,
                subject="development capture catalog",
            )
        )
    except (BattleScenarioDevelopmentCaptureCatalogError, OSError, ValueError) as error:
        raise BattleScenarioDevelopmentCaptureCatalogV2BuildError(str(error)) from None
    if reopened != catalog:
        raise BattleScenarioDevelopmentCaptureCatalogV2BuildError(
            "development catalog differs after independent reopen"
        )
    return {
        "schema": "pokemon-red-battle-scenario-development-capture-catalog-v2-receipt-v1",
        "status": "authenticated_action_free",
        "catalog_sha256": catalog.catalog_sha256,
        "capture_count": len(catalog.captures),
        "producer_count": len(catalog.producers),
        "historical_failed_assignments": 1,
        "controller_actions": 0,
        "emulator_frames": 0,
        "outcomes_opened": 0,
        "model_fits": 0,
        "private_path_fields": 0,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        receipt = _run(_parser().parse_args(argv))
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema": (
                        "pokemon-red-battle-scenario-development-capture-"
                        "catalog-v2-failure-v1"
                    ),
                    "status": "failed_closed",
                    "reason_code": "development_capture_catalog_v2_authentication_failed",
                    "failure_type": type(error).__name__,
                    "controller_actions": 0,
                    "emulator_frames": 0,
                    "outcomes_opened": 0,
                    "model_fits": 0,
                    "private_path_fields": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
