#!/usr/bin/env python3
"""Execute one frozen Red battle batch, fit on train, and evaluate on development."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker  # noqa: E402
from pokemon_red_completion.battle_outcome_batch import (  # noqa: E402
    BattleOutcomeBatchError,
    BattleOutcomePressureCandidate,
    battle_outcome_fixed_heuristic_choice,
    battle_outcome_model_sha256,
    parse_battle_outcome_batch_freeze,
    reconstruct_retained_battle_outcome_example,
    revalidate_battle_outcome_pressure_candidate,
)
from pokemon_red_completion.battle_outcome_experiment import (  # noqa: E402
    BattleOutcomeCaptureBinding,
    battle_outcome_controller_timing_sha256,
)
from pokemon_red_completion.battle_outcome_learning import (  # noqa: E402
    BattleOutcomeExample,
    adapt_mlp_last_layer_from_outcomes,
    compare_battle_outcome_preferences,
    evaluate_battle_outcome_preferences,
)
from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    BattleScenarioCapture,
    open_battle_scenario_capture,
)
from pokemon_red_completion.claim_first_admission import (  # noqa: E402
    ClaimFirstRootPair,
    claim_first_availability_snapshot_lease,
    claim_first_pair_registry,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.goal_manager_composition_qualification import (  # noqa: E402
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.goal_manager_development import (  # noqa: E402
    goal_manager_development_numpy_runtime_sha256,
)
from pokemon_red_completion.learned_battle_policy import (  # noqa: E402
    load_battle_model_artifact,
)
from pokemon_red_completion.private_artifacts import open_private_root  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_battle_outcome_runtime import (  # noqa: E402
    RedBattleOutcomeCollection,
    collect_red_battle_outcome_example,
    prepare_red_battle_outcome_capture,
)
from pokemon_red_completion.red_battle_scenario import (  # noqa: E402
    PreparedRedBattleScenario,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.runtime_identity import (  # noqa: E402
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402

RUNNER_PATH = PROJECT_ROOT / "scripts" / "run_battle_outcome_batch.py"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAXIMUM_FREEZE_BYTES = 32 * 1024 * 1024
_MAXIMUM_RECORD_BYTES = 2 * 1024 * 1024


class BattleOutcomeBatchRunError(RuntimeError):
    """Raised when a frozen batch cannot execute once without substitution."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--expected-freeze-sha256", required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--expected-base-model-sha256", required=True)
    parser.add_argument("--retained-train-record", type=Path, required=True)
    parser.add_argument("--expected-retained-train-record-sha256", required=True)
    parser.add_argument("--retained-train-capture", type=Path, nargs=2, required=True)
    parser.add_argument(
        "--train-capture",
        type=Path,
        nargs=2,
        action="append",
        required=True,
    )
    parser.add_argument(
        "--development-capture",
        type=Path,
        nargs=2,
        action="append",
        required=True,
    )
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:
        raise BattleOutcomeBatchRunError("published source lacks a commit")
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)

    freeze_payload = _read_private_file(
        args.freeze,
        maximum_bytes=_MAXIMUM_FREEZE_BYTES,
        subject="batch freeze",
    )
    freeze_sha256 = hashlib.sha256(freeze_payload).hexdigest()
    if freeze_sha256 != _sha256(args.expected_freeze_sha256, "batch freeze"):
        raise BattleOutcomeBatchRunError("batch freeze digest differs")
    try:
        freeze = parse_battle_outcome_batch_freeze(freeze_payload)
    except BattleOutcomeBatchError as error:
        raise BattleOutcomeBatchRunError(str(error)) from None
    if (
        freeze.consumer_source_commit != source.git_commit
        or freeze.consumer_source_bundle_sha256 != source_bundle
    ):
        raise BattleOutcomeBatchRunError("batch execution source differs from its freeze")

    base_model = load_battle_model_artifact(args.base_model)
    if not isinstance(base_model, MaskedMLPMoveRanker):
        raise BattleOutcomeBatchRunError("batch requires the nonlinear prior")
    base_model_sha256 = battle_outcome_model_sha256(base_model)
    if (
        base_model_sha256 != _sha256(args.expected_base_model_sha256, "base model")
        or base_model_sha256 != freeze.roster.original_prior_sha256
    ):
        raise BattleOutcomeBatchRunError("base model differs from the frozen batch")

    retained_payload = _read_private_file(
        args.retained_train_record,
        maximum_bytes=_MAXIMUM_RECORD_BYTES,
        subject="retained train record",
    )
    retained_record_sha256 = canonical_sha256(
        _parse_canonical_mapping(retained_payload, "retained train record")
    )
    if (
        retained_record_sha256
        != _sha256(
            args.expected_retained_train_record_sha256,
            "retained train record",
        )
        or retained_record_sha256 != freeze.roster.retained_prefix.train_record_sha256
    ):
        raise BattleOutcomeBatchRunError("retained train record digest differs")
    retained_record = _parse_canonical_mapping(retained_payload, "retained train record")

    runtime = build_runtime_identity()
    require_pyboy_import_origins(runtime)
    retained_plan = freeze.roster.retained_prefix.plan
    if (
        runtime.sha256 != retained_plan.runtime_identity_sha256
        or goal_manager_development_numpy_runtime_sha256() != retained_plan.numpy_runtime_sha256
        or battle_outcome_controller_timing_sha256() != retained_plan.controller_timing_sha256
    ):
        raise BattleOutcomeBatchRunError("batch runtime differs from the frozen prior")
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    if rom.sha256 != retained_plan.rom_sha256:
        raise BattleOutcomeBatchRunError("ROM differs from the frozen batch")

    retained_capture = open_battle_scenario_capture(*args.retained_train_capture)
    train_captures = _ordered_captures(
        args.train_capture,
        expected=freeze.roster.fresh_train,
        partition=ScenarioPartition.TRAIN,
    )
    development_captures = _ordered_captures(
        args.development_capture,
        expected=freeze.roster.development,
        partition=ScenarioPartition.DEVELOPMENT,
    )
    _require_capture_binding(retained_capture, freeze.roster.retained_prefix.train)

    def session_factory():  # type: ignore[no-untyped-def]
        return PyBoyAdapter(rom_path)

    retained_prepared = prepare_red_battle_outcome_capture(
        retained_capture,
        session_factory=session_factory,
    )
    revalidate_battle_outcome_pressure_candidate(
        freeze.roster.prefix,
        retained_prepared.features,
        base_model,
        claim_available=False,
    )
    retained_example = reconstruct_retained_battle_outcome_example(
        freeze.roster.retained_prefix,
        retained_record,
        features=retained_prepared.features,
        model=base_model,
    )
    train_prepared = tuple(
        _prepare_candidate(candidate, capture, base_model, session_factory)
        for candidate, capture in zip(
            freeze.roster.fresh_train,
            train_captures,
            strict=True,
        )
    )
    development_prepared = tuple(
        _prepare_candidate(candidate, capture, base_model, session_factory)
        for candidate, capture in zip(
            freeze.roster.development,
            development_captures,
            strict=True,
        )
    )

    claim_registry = open_fixed_account_claim_registry()
    selected = (*freeze.roster.fresh_train, *freeze.roster.development)
    with claim_first_availability_snapshot_lease(claim_registry) as lease:
        snapshot = lease.observe(
            tuple(
                (item.binding.logical_root_sha256, item.binding.physical_root_sha256)
                for item in selected
            )
        )
        if any(
            not snapshot.availability_for(
                item.binding.logical_root_sha256,
                item.binding.physical_root_sha256,
            )
            for item in selected
        ):
            raise BattleOutcomeBatchRunError("a frozen batch root is no longer available")

    execution_sha256 = canonical_sha256(
        {
            "base_model_sha256": base_model_sha256,
            "freeze_sha256": freeze_sha256,
            "rom_sha256": rom.sha256,
            "runtime_identity_sha256": runtime.sha256,
            "schema": "pokemon.red.battle-outcome-batch-execution.v1",
            "source_bundle_sha256": source_bundle,
        }
    )
    runner_sha256 = hashlib.sha256(RUNNER_PATH.read_bytes()).hexdigest()
    root_pairs = tuple(
        _root_pair(
            item.binding,
            freeze_sha256=freeze_sha256,
            execution_sha256=execution_sha256,
            runner_sha256=runner_sha256,
            source_commit=source.git_commit,
        )
        for item in selected
    )

    private_root = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    artifact_id = f"red-battle-outcome-batch-{freeze_sha256}"
    writer = private_root.begin_artifact(artifact_id, kind="battle_outcome_batch")
    train_collections: list[RedBattleOutcomeCollection] = []
    development_collections: list[RedBattleOutcomeCollection] = []
    with writer:
        writer.append(
            "assignment",
            {
                "record_type": "battle_outcome_batch_assignment",
                "freeze_sha256": freeze_sha256,
                "roster_sha256": freeze.roster.roster_sha256,
                "source": source.public_dict(),
                "execution_sha256": execution_sha256,
                "authority": "shadow_only",
            },
            durable=True,
        )
        with claim_first_pair_registry(claim_registry) as registry:
            claims = tuple(registry.claim(pair) for pair in root_pairs)
        for claim, candidate in zip(claims, selected, strict=True):
            writer.append(
                "root_claims",
                {
                    "record_type": "battle_outcome_batch_root_claim",
                    "freeze_sha256": freeze_sha256,
                    "capture_id": candidate.capture_id,
                    "partition": candidate.partition.value,
                    "claim_sha256": claim.claim_sha256,
                    **claim.private_dict(),
                },
                durable=True,
            )

        for ordinal, (candidate, capture, prepared, claim) in enumerate(
            zip(
                freeze.roster.fresh_train,
                train_captures,
                train_prepared,
                claims[: len(train_captures)],
                strict=True,
            )
        ):
            collection = _collect_claimed_capture(
                writer,
                freeze_sha256=freeze_sha256,
                ordinal=ordinal,
                candidate=candidate,
                capture=capture,
                prepared=prepared,
                root_pair=claim,
                session_factory=session_factory,
            )
            train_collections.append(collection)

        training_examples = (
            retained_example,
            *(item.example for item in train_collections),
        )
        update = adapt_mlp_last_layer_from_outcomes(
            base_model,
            training_examples,
            epochs=retained_plan.epochs,
            learning_rate=retained_plan.learning_rate,
            prior_l2=retained_plan.prior_l2,
        )
        updated_model = update.model
        updated_model_sha256 = battle_outcome_model_sha256(updated_model)
        writer.append(
            "model",
            {
                "record_type": "battle_outcome_batch_candidate_model",
                "freeze_sha256": freeze_sha256,
                "model": updated_model.to_dict(),
                "model_sha256": updated_model_sha256,
                "update_report": update.report.public_dict(),
                "development_influenced_fit": False,
                "authority": "shadow_only",
            },
            durable=True,
        )

        commitments = tuple(
            _prediction_commitment(
                freeze_sha256=freeze_sha256,
                candidate=candidate,
                prepared=prepared,
                base_model=base_model,
                updated_model=updated_model,
            )
            for candidate, prepared in zip(
                freeze.roster.development,
                development_prepared,
                strict=True,
            )
        )
        for commitment in commitments:
            writer.append("prediction_commitments", commitment, durable=True)

        development_claims = claims[len(train_captures) :]
        for ordinal, (candidate, capture, prepared, claim) in enumerate(
            zip(
                freeze.roster.development,
                development_captures,
                development_prepared,
                development_claims,
                strict=True,
            )
        ):
            collection = _collect_claimed_capture(
                writer,
                freeze_sha256=freeze_sha256,
                ordinal=ordinal,
                candidate=candidate,
                capture=capture,
                prepared=prepared,
                root_pair=claim,
                session_factory=session_factory,
            )
            development_collections.append(collection)

        development_examples = tuple(item.example for item in development_collections)
        base_evaluation = evaluate_battle_outcome_preferences(
            base_model,
            development_examples,
        )
        updated_evaluation = evaluate_battle_outcome_preferences(
            updated_model,
            development_examples,
        )
        paired = compare_battle_outcome_preferences(
            base_model,
            updated_model,
            development_examples,
        )
        heuristic = _heuristic_evaluation(
            development_examples,
            development_prepared,
        )
        terminal = {
            "record_type": "battle_outcome_batch_terminal",
            "status": "descriptive_batch_complete",
            "freeze_sha256": freeze_sha256,
            "base_model_sha256": base_model_sha256,
            "updated_model_sha256": updated_model_sha256,
            "training_examples": len(training_examples),
            "fresh_train_examples": len(train_collections),
            "development_examples": len(development_collections),
            "base_development": base_evaluation.public_dict(),
            "updated_development": updated_evaluation.public_dict(),
            "paired_development": paired.public_dict(),
            "fixed_heuristic_development": heuristic,
            "claim": "bounded_descriptive_batch_only",
            "development_influenced_fit": False,
            "promotion_gate_passed": False,
            "authority_promoted": False,
            "red_sealed_test_cases_opened": 0,
            "crystal_contexts_opened": 0,
            "teacher_queries": 0,
            "teacher_choice_targets": 0,
            "full_game_replays": 0,
            "private_path_fields": 0,
        }
        writer.append("terminal", terminal, durable=True)

    public_terminal = dict(terminal)
    del public_terminal["record_type"]
    return {
        "schema": "pokemon-red-battle-outcome-batch-run-receipt-v1",
        "artifact": writer.summary.public_dict(),
        **public_terminal,
    }


