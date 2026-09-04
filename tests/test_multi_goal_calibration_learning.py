from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalManagerExample,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_NAMES,
    GoalManagerLinearModel,
)
from pokemon_red_completion.goal_manager_trajectory import CollectedGoalManagerDataset
from pokemon_red_completion.multi_goal_calibration_admission import (
    AdmittedMultiGoalCalibrationOutcome,
)
from pokemon_red_completion.multi_goal_calibration_learning import (
    MultiGoalCalibrationLearningError,
    admit_multi_goal_calibration_train_set,
    fit_multi_goal_calibration_train_set,
)

KINDS = (
    GoalKind.DEVELOP_TEAM,
    GoalKind.DEVELOP_TEAM,
    GoalKind.ADVANCE_STORY,
    GoalKind.EVOLVE_SPECIES,
    GoalKind.MANAGE_STORAGE,
    GoalKind.ADVANCE_STORY,
    GoalKind.MANAGE_STORAGE,
)
REWARDS = (1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0)
ROOTS = (0, 1, 1, 1, 2, 3, 3)


def _question(index: int) -> GoalManagerQuestion:
    kinds = (
        GoalKind.ADVANCE_STORY,
        GoalKind.DEVELOP_TEAM,
        GoalKind.EVOLVE_SPECIES,
        GoalKind.MANAGE_STORAGE,
    )
    return GoalManagerQuestion(
        GoalSituation(*([0.25 + index * 0.01] * 9)),
        tuple(
            GoalOpportunity(
                f"binding:{index}:{kind.value}",
                kind,
                GoalAvailability.AVAILABLE,
                estimated_effort=0.1 + ordinal * 0.1,
                estimated_risk=0.05 + ordinal * 0.05,
            )
            for ordinal, kind in enumerate(kinds)
        ),
    )


def _checkpoint() -> LivingCollectionCheckpoint:
    return LivingCollectionCheckpoint(
        registered_species=1,
        living_species=1,
        required_specimens_remaining=1,
        retained_captures=1,
        storage_headroom=1,
        undeclared_specimen_losses=0,
        completion_contract_sha256="1" * 64,
        specimen_ledger_sha256="2" * 64,
        required_specimens_sha256="3" * 64,
        specimen_counts=(("pokemon:national:001", 1),),
    )


def _outcome(index: int) -> AdmittedMultiGoalCalibrationOutcome:
    question = _question(index)
    kind = KINDS[index]
    selected = next(
        ordinal
        for ordinal, opportunity in enumerate(question.opportunities)
        if opportunity.kind is kind
    )
    status = (
        GoalDecisionOutcome.SUCCEEDED
        if REWARDS[index] == 1.0
        else GoalDecisionOutcome.FAILED
    )
    example = GoalManagerExample(
        decision_id=f"episode-{index}:goal-manager:0",
        episode_id=f"episode-{index}",
        decision_index=0,
        root_lineage_id=f"red-goal-root-{ROOTS[index] + 1:064x}",
        partition="train",
        environment_id="pokemon.mainline:red:gb:us:rev0",
        actor="forced_calibration_arm",
        policy_id="pokemon.core.goal-manager.forced-calibration-arm.v1",
        question=question,
        selected_candidate_index=selected,
        outcome_status=status,
        failure_reason=(
            None
            if status is GoalDecisionOutcome.SUCCEEDED
            else GoalFailureReason.BINDING_FAILED
        ),
    )
    dataset = CollectedGoalManagerDataset(
        episode_id=example.episode_id,
        manifest_sha256=f"{index + 10:064x}",
        root_lineage_id=example.root_lineage_id,
        partition="train",
        environment_id=example.environment_id,
        actor=example.actor,
        policy_id=example.policy_id,
        collection_id="4" * 64,
        assignment_id=f"{index + 20:064x}",
        source_commit="5" * 40,
        context_catalog_sha256="6" * 64,
        context_id=f"{index + 30:064x}",
        binding_manifest_sha256=f"{index + 40:064x}",
        capture_state_sha256=f"{index + 50:064x}",
        capture_envelope_sha256=f"{index + 60:064x}",
        examples=(example,),
    )
    checkpoint = _checkpoint()
    return AdmittedMultiGoalCalibrationOutcome(
        dataset=dataset,
        selected_goal_kind=kind,
        status=status,
        reward=REWARDS[index],
        actions_executed=0,
        frames_executed=0,
        semantic_state_changed=status is GoalDecisionOutcome.SUCCEEDED,
        collection_before=checkpoint,
        collection_after=checkpoint,
    )


