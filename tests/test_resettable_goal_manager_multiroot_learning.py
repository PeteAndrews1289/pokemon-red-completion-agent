from __future__ import annotations

import numpy as np
import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalKind,
    GoalManagerExample,
    GoalOpportunity,
    GoalSituation,
)
from pokemon_red_completion.goal_manager_development import (
    AdmittedGoalManagerDevelopmentEpisode,
    GoalManagerDevelopmentTarget,
)
from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_NAMES,
    GoalManagerLinearModel,
)
from pokemon_red_completion.goal_manager_trajectory import CollectedGoalManagerDataset
from pokemon_red_completion.resettable_goal_manager_multiroot_learning import (
    ResettableGoalManagerLearningError,
    admit_resettable_goal_manager_train_set,
    compare_resettable_goal_manager_development,
    fit_resettable_goal_manager_train_set,
)


def _question():  # type: ignore[no-untyped-def]
    situation = GoalSituation.from_satisfaction(
        story=0.5,
        collection=0.5,
        team=0.5,
        evolution=0.5,
        safety=0.5,
        resources=0.5,
        storage=0.5,
        control=0.5,
        world_knowledge=0.5,
    )
    return (
        situation,
        tuple(
            GoalOpportunity(
                f"binding-{kind.value}",
                kind,
                GoalAvailability.AVAILABLE,
                estimated_effort=0.2 + index * 0.1,
                estimated_risk=0.05 + index * 0.02,
            )
            for index, kind in enumerate(
                (
                    GoalKind.ACQUIRE_SPECIES,
                    GoalKind.DEVELOP_TEAM,
                    GoalKind.RESTORE_TEAM,
                    GoalKind.MANAGE_STORAGE,
                )
            )
        ),
    )