def _ordered_captures(
    pairs: object,
    *,
    expected: Sequence[BattleOutcomePressureCandidate],
    partition: ScenarioPartition,
) -> tuple[BattleScenarioCapture, ...]:
    if not isinstance(pairs, list) or len(pairs) != len(expected):
        raise BattleOutcomeBatchRunError(
            f"batch requires exactly {len(expected)} {partition.value} captures"
        )
    opened = tuple(
        open_battle_scenario_capture(*pair)
        for pair in pairs
        if isinstance(pair, list) and len(pair) == 2
    )
    if len(opened) != len(expected):
        raise BattleOutcomeBatchRunError("batch capture arguments are malformed")
    by_id = {item.manifest.capture_id: item for item in opened}
    if len(by_id) != len(opened) or set(by_id) != {item.capture_id for item in expected}:
        raise BattleOutcomeBatchRunError("batch capture inventory differs from its roster")
    ordered = tuple(by_id[item.capture_id] for item in expected)
    for capture, candidate in zip(ordered, expected, strict=True):
        _require_capture_binding(capture, candidate.binding)
    return ordered


def _require_capture_binding(
    capture: BattleScenarioCapture,
    binding: BattleOutcomeCaptureBinding,
) -> None:
    manifest = capture.manifest
    if (
        manifest.partition is not binding.partition
        or manifest.capture_id != binding.capture_id
        or capture.manifest_sha256 != binding.manifest_sha256
        or manifest.state_sha256 != binding.state_sha256
        or manifest.initial_observation_sha256 != binding.initial_observation_sha256
        or manifest.source_commit != binding.source_commit
        or manifest.source_state_sha256 != binding.source_state_sha256
        or manifest.root_lineage_id != binding.root_lineage_id
        or manifest.expected_map != binding.expected_map
        or manifest.expected_battle_state != binding.expected_battle_state
    ):
        raise BattleOutcomeBatchRunError("battle capture differs from the frozen roster")