def _model() -> GoalManagerLinearModel:
    width = len(GOAL_MANAGER_FEATURE_NAMES)
    return GoalManagerLinearModel(
        weights=np.zeros(width),
        feature_mean=np.zeros(width),
        feature_scale=np.ones(width),
        l2=0.02,
        training_epochs=1,
    )


def test_fixed_train_set_retains_all_seven_outcomes_without_teacher_labels() -> None:
    train_set = admit_multi_goal_calibration_train_set(
        _outcome(index) for index in range(7)
    )

    assert train_set.public_dict() == {
        "schema": "pokemon.red.multi-goal-calibration-train-set.v1",
        "targets": 7,
        "roots": 4,
        "positive_targets": 4,
        "negative_targets": 3,
        "selected_goal_kind_counts": {
            "advance_story": 2,
            "develop_team": 2,
            "evolve_species": 1,
            "manage_storage": 2,
        },
        "unique_episode_manifests": 7,
        "teacher_queries": 0,
        "private_path_fields": 0,
    }
    assert all(target.behavior_probability == 1.0 for _, target in train_set.rows)
    assert all(target.importance_weight == 1.0 for _, target in train_set.rows)


def test_train_set_rejects_outcome_selected_denominator_changes() -> None:
    with pytest.raises(MultiGoalCalibrationLearningError, match="denominator"):
        admit_multi_goal_calibration_train_set(_outcome(index) for index in range(6))

    duplicate = replace(
        _outcome(6),
        dataset=replace(_outcome(6).dataset, manifest_sha256=f"{10:064x}"),
    )
    with pytest.raises(MultiGoalCalibrationLearningError, match="denominator"):
        admit_multi_goal_calibration_train_set(
            (*(_outcome(index) for index in range(6)), duplicate)
        )


def test_fit_uses_the_bounded_train_update_and_guard_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    train_set = admit_multi_goal_calibration_train_set(
        _outcome(index) for index in range(7)
    )
    base = _model()
    guarded: list[tuple[GoalManagerLinearModel, GoalManagerLinearModel, int]] = []
    monkeypatch.setattr(
        "pokemon_red_completion.multi_goal_calibration_learning.require_unchanged_guard_winners",
        lambda old, new, rows: guarded.append((old, new, len(rows))),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.multi_goal_calibration_learning.maximum_policy_kl",
        lambda _old, _new, _rows: 0.001,
    )

    result = fit_multi_goal_calibration_train_set(
        base,
        train_set,
        guard_winners=(train_set.rows[0][0],) * 18,
        guard_menus=(train_set.rows[0][0],) * 54,
    )

    assert result.update.before.examples == 7
    assert result.update.after.weighted_binary_cross_entropy < (
        result.update.before.weighted_binary_cross_entropy
    )
    assert result.maximum_guard_menu_kl == 0.001
    assert guarded == [(base, result.update.model, 18)]


def test_fit_rejects_incomplete_guard_sets() -> None:
    train_set = admit_multi_goal_calibration_train_set(
        _outcome(index) for index in range(7)
    )

    with pytest.raises(MultiGoalCalibrationLearningError, match="guard set"):
        fit_multi_goal_calibration_train_set(
            _model(),
            train_set,
            guard_winners=(train_set.rows[0][0],) * 17,
            guard_menus=(train_set.rows[0][0],) * 54,
        )
