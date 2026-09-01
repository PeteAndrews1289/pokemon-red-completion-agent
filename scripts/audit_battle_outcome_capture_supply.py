#!/usr/bin/env python3
"""Audit Red V2 battle capture supply without opening states or running gameplay."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import freeze_battle_outcome_batch as freezer  # noqa: E402

from pokemon_red_completion.battle_outcome_capture_authentication import (  # noqa: E402
    BattleOutcomeCaptureAuthenticationError,
    authenticate_battle_scenario_source_binding,
)
from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    parse_battle_scenario_capture_manifest,
)
from pokemon_red_completion.battle_scenario_capture_catalog import (  # noqa: E402
    BattleScenarioCaptureCatalogError,
    parse_battle_scenario_capture_catalog,
)
from pokemon_red_completion.goal_manager_context_catalog import (  # noqa: E402
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


class BattleOutcomeCaptureSupplyAuditError(RuntimeError):
    """Raised when immutable metadata cannot support a supply audit."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--train-capture-catalog", type=Path, required=True)
    parser.add_argument("--expected-train-capture-catalog-sha256", required=True)
    parser.add_argument(
        "--development-producer-catalog",
        action="append",
        nargs=3,
        metavar=("SOURCE_COMMIT", "CATALOG", "EXPECTED_SHA256"),
        required=True,
    )
    parser.add_argument(
        "--development-manifest",
        action="append",
        nargs=2,
        metavar=("SOURCE_COMMIT", "MANIFEST"),
        required=True,
    )
    parser.add_argument("--required-development-contexts", type=int, default=8)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
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
        raise BattleOutcomeCaptureSupplyAuditError("historical registry differs")

    context_payload = freezer._read_bounded_private_file(  # noqa: SLF001
        args.context_catalog,
        maximum_bytes=freezer._MAXIMUM_CONTEXT_CATALOG_BYTES,  # noqa: SLF001
        subject="context catalog",
    )
    context_sha256 = hashlib.sha256(context_payload).hexdigest()
    if context_sha256 != freezer._sha256(  # noqa: SLF001
        args.expected_context_catalog_sha256,
        "context catalog",
    ):
        raise BattleOutcomeCaptureSupplyAuditError("context catalog digest differs")
    context_catalog = parse_goal_manager_context_catalog(context_payload, registry)

    train_payload = freezer._read_bounded_private_file(  # noqa: SLF001
        args.train_capture_catalog,
        maximum_bytes=freezer._MAXIMUM_CAPTURE_CATALOG_BYTES,  # noqa: SLF001
        subject="train capture catalog",
    )
    train_sha256 = hashlib.sha256(train_payload).hexdigest()
    if train_sha256 != freezer._sha256(  # noqa: SLF001
        args.expected_train_capture_catalog_sha256,
        "train capture catalog",
    ):
        raise BattleOutcomeCaptureSupplyAuditError("train capture catalog digest differs")
    try:
        train_catalog = parse_battle_scenario_capture_catalog(train_payload)
    except BattleScenarioCaptureCatalogError as error:
        raise BattleOutcomeCaptureSupplyAuditError(str(error)) from None
    if any(
        producer.context_catalog_sha256 != context_sha256
        or producer.registry_sha256 != expected_registry
        or producer.registry_source_commit != registry_commit
        for producer in train_catalog.producers
    ):
        raise BattleOutcomeCaptureSupplyAuditError(
            "train capture catalog experiment binding differs"
        )

    development_catalogs = freezer._development_catalogs(  # noqa: SLF001
        args.development_producer_catalog,
    )
    manifests = args.development_manifest
    if (
        not isinstance(manifests, list)
        or not manifests
        or len(manifests) > freezer._MAXIMUM_CAPTURE_SPECS  # noqa: SLF001
    ):
        raise BattleOutcomeCaptureSupplyAuditError(
            "development manifest inventory size differs"
        )
    required = args.required_development_contexts
    if type(required) is not int or not 1 <= required <= freezer._MAXIMUM_CAPTURE_SPECS:  # noqa: E721, SLF001
        raise BattleOutcomeCaptureSupplyAuditError(
            "required development context count differs"
        )

    producer_membership_matches = 0
    partition_matches = 0
    source_commit_matches = 0
    source_catalog_matches = 0
    lineage_matches = 0
    compatible = 0
    capture_ids: set[str] = set()
    source_states: set[str] = set()
    manifest_digests: set[str] = set()
    for raw in manifests:
        if (
            not isinstance(raw, list)
            or len(raw) != 2
            or any(not isinstance(item, str) for item in raw)
        ):
            raise BattleOutcomeCaptureSupplyAuditError(
                "development manifest inventory differs"
            )
        source_commit = freezer._commit(raw[0], "development producer")  # noqa: SLF001
        producer = development_catalogs.get(source_commit)
        if producer is None:
            raise BattleOutcomeCaptureSupplyAuditError(
                "development manifest has no producer catalog"
            )
        payload = freezer._read_bounded_private_file(  # noqa: SLF001
            Path(raw[1]),
            maximum_bytes=freezer._MAXIMUM_CAPTURE_MANIFEST_BYTES,  # noqa: SLF001
            subject="development capture manifest",
        )
        try:
            manifest = parse_battle_scenario_capture_manifest(payload)
        except (RuntimeError, TypeError, ValueError) as error:
            raise BattleOutcomeCaptureSupplyAuditError(str(error)) from None
        source_state_sha256 = manifest.source_state_sha256
        if not isinstance(source_state_sha256, str):
            raise BattleOutcomeCaptureSupplyAuditError(
                "development manifest has no source state identity"
            )
        manifest_digest = hashlib.sha256(payload).hexdigest()
        if (
            manifest.capture_id in capture_ids
            or source_state_sha256 in source_states
            or manifest_digest in manifest_digests
        ):
            raise BattleOutcomeCaptureSupplyAuditError(
                "development manifest inventory repeats an input"
        )
        capture_ids.add(manifest.capture_id)
        source_states.add(source_state_sha256)
        manifest_digests.add(manifest_digest)

        membership = producer[1].get(manifest.capture_id)
        membership_matches = membership == (
            source_state_sha256,
            manifest.root_lineage_id,
        )
        partition_match = manifest.partition is ScenarioPartition.DEVELOPMENT
        source_commit_match = manifest.source_commit == source_commit
        producer_membership_matches += int(membership_matches)
        partition_matches += int(partition_match)
        source_commit_matches += int(source_commit_match)
        try:
            source_binding = authenticate_battle_scenario_source_binding(
                source_state_sha256,
                expected_partition=ScenarioPartition.DEVELOPMENT,
                catalog=context_catalog,
                registry=registry,
            )
        except BattleOutcomeCaptureAuthenticationError:
            continue
        source_catalog_matches += 1
        lineage_match = source_binding.root_lineage_id == manifest.root_lineage_id
        lineage_matches += int(lineage_match)
        compatible += int(
            membership_matches
            and partition_match
            and source_commit_match
            and lineage_match
        )

    ready = len(train_catalog.captures) == 7 and compatible >= required
    return {
        "schema": "pokemon-red-battle-outcome-capture-supply-audit-v1",
        "status": "ready" if ready else "insufficient_compatible_supply",
        "train_capture_catalog_sha256": train_sha256,
        "train_captures": len(train_catalog.captures),
        "train_producers": len(train_catalog.producers),
        "development_manifests": len(manifests),
        "development_producer_catalogs": len(development_catalogs),
        "producer_membership_matches": producer_membership_matches,
        "partition_matches": partition_matches,
        "source_commit_matches": source_commit_matches,
        "source_catalog_matches": source_catalog_matches,
        "lineage_matches": lineage_matches,
        "compatible_development_captures": compatible,
        "required_development_captures": required,
        "development_deficit": max(0, required - compatible),
        "state_files_opened": 0,
        "rom_files_opened": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "outcomes_opened": 0,
        "predictions_computed": 0,
        "model_fits": 0,
        "teacher_queries": 0,
        "root_claims_created": 0,
        "red_sealed_test_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }


def main() -> int:
    try:
        receipt = _run(_parser().parse_args())
    except (
        BattleOutcomeCaptureSupplyAuditError,
        freezer.BattleOutcomeBatchFreezeError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        raise SystemExit(f"battle capture supply audit failed: {error}") from None
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
