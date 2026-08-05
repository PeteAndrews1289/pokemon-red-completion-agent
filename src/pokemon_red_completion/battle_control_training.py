"""Dataset projection and group-held-out training for full-battle control."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pokemon_red_completion.battle_control_features import (
    CONTROL_CLASS_REFS,
    BattleControlExample,
    control_class_ref,
    project_control_features,
)
from pokemon_red_completion.battle_control_labels import BattleControlDataset
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
class BattleControlCandidate:
    model: BattleControlMLP
    training: BattleControlMetrics
    validation: BattleControlMetrics
    validation_battle_plan_ids: tuple[str, ...]
    training_artifact_ids: tuple[str, ...]
    validation_artifact_ids: tuple[str, ...]
    source_manifest_sha256s: tuple[str, ...]

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
        }


def control_examples(dataset: BattleControlDataset) -> tuple[BattleControlExample, ...]:
    """Project every authenticated label without using objective or game IDs as features."""

    projector = BattleFeatureProjector(PokemonRedBattleCatalog())
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
            ),
            class_index=CONTROL_CLASS_REFS.index(control_class_ref(label.teacher_action)),
            battle_plan_id=label.battle_plan_id,
            decision_index=label.decision_index,
        ))
    return tuple(examples)


def fit_group_heldout_control_candidate(
    dataset: BattleControlDataset,
    *,
    validation_battle_plan_ids: Iterable[str],
    seed: int = 0,
    hidden_units: int = 24,
    epochs: int = 500,
    learning_rate: float = 0.01,
    l2: float = 1e-4,
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
    )
    return BattleControlCandidate(
        model=model,
        training=evaluate_control_model(model, train),
        validation=evaluate_control_model(model, validation),
        validation_battle_plan_ids=validation_groups,
        training_artifact_ids=(dataset.artifact_id,),
        validation_artifact_ids=(dataset.artifact_id,),
        source_manifest_sha256s=(dataset.manifest_sha256,),
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
    )
    return BattleControlCandidate(
        model=model,
        training=evaluate_control_model(model, train),
        validation=evaluate_control_model(model, validation),
        validation_battle_plan_ids=(),
        training_artifact_ids=tuple(dataset.artifact_id for dataset in training_roots),
        validation_artifact_ids=tuple(dataset.artifact_id for dataset in validation_roots),
        source_manifest_sha256s=manifests,
    )
