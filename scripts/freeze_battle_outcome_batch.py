#!/usr/bin/env python3
"""Freeze one outcome-blind Red V2 battle inventory and roster atomically."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_neural_model import (  # noqa: E402
    MaskedMLPMoveRanker,
)
from pokemon_red_completion.battle_outcome_batch import (  # noqa: E402
    BattleOutcomeBatchError,
    BattleOutcomeBatchFreeze,
    RetainedBattleOutcomePrefix,
    battle_outcome_model_sha256,
    build_battle_outcome_batch_freeze,
    build_battle_outcome_pressure_candidate,
    build_battle_outcome_pressure_inventory,
    parse_battle_outcome_batch_freeze,
    parse_retained_battle_outcome_prefix,
)
from pokemon_red_completion.battle_outcome_capture_authentication import (  # noqa: E402
    BattleOutcomeCaptureAuthenticationError,
    authenticate_battle_outcome_capture_binding,
    authenticate_battle_scenario_source_binding,
)
from pokemon_red_completion.battle_outcome_experiment import (  # noqa: E402
    BattleOutcomeCaptureBinding,
)
from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    open_battle_scenario_capture,
    parse_battle_scenario_capture_manifest,
)
from pokemon_red_completion.battle_scenario_capture_catalog import (  # noqa: E402
    BattleScenarioCaptureCatalog,
    BattleScenarioCaptureCatalogEntry,
    BattleScenarioCaptureCatalogError,
    parse_battle_scenario_capture_catalog,
)
from pokemon_red_completion.battle_semantics import (  # noqa: E402
    BattleFeatureBatch,
)
from pokemon_red_completion.claim_first_admission import (  # noqa: E402
    ClaimFirstAdmissionError,
    claim_first_availability_snapshot_lease,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
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
from pokemon_red_completion.learned_battle_policy import (  # noqa: E402
    load_battle_model_artifact,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_battle_outcome_runtime import (  # noqa: E402
    prepare_red_battle_outcome_capture,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.runtime_identity import (  # noqa: E402
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAXIMUM_CONTEXT_CATALOG_BYTES = 4 * 1024 * 1024
_MAXIMUM_CAPTURE_CATALOG_BYTES = 4 * 1024 * 1024
_MAXIMUM_CAPTURE_MANIFEST_BYTES = 64 * 1024
_MAXIMUM_RETAINED_PREFIX_BYTES = 512 * 1024
_MAXIMUM_FREEZE_BYTES = 32 * 1024 * 1024
_MAXIMUM_CAPTURE_SPECS = 512

PreparedBinding = tuple[BattleOutcomeCaptureBinding, BattleFeatureBatch]


@dataclass(frozen=True, slots=True)
class CatalogCaptureSpec:
    """One path-local capture joined to immutable path-free producer evidence."""

    partition: ScenarioPartition
    producer_source_commit: str
    producer_catalog_sha256: str
    state_path: Path
    manifest_path: Path
    capture_id: str
    source_state_sha256: str
    root_lineage_id: str
    state_sha256: str | None = None
    manifest_sha256: str | None = None


class BattleOutcomeBatchFreezeError(RuntimeError):
    """Raised before a V2 inventory/roster freeze can be retained."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster-id", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--retained-prefix", type=Path, required=True)
    parser.add_argument("--expected-retained-prefix-sha256", required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--expected-base-model-sha256", required=True)
    parser.add_argument("--retained-train-state", type=Path, required=True)
    parser.add_argument("--retained-train-manifest", type=Path, required=True)
    parser.add_argument("--train-capture-catalog", type=Path, required=True)
    parser.add_argument("--expected-train-capture-catalog-sha256", required=True)
    parser.add_argument(
        "--train-producer-directory",
        action="append",
        nargs=2,
        metavar=("PRODUCER_ID", "DIRECTORY"),
        required=True,
    )
    parser.add_argument(
        "--development-producer-catalog",
        action="append",
        nargs=3,
        metavar=("SOURCE_COMMIT", "CATALOG", "EXPECTED_SHA256"),
        required=True,
    )
    parser.add_argument(
        "--development-capture",
        action="append",
        nargs=3,
        metavar=("SOURCE_COMMIT", "STATE", "MANIFEST"),
        required=True,
    )
    parser.add_argument("--out-freeze", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    source_commit = _commit(args.expected_source_commit, "source")
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if (
        source.git_commit != source_commit
        or source_bundle
        != _sha256(args.expected_source_bundle_sha256, "source bundle")
    ):
        raise BattleOutcomeBatchFreezeError("published source identity differs")

    runtime = build_runtime_identity()
    require_pyboy_import_origins(runtime)
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    base_model = load_battle_model_artifact(args.base_model)
    if not isinstance(base_model, MaskedMLPMoveRanker):
        raise BattleOutcomeBatchFreezeError(
            "battle batch requires the nonlinear prior"
        )
    base_model_sha256 = battle_outcome_model_sha256(base_model)
    if base_model_sha256 != _sha256(
        args.expected_base_model_sha256,
        "base model",
    ):
        raise BattleOutcomeBatchFreezeError("base model differs")

    registry_commit = _commit(args.registry_source_commit, "registry source")
    registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        registry_commit,
    )
    if registry.registry_sha256 != _sha256(
        args.expected_registry_sha256,
        "registry",
    ):
        raise BattleOutcomeBatchFreezeError("historical registry differs")
    catalog_payload = _read_bounded_private_file(
        args.context_catalog,
        maximum_bytes=_MAXIMUM_CONTEXT_CATALOG_BYTES,
        subject="context catalog",
    )
    if hashlib.sha256(catalog_payload).hexdigest() != _sha256(
        args.expected_context_catalog_sha256,
        "context catalog",
    ):
        raise BattleOutcomeBatchFreezeError("context catalog digest differs")
    context_catalog = parse_goal_manager_context_catalog(catalog_payload, registry)

    retained_payload = _read_bounded_private_file(
        args.retained_prefix,
        maximum_bytes=_MAXIMUM_RETAINED_PREFIX_BYTES,
        subject="retained prefix",
    )
    if hashlib.sha256(retained_payload).hexdigest() != _sha256(
        args.expected_retained_prefix_sha256,
        "retained prefix",
    ):
        raise BattleOutcomeBatchFreezeError("retained prefix digest differs")
    try:
        retained_prefix = parse_retained_battle_outcome_prefix(retained_payload)
    except BattleOutcomeBatchError as error:
        raise BattleOutcomeBatchFreezeError(str(error)) from None
    if retained_prefix.original_prior_sha256 != base_model_sha256:
        raise BattleOutcomeBatchFreezeError(
            "retained prefix differs from the original prior"
        )

    train_catalog_payload = _read_bounded_private_file(
        args.train_capture_catalog,
        maximum_bytes=_MAXIMUM_CAPTURE_CATALOG_BYTES,
        subject="train capture catalog",
    )
    train_catalog_sha256 = hashlib.sha256(train_catalog_payload).hexdigest()
    if train_catalog_sha256 != _sha256(
        args.expected_train_capture_catalog_sha256,
        "train capture catalog",
    ):
        raise BattleOutcomeBatchFreezeError("train capture catalog digest differs")
    try:
        train_catalog = parse_battle_scenario_capture_catalog(train_catalog_payload)
    except BattleScenarioCaptureCatalogError as error:
        raise BattleOutcomeBatchFreezeError(str(error)) from None
    if train_catalog.rom_sha256 != rom.sha256:
        raise BattleOutcomeBatchFreezeError("train capture catalog ROM differs")
    train_specs = _train_catalog_specs(
        train_catalog,
        args.train_producer_directory,
        catalog_sha256=train_catalog_sha256,
        rom_path=rom_path,
    )
    development_catalogs = _development_catalogs(
        args.development_producer_catalog,
    )
    development_specs = _development_capture_specs(
        args.development_capture,
        catalogs=development_catalogs,
        catalog=context_catalog,
        registry=registry,
    )

    def session_factory():  # type: ignore[no-untyped-def]
        return PyBoyAdapter(rom_path)

    prefix = _open_prepared_binding(
        CatalogCaptureSpec(
            partition=ScenarioPartition.TRAIN,
            producer_source_commit=retained_prefix.train.source_commit,
            producer_catalog_sha256=retained_prefix.plan_sha256,
            state_path=args.retained_train_state,
            manifest_path=args.retained_train_manifest,
            capture_id=retained_prefix.train.capture_id,
            source_state_sha256=retained_prefix.train.source_state_sha256,
            root_lineage_id=retained_prefix.train.root_lineage_id,
            state_sha256=retained_prefix.train.state_sha256,
            manifest_sha256=retained_prefix.train.manifest_sha256,
        ),
        base_model=base_model,
        catalog=context_catalog,
        registry=registry,
        session_factory=session_factory,
    )
    if prefix[0] != retained_prefix.train:
        raise BattleOutcomeBatchFreezeError(
            "retained train capture differs from the verified prefix"
        )
    screened = tuple(
        _open_prepared_binding(
            spec,
            base_model=base_model,
            catalog=context_catalog,
            registry=registry,
            session_factory=session_factory,
        )
        for spec in (*train_specs, *development_specs)
    )

    destination = _private_new_freeze(args.out_freeze, rom_path=rom_path)
    registry_path = open_fixed_account_claim_registry()
    freeze = _freeze_under_shared_lease(
        roster_id=args.roster_id,
        retained_prefix=retained_prefix,
        base_model=base_model,
        prefix=prefix,
        screened=screened,
        registry_path=registry_path,
        destination=destination,
        consumer_source_commit=source_commit,
        consumer_source_bundle_sha256=source_bundle,
        capture_catalog_sha256s=tuple(
            sorted(
                {
                    train_catalog_sha256,
                    *(item.producer_catalog_sha256 for item in development_specs),
                }
            )
        ),
    )
    reopened_payload = _read_bounded_private_file(
        destination,
        maximum_bytes=_MAXIMUM_FREEZE_BYTES,
        subject="batch freeze",
    )
    try:
        reopened = parse_battle_outcome_batch_freeze(reopened_payload)
    except BattleOutcomeBatchError as error:
        raise BattleOutcomeBatchFreezeError(str(error)) from None
    if reopened != freeze:
        raise BattleOutcomeBatchFreezeError(
            "retained batch freeze differs after independent reopen"
        )
    return {
        "schema": "pokemon-red-battle-outcome-batch-freeze-receipt-v2",
        "status": "prospective_unexecuted_batch_frozen",
        "roster_id": freeze.roster.roster_id,
        "freeze_sha256": freeze.freeze_sha256,
        "inventory_sha256": freeze.inventory.inventory_sha256,
        "roster_sha256": freeze.roster.roster_sha256,
        "source_commit": source_commit,
        "source_bundle_sha256": source_bundle,
        "runtime_identity_sha256": runtime.sha256,
        "rom_sha256": rom.sha256,
        "base_model_sha256": base_model_sha256,
        "capture_catalog_count": len(freeze.capture_catalog_sha256s),
        "capture_producer_commit_count": len(
            {
                item.binding.source_commit
                for item in (*freeze.roster.fresh_train, *freeze.roster.development)
            }
        ),
        "screened_candidate_count": len(freeze.inventory.screened),
        "fresh_train_contexts": len(freeze.roster.fresh_train),
        "development_contexts": len(freeze.roster.development),
        "retained_train_contexts": 1,
        "read_only_runtime_preparations": len(screened) + 1,
        "prior_score_vector_evaluations": len(screened) + 1,
        "hidden_representation_evaluations": len(screened) + 1,
        "controller_actions": 0,
        "emulator_frames": 0,
        "outcomes_opened": 0,
        "root_claims_created": 0,
        "model_choice_predictions": 0,
        "model_fits": 0,
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "red_sealed_test_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "full_game_replays": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }


def _open_prepared_binding(
    spec: CatalogCaptureSpec,
    *,
    base_model: MaskedMLPMoveRanker,
    catalog: GoalManagerContextCatalog,
    registry: GoalManagerCollectionRegistry,
    session_factory: object,
) -> PreparedBinding:
    try:
        capture = open_battle_scenario_capture(spec.state_path, spec.manifest_path)
        if (
            capture.manifest.capture_id != spec.capture_id
            or capture.manifest.source_state_sha256 != spec.source_state_sha256
            or capture.manifest.root_lineage_id != spec.root_lineage_id
            or (
                spec.state_sha256 is not None
                and capture.manifest.state_sha256 != spec.state_sha256
            )
            or (
                spec.manifest_sha256 is not None
                and capture.manifest_sha256 != spec.manifest_sha256
            )
        ):
            raise BattleOutcomeBatchFreezeError(
                "battle capture differs from its producer catalog"
            )
        prepared = prepare_red_battle_outcome_capture(
            capture,
            session_factory=session_factory,  # type: ignore[arg-type]
        )
        binding = authenticate_battle_outcome_capture_binding(
            capture,
            prepared=prepared,
            base_model=base_model,
            expected_partition=spec.partition,
            source_commit=spec.producer_source_commit,
            catalog=catalog,
            registry=registry,
        )
    except (
        BattleOutcomeCaptureAuthenticationError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        raise BattleOutcomeBatchFreezeError(
            "battle capture boundary cannot be authenticated read-only"
        ) from None
    return binding, prepared.features


def _freeze_under_shared_lease(
    *,
    roster_id: str,
    retained_prefix: RetainedBattleOutcomePrefix,
    base_model: MaskedMLPMoveRanker,
    prefix: PreparedBinding,
    screened: Sequence[PreparedBinding],
    registry_path: Path,
    destination: Path,
    consumer_source_commit: str,
    consumer_source_bundle_sha256: str,
    capture_catalog_sha256s: Sequence[str],
) -> BattleOutcomeBatchFreeze:
    bindings = (prefix[0], *(item[0] for item in screened))
    root_pairs = (
        (
            retained_prefix.train.logical_root_sha256,
            retained_prefix.train.physical_root_sha256,
        ),
        (
            retained_prefix.forbidden_development.logical_root_sha256,
            retained_prefix.forbidden_development.physical_root_sha256,
        ),
        *(
            (binding.logical_root_sha256, binding.physical_root_sha256)
            for binding in bindings[1:]
        ),
    )
    try:
        with claim_first_availability_snapshot_lease(registry_path) as lease:
            snapshot = lease.observe(root_pairs)
            prefix_candidate = build_battle_outcome_pressure_candidate(
                prefix[0],
                prefix[1],
                base_model,
                expected_prior_sha256=retained_prefix.original_prior_sha256,
                claim_available=snapshot.availability_for(
                    prefix[0].logical_root_sha256,
                    prefix[0].physical_root_sha256,
                ),
            )
            screened_candidates = tuple(
                build_battle_outcome_pressure_candidate(
                    binding,
                    features,
                    base_model,
                    expected_prior_sha256=retained_prefix.original_prior_sha256,
                    claim_available=snapshot.availability_for(
                        binding.logical_root_sha256,
                        binding.physical_root_sha256,
                    ),
                )
                for binding, features in screened
            )
            inventory = build_battle_outcome_pressure_inventory(
                retained_prefix=retained_prefix,
                claim_snapshot=snapshot,
                prefix=prefix_candidate,
                screened=screened_candidates,
            )
            freeze = build_battle_outcome_batch_freeze(
                roster_id=roster_id,
                consumer_source_commit=consumer_source_commit,
                consumer_source_bundle_sha256=consumer_source_bundle_sha256,
                capture_catalog_sha256s=capture_catalog_sha256s,
                inventory=inventory,
            )
            payload = freeze.canonical_bytes()
            if parse_battle_outcome_batch_freeze(payload) != freeze:
                raise BattleOutcomeBatchFreezeError(
                    "batch freeze failed its canonical self-check"
                )
            _write_exclusive(destination, payload)
    except (BattleOutcomeBatchError, ClaimFirstAdmissionError) as error:
        raise BattleOutcomeBatchFreezeError(str(error)) from None
    return freeze


def _train_catalog_specs(
    catalog: BattleScenarioCaptureCatalog,
    value: object,
    *,
    catalog_sha256: str,
    rom_path: Path,
) -> tuple[CatalogCaptureSpec, ...]:
    if not isinstance(value, list) or not value:
        raise BattleOutcomeBatchFreezeError("train producer directories differ")
    directories: dict[str, Path] = {}
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise BattleOutcomeBatchFreezeError("train producer directories differ")
        producer_id, raw_directory = item
        if not isinstance(producer_id, str) or not isinstance(raw_directory, str):
            raise BattleOutcomeBatchFreezeError("train producer directories differ")
        if producer_id in directories:
            raise BattleOutcomeBatchFreezeError("train producer directory repeats")
        directories[producer_id] = _private_capture_directory(
            Path(raw_directory),
            rom_path=rom_path,
        )
    producers = {item.producer_id: item for item in catalog.producers}
    if set(directories) != set(producers) or len(set(directories.values())) != len(directories):
        raise BattleOutcomeBatchFreezeError("train producer directories differ")
    return tuple(
        _catalog_entry_spec(
            entry,
            producer_source_commit=producers[entry.producer_id].source_commit,
            producer_catalog_sha256=catalog_sha256,
            directory=directories[entry.producer_id],
        )
        for entry in catalog.captures
    )


def _catalog_entry_spec(
    entry: BattleScenarioCaptureCatalogEntry,
    *,
    producer_source_commit: str,
    producer_catalog_sha256: str,
    directory: Path,
) -> CatalogCaptureSpec:
    return CatalogCaptureSpec(
        partition=ScenarioPartition.TRAIN,
        producer_source_commit=producer_source_commit,
        producer_catalog_sha256=producer_catalog_sha256,
        state_path=directory / entry.state_filename,
        manifest_path=directory / entry.manifest_filename,
        capture_id=entry.capture_id,
        source_state_sha256=entry.source_state_sha256,
        root_lineage_id=entry.root_lineage_id,
        state_sha256=entry.state_sha256,
        manifest_sha256=entry.manifest_sha256,
    )


def _development_catalogs(
    value: object,
) -> dict[str, tuple[str, dict[str, tuple[str, str]]]]:
    if not isinstance(value, list) or not value:
        raise BattleOutcomeBatchFreezeError("development producer catalogs differ")
    result: dict[str, tuple[str, dict[str, tuple[str, str]]]] = {}
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 3
            or any(not isinstance(field, str) for field in item)
        ):
            raise BattleOutcomeBatchFreezeError("development producer catalogs differ")
        source_commit = _commit(item[0], "development producer")
        if source_commit in result:
            raise BattleOutcomeBatchFreezeError("development producer catalog repeats")
        path = Path(item[1])
        expected_sha256 = _sha256(item[2], "development producer catalog")
        payload = _read_bounded_private_file(
            path,
            maximum_bytes=_MAXIMUM_CAPTURE_CATALOG_BYTES,
            subject="development producer catalog",
        )
        observed_sha256 = hashlib.sha256(payload).hexdigest()
        if observed_sha256 != expected_sha256:
            raise BattleOutcomeBatchFreezeError(
                "development producer catalog digest differs"
            )
        members = _historical_development_catalog_members(
            payload,
            source_commit=source_commit,
        )
        result[source_commit] = observed_sha256, members
    return result


def _historical_development_catalog_members(
    payload: bytes,
    *,
    source_commit: str,
) -> dict[str, tuple[str, str]]:
    try:
        document = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleOutcomeBatchFreezeError(
            "development producer catalog is invalid"
        ) from None
    allowed = {
        "pokemon-red-private-battle-learning-curve-catalog-v1",
        "pokemon-red-private-battle-learning-curve-catalog-v2",
    }
    if (
        not isinstance(document, dict)
        or document.get("schema") not in allowed
        or document.get("runner_source_commit") != source_commit
        or not isinstance(document.get("slots"), list)
    ):
        raise BattleOutcomeBatchFreezeError("development producer catalog differs")
    members: dict[str, tuple[str, str]] = {}
    for slot in document["slots"]:
        if not isinstance(slot, dict) or slot.get("partition") != "development":
            continue
        capture_id = slot.get("capture_id")
        source_state_sha256 = slot.get("source_state_sha256")
        root_lineage_id = slot.get("root_lineage_id")
        if (
            not isinstance(capture_id, str)
            or not isinstance(source_state_sha256, str)
            or _SHA256.fullmatch(source_state_sha256) is None
            or not isinstance(root_lineage_id, str)
            or capture_id in members
        ):
            raise BattleOutcomeBatchFreezeError("development producer catalog differs")
        members[capture_id] = source_state_sha256, root_lineage_id
    if not members or len({item[0] for item in members.values()}) != len(members):
        raise BattleOutcomeBatchFreezeError("development producer catalog differs")
    return members


def _development_capture_specs(
    value: object,
    *,
    catalogs: dict[str, tuple[str, dict[str, tuple[str, str]]]],
    catalog: GoalManagerContextCatalog,
    registry: GoalManagerCollectionRegistry,
) -> tuple[CatalogCaptureSpec, ...]:
    if not isinstance(value, list) or not value or len(value) > _MAXIMUM_CAPTURE_SPECS:
        raise BattleOutcomeBatchFreezeError("development capture inventory size differs")
    specs: list[CatalogCaptureSpec] = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 3
            or any(not isinstance(field, str) for field in item)
        ):
            raise BattleOutcomeBatchFreezeError("development capture inventory differs")
        source_commit = _commit(item[0], "development capture producer")
        producer = catalogs.get(source_commit)
        if producer is None:
            raise BattleOutcomeBatchFreezeError(
                "development capture has no producer catalog"
            )
        state_path = Path(item[1])
        manifest_path = Path(item[2])
        try:
            manifest_payload = _read_bounded_private_file(
                manifest_path,
                maximum_bytes=_MAXIMUM_CAPTURE_MANIFEST_BYTES,
                subject="development capture manifest",
            )
            manifest = parse_battle_scenario_capture_manifest(manifest_payload)
        except (OSError, RuntimeError, TypeError, ValueError):
            raise BattleOutcomeBatchFreezeError(
                "development capture manifest cannot be opened"
            ) from None
        source_state_sha256 = manifest.source_state_sha256
        expected = producer[1].get(manifest.capture_id)
        if (
            manifest.partition is not ScenarioPartition.DEVELOPMENT
            or manifest.source_commit != source_commit
            or not isinstance(source_state_sha256, str)
            or expected
            != (
                source_state_sha256,
                manifest.root_lineage_id,
            )
        ):
            raise BattleOutcomeBatchFreezeError(
                "development capture differs from its producer catalog"
            )
        try:
            source_binding = authenticate_battle_scenario_source_binding(
                source_state_sha256,
                expected_partition=ScenarioPartition.DEVELOPMENT,
                catalog=catalog,
                registry=registry,
            )
        except BattleOutcomeCaptureAuthenticationError:
            raise BattleOutcomeBatchFreezeError(
                "development capture is incompatible with the current source catalog"
            ) from None
        if source_binding.root_lineage_id != manifest.root_lineage_id:
            raise BattleOutcomeBatchFreezeError(
                "development capture is incompatible with the current source catalog"
            )
        specs.append(
            CatalogCaptureSpec(
                partition=ScenarioPartition.DEVELOPMENT,
                producer_source_commit=source_commit,
                producer_catalog_sha256=producer[0],
                state_path=state_path,
                manifest_path=manifest_path,
                capture_id=manifest.capture_id,
                source_state_sha256=source_state_sha256,
                root_lineage_id=manifest.root_lineage_id,
                state_sha256=manifest.state_sha256,
                manifest_sha256=hashlib.sha256(manifest_payload).hexdigest(),
            )
        )
    identities = (
        {(item.state_path, item.manifest_path) for item in specs},
        {item.capture_id for item in specs},
        {item.source_state_sha256 for item in specs},
        {item.state_sha256 for item in specs},
        {item.manifest_sha256 for item in specs},
    )
    if any(len(items) != len(specs) for items in identities):
        raise BattleOutcomeBatchFreezeError("development capture inventory repeats an input")
    return tuple(specs)


def _private_capture_directory(path: Path, *, rom_path: Path) -> Path:
    try:
        named = path.lstat()
        resolved = path.resolve(strict=True)
        opened = resolved.stat()
    except OSError:
        raise BattleOutcomeBatchFreezeError("train producer directory is unavailable") from None
    if (
        path.is_symlink()
        or not stat.S_ISDIR(named.st_mode)
        or named.st_dev != opened.st_dev
        or named.st_ino != opened.st_ino
        or opened.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) & 0o022
        or resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved == rom_path.resolve().parent
    ):
        raise BattleOutcomeBatchFreezeError("train producer directory is unavailable")
    return resolved


