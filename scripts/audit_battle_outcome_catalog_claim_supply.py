#!/usr/bin/env python3
"""Audit claim availability across authenticated battle capture catalogs only."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import freeze_battle_outcome_batch as freezer  # noqa: E402

from pokemon_red_completion.battle_outcome_capture_authentication import (  # noqa: E402
    BattleOutcomeCaptureAuthenticationError,
    authenticate_battle_scenario_source_binding,
)
from pokemon_red_completion.battle_scenario_capture_catalog import (  # noqa: E402
    BattleScenarioCaptureCatalogError,
    parse_battle_scenario_capture_catalog,
)
from pokemon_red_completion.battle_scenario_development_capture_catalog import (  # noqa: E402
    BattleScenarioDevelopmentCaptureCatalog,
    BattleScenarioDevelopmentCaptureCatalogError,
    parse_battle_scenario_development_capture_catalog,
)
from pokemon_red_completion.claim_first_admission import (  # noqa: E402
    ClaimFirstAvailabilitySnapshot,
    claim_first_availability_snapshot_lease,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.goal_manager_composition_qualification import (  # noqa: E402
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.goal_manager_context_catalog import (  # noqa: E402
    GoalManagerContextCatalog,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    GoalManagerCollectionRegistry,
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


class BattleOutcomeCatalogClaimSupplyAuditError(RuntimeError):
    """Raised when catalog metadata cannot support a claim census."""


@dataclass(frozen=True, slots=True)
class CatalogRoot:
    """One catalog-authenticated logical and physical claim identity."""

    partition: ScenarioPartition
    logical_root_sha256: str
    physical_root_sha256: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument(
        "--train-capture-catalog",
        action="append",
        nargs=2,
        metavar=("CATALOG", "EXPECTED_SHA256"),
        required=True,
    )
    parser.add_argument(
        "--development-capture-catalog",
        action="append",
        nargs=2,
        metavar=("CATALOG", "EXPECTED_SHA256"),
        required=True,
    )
    parser.add_argument("--required-train-contexts", type=int, default=7)
    parser.add_argument("--required-development-contexts", type=int, default=8)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    registry, context_catalog, context_sha256 = _open_experiment_context(args)
    train_roots, train_digests, train_roms = _open_train_catalogs(
        args.train_capture_catalog,
        context_catalog=context_catalog,
        context_sha256=context_sha256,
        registry=registry,
    )
    development_roots, development_digests, development_roms = (
        _open_development_catalogs(
            args.development_capture_catalog,
            context_catalog=context_catalog,
            context_sha256=context_sha256,
            registry=registry,
        )
    )
    roots = (*train_roots, *development_roots)
    if not roots:
        raise BattleOutcomeCatalogClaimSupplyAuditError("capture catalogs are empty")
    pairs = tuple(
        (item.logical_root_sha256, item.physical_root_sha256) for item in roots
    )
    if len(set(pairs)) != len(pairs):
        raise BattleOutcomeCatalogClaimSupplyAuditError(
            "capture catalogs repeat a logical/physical root pair"
        )
    if len({item.logical_root_sha256 for item in roots}) != len(roots):
        raise BattleOutcomeCatalogClaimSupplyAuditError(
            "capture catalogs repeat a logical root"
        )
    if len({item.physical_root_sha256 for item in roots}) != len(roots):
        raise BattleOutcomeCatalogClaimSupplyAuditError(
            "capture catalogs repeat a physical root"
        )
    roms = train_roms | development_roms
    if len(roms) != 1:
        raise BattleOutcomeCatalogClaimSupplyAuditError(
            "capture catalogs do not share one ROM identity"
        )
    required_train = _required_count(args.required_train_contexts, "train")
    required_development = _required_count(
        args.required_development_contexts,
        "development",
    )
    with claim_first_availability_snapshot_lease(
        open_fixed_account_claim_registry()
    ) as lease:
        snapshot = lease.observe(pairs)
        counts = _availability_counts(roots, snapshot)
    train_ready = counts["train_available"] >= required_train
    development_ready = counts["development_available"] >= required_development
    return {
        "schema": "pokemon-red-battle-outcome-catalog-claim-supply-audit-v1",
        "status": (
            "complete_successor_supply_available"
            if train_ready and development_ready
            else "successor_capture_generation_required"
        ),
        "source": source.public_dict(),
        "source_bundle_sha256": working_source_bundle_sha256(PROJECT_ROOT),
        "registry_sha256": registry.registry_sha256,
        "registry_source_commit": registry.execution.source_commit,
        "context_catalog_sha256": context_sha256,
        "rom_sha256": next(iter(roms)),
        "train_catalogs": len(args.train_capture_catalog),
        "train_capture_catalog_sha256s": list(train_digests),
        "development_catalogs": len(args.development_capture_catalog),
        "development_capture_catalog_sha256s": list(development_digests),
        **counts,
        "required_train": required_train,
        "required_development": required_development,
        "train_deficit": max(0, required_train - counts["train_available"]),
        "development_deficit": max(
            0,
            required_development - counts["development_available"],
        ),
        "availability_snapshot_sha256": snapshot.snapshot_sha256,
        "state_files_opened": 0,
        "capture_manifests_opened": 0,
        "rom_files_opened": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "outcomes_opened": 0,
        "predictions_computed": 0,
        "model_fits": 0,
        "teacher_queries": 0,
        "root_claims_created": 0,
        "sealed_red_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }


def _open_experiment_context(
    args: argparse.Namespace,
) -> tuple[GoalManagerCollectionRegistry, GoalManagerContextCatalog, str]:
    registry_commit = freezer._commit(  # noqa: SLF001
        args.registry_source_commit,
        "registry source",
    )
    registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        registry_commit,
    )
    expected_registry = freezer._sha256(  # noqa: SLF001
        args.expected_registry_sha256,
        "registry",
    )
    if registry.registry_sha256 != expected_registry:
        raise BattleOutcomeCatalogClaimSupplyAuditError("historical registry differs")
    payload = freezer._read_bounded_private_file(  # noqa: SLF001
        args.context_catalog,
        maximum_bytes=freezer._MAXIMUM_CONTEXT_CATALOG_BYTES,  # noqa: SLF001
        subject="context catalog",
    )
    observed_sha256 = hashlib.sha256(payload).hexdigest()
    if observed_sha256 != freezer._sha256(  # noqa: SLF001
        args.expected_context_catalog_sha256,
        "context catalog",
    ):
        raise BattleOutcomeCatalogClaimSupplyAuditError("context catalog digest differs")
    return registry, parse_goal_manager_context_catalog(payload, registry), observed_sha256


def _open_train_catalogs(
    raw_catalogs: object,
    *,
    context_catalog: GoalManagerContextCatalog,
    context_sha256: str,
    registry: GoalManagerCollectionRegistry,
) -> tuple[tuple[CatalogRoot, ...], tuple[str, ...], frozenset[str]]:
    roots: list[CatalogRoot] = []
    digests: list[str] = []
    roms: set[str] = set()
    for path, expected_sha256 in _catalog_specs(raw_catalogs, "train"):
        payload = freezer._read_bounded_private_file(  # noqa: SLF001
            path,
            maximum_bytes=freezer._MAXIMUM_CAPTURE_CATALOG_BYTES,  # noqa: SLF001
            subject="train capture catalog",
        )
        if hashlib.sha256(payload).hexdigest() != expected_sha256:
            raise BattleOutcomeCatalogClaimSupplyAuditError(
                "train capture catalog digest differs"
            )
        try:
            catalog = parse_battle_scenario_capture_catalog(payload)
        except BattleScenarioCaptureCatalogError as error:
            raise BattleOutcomeCatalogClaimSupplyAuditError(str(error)) from None
        if any(
            producer.context_catalog_sha256 != context_sha256
            or producer.registry_sha256 != registry.registry_sha256
            or producer.registry_source_commit != registry.execution.source_commit
            for producer in catalog.producers
        ):
            raise BattleOutcomeCatalogClaimSupplyAuditError(
                "train capture catalog experiment binding differs"
            )
        digests.append(expected_sha256)
        roms.add(catalog.rom_sha256)
        for entry in catalog.captures:
            roots.append(
                _catalog_root(
                    partition=ScenarioPartition.TRAIN,
                    source_state_sha256=entry.source_state_sha256,
                    state_sha256=entry.state_sha256,
                    root_lineage_id=entry.root_lineage_id,
                    context_catalog=context_catalog,
                    registry=registry,
                )
            )
    return tuple(roots), tuple(digests), frozenset(roms)


def _open_development_catalogs(
    raw_catalogs: object,
    *,
    context_catalog: GoalManagerContextCatalog,
    context_sha256: str,
    registry: GoalManagerCollectionRegistry,
) -> tuple[tuple[CatalogRoot, ...], tuple[str, ...], frozenset[str]]:
    roots: list[CatalogRoot] = []
    digests: list[str] = []
    roms: set[str] = set()
    for path, expected_sha256 in _catalog_specs(raw_catalogs, "development"):
        payload = freezer._read_bounded_private_file(  # noqa: SLF001
            path,
            maximum_bytes=freezer._MAXIMUM_CAPTURE_CATALOG_BYTES,  # noqa: SLF001
            subject="development capture catalog",
        )
        if hashlib.sha256(payload).hexdigest() != expected_sha256:
            raise BattleOutcomeCatalogClaimSupplyAuditError(
                "development capture catalog digest differs"
            )
        try:
            catalog = parse_battle_scenario_development_capture_catalog(payload)
        except BattleScenarioDevelopmentCaptureCatalogError as error:
            raise BattleOutcomeCatalogClaimSupplyAuditError(str(error)) from None
        producers = (
            (catalog.producer,)
            if isinstance(catalog, BattleScenarioDevelopmentCaptureCatalog)
            else catalog.producers
        )
        if any(
            producer.context_catalog_sha256 != context_sha256
            or producer.registry_sha256 != registry.registry_sha256
            or producer.registry_source_commit != registry.execution.source_commit
            for producer in producers
        ):
            raise BattleOutcomeCatalogClaimSupplyAuditError(
                "development capture catalog experiment binding differs"
            )
        digests.append(expected_sha256)
        roms.update(producer.rom_sha256 for producer in producers)
        for entry in catalog.captures:
            roots.append(
                _catalog_root(
                    partition=ScenarioPartition.DEVELOPMENT,
                    source_state_sha256=entry.source_state_sha256,
                    state_sha256=entry.state_sha256,
                    root_lineage_id=entry.root_lineage_id,
                    context_catalog=context_catalog,
                    registry=registry,
                )
            )
    return tuple(roots), tuple(digests), frozenset(roms)


def _catalog_root(
    *,
    partition: ScenarioPartition,
    source_state_sha256: str,
    state_sha256: str,
    root_lineage_id: str,
    context_catalog: GoalManagerContextCatalog,
    registry: GoalManagerCollectionRegistry,
) -> CatalogRoot:
    try:
        binding = authenticate_battle_scenario_source_binding(
            source_state_sha256,
            expected_partition=partition,
            catalog=context_catalog,
            registry=registry,
        )
    except BattleOutcomeCaptureAuthenticationError as error:
        raise BattleOutcomeCatalogClaimSupplyAuditError(str(error)) from None
    if binding.root_lineage_id != root_lineage_id:
        raise BattleOutcomeCatalogClaimSupplyAuditError(
            "capture catalog lineage differs from its authenticated source"
        )
    return CatalogRoot(
        partition=partition,
        logical_root_sha256=binding.root_consumption_sha256,
        physical_root_sha256=state_sha256,
    )


def _catalog_specs(value: object, subject: str) -> tuple[tuple[Path, str], ...]:
    if not isinstance(value, list) or not value:
        raise BattleOutcomeCatalogClaimSupplyAuditError(f"{subject} catalogs differ")
    result: list[tuple[Path, str]] = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
        ):
            raise BattleOutcomeCatalogClaimSupplyAuditError(
                f"{subject} catalogs differ"
            )
        result.append(
            (
                Path(item[0]),
                freezer._sha256(item[1], f"{subject} catalog"),  # noqa: SLF001
            )
        )
    if len(set(result)) != len(result):
        raise BattleOutcomeCatalogClaimSupplyAuditError(
            f"{subject} catalog repeats"
        )
    return tuple(result)


def _required_count(value: object, subject: str) -> int:
    if type(value) is not int or not 1 <= value <= freezer._MAXIMUM_CAPTURE_SPECS:  # noqa: E721, SLF001
        raise BattleOutcomeCatalogClaimSupplyAuditError(
            f"required {subject} context count differs"
        )
    return value


def _availability_counts(
    roots: Iterable[CatalogRoot],
    snapshot: ClaimFirstAvailabilitySnapshot,
) -> dict[str, int]:
    totals: Counter[str] = Counter()
    available: Counter[str] = Counter()
    for item in roots:
        partition = item.partition.value
        totals[partition] += 1
        available[partition] += int(
            snapshot.availability_for(
                item.logical_root_sha256,
                item.physical_root_sha256,
            )
        )
    return {
        "train_total": totals["train"],
        "train_available": available["train"],
        "train_claimed": totals["train"] - available["train"],
        "development_total": totals["development"],
        "development_available": available["development"],
        "development_claimed": totals["development"] - available["development"],
    }


def main() -> int:
    try:
        receipt = _run(_parser().parse_args())
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise SystemExit(f"battle catalog claim-supply audit failed: {error}") from None
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
