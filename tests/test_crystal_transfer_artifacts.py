from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_crystal_completion.transfer_artifacts import (
    CrystalExecutionStatus,
    CrystalPredictorExecution,
    CrystalTransferArtifactError,
    CrystalTransferCaseOutcome,
    CrystalTransferContext,
    CrystalTransferPrediction,
    build_crystal_prediction_commitment_payload,
    build_crystal_transfer_catalog_payload,
    build_crystal_transfer_outcome_set_payload,
    evaluate_crystal_sealed_transfer,
    parse_crystal_prediction_commitment,
    parse_crystal_transfer_catalog,
    parse_crystal_transfer_outcome_set,
    validate_crystal_transfer_catalog_set,
)
from pokemon_crystal_completion.transfer_protocol import (
    CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS,
    CRYSTAL_BASELINE_PREDICTOR_SHA256,
    CRYSTAL_RED_FROZEN_MODEL_SHA256,
    CRYSTAL_SEALED_PREDICTOR_IDS,
    CRYSTAL_ZERO_SHOT_PREDICTOR_IDS,
    CrystalTransferPlan,
    CrystalTransferSlot,
    parse_crystal_transfer_plan,
)
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT_ROOT / "configs" / "crystal-goal-manager-transfer-v1.json"
ROM_SHA256 = "c" * 64
SOURCE_COMMIT = "a" * 40
SOURCE_BUNDLE = "b" * 64


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _plan() -> CrystalTransferPlan:
    return parse_crystal_transfer_plan(PLAN_PATH.read_bytes())