def _episode(
    index: int,
    *,
    partition: str,
    root: str,
    selected_kind: GoalKind,
) -> AdmittedGoalManagerDevelopmentEpisode:
    situation, opportunities = _question()
    from pokemon_red_completion.goal_manager import GoalManagerQuestion

    question = GoalManagerQuestion(situation=situation, opportunities=opportunities)
    selected = next(
        position
        for position, opportunity in enumerate(opportunities)
        if opportunity.kind is selected_kind
    )
    decision_id = f"decision-{partition}-{index}"
    example = GoalManagerExample(
        decision_id=decision_id,
        episode_id=f"episode-{partition}-{index}",
        decision_index=0,
        root_lineage_id=root,
        partition=partition,
        environment_id="pokemon.mainline:red:gb:us:rev0",
        actor="exploratory_goal_manager",
        policy_id="red-goal-manager-outcome-development-v1",
        question=question,
        selected_candidate_index=selected,
        outcome_status=GoalDecisionOutcome.SUCCEEDED,
    )
    target = GoalManagerDevelopmentTarget(
        decision_id=decision_id,
        selected_candidate_index=selected,
        reward=1.0,
        behavior_probability=0.25,
        importance_weight=4.0,
    )
    dataset = CollectedGoalManagerDataset(
        episode_id=example.episode_id,
        manifest_sha256=f"{index + 1:064x}",
        root_lineage_id=root,
        partition=partition,
        environment_id=example.environment_id,
        actor=example.actor,
        policy_id=example.policy_id,
        collection_id="collection",
        assignment_id=f"{index + 20:064x}",
        source_commit="a" * 40,
        context_catalog_sha256="b" * 64,
        context_id=f"context-{index}",
        binding_manifest_sha256="c" * 64,
        capture_state_sha256=f"{index + 40:064x}",
        capture_envelope_sha256=f"{index + 60:064x}",
        examples=(example,),
    )
    return AdmittedGoalManagerDevelopmentEpisode(
        dataset=dataset,
        stopped_reason="decision_limit",
        composition=False,
        collection_relevant_outcomes=int(
            selected_kind in {GoalKind.ACQUIRE_SPECIES, GoalKind.MANAGE_STORAGE}
        ),
        successful_retained_acquisitions=int(
            selected_kind is GoalKind.ACQUIRE_SPECIES
        ),
        successful_specimen_preserving_storage=int(
            selected_kind is GoalKind.MANAGE_STORAGE
        ),
        targets=(target,),
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


def _acquisition_favoring_model() -> GoalManagerLinearModel:
    model = _model()
    weights = model.weights.copy()
    weights[GOAL_MANAGER_FEATURE_NAMES.index("candidate.kind.acquire_species")] = 1.0
    return GoalManagerLinearModel(
        weights=weights,
        feature_mean=model.feature_mean,
        feature_scale=model.feature_scale,
        l2=model.l2,
        training_epochs=model.training_epochs,
    )


def test_admits_six_train_targets_across_three_roots_and_goal_kinds() -> None:
    kinds = (
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.DEVELOP_TEAM,
        GoalKind.DEVELOP_TEAM,
        GoalKind.RESTORE_TEAM,
        GoalKind.RESTORE_TEAM,
    )
    episodes = tuple(
        _episode(index, partition="train", root=f"root-{index // 2}", selected_kind=kind)
        for index, kind in enumerate(kinds)
    )

    admitted = admit_resettable_goal_manager_train_set(episodes)

    assert len(admitted.rows) == 6
    assert admitted.roots == ("root-0", "root-1", "root-2")
    assert GoalKind.ACQUIRE_SPECIES.value in admitted.selected_goal_kinds


def test_train_gate_rejects_three_noncollection_goal_kinds() -> None:
    kinds = (
        GoalKind.DEVELOP_TEAM,
        GoalKind.DEVELOP_TEAM,
        GoalKind.RESTORE_TEAM,
        GoalKind.RESTORE_TEAM,
        GoalKind.MANAGE_STORAGE,
        GoalKind.MANAGE_STORAGE,
    )
    episodes = tuple(
        _episode(index, partition="train", root=f"root-{index // 2}", selected_kind=kind)
        for index, kind in enumerate(kinds)
    )

    with pytest.raises(ResettableGoalManagerLearningError, match="collection threshold"):
        admit_resettable_goal_manager_train_set(episodes)


def test_fit_revalidates_train_episodes_and_requires_frozen_guard_rosters() -> None:
    kinds = (
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.DEVELOP_TEAM,
        GoalKind.DEVELOP_TEAM,
        GoalKind.RESTORE_TEAM,
        GoalKind.RESTORE_TEAM,
    )
    episodes = tuple(
        _episode(index, partition="train", root=f"root-{index // 2}", selected_kind=kind)
        for index, kind in enumerate(kinds)
    )

    with pytest.raises(ResettableGoalManagerLearningError, match="54-menu guard"):
        fit_resettable_goal_manager_train_set(
            _model(),
            episodes,
            guard_examples=(),
            kl_examples=(),
        )


def test_comparison_requires_four_episodes_on_two_disjoint_roots() -> None:
    episodes = tuple(
        _episode(
            index,
            partition="development",
            root=f"development-root-{index // 2}",
            selected_kind=GoalKind.ACQUIRE_SPECIES,
        )
        for index in range(4)
    )

    comparison = compare_resettable_goal_manager_development(
        _model(),
        _model(),
        episodes,
        train_roots=("train-root-0", "train-root-1"),
    )

    assert comparison.directional_wins == 0
    assert comparison.directional_ties == 4
    assert comparison.favorable is False


def test_comparison_favorable_path_requires_improvement_without_a_loss() -> None:
    episodes = tuple(
        _episode(
            index,
            partition="development",
            root=f"development-root-{index // 2}",
            selected_kind=GoalKind.ACQUIRE_SPECIES,
        )
        for index in range(4)
    )

    favorable = compare_resettable_goal_manager_development(
        _model(),
        _acquisition_favoring_model(),
        episodes,
        train_roots=("train-root-0", "train-root-1"),
    )

    assert favorable.directional_wins == 4
    assert favorable.directional_losses == 0
    assert favorable.candidate.weighted_binary_cross_entropy < (
        favorable.base.weighted_binary_cross_entropy
    )
    assert favorable.favorable is True

    one_loss = (*episodes[:3], _episode(
        3,
        partition="development",
        root="development-root-1",
        selected_kind=GoalKind.DEVELOP_TEAM,
    ))
    rejected = compare_resettable_goal_manager_development(
        _model(),
        _acquisition_favoring_model(),
        one_loss,
        train_roots=("train-root-0", "train-root-1"),
    )

    assert rejected.directional_wins == 3
    assert rejected.directional_losses == 1
    assert rejected.favorable is False


def test_comparison_rejects_train_root_overlap() -> None:
    episodes = tuple(
        _episode(
            index,
            partition="development",
            root=f"development-root-{index // 2}",
            selected_kind=GoalKind.ACQUIRE_SPECIES,
        )
        for index in range(4)
    )

    with pytest.raises(ResettableGoalManagerLearningError, match="disjoint split"):
        compare_resettable_goal_manager_development(
            _model(),
            _model(),
            episodes,
            train_roots=("development-root-0",),
        )