def _capture_specs(value: object, subject: str) -> tuple[tuple[Path, Path], ...]:
    if not isinstance(value, list) or not value or len(value) > _MAXIMUM_CAPTURE_SPECS:
        raise BattleOutcomeBatchFreezeError(
            f"{subject} capture inventory size differs"
        )
    specs: list[tuple[Path, Path]] = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or any(not isinstance(path, Path) for path in item)
        ):
            raise BattleOutcomeBatchFreezeError(
                f"{subject} capture inventory differs"
            )
        specs.append((item[0], item[1]))
    if len(set(specs)) != len(specs):
        raise BattleOutcomeBatchFreezeError(
            f"{subject} capture inventory repeats an input"
        )
    return tuple(specs)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate object key")
        value[key] = item
    return value


def _private_new_freeze(destination: Path, *, rom_path: Path) -> Path:
    resolved = destination.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise BattleOutcomeBatchFreezeError("batch freeze must remain private")
    if resolved.parent == rom_path.resolve().parent:
        raise BattleOutcomeBatchFreezeError(
            "batch freeze cannot be written beside the ROM"
        )
    if not resolved.parent.is_dir() or resolved.exists() or destination.is_symlink():
        raise BattleOutcomeBatchFreezeError(
            "batch freeze output is unavailable or already exists"
        )
    return resolved


