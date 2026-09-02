#!/usr/bin/env python3
"""Qualify the fixed clustered Red battle curriculum without taking actions."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import freeze_battle_outcome_batch as batch_freezer  # noqa: E402

from pokemon_red_completion.battle_neural_model import (  # noqa: E402
    MaskedMLPMoveRanker,
)
from pokemon_red_completion.battle_outcome_batch import (  # noqa: E402
    BattleOutcomeBatchError,
    BattleOutcomePressureCandidate,
    RetainedBattleOutcomePrefix,
    battle_outcome_model_sha256,
    build_battle_outcome_pressure_candidate,
    parse_retained_battle_outcome_prefix,
)
from pokemon_red_completion.battle_outcome_clustered_curriculum import (  # noqa: E402
    BattleOutcomeClusteredCurriculum,
    BattleOutcomeClusteredCurriculumError,
    build_battle_outcome_clustered_curriculum,
    parse_battle_outcome_clustered_curriculum,
)
from pokemon_red_completion.battle_scenario_capture_catalog import (  # noqa: E402
    BattleScenarioCaptureCatalogError,
    BattleScenarioRetainedTrainCaptureCatalog,
    parse_battle_scenario_retained_train_capture_catalog,
)
from pokemon_red_completion.claim_first_admission import (  # noqa: E402
    ClaimFirstAdmissionError,
    ClaimFirstAvailabilitySnapshot,
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
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
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
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.runtime_identity import (  # noqa: E402
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402

_MAXIMUM_CONTEXT_CATALOG_BYTES = 4 * 1024 * 1024
_MAXIMUM_CAPTURE_CATALOG_BYTES = 4 * 1024 * 1024
_MAXIMUM_RETAINED_PREFIX_BYTES = 512 * 1024
_MAXIMUM_CURRICULUM_BYTES = 32 * 1024 * 1024

PreparedBinding = batch_freezer.PreparedBinding
CatalogCaptureSpec = batch_freezer.CatalogCaptureSpec


class BattleOutcomeClusteredQualificationError(RuntimeError):
    """Raised before an outcome-blind clustered curriculum can be retained."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curriculum-id", required=True)
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
    parser.add_argument("--train-producer-directory", type=Path, required=True)
    parser.add_argument("--development-capture-catalog", type=Path, required=True)
    parser.add_argument(
        "--expected-development-capture-catalog-sha256", required=True
    )
    parser.add_argument(
        "--development-producer-directory",
        action="append",
        type=Path,
        required=True,
    )
    parser.add_argument("--out-curriculum", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    source_commit = batch_freezer._commit(args.expected_source_commit, "source")
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if source.git_commit != source_commit or source_bundle != batch_freezer._sha256(
        args.expected_source_bundle_sha256,
        "source bundle",
    ):
        raise BattleOutcomeClusteredQualificationError(
            "published qualification source identity differs"
        )

    runtime = build_runtime_identity()
    require_pyboy_import_origins(runtime)
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    base_model = load_battle_model_artifact(args.base_model)
    if not isinstance(base_model, MaskedMLPMoveRanker):
        raise BattleOutcomeClusteredQualificationError(
            "clustered curriculum requires the nonlinear prior"
        )
    base_model_sha256 = battle_outcome_model_sha256(base_model)
    if base_model_sha256 != batch_freezer._sha256(
        args.expected_base_model_sha256,
        "base model",
    ):
        raise BattleOutcomeClusteredQualificationError("base model differs")

    registry_commit = batch_freezer._commit(
        args.registry_source_commit,
        "registry source",
    )
    registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        registry_commit,
    )
    if registry.registry_sha256 != batch_freezer._sha256(
        args.expected_registry_sha256,
        "registry",
    ):
        raise BattleOutcomeClusteredQualificationError("historical registry differs")
    context_payload = batch_freezer._read_bounded_private_file(
        args.context_catalog,
        maximum_bytes=_MAXIMUM_CONTEXT_CATALOG_BYTES,
        subject="context catalog",
    )
    context_catalog_sha256 = hashlib.sha256(context_payload).hexdigest()
    if context_catalog_sha256 != batch_freezer._sha256(
        args.expected_context_catalog_sha256,
        "context catalog",
    ):
        raise BattleOutcomeClusteredQualificationError("context catalog digest differs")
    context_catalog = parse_goal_manager_context_catalog(context_payload, registry)

    retained_payload = batch_freezer._read_bounded_private_file(
        args.retained_prefix,
        maximum_bytes=_MAXIMUM_RETAINED_PREFIX_BYTES,
        subject="retained prefix",
    )
    if hashlib.sha256(retained_payload).hexdigest() != batch_freezer._sha256(
        args.expected_retained_prefix_sha256,
        "retained prefix",
    ):
        raise BattleOutcomeClusteredQualificationError("retained prefix digest differs")
    try:
        retained_prefix = parse_retained_battle_outcome_prefix(retained_payload)
    except BattleOutcomeBatchError as error:
        raise BattleOutcomeClusteredQualificationError(str(error)) from None
    batch_freezer._require_retained_runtime_compatibility(retained_prefix, runtime)
    if retained_prefix.original_prior_sha256 != base_model_sha256:
        raise BattleOutcomeClusteredQualificationError(
            "retained prefix differs from the original prior"
        )

    train_payload = batch_freezer._read_bounded_private_file(
        args.train_capture_catalog,
        maximum_bytes=_MAXIMUM_CAPTURE_CATALOG_BYTES,
        subject="retained train capture catalog",
    )
    train_catalog_sha256 = hashlib.sha256(train_payload).hexdigest()
    if train_catalog_sha256 != batch_freezer._sha256(
        args.expected_train_capture_catalog_sha256,
        "retained train capture catalog",
    ):
        raise BattleOutcomeClusteredQualificationError(
            "retained train capture catalog digest differs"
        )
    try:
        train_catalog = parse_battle_scenario_retained_train_capture_catalog(
            train_payload
        )
    except BattleScenarioCaptureCatalogError as error:
        raise BattleOutcomeClusteredQualificationError(str(error)) from None
    if train_catalog.rom_sha256 != rom.sha256:
        raise BattleOutcomeClusteredQualificationError(
            "retained train capture catalog ROM differs"
        )
    train_specs = _retained_train_catalog_specs(
        train_catalog,
        args.train_producer_directory,
        catalog_sha256=train_catalog_sha256,
        rom_path=rom_path,
    )

    development_specs = batch_freezer._typed_development_catalog_specs(
        args.development_capture_catalog,
        expected_catalog_sha256=args.expected_development_capture_catalog_sha256,
        producer_directory=args.development_producer_directory,
        rom_sha256=rom.sha256,
        context_catalog_sha256=context_catalog_sha256,
        registry_sha256=registry.registry_sha256,
        registry_source_commit=registry_commit,
        rom_path=rom_path,
    )
    development_catalog_sha256 = batch_freezer._sha256(
        args.expected_development_capture_catalog_sha256,
        "development capture catalog",
    )

    def session_factory():  # type: ignore[no-untyped-def]
        return PyBoyAdapter(rom_path)

    prefix = batch_freezer._open_prepared_binding(
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
        raise BattleOutcomeClusteredQualificationError(
            "retained train capture differs from the verified prefix"
        )
    fresh_train = tuple(
        batch_freezer._open_prepared_binding(
            spec,
            base_model=base_model,
            catalog=context_catalog,
            registry=registry,
            session_factory=session_factory,
        )
        for spec in train_specs
    )
    development = tuple(
        batch_freezer._open_prepared_binding(
            spec,
            base_model=base_model,
            catalog=context_catalog,
            registry=registry,
            session_factory=session_factory,
        )
        for spec in development_specs
    )

    destination = batch_freezer._private_new_freeze(
        args.out_curriculum,
        rom_path=rom_path,
    )
    curriculum = _qualify_under_shared_lease(
        curriculum_id=args.curriculum_id,
        retained_prefix=retained_prefix,
        base_model=base_model,
        prefix=prefix,
        fresh_train=fresh_train,
        development=development,
        registry_path=open_fixed_account_claim_registry(),
        train_catalog_sha256=train_catalog_sha256,
        development_catalog_sha256=development_catalog_sha256,
        destination=destination,
    )
    reopened_payload = batch_freezer._read_bounded_private_file(
        destination,
        maximum_bytes=_MAXIMUM_CURRICULUM_BYTES,
        subject="clustered curriculum",
    )
    try:
        reopened = parse_battle_outcome_clustered_curriculum(reopened_payload)
    except BattleOutcomeClusteredCurriculumError as error:
        raise BattleOutcomeClusteredQualificationError(str(error)) from None
    if reopened != curriculum:
        raise BattleOutcomeClusteredQualificationError(
            "clustered curriculum differs after independent reopen"
        )
    summary = curriculum.public_dict()["information_summary"]
    if not isinstance(summary, Mapping):
        raise BattleOutcomeClusteredQualificationError(
            "clustered curriculum information summary differs"
        )
    return {
        "schema": "pokemon-red-battle-outcome-clustered-qualification-receipt-v1",
        "status": "qualified_action_free",
        "curriculum_id": curriculum.curriculum_id,
        "curriculum_sha256": curriculum.curriculum_sha256,
        "source_commit": source_commit,
        "source_bundle_sha256": source_bundle,
        "runtime_identity_sha256": runtime.sha256,
        "rom_sha256": rom.sha256,
        "base_model_sha256": base_model_sha256,
        "train_catalog_sha256": train_catalog_sha256,
        "development_catalog_sha256": development_catalog_sha256,
        "train_contexts": summary["train_contexts"],
        "fresh_train_contexts": summary["fresh_train_contexts"],
        "development_contexts": summary["development_contexts"],
        "fresh_train_measured_action_arms": summary[
            "fresh_train_measured_action_arms"
        ],
        "development_measured_action_arms": summary[
            "development_measured_action_arms"
        ],
        "train_hidden_contrast_rank": summary["train_hidden_contrast_rank"],
        "development_hidden_contrast_rank": summary[
            "development_hidden_contrast_rank"
        ],
        "read_only_runtime_preparations": 14,
        "prior_score_vector_evaluations": 14,
        "hidden_representation_evaluations": 14,
        "controller_actions": 0,
        "emulator_frames": 0,
        "root_claims_created": 0,
        "outcomes_opened": 0,
        "predictions_computed": 0,
        "model_fits": 0,
        "teacher_queries": 0,
        "sealed_red_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "full_game_replays": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }


def _retained_train_catalog_specs(
    catalog: BattleScenarioRetainedTrainCaptureCatalog,
    directory: Path,
    *,
    catalog_sha256: str,
    rom_path: Path,
) -> tuple[CatalogCaptureSpec, ...]:
    resolved = batch_freezer._private_capture_directory(
        directory,
        rom_path=rom_path,
        subject="retained train producer directory",
    )
    producer = catalog.producer
    observed_directory_sha256 = hashlib.sha256(
        str(resolved).encode("utf-8")
    ).hexdigest()
    if producer.capture_directory_sha256 != observed_directory_sha256:
        raise BattleOutcomeClusteredQualificationError(
            "retained train producer directory differs"
        )
    return tuple(
        batch_freezer._catalog_entry_spec(
            entry,
            producer_source_commit=producer.source_commit,
            producer_catalog_sha256=catalog_sha256,
            directory=resolved,
        )
        for entry in catalog.captures
    )


def _pressure_candidates(
    prepared: Sequence[PreparedBinding],
    *,
    base_model: MaskedMLPMoveRanker,
    retained_prefix: RetainedBattleOutcomePrefix,
    snapshot: ClaimFirstAvailabilitySnapshot,
) -> tuple[BattleOutcomePressureCandidate, ...]:
    return tuple(
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
        for binding, features in prepared
    )


def _qualify_under_shared_lease(
    *,
    curriculum_id: str,
    retained_prefix: RetainedBattleOutcomePrefix,
    base_model: MaskedMLPMoveRanker,
    prefix: PreparedBinding,
    fresh_train: Sequence[PreparedBinding],
    development: Sequence[PreparedBinding],
    registry_path: Path,
    train_catalog_sha256: str,
    development_catalog_sha256: str,
    destination: Path,
) -> BattleOutcomeClusteredCurriculum:
    prepared = (prefix, *fresh_train, *development)
    bindings = tuple(item[0] for item in prepared)
    root_pairs = (
        (
            retained_prefix.forbidden_development.logical_root_sha256,
            retained_prefix.forbidden_development.physical_root_sha256,
        ),
        *((item.logical_root_sha256, item.physical_root_sha256) for item in bindings),
    )
    try:
        with claim_first_availability_snapshot_lease(registry_path) as lease:
            snapshot = lease.observe(root_pairs)
            candidates = _pressure_candidates(
                prepared,
                base_model=base_model,
                retained_prefix=retained_prefix,
                snapshot=snapshot,
            )
            curriculum = build_battle_outcome_clustered_curriculum(
                curriculum_id=curriculum_id,
                retained_prefix=retained_prefix,
                prefix=candidates[0],
                fresh_train=candidates[1:6],
                development=candidates[6:],
                claim_registry_sha256=snapshot.registry_state_sha256,
                train_catalog_sha256=train_catalog_sha256,
                development_catalog_sha256=development_catalog_sha256,
            )
            payload = curriculum.canonical_bytes()
            if parse_battle_outcome_clustered_curriculum(payload) != curriculum:
                raise BattleOutcomeClusteredQualificationError(
                    "clustered curriculum failed its canonical self-check"
                )
            batch_freezer._write_exclusive(destination, payload)
    except (
        BattleOutcomeBatchError,
        BattleOutcomeClusteredCurriculumError,
        ClaimFirstAdmissionError,
    ) as error:
        raise BattleOutcomeClusteredQualificationError(str(error)) from None
    return curriculum


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = _run(args)
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema": (
                        "pokemon-red-battle-outcome-clustered-qualification-failure-v1"
                    ),
                    "status": "failed_closed",
                    "reason_code": "clustered_curriculum_qualification_failed",
                    "failure_type": type(error).__name__,
                    "controller_actions": 0,
                    "emulator_frames": 0,
                    "root_claims_created": 0,
                    "outcomes_opened": 0,
                    "predictions_computed": 0,
                    "model_fits": 0,
                    "teacher_queries": 0,
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
