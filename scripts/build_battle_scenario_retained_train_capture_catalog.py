#!/usr/bin/env python3
"""Build an action-free catalog of the five retained train captures."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import build_battle_scenario_capture_catalog as catalog_builder  # noqa: E402

from pokemon_red_completion.battle_scenario_capture_catalog import (  # noqa: E402
    BattleScenarioCaptureCatalogError,
    build_battle_scenario_retained_train_capture_catalog,
    parse_battle_scenario_retained_train_capture_catalog,
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


class BattleScenarioRetainedTrainCatalogBuildError(RuntimeError):
    """Raised when the exact five-success predecessor cannot be authenticated."""


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
    parser.add_argument("--out-catalog", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    expected_commit = catalog_builder._commit(
        args.expected_source_commit,
        "retained train catalog builder source",
    )
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if (
        source.git_commit != expected_commit
        or source_bundle
        != catalog_builder._sha256(
            args.expected_source_bundle_sha256,
            "retained train catalog builder source bundle",
        )
    ):
        raise BattleScenarioRetainedTrainCatalogBuildError(
            "published catalog builder identity differs"
        )

    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    capture_directory = catalog_builder._private_capture_directory(
        args.predecessor_capture_directory,
        rom_path=rom_path,
    )
    plan = catalog_builder._read_predecessor_plan(
        args.predecessor_plan,
        parent=capture_directory,
        expected_sha256=args.expected_predecessor_plan_sha256,
    )
    journal = catalog_builder._read_journal(
        args.predecessor_journal,
        parent=capture_directory,
        expected_sha256=args.expected_predecessor_journal_sha256,
    )
    catalog_builder._require_terminal_producer(
        plan,
        journal,
        expected_successes=5,
        expected_failures=2,
        capture_directory=capture_directory,
    )
    entries, _ = catalog_builder._catalog_entries(
        producer_id="predecessor",
        plan=plan,
        journal=journal,
        capture_directory=capture_directory,
        rom_path=rom_path,
    )
    try:
        catalog = build_battle_scenario_retained_train_capture_catalog(
            catalog_id=args.catalog_id,
            builder_source_commit=expected_commit,
            builder_source_bundle_sha256=source_bundle,
            rom_sha256=rom.sha256,
            producer=catalog_builder._producer(
                "predecessor",
                journal,
                successes=5,
                failures=2,
            ),
            captures=entries,
        )
    except (BattleScenarioCaptureCatalogError, TypeError, ValueError) as error:
        raise BattleScenarioRetainedTrainCatalogBuildError(str(error)) from None

    destination = catalog_builder._private_new_catalog(
        args.out_catalog,
        rom_path=rom_path,
    )
    catalog_builder._write_exclusive(destination, catalog.canonical_bytes())
    reopened_payload = catalog_builder._read_owned_regular(
        destination,
        maximum_bytes=2 * 1024 * 1024,
        subject="retained train capture catalog",
    )
    try:
        reopened = parse_battle_scenario_retained_train_capture_catalog(
            reopened_payload
        )
    except BattleScenarioCaptureCatalogError as error:
        raise BattleScenarioRetainedTrainCatalogBuildError(str(error)) from None
    if reopened != catalog:
        raise BattleScenarioRetainedTrainCatalogBuildError(
            "retained train catalog failed canonical reopen"
        )
    return {
        "schema": "pokemon-red-battle-scenario-retained-train-catalog-receipt-v1",
        "status": "authenticated_action_free",
        "catalog_id": catalog.catalog_id,
        "catalog_sha256": hashlib.sha256(reopened_payload).hexdigest(),
        "capture_count": len(catalog.captures),
        "historical_failed_assignments": 2,
        "venue_counts": {
            venue: sum(item.venue_id == venue for item in catalog.captures)
            for venue in sorted({item.venue_id for item in catalog.captures})
        },
        "controller_actions": 0,
        "emulator_frames": 0,
        "root_claims_created": 0,
        "outcomes_opened": 0,
        "predictions_computed": 0,
        "model_fits": 0,
        "teacher_queries": 0,
        "sealed_red_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = _run(args)
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema": (
                        "pokemon-red-battle-scenario-retained-train-catalog-failure-v1"
                    ),
                    "status": "failed_closed",
                    "reason_code": "retained_train_catalog_authentication_failed",
                    "failure_type": type(error).__name__,
                    "controller_actions": 0,
                    "emulator_frames": 0,
                    "outcomes_opened": 0,
                    "predictions_computed": 0,
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