def _available_kinds(slot: CrystalTransferSlot) -> frozenset[GoalKind]:
    kinds = tuple(GoalKind)
    focus_index = kinds.index(slot.goal_kind)
    start = (focus_index // 3) * 3
    return frozenset(kinds[start : start + 3])


def _question(
    slot: CrystalTransferSlot,
    *,
    all_available: bool = False,
    candidate_order: tuple[GoalKind, ...] | None = None,
) -> GoalManagerQuestion:
    order = slot.candidate_goal_kinds if candidate_order is None else candidate_order
    available = frozenset(GoalKind) if all_available else _available_kinds(slot)
    offset = slot.partition_ordinal / 1000
    situation = GoalSituation(
        story_pressure=0.11 + offset,
        collection_pressure=0.12 + offset,
        team_pressure=0.13 + offset,
        evolution_pressure=0.14 + offset,
        safety_pressure=0.15 + offset,
        resource_pressure=0.16 + offset,
        storage_pressure=0.17 + offset,
        recovery_pressure=0.18 + offset,
        exploration_pressure=0.19 + offset,
    )
    opportunities = tuple(
        GoalOpportunity(
            binding_ref=f"private:{slot.slot_id}:{kind.value}",
            kind=kind,
            availability=(
                GoalAvailability.AVAILABLE
                if kind in available
                else GoalAvailability.UNAVAILABLE
            ),
            estimated_effort=(0.2 + kinds_index / 100 if kind in available else None),
            estimated_risk=(0.1 + kinds_index / 100 if kind in available else None),
            unavailable_reason=(
                None if kind in available else GoalUnavailableReason.MISSING_CAPABILITY
            ),
        )
        for kinds_index, kind in enumerate(order)
    )
    return GoalManagerQuestion(situation, opportunities)


def _context(
    slot: CrystalTransferSlot,
    *,
    state_key: str | None = None,
    all_available: bool = False,
    candidate_order: tuple[GoalKind, ...] | None = None,
) -> CrystalTransferContext:
    return CrystalTransferContext.build(
        slot,
        state_sha256=_sha256(state_key or f"{slot.slot_id}:state"),
        envelope_sha256=_sha256(f"{slot.slot_id}:envelope"),
        binding_manifest_sha256=_sha256(f"{slot.slot_id}:bindings"),
        question=_question(
            slot,
            all_available=all_available,
            candidate_order=candidate_order,
        ),
    )


def _catalog(plan: CrystalTransferPlan, partition: str):  # type: ignore[no-untyped-def]
    slots = tuple(slot for slot in plan.slots if slot.partition == partition)
    payload = build_crystal_transfer_catalog_payload(
        plan,
        partition=partition,
        rom_sha256=ROM_SHA256,
        adapter_source_commit=SOURCE_COMMIT,
        adapter_source_bundle_sha256=SOURCE_BUNDLE,
        entries=tuple(_context(slot) for slot in slots),
    )
    return parse_crystal_transfer_catalog(payload, plan), payload


def _prediction_rows(catalog, *, scratch_misses: int = 0):  # type: ignore[no-untyped-def]
    predictor_ids = (
        CRYSTAL_ZERO_SHOT_PREDICTOR_IDS
        if catalog.partition == "zero_shot_probe"
        else CRYSTAL_SEALED_PREDICTOR_IDS
    )
    rows: list[CrystalTransferPrediction] = []
    for ordinal, context in enumerate(catalog.entries):
        for predictor_id in predictor_ids:
            selected = context.focus_candidate_index
            if predictor_id == "scratch_budget_9" and ordinal < scratch_misses:
                selected = next(
                    index
                    for index in context.available_candidate_indices
                    if index != context.focus_candidate_index
                )
            rows.append(
                CrystalTransferPrediction.build(
                    context,
                    predictor_id=predictor_id,
                    predictor_sha256=(
                        CRYSTAL_RED_FROZEN_MODEL_SHA256
                        if predictor_id == "red_frozen"
                        else CRYSTAL_BASELINE_PREDICTOR_SHA256.get(
                            predictor_id,
                            _sha256(f"predictor:{predictor_id}"),
                        )
                    ),
                    selected_candidate_index=selected,
                    confidence=0.8,
                    tied=False,
                )
            )
    return tuple(rows)


def _adapted_predictors() -> dict[str, str]:
    return {
        predictor_id: _sha256(f"predictor:{predictor_id}")
        for predictor_id in CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS
    }


def _commitment(plan, catalog, *, scratch_misses: int = 0):  # type: ignore[no-untyped-def]
    adapted = _adapted_predictors() if catalog.partition == "sealed_test" else None
    payload = build_crystal_prediction_commitment_payload(
        plan,
        catalog,
        _prediction_rows(catalog, scratch_misses=scratch_misses),
        teacher_labels_observed=0,
        teacher_actions_executed=0,
        adapted_predictor_sha256=adapted,
    )
    return (
        parse_crystal_prediction_commitment(
            payload,
            plan,
            catalog,
            adapted_predictor_sha256=adapted,
        ),
        payload,
    )


def _outcomes(catalog):  # type: ignore[no-untyped-def]
    return tuple(
        CrystalTransferCaseOutcome(
            slot_id=context.slot_id,
            context_sha256=context.context_sha256,
            teacher_selected_candidate_index=context.focus_candidate_index,
            teacher_failure_class=None,
            executions=tuple(
                CrystalPredictorExecution(
                    predictor_id=predictor_id,
                    status=CrystalExecutionStatus.SUCCEEDED,
                    independently_verified=True,
                )
                for predictor_id in CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS
            ),
        )
        for context in catalog.entries
    )


def _outcome_set(plan, catalog, commitment):  # type: ignore[no-untyped-def]
    payload = build_crystal_transfer_outcome_set_payload(
        plan,
        catalog,
        commitment,
        _outcomes(catalog),
    )
    return (
        parse_crystal_transfer_outcome_set(
            payload,
            plan,
            catalog,
            commitment,
        ),
        payload,
    )


def test_all_three_unlabeled_catalogs_are_canonical_disjoint_and_path_free() -> None:
    plan = _plan()
    catalogs_and_payloads = tuple(_catalog(plan, partition.name) for partition in plan.partitions)
    catalogs = tuple(item[0] for item in catalogs_and_payloads)

    validate_crystal_transfer_catalog_set(plan, catalogs)
    assert tuple(len(catalog.entries) for catalog in catalogs) == (18, 27, 27)
    assert all(catalog.public_dict()["context_dependent_menu_count"] == 3 for catalog in catalogs)
    assert all(catalog.public_dict()["teacher_label_fields"] == 0 for catalog in catalogs)
    encoded = b"".join(item[1] for item in catalogs_and_payloads).decode("ascii")
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    assert "teacher_selected_candidate_index" not in encoded
    assert "prediction_sha256" not in encoded


def test_catalog_rejects_repeated_state_wrong_order_or_decorative_menus() -> None:
    plan = _plan()
    slots = tuple(slot for slot in plan.slots if slot.partition == "zero_shot_probe")
    duplicate_state = (
        _context(slots[0], state_key="duplicate"),
        _context(slots[1], state_key="duplicate"),
        *(_context(slot) for slot in slots[2:]),
    )
    with pytest.raises(CrystalTransferArtifactError, match="repeats a state"):
        build_crystal_transfer_catalog_payload(
            plan,
            partition="zero_shot_probe",
            rom_sha256=ROM_SHA256,
            adapter_source_commit=SOURCE_COMMIT,
            adapter_source_bundle_sha256=SOURCE_BUNDLE,
            entries=duplicate_state,
        )

    wrong_order = tuple(reversed(slots[0].candidate_goal_kinds))
    reordered = (_context(slots[0], candidate_order=wrong_order), *map(_context, slots[1:]))
    with pytest.raises(CrystalTransferArtifactError, match="slot semantics"):
        build_crystal_transfer_catalog_payload(
            plan,
            partition="zero_shot_probe",
            rom_sha256=ROM_SHA256,
            adapter_source_commit=SOURCE_COMMIT,
            adapter_source_bundle_sha256=SOURCE_BUNDLE,
            entries=reordered,
        )

    decorative = tuple(_context(slot, all_available=True) for slot in slots)
    with pytest.raises(CrystalTransferArtifactError, match="menu reversals"):
        build_crystal_transfer_catalog_payload(
            plan,
            partition="zero_shot_probe",
            rom_sha256=ROM_SHA256,
            adapter_source_commit=SOURCE_COMMIT,
            adapter_source_bundle_sha256=SOURCE_BUNDLE,
            entries=decorative,
        )


def test_catalog_parser_rejects_noncanonical_or_drifted_identity() -> None:
    plan = _plan()
    _catalog_record, payload = _catalog(plan, "zero_shot_probe")
    document = json.loads(payload)

    with pytest.raises(CrystalTransferArtifactError, match="canonical"):
        parse_crystal_transfer_catalog(json.dumps(document, indent=2).encode("ascii"), plan)
    document["plan_sha256"] = "0" * 64
    mutated = (
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
    )
    with pytest.raises(CrystalTransferArtifactError, match="plan digest"):
        parse_crystal_transfer_catalog(mutated, plan)


def test_prediction_commitments_cover_every_predictor_before_teacher_access() -> None:
    plan = _plan()
    zero_catalog, _payload = _catalog(plan, "zero_shot_probe")
    zero_commitment, encoded = _commitment(plan, zero_catalog)
    assert zero_commitment.predictor_ids == CRYSTAL_ZERO_SHOT_PREDICTOR_IDS
    assert len(zero_commitment.predictions) == 18 * len(CRYSTAL_ZERO_SHOT_PREDICTOR_IDS)
    assert b"teacher_choice_target" not in encoded

    sealed_catalog, _payload = _catalog(plan, "sealed_test")
    sealed_commitment, _encoded = _commitment(plan, sealed_catalog)
    assert sealed_commitment.predictor_ids == CRYSTAL_SEALED_PREDICTOR_IDS
    assert len(sealed_commitment.predictions) == 27 * len(CRYSTAL_SEALED_PREDICTOR_IDS)
    assert sealed_commitment.public_dict()["teacher_labels_observed_at_commit"] == 0


def test_commitment_rejects_teacher_access_missing_rows_or_unavailable_choice() -> None:
    plan = _plan()
    catalog, _payload = _catalog(plan, "zero_shot_probe")
    rows = _prediction_rows(catalog)
    with pytest.raises(CrystalTransferArtifactError, match="before any teacher"):
        build_crystal_prediction_commitment_payload(
            plan,
            catalog,
            rows,
            teacher_labels_observed=1,
            teacher_actions_executed=0,
        )
    with pytest.raises(CrystalTransferArtifactError, match="exact slot/predictor coverage"):
        build_crystal_prediction_commitment_payload(
            plan,
            catalog,
            rows[:-1],
            teacher_labels_observed=0,
            teacher_actions_executed=0,
        )
    first_context = catalog.entries[0]
    unavailable = next(
        index
        for index in range(len(GoalKind))
        if index not in first_context.available_candidate_indices
    )
    with pytest.raises(CrystalTransferArtifactError, match="unavailable"):
        CrystalTransferPrediction.build(
            first_context,
            predictor_id="red_frozen",
            predictor_sha256="d" * 64,
            selected_candidate_index=unavailable,
            confidence=0.5,
            tied=False,
        )


def test_commitment_rejects_unbound_fixed_or_adapted_predictor_identity() -> None:
    plan = _plan()
    zero_catalog, _payload = _catalog(plan, "zero_shot_probe")
    zero_rows = tuple(
        CrystalTransferPrediction.build(
            zero_catalog.entry(row.slot_id),
            predictor_id=row.predictor_id,
            predictor_sha256=(
                "d" * 64 if row.predictor_id == "red_frozen" else row.predictor_sha256
            ),
            selected_candidate_index=row.selected_candidate_index,
            confidence=row.confidence,
            tied=row.tied,
        )
        for row in _prediction_rows(zero_catalog)
    )
    with pytest.raises(CrystalTransferArtifactError, match="fixed predictor"):
        build_crystal_prediction_commitment_payload(
            plan,
            zero_catalog,
            zero_rows,
            teacher_labels_observed=0,
            teacher_actions_executed=0,
        )

    sealed_catalog, _payload = _catalog(plan, "sealed_test")
    adapted = _adapted_predictors()
    wrong = {**adapted, "red_initialized_budget_9": "e" * 64}
    with pytest.raises(CrystalTransferArtifactError, match="adapted predictor"):
        build_crystal_prediction_commitment_payload(
            plan,
            sealed_catalog,
            _prediction_rows(sealed_catalog),
            teacher_labels_observed=0,
            teacher_actions_executed=0,
            adapted_predictor_sha256=wrong,
        )


def test_primary_evaluation_is_unavailable_until_all_27_outcomes_exist() -> None:
    plan = _plan()
    catalog, _payload = _catalog(plan, "sealed_test")
    commitment, _encoded = _commitment(plan, catalog, scratch_misses=6)
    outcomes = _outcomes(catalog)

    with pytest.raises(CrystalTransferArtifactError, match="every sealed outcome"):
        build_crystal_transfer_outcome_set_payload(
            plan,
            catalog,
            commitment,
            outcomes[:-1],
        )

    outcome_set, encoded = _outcome_set(plan, catalog, commitment)
    evaluation = evaluate_crystal_sealed_transfer(plan, catalog, commitment, outcome_set)
    assert evaluation.examples == 27
    assert evaluation.primary.red_initialized_wins == 6
    assert evaluation.primary.red_initialized_losses == 0
    assert evaluation.primary.paired_two_sided_exact_p == pytest.approx(0.03125)
    assert evaluation.primary.passed
    public = evaluation.public_dict()
    assert public["intermediate_statistics_emitted"] is False
    assert public["missing_teacher_labels"] == 0
    assert public["catalog_stratum_mismatches"] == 0
    assert public["outcome_set_sha256"] == hashlib.sha256(encoded).hexdigest()
    assert evaluation.canonical_bytes() == (
        json.dumps(
            public,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )

    with pytest.raises(CrystalTransferArtifactError, match="outcome-set digest"):
        evaluate_crystal_sealed_transfer(
            plan,
            catalog,
            commitment,
            replace(outcome_set, outcome_set_sha256="f" * 64),
        )
    with pytest.raises(CrystalTransferArtifactError, match="commitment digest"):
        build_crystal_transfer_outcome_set_payload(
            plan,
            catalog,
            replace(commitment, commitment_sha256="e" * 64),
            outcomes,
        )


def test_missing_teacher_label_counts_both_predictions_incorrect_and_preserves_failure() -> None:
    plan = _plan()
    catalog, _payload = _catalog(plan, "sealed_test")
    commitment, _encoded = _commitment(plan, catalog, scratch_misses=6)
    outcomes = list(_outcomes(catalog))
    outcomes[-1] = replace(
        outcomes[-1],
        teacher_selected_candidate_index=None,
        teacher_failure_class="external_interruption",
    )

    payload = build_crystal_transfer_outcome_set_payload(
        plan,
        catalog,
        commitment,
        outcomes,
    )
    outcome_set = parse_crystal_transfer_outcome_set(
        payload,
        plan,
        catalog,
        commitment,
    )
    evaluation = evaluate_crystal_sealed_transfer(
        plan,
        catalog,
        commitment,
        outcome_set,
    )
    metrics = dict(evaluation.predictor_metrics)
    assert evaluation.missing_teacher_labels == 1
    assert metrics["red_initialized_budget_9"].correct == 26
    assert metrics["scratch_budget_9"].correct == 20
    assert evaluation.primary.red_initialized_wins == 6
    assert evaluation.primary.red_initialized_losses == 0


def test_execution_records_fail_closed_on_unverified_success_or_unknown_failure() -> None:
    with pytest.raises(CrystalTransferArtifactError, match="independent verification"):
        CrystalPredictorExecution(
            predictor_id="red_initialized_budget_9",
            status=CrystalExecutionStatus.SUCCEEDED,
            independently_verified=False,
        )
    with pytest.raises(CrystalTransferArtifactError, match="failure class"):
        CrystalPredictorExecution(
            predictor_id="red_initialized_budget_9",
            status=CrystalExecutionStatus.FAILED,
            independently_verified=False,
            failure_class="made_up",
        )
