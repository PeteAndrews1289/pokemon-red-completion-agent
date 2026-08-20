"""Dataset projection and group-held-out training for full-battle control."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pokemon_red_completion.battle_action_targets import resolve_battle_action_target
from pokemon_red_completion.battle_actions import BattleAction, BattleActionKind
from pokemon_red_completion.battle_control_features import (
    CONTROL_CLASS_REFS,
    BattleControlExample,
    BattleControlHistoryTracker,
    control_class_ref,
    project_control_features,
)
from pokemon_red_completion.battle_control_labels import BattleControlDataset, BattleControlLabel
from pokemon_red_completion.battle_control_model import (
    BattleControlMetrics,
    BattleControlMLP,
    BattleControlModelError,
    evaluate_control_model,
)
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.trajectory import SemanticSnapshot


@dataclass(frozen=True, slots=True)
class BattleSwitchTargetMetrics:
    """Teacher-target agreement for generic semantic switch resolution."""

    examples: int
    correct: int

    def __post_init__(self) -> None:
        if (
            type(self.examples) is not int  # noqa: E721
            or type(self.correct) is not int  # noqa: E721
            or self.examples < 0
            or not 0 <= self.correct <= self.examples
        ):
            raise ValueError("switch target metric counts are invalid")

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.examples if self.examples else None

    def public_dict(self) -> dict[str, object]:
        return {
            "examples": self.examples,
            "correct": self.correct,
            "accuracy": self.accuracy,
        }


@dataclass(frozen=True, slots=True)
class BattleControlCandidate:
    model: BattleControlMLP
    training: BattleControlMetrics
    validation: BattleControlMetrics
    validation_battle_plan_ids: tuple[str, ...]
    training_artifact_ids: tuple[str, ...]
    validation_artifact_ids: tuple[str, ...]
    source_manifest_sha256s: tuple[str, ...]
    training_switch_targets: BattleSwitchTargetMetrics
    validation_switch_targets: BattleSwitchTargetMetrics

    def public_summary(self) -> dict[str, object]:
        return {
            "schema": "pokemon-battle-control-candidate-summary-v1",
            "model_id": self.model.model_id,
            "class_refs": list(self.model.class_refs),
            "training": self.training.public_dict(),
            "validation": self.validation.public_dict(),
            "validation_battle_plan_ids": list(self.validation_battle_plan_ids),
            "training_artifact_ids": list(self.training_artifact_ids),
            "validation_artifact_ids": list(self.validation_artifact_ids),
            "source_manifest_sha256s": list(self.source_manifest_sha256s),
            "training_switch_targets": self.training_switch_targets.public_dict(),
            "validation_switch_targets": self.validation_switch_targets.public_dict(),
        }


def control_examples(dataset: BattleControlDataset) -> tuple[BattleControlExample, ...]:
    """Project every authenticated label without using objective or game IDs as features."""

    projector = BattleFeatureProjector(PokemonRedBattleCatalog())
    history = BattleControlHistoryTracker()
    examples: list[BattleControlExample] = []
    for label in dataset.labels:
        observation = label.observation
        snapshot = SemanticSnapshot(
            game_id=str(observation["game_id"]),
            mode=str(observation["mode"]),
            location=observation.get("location"),  # type: ignore[arg-type]
            facts=tuple(observation.get("facts", ())),  # type: ignore[arg-type]
            features=observation["features"],  # type: ignore[arg-type]
            schema_version=int(observation["schema_version"]),
        )
        examples.append(BattleControlExample(
            features=project_control_features(
                observation,
                move_batch=projector.project(snapshot),
                history=history.before(label.battle_plan_id, observation),
                catalog=projector.catalog,
            ),
            class_index=CONTROL_CLASS_REFS.index(control_class_ref(label.teacher_action)),
            battle_plan_id=label.battle_plan_id,
            decision_index=label.decision_index,
        ))
        history.advance(label.teacher_action, observation)
    return tuple(examples)


def evaluate_switch_target_resolution(
    labels: Iterable[BattleControlLabel],
) -> BattleSwitchTargetMetrics:
    """Measure whether a targetless switch resolves to the demonstrated member."""

    projector = BattleFeatureProjector(PokemonRedBattleCatalog())
    examples = 0
    correct = 0
    for label in labels:
        teacher_action = label.teacher_action
        if teacher_action.kind is not BattleActionKind.SWITCH:
            continue
        try:
            resolved = resolve_battle_action_target(
                BattleAction.switch(),
                label.observation,
                catalog=projector.catalog,
            )
        except ValueError as error:
            raise BattleControlModelError(
                "switch target label lacks reserve matchup semantics"
            ) from error
        # Historical v1 label streams may contain a generic switch request. It
        # remains a valid action-class example, and the successful resolution
        # above proves it is executable, but it supplies no independent target
        # label to score. New recordings bind the selected reserve before they
        # are persisted.
        if teacher_action.party_slot is None:
            continue
        examples += 1
        correct += int(resolved.party_slot == teacher_action.party_slot)
    return BattleSwitchTargetMetrics(examples=examples, correct=correct)


def fit_group_heldout_control_candidate(
    dataset: BattleControlDataset,
    *,
    validation_battle_plan_ids: Iterable[str],
    seed: int = 0,
    hidden_units: int = 24,
    epochs: int = 500,
    learning_rate: float = 0.01,
    l2: float = 1e-4,
    class_balance_power: float = 1.0,
) -> BattleControlCandidate:
    """Fit without allowing any battle identity to cross the validation boundary."""

    validation_groups = tuple(dict.fromkeys(validation_battle_plan_ids))
    if not validation_groups:
        raise BattleControlModelError("at least one validation battle group is required")
    rows = control_examples(dataset)
    observed_groups = {row.battle_plan_id for row in rows}
    if not set(validation_groups) <= observed_groups:
        raise BattleControlModelError("validation battle group is absent from the dataset")
    validation_set = set(validation_groups)
    train = tuple(row for row in rows if row.battle_plan_id not in validation_set)
    validation = tuple(row for row in rows if row.battle_plan_id in validation_set)
    training_labels = tuple(
        label for label in dataset.labels if label.battle_plan_id not in validation_set
    )
    validation_labels = tuple(
        label for label in dataset.labels if label.battle_plan_id in validation_set
    )
    if not train or not validation:
        raise BattleControlModelError("control train/validation split is empty")
    train_classes = {CONTROL_CLASS_REFS[row.class_index] for row in train}
    validation_classes = {CONTROL_CLASS_REFS[row.class_index] for row in validation}
    if not validation_classes <= train_classes:
        missing = sorted(validation_classes - train_classes)
        raise BattleControlModelError(
            f"validation contains action classes absent from training: {missing!r}"
        )
    model = BattleControlMLP.fit(
        train,
        seed=seed,
        hidden_units=hidden_units,
        epochs=epochs,
        learning_rate=learning_rate,
        l2=l2,
        class_balance_power=class_balance_power,
    )
    return BattleControlCandidate(
        model=model,
        training=evaluate_control_model(model, train),
        validation=evaluate_control_model(model, validation),
        validation_battle_plan_ids=validation_groups,
        training_artifact_ids=(dataset.artifact_id,),
        validation_artifact_ids=(dataset.artifact_id,),
        source_manifest_sha256s=(dataset.manifest_sha256,),
        training_switch_targets=evaluate_switch_target_resolution(training_labels),
        validation_switch_targets=evaluate_switch_target_resolution(validation_labels),
    )


def fit_preassigned_control_candidate(
    training_datasets: Iterable[BattleControlDataset],
    validation_datasets: Iterable[BattleControlDataset],
    *,
    seed: int = 0,
    hidden_units: int = 24,
    epochs: int = 500,
    learning_rate: float = 0.01,
    l2: float = 1e-4,
    class_balance_power: float = 1.0,
) -> BattleControlCandidate:
    """Fit on complete rollout lineages and validate on disjoint rollout lineages."""

    training_roots = tuple(training_datasets)
    validation_roots = tuple(validation_datasets)
    if not training_roots or not validation_roots:
        raise BattleControlModelError("control lineage partitions must both be non-empty")
    all_roots = (*training_roots, *validation_roots)
    manifests = tuple(dataset.manifest_sha256 for dataset in all_roots)
    if len(set(manifests)) != len(manifests):
        raise BattleControlModelError("control lineage partitions must be disjoint")
    source_models = {dataset.source_model_sha256 for dataset in all_roots}
    if len(source_models) != 1:
        raise BattleControlModelError("control lineages were collected from different move models")
    train = tuple(row for dataset in training_roots for row in control_examples(dataset))
    validation = tuple(
        row for dataset in validation_roots for row in control_examples(dataset)
    )
    train_classes = {CONTROL_CLASS_REFS[row.class_index] for row in train}
    validation_classes = {CONTROL_CLASS_REFS[row.class_index] for row in validation}
    if not validation_classes <= train_classes:
        missing = sorted(validation_classes - train_classes)
        raise BattleControlModelError(
            f"validation contains action classes absent from training: {missing!r}"
        )
    model = BattleControlMLP.fit(
        train,
        seed=seed,
        hidden_units=hidden_units,
        epochs=epochs,
        learning_rate=learning_rate,
        l2=l2,
        class_balance_power=class_balance_power,
    )
    return BattleControlCandidate(
        model=model,
        training=evaluate_control_model(model, train),
        validation=evaluate_control_model(model, validation),
        validation_battle_plan_ids=(),
        training_artifact_ids=tuple(dataset.artifact_id for dataset in training_roots),
        validation_artifact_ids=tuple(dataset.artifact_id for dataset in validation_roots),
        source_manifest_sha256s=manifests,
        training_switch_targets=evaluate_switch_target_resolution(
            label for dataset in training_roots for label in dataset.labels
        ),
        validation_switch_targets=evaluate_switch_target_resolution(
            label for dataset in validation_roots for label in dataset.labels
        ),
    )
