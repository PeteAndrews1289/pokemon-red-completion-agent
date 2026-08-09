"""Authenticated whole-lineage training for battle switch-target selection."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pokemon_red_completion.battle_action_targets import resolve_battle_action_target
from pokemon_red_completion.battle_actions import BattleAction, BattleActionKind
from pokemon_red_completion.battle_control_labels import BattleControlDataset
from pokemon_red_completion.battle_switch_target import (
    SWITCH_TARGET_FEATURE_NAMES,
    BattleSwitchTargetExample,
    project_switch_target_candidates,
)
from pokemon_red_completion.battle_switch_target_model import (
    BattleSwitchTargetMetrics,
    BattleSwitchTargetMLP,
    BattleSwitchTargetModelError,
    evaluate_switch_target_model,
)
from pokemon_red_completion.red_battle_catalog import RED_BATTLE_CATALOG


@dataclass(frozen=True, slots=True)
class BattleSwitchTargetBaselineMetrics:
    examples: int
    correct: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.examples

    def public_dict(self) -> dict[str, object]:
        return {
            "examples": self.examples,
            "correct": self.correct,
            "accuracy": self.accuracy,
        }


@dataclass(frozen=True, slots=True)
class BattleSwitchTargetCandidateModel:
    """Offline candidate only; constructing this value grants no runtime authority."""

    model: BattleSwitchTargetMLP
    training: BattleSwitchTargetMetrics
    validation: BattleSwitchTargetMetrics
    training_baseline: BattleSwitchTargetBaselineMetrics
    validation_baseline: BattleSwitchTargetBaselineMetrics
    training_artifact_ids: tuple[str, ...]
    validation_artifact_ids: tuple[str, ...]
    source_manifest_sha256s: tuple[str, ...]

    def public_summary(self) -> dict[str, object]:
        return {
            "schema": "pokemon-battle-switch-target-candidate-summary-v1",
            "deployment_authority": False,
            "model_id": self.model.model_id,
            "feature_schema_id": self.model.feature_schema_id,
            "feature_names": list(SWITCH_TARGET_FEATURE_NAMES),
            "training": self.training.public_dict(),
            "validation": self.validation.public_dict(),
            "training_baseline": self.training_baseline.public_dict(),
            "validation_baseline": self.validation_baseline.public_dict(),
            "training_artifact_ids": list(self.training_artifact_ids),
            "validation_artifact_ids": list(self.validation_artifact_ids),
            "source_manifest_sha256s": list(self.source_manifest_sha256s),
        }


def switch_target_examples(
    datasets: Iterable[BattleControlDataset],
) -> tuple[BattleSwitchTargetExample, ...]:
    """Project explicit demonstrated targets without objective or game identity."""

    examples: list[BattleSwitchTargetExample] = []
    for dataset in datasets:
        for label in dataset.labels:
            action = label.teacher_action
            if action.kind is not BattleActionKind.SWITCH or action.party_slot is None:
                continue
            try:
                observation = project_switch_target_candidates(
                    label.observation,
                    RED_BATTLE_CATALOG,
                )
                selected = observation.candidate_index_for_party_slot(action.party_slot)
            except ValueError as error:
                raise BattleSwitchTargetModelError(
                    "switch target label lacks candidate-relative mechanics"
                ) from error
            examples.append(
                BattleSwitchTargetExample(
                    observation=observation,
                    selected_candidate_index=selected,
                    battle_plan_id=label.battle_plan_id,
                    decision_index=label.decision_index,
                )
            )
    return tuple(examples)


def evaluate_deterministic_switch_target_baseline(
    datasets: Iterable[BattleControlDataset],
) -> BattleSwitchTargetBaselineMetrics:
    """Score the currently deployed semantic matchup resolver on explicit labels."""

    examples = 0
    correct = 0
    for dataset in datasets:
        for label in dataset.labels:
            action = label.teacher_action
            if action.kind is not BattleActionKind.SWITCH or action.party_slot is None:
                continue
            try:
                resolved = resolve_battle_action_target(
                    BattleAction.switch(),
                    label.observation,
                    catalog=RED_BATTLE_CATALOG,
                )
            except ValueError as error:
                raise BattleSwitchTargetModelError(
                    "switch target baseline cannot resolve an explicit label"
                ) from error
            examples += 1
            correct += int(resolved.party_slot == action.party_slot)
    if not examples:
        raise BattleSwitchTargetModelError("switch target baseline has no explicit labels")
    return BattleSwitchTargetBaselineMetrics(examples=examples, correct=correct)


def fit_preassigned_switch_target_candidate(
    training_datasets: Iterable[BattleControlDataset],
    validation_datasets: Iterable[BattleControlDataset],
    *,
    hidden_units: int = 2,
    epochs: int = 1000,
    learning_rate: float = 0.01,
    l2: float = 0.03,
    seed: int = 0,
) -> BattleSwitchTargetCandidateModel:
    """Fit on complete lineages and evaluate once on disjoint lineages."""

    training_roots = tuple(training_datasets)
    validation_roots = tuple(validation_datasets)
    if not training_roots or not validation_roots:
        raise BattleSwitchTargetModelError("switch target lineage partitions are empty")
    all_roots = (*training_roots, *validation_roots)
    manifests = tuple(dataset.manifest_sha256 for dataset in all_roots)
    if len(set(manifests)) != len(manifests):
        raise BattleSwitchTargetModelError("switch target lineages must be disjoint")
    if len({dataset.source_model_sha256 for dataset in all_roots}) != 1:
        raise BattleSwitchTargetModelError(
            "switch target lineages were collected from different move models"
        )
    train = switch_target_examples(training_roots)
    validation = switch_target_examples(validation_roots)
    if not train or not validation:
        raise BattleSwitchTargetModelError("switch target lineage labels are empty")
    model = BattleSwitchTargetMLP.fit(
        train,
        hidden_units=hidden_units,
        epochs=epochs,
        learning_rate=learning_rate,
        l2=l2,
        seed=seed,
    )
    return BattleSwitchTargetCandidateModel(
        model=model,
        training=evaluate_switch_target_model(model, train),
        validation=evaluate_switch_target_model(model, validation),
        training_baseline=evaluate_deterministic_switch_target_baseline(training_roots),
        validation_baseline=evaluate_deterministic_switch_target_baseline(validation_roots),
        training_artifact_ids=tuple(dataset.artifact_id for dataset in training_roots),
        validation_artifact_ids=tuple(dataset.artifact_id for dataset in validation_roots),
        source_manifest_sha256s=manifests,
    )