def _prepare_candidate(
    candidate: BattleOutcomePressureCandidate,
    capture: BattleScenarioCapture,
    base_model: MaskedMLPMoveRanker,
    session_factory: Callable[..., object],
) -> PreparedRedBattleScenario:
    prepared = prepare_red_battle_outcome_capture(
        capture,
        session_factory=session_factory,  # type: ignore[arg-type]
    )
    try:
        revalidate_battle_outcome_pressure_candidate(
            candidate,
            prepared.features,
            base_model,
            claim_available=True,
        )
    except BattleOutcomeBatchError as error:
        raise BattleOutcomeBatchRunError(str(error)) from None
    return prepared


def _root_pair(
    binding: BattleOutcomeCaptureBinding,
    *,
    freeze_sha256: str,
    execution_sha256: str,
    runner_sha256: str,
    source_commit: str,
) -> ClaimFirstRootPair:
    return ClaimFirstRootPair(
        logical_root_sha256=binding.logical_root_sha256,
        physical_root_sha256=binding.physical_root_sha256,
        stage=f"battle-batch-{binding.partition.value}",
        execution_identity_sha256=execution_sha256,
        plan_sha256=freeze_sha256,
        slot_sha256=binding.manifest_sha256,
        runner_sha256=runner_sha256,
        source_commit=source_commit,
    )


