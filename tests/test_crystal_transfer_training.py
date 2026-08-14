from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from pokemon_crystal_completion.source_contract import CRYSTAL_GAME_ID
from pokemon_crystal_completion.transfer_artifacts import (
    CrystalTransferContext,
    build_crystal_transfer_catalog_payload,
    parse_crystal_transfer_catalog,
)
from pokemon_crystal_completion.transfer_protocol import (
    CrystalTransferSlot,
    parse_crystal_transfer_plan,
)
from pokemon_crystal_completion.transfer_training import (
    crystal_adaptation_predictor_sha256,
    fit_crystal_adaptation_pairs,
)
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalKind,
    GoalManagerExample,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_NAMES,
    GoalManagerLinearModel,
    GoalManagerModelError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT_ROOT / "configs" / "crystal-goal-manager-transfer-v1.json"
ROM_SHA256 = "c" * 64
SOURCE_COMMIT = "a" * 40
SOURCE_BUNDLE = "b" * 64


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _plan():  # type: ignore[no-untyped-def]
    return parse_crystal_transfer_plan(PLAN_PATH.read_bytes())


def _example(
    index: int,
    kind: GoalKind,
    slot: CrystalTransferSlot,
    *,
    environment: str = CRYSTAL_GAME_ID,
):  # type: ignore[no-untyped-def]
    kinds = tuple(GoalKind)
    focus_index = kinds.index(kind)
    start = (focus_index // 3) * 3
    available = frozenset(kinds[start : start + 3])
    pressure_fields = {
        GoalKind.ADVANCE_STORY: "story_pressure",
        GoalKind.ACQUIRE_SPECIES: "collection_pressure",
        GoalKind.DEVELOP_TEAM: "team_pressure",
        GoalKind.EVOLVE_SPECIES: "evolution_pressure",
        GoalKind.RESTORE_TEAM: "safety_pressure",
        GoalKind.RESUPPLY: "resource_pressure",
        GoalKind.MANAGE_STORAGE: "storage_pressure",
        GoalKind.RECOVER_CONTROL: "recovery_pressure",
        GoalKind.EXPLORE: "exploration_pressure",
    }
    pressures = {field: 0.05 + index * 0.0001 for field in pressure_fields.values()}
    pressures[pressure_fields[kind]] = 0.85
    options = tuple(
        GoalOpportunity(
            binding_ref=f"private:{index}:{candidate.value}",
            kind=candidate,
            availability=(
                GoalAvailability.AVAILABLE
                if candidate in available
                else GoalAvailability.UNAVAILABLE
            ),
            estimated_effort=(0.1 + position / 100 if candidate in available else None),
            estimated_risk=(0.2 + position / 100 if candidate in available else None),
            unavailable_reason=(
                None
                if candidate in available
                else GoalUnavailableReason.MISSING_CAPABILITY
            ),
        )
        for position, candidate in enumerate(slot.candidate_goal_kinds)
    )
    question = GoalManagerQuestion(GoalSituation(**pressures), options)
    return GoalManagerExample(
        decision_id=slot.slot_id,
        episode_id=f"crystal-adaptation-episode-{index:03d}",
        decision_index=0,
        root_lineage_id=f"crystal-adaptation-root-{index:03d}",
        partition="adaptation",
        environment_id=environment,
        actor="deterministic_teacher",
        policy_id="portable-goal-teacher-v1",
        question=question,
        selected_candidate_index=slot.focus_candidate_index,
        outcome_status=GoalDecisionOutcome.SUCCEEDED,
    )


def _adaptation() -> tuple[GoalManagerExample, ...]:
    plan = _plan()
    slots = tuple(slot for slot in plan.slots if slot.partition == "adaptation")
    return tuple(
        _example(index, slot.goal_kind, slot)
        for index, slot in enumerate(slots)
    )


def _catalog(plan, rows):  # type: ignore[no-untyped-def]
    slots = tuple(slot for slot in plan.slots if slot.partition == "adaptation")
    contexts = tuple(
        CrystalTransferContext.build(
            slot,
            state_sha256=_sha256(f"{slot.slot_id}:state"),
            envelope_sha256=_sha256(f"{slot.slot_id}:envelope"),
            binding_manifest_sha256=_sha256(f"{slot.slot_id}:bindings"),
            question=row.question,
        )
        for slot, row in zip(slots, rows, strict=True)
    )
    payload = build_crystal_transfer_catalog_payload(
        plan,
        partition="adaptation",
        rom_sha256=ROM_SHA256,
        adapter_source_commit=SOURCE_COMMIT,
        adapter_source_bundle_sha256=SOURCE_BUNDLE,
        entries=contexts,
    )
    return parse_crystal_transfer_catalog(payload, plan)


def _source_model() -> GoalManagerLinearModel:
    width = len(GOAL_MANAGER_FEATURE_NAMES)
    return GoalManagerLinearModel(
        weights=np.linspace(-0.15, 0.15, width, dtype=np.float64),
        feature_mean=np.linspace(0.05, 0.20, width, dtype=np.float64),
        feature_scale=np.linspace(0.75, 1.25, width, dtype=np.float64),
        l2=0.02,
        training_epochs=800,
    )


def test_paired_adaptation_resets_each_budget_and_changes_only_initial_weights() -> None:
    source = _source_model()
    source_weights = source.weights.copy()
    plan = _plan()
    rows = _adaptation()
    pairs = fit_crystal_adaptation_pairs(
        source,
        rows,
        plan=plan,
        catalog=_catalog(plan, rows),
    )

    assert tuple(pair.budget for pair in pairs) == (9, 18, 27)
    assert np.array_equal(source.weights, source_weights), "adaptation must not mutate Red"
    for pair in pairs:
        assert np.array_equal(pair.red_initialized.feature_mean, source.feature_mean)
        assert np.array_equal(pair.scratch.feature_mean, source.feature_mean)
        assert np.array_equal(pair.red_initialized.feature_scale, source.feature_scale)
        assert np.array_equal(pair.scratch.feature_scale, source.feature_scale)
        assert not np.array_equal(pair.red_initialized.weights, pair.scratch.weights)
        public = pair.public_dict()
        assert public["same_examples"] is True
        assert public["same_order"] is True
        assert public["same_optimizer"] is True
        assert public["same_feature_normalizer"] is True
        assert public["differing_field"] == "initial_weights"
    manifest = crystal_adaptation_predictor_sha256(pairs)
    assert tuple(predictor_id for predictor_id, _digest in manifest) == (
        "red_initialized_budget_9",
        "scratch_budget_9",
        "red_initialized_budget_18",
        "scratch_budget_18",
        "red_initialized_budget_27",
        "scratch_budget_27",
    )
    assert all(len(digest) == 64 for _predictor_id, digest in manifest)


def test_zero_weight_comparator_preserves_only_the_authenticated_preprocessing() -> None:
    source = _source_model()
    scratch = source.zero_weight_comparator()

    assert np.count_nonzero(scratch.weights) == 0
    assert np.array_equal(scratch.feature_mean, source.feature_mean)
    assert np.array_equal(scratch.feature_scale, source.feature_scale)
    assert not np.shares_memory(scratch.weights, source.weights)
    assert not np.shares_memory(scratch.feature_mean, source.feature_mean)


def test_fine_tune_requires_adaptation_rows_and_is_deterministic() -> None:
    source = _source_model()
    rows = _adaptation()[:9]
    first = source.fine_tune(rows, epochs=5)
    second = source.fine_tune(rows, epochs=5)

    assert np.array_equal(first.weights, second.weights)
    with pytest.raises(GoalManagerModelError, match="adaptation-partition"):
        source.fine_tune(tuple(replace(row, partition="train") for row in rows), epochs=5)


def test_paired_adaptation_rejects_wrong_count_environment_or_unbalanced_prefix() -> None:
    source = _source_model()
    plan = _plan()
    rows = _adaptation()
    with pytest.raises(GoalManagerModelError, match="exactly 27"):
        fit_crystal_adaptation_pairs(
            source,
            rows[:-1],
            plan=plan,
            catalog=_catalog(plan, rows),
        )
    with pytest.raises(GoalManagerModelError, match="environment"):
        fit_crystal_adaptation_pairs(
            source,
            (replace(rows[0], environment_id="pokemon.mainline:red"), *rows[1:]),
            plan=plan,
            catalog=_catalog(plan, rows),
        )
    alternate_index = next(
        index
        for index in rows[0].question.available_indices
        if index != rows[0].selected_candidate_index
    )
    mismatched = (replace(rows[0], selected_candidate_index=alternate_index), *rows[1:])
    with pytest.raises(GoalManagerModelError, match="frozen catalog context"):
        fit_crystal_adaptation_pairs(
            source,
            mismatched,
            plan=plan,
            catalog=_catalog(plan, rows),
        )
    with pytest.raises(ValueError, match="catalog digest"):
        fit_crystal_adaptation_pairs(
            source,
            rows,
            plan=plan,
            catalog=replace(_catalog(plan, rows), catalog_sha256="d" * 64),
        )