def _write_exclusive(destination: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    directory_descriptor = -1
    created = False
    failed = False
    try:
        descriptor = os.open(destination, flags, 0o600)
        created = True
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        directory_flags |= getattr(os, "O_DIRECTORY", 0)
        directory_descriptor = os.open(destination.parent, directory_flags)
        os.fsync(directory_descriptor)
    except OSError:
        failed = True
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                failed = True
        if directory_descriptor >= 0:
            try:
                os.close(directory_descriptor)
            except OSError:
                failed = True
    if failed:
        if created:
            with suppress(OSError):
                destination.unlink()
        raise BattleOutcomeBatchFreezeError(
            "batch freeze could not be retained durably"
        )


def _read_bounded_private_file(
    path: Path,
    *,
    maximum_bytes: int,
    subject: str,
) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
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
            raise OSError("unsafe private input")
        chunks: list[bytes] = []
        remaining = opened.st_size + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(payload) != opened.st_size
            or after.st_dev != opened.st_dev
            or after.st_ino != opened.st_ino
            or after.st_size != opened.st_size
        ):
            raise OSError("private input changed while opening")
    except OSError:
        raise BattleOutcomeBatchFreezeError(f"{subject} is unavailable") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
    return payload


def _sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleOutcomeBatchFreezeError(f"{subject} digest is invalid")
    return value


def _commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise BattleOutcomeBatchFreezeError(f"{subject} commit is invalid")
    return value


def main() -> int:
    try:
        receipt = _run(_parser().parse_args())
    except (BattleOutcomeBatchFreezeError, OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f"battle batch freeze failed: {error}") from None
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