def _collect_claimed_capture(
    writer,  # type: ignore[no-untyped-def]
    *,
    freeze_sha256: str,
    ordinal: int,
    candidate: BattleOutcomePressureCandidate,
    capture: BattleScenarioCapture,
    prepared: PreparedRedBattleScenario,
    root_pair: ClaimFirstRootPair,
    session_factory,  # type: ignore[no-untyped-def]
) -> RedBattleOutcomeCollection:
    claimed: set[int] = set()
    retained: set[int] = set()
    expected = set(candidate.supported_candidate_indices)

    def claim(index: int) -> None:
        if index not in expected or index in claimed:
            raise BattleOutcomeBatchRunError("candidate claim is duplicated or invalid")
        writer.append(
            "candidate_claims",
            {
                "record_type": "battle_outcome_batch_candidate_claim",
                "freeze_sha256": freeze_sha256,
                "root_pair_claim_sha256": root_pair.claim_sha256,
                "partition": candidate.partition.value,
                "ordinal": ordinal,
                "capture_id": candidate.capture_id,
                "candidate_index": index,
                "input_status_at_claim": "not_yet_sent",
            },
            durable=True,
        )
        claimed.add(index)

    def retain(index, outcome):  # type: ignore[no-untyped-def]
        if index not in claimed or index in retained:
            raise BattleOutcomeBatchRunError("candidate outcome lacks one durable claim")
        writer.append(
            "candidate_outcomes",
            {
                "record_type": "battle_outcome_batch_candidate_outcome",
                "freeze_sha256": freeze_sha256,
                "root_pair_claim_sha256": root_pair.claim_sha256,
                "partition": candidate.partition.value,
                "ordinal": ordinal,
                "capture_id": candidate.capture_id,
                "candidate_index": index,
                "outcome": outcome.public_dict(),
                "teacher_queries": 0,
                "teacher_choice_targets": 0,
            },
            durable=True,
        )
        retained.add(index)

    collection = collect_red_battle_outcome_example(
        capture,
        session_factory=session_factory,
        candidate_claim_sink=claim,
        outcome_sink=retain,
    )
    measured = {index for index, outcome in enumerate(collection.outcomes) if outcome is not None}
    if (
        collection.initial_observation_sha256 != prepared.initial_observation_sha256
        or collection.example.features != prepared.features
        or measured != expected
        or claimed != expected
        or retained != expected
    ):
        raise BattleOutcomeBatchRunError("batch collection differs from its frozen menu")
    writer.append(
        "outcomes",
        {
            "record_type": "battle_outcome_batch_collection",
            "freeze_sha256": freeze_sha256,
            "partition": candidate.partition.value,
            "ordinal": ordinal,
            "collection": collection.public_dict(),
        },
        durable=True,
    )
    return collection


def _prediction_commitment(
    *,
    freeze_sha256: str,
    candidate: BattleOutcomePressureCandidate,
    prepared: PreparedRedBattleScenario,
    base_model: MaskedMLPMoveRanker,
    updated_model: MaskedMLPMoveRanker,
) -> dict[str, object]:
    features = prepared.features
    return {
        "record_type": "battle_outcome_batch_development_commitment",
        "freeze_sha256": freeze_sha256,
        "capture_id": candidate.capture_id,
        "initial_observation_sha256": prepared.initial_observation_sha256,
        "base_model_sha256": battle_outcome_model_sha256(base_model),
        "base_candidate_index": base_model.predict(
            features.candidate_vectors,
            legal_mask=features.legal_mask,
            current_pp=features.current_pp,
        ),
        "updated_model_sha256": battle_outcome_model_sha256(updated_model),
        "updated_candidate_index": updated_model.predict(
            features.candidate_vectors,
            legal_mask=features.legal_mask,
            current_pp=features.current_pp,
        ),
        "fixed_heuristic_candidate_index": battle_outcome_fixed_heuristic_choice(features),
        "development_outcomes_opened": 0,
    }


def _heuristic_evaluation(
    examples: Sequence[BattleOutcomeExample],
    prepared: Sequence[PreparedRedBattleScenario],
) -> dict[str, object]:
    choices = tuple(battle_outcome_fixed_heuristic_choice(item.features) for item in prepared)
    selected = tuple(
        example.outcomes[index] for example, index in zip(examples, choices, strict=True)
    )
    if any(item is None for item in selected):
        raise BattleOutcomeBatchRunError("fixed heuristic selected an unmeasured action")
    return {
        "schema": "pokemon-red-battle-outcome-fixed-heuristic-evaluation-v1",
        "example_count": len(examples),
        "correct_preferences": sum(
            choice in example.best_candidate_indices
            for choice, example in zip(choices, examples, strict=True)
        ),
        "mean_selected_utility": sum(item.utility for item in selected if item is not None)
        / len(selected),
        "candidate_indices": list(choices),
    }


def _read_private_file(path: Path, *, maximum_bytes: int, subject: str) -> bytes:
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
            raise OSError("unsafe private input")
        payload = os.read(descriptor, opened.st_size + 1)
        if len(payload) != opened.st_size:
            raise OSError("private input changed")
        return payload
    except OSError:
        raise BattleOutcomeBatchRunError(f"{subject} cannot be authenticated") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _parse_canonical_mapping(payload: bytes, subject: str) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleOutcomeBatchRunError(f"{subject} is not canonical JSON") from None
    if not isinstance(value, dict) or _canonical(value) != payload:
        raise BattleOutcomeBatchRunError(f"{subject} is not canonical JSON")
    return value


def _sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleOutcomeBatchRunError(f"{subject} digest is invalid")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = _run(args)
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema": "pokemon-red-battle-outcome-batch-run-failure-v1",
                    "status": "failed_closed",
                    "failure_type": type(error).__name__,
                    "retry_permitted": False,
                    "authority_promoted": False,
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
