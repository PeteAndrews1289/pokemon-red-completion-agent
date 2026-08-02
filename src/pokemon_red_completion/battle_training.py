"""Deterministic diagnostic training for the transferable battle move ranker."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from pokemon_red_completion.battle_dataset import (
    BattleDecisionExample,
    BattleEpisodeDataset,
    grouped_diagnostic_folds,
)
from pokemon_red_completion.battle_model import (
    BattleChoiceExample,
    MaskedLinearMoveRanker,
    choice_accuracy,
    mean_listwise_cross_entropy,
)


class BattleTrainingError(RuntimeError):
    """Raised when a battle training run cannot produce reproducible diagnostics."""


BATTLE_VALIDATION_MIN_SELECTIVE_ACCURACY = 0.80
BATTLE_VALIDATION_MIN_SELECTIVE_COVERAGE = 0.20


@dataclass(frozen=True, slots=True)
class BattleTrainingConfig:
    """Frozen optimizer configuration shared by diagnostic and assigned lanes."""

    seed: int = 1289
    folds: int = 5
    epochs: int = 300
    learning_rate: float = 0.03
    l2: float = 1e-4

    def __post_init__(self) -> None:
        for field_name in ("seed", "folds", "epochs"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise BattleTrainingError(f"{field_name} must be a non-negative integer")
        if self.folds < 2:
            raise BattleTrainingError("folds must be at least two")
        if self.epochs < 1:
            raise BattleTrainingError("epochs must be at least one")
        for field_name in ("learning_rate", "l2"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise BattleTrainingError(f"{field_name} must be finite")
            if not math.isfinite(float(value)):
                raise BattleTrainingError(f"{field_name} must be finite")
        if self.learning_rate <= 0:
            raise BattleTrainingError("learning_rate must be positive")
        if self.l2 < 0:
            raise BattleTrainingError("l2 must be non-negative")

    def public_dict(
        self,
        *,
        split_unit: str = "diagnostic_battle_group",
    ) -> dict[str, object]:
        if split_unit not in {"diagnostic_battle_group", "preassigned_root_lineage"}:
            raise BattleTrainingError("training split unit is unsupported")
        payload: dict[str, object] = {
            "seed": self.seed,
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "l2": self.l2,
            "split_unit": split_unit,
        }
        if split_unit == "diagnostic_battle_group":
            payload["folds"] = self.folds
        return payload


@dataclass(frozen=True, slots=True)
class BattleFoldMetrics:
    """Aggregate-only metrics for one whole-group cross-validation fold."""

    fold_index: int
    train_decisions: int
    test_decisions: int
    train_groups: int
    test_groups: int
    accuracy: float
    cross_entropy: float
    majority_accuracy: float

    def public_dict(self) -> dict[str, object]:
        return {
            "fold_index": self.fold_index,
            "train_decisions": self.train_decisions,
            "test_decisions": self.test_decisions,
            "train_groups": self.train_groups,
            "test_groups": self.test_groups,
            "accuracy": self.accuracy,
            "cross_entropy": self.cross_entropy,
            "majority_accuracy": self.majority_accuracy,
        }


@dataclass(frozen=True, slots=True)
class BattleDiagnosticResult:
    """A fitted private model plus leakage-resistant diagnostic evidence."""

    model: MaskedLinearMoveRanker
    config: BattleTrainingConfig
    dataset_manifest_sha256: str
    decisions: int
    groups: int
    folds: tuple[BattleFoldMetrics, ...]
    accuracy: float
    macro_f1: float
    per_slot_recall: tuple[float | None, ...]
    cross_entropy: float
    majority_accuracy: float
    training_accuracy: float
    legal_choice_rate: float
    free_choice_decisions: int
    forced_choice_decisions: int
    unobserved_context_decisions: int
    free_choice_accuracy: float | None
    forced_choice_accuracy: float | None
    model_sha256: str
    promotion_eligible: bool
    reasons: tuple[str, ...]

    def public_receipt(self) -> dict[str, object]:
        return {
            "schema": "battle-imitation-diagnostic-v1",
            "status": "complete",
            "scope": {
                "decisions": self.decisions,
                "groups": self.groups,
                "source_episodes": 1,
                "source_root_lineages": 1,
                "free_choice_decisions": self.free_choice_decisions,
                "forced_choice_decisions": self.forced_choice_decisions,
                "unobserved_context_decisions": self.unobserved_context_decisions,
            },
            "dataset_manifest_sha256": self.dataset_manifest_sha256,
            "model": {
                "model_id": self.model.model_id,
                "feature_schema_id": self.model.feature_schema_id,
                "feature_count": len(self.model.feature_names),
                "sha256": self.model_sha256,
                "serialization": "canonical_json",
            },
            "training": self.config.public_dict(),
            "metrics": {
                "accuracy": self.accuracy,
                "macro_f1": self.macro_f1,
                "per_slot_recall": list(self.per_slot_recall),
                "cross_entropy": self.cross_entropy,
                "majority_accuracy": self.majority_accuracy,
                "training_accuracy": self.training_accuracy,
                "legal_choice_rate": self.legal_choice_rate,
                "free_choice_accuracy": self.free_choice_accuracy,
                "forced_choice_accuracy": self.forced_choice_accuracy,
                "folds": [fold.public_dict() for fold in self.folds],
            },
            "qualification": {
                "promotion_eligible": self.promotion_eligible,
                "held_out_evaluation": False,
                "learned_policy_rollout": False,
                "reasons": list(self.reasons),
            },
        }


@dataclass(frozen=True, slots=True)
class BattleConfidenceSelection:
    """Validation-only threshold for optional teacher fallback or abstention."""

    threshold: float | None
    target_accuracy: float
    accuracy: float | None
    coverage: float
    eligible: bool

    def public_dict(self) -> dict[str, object]:
        return {
            "threshold": self.threshold,
            "target_accuracy": self.target_accuracy,
            "accuracy": self.accuracy,
            "coverage": self.coverage,
            "minimum_coverage": BATTLE_VALIDATION_MIN_SELECTIVE_COVERAGE,
            "eligible": self.eligible,
            "selection_partition": "validation",
            "selection_population": "free_choice_decisions",
        }


@dataclass(frozen=True, slots=True)
class BattlePreassignedValidationResult:
    """A train-only model evaluated on preregistered validation lineages."""

    model: MaskedLinearMoveRanker
    config: BattleTrainingConfig
    corpus_manifest_roster_sha256: str
    train_episodes: int
    train_root_lineages: int
    train_decisions: int
    train_groups: int
    validation_episodes: int
    validation_root_lineages: int
    validation_decisions: int
    validation_groups: int
    visible_snapshot_overlap_count: int
    novel_visible_decisions: int
    accuracy: float
    macro_f1: float
    per_slot_recall: tuple[float | None, ...]
    cross_entropy: float
    uniform_legal_cross_entropy: float
    majority_accuracy: float
    training_accuracy: float
    legal_choice_rate: float
    free_choice_decisions: int
    forced_choice_decisions: int
    unobserved_context_decisions: int
    free_choice_accuracy: float | None
    free_choice_majority_accuracy: float | None
    forced_choice_accuracy: float | None
    novel_visible_accuracy: float | None
    novel_visible_cross_entropy: float | None
    confidence: BattleConfidenceSelection
    model_sha256: str
    freeze_eligible: bool
    reasons: tuple[str, ...]

    def public_receipt(self) -> dict[str, object]:
        return {
            "schema": "battle-imitation-preassigned-validation-v1",
            "status": "complete",
            "scope": {
                "train_episodes": self.train_episodes,
                "train_root_lineages": self.train_root_lineages,
                "train_decisions": self.train_decisions,
                "train_groups": self.train_groups,
                "validation_episodes": self.validation_episodes,
                "validation_root_lineages": self.validation_root_lineages,
                "validation_decisions": self.validation_decisions,
                "validation_groups": self.validation_groups,
                "free_choice_decisions": self.free_choice_decisions,
                "forced_choice_decisions": self.forced_choice_decisions,
                "unobserved_context_decisions": self.unobserved_context_decisions,
                "visible_snapshot_overlap_count": self.visible_snapshot_overlap_count,
                "novel_visible_decisions": self.novel_visible_decisions,
            },
            "corpus_manifest_roster_sha256": self.corpus_manifest_roster_sha256,
            "model": {
                "model_id": self.model.model_id,
                "feature_schema_id": self.model.feature_schema_id,
                "feature_count": len(self.model.feature_names),
                "sha256": self.model_sha256,
                "serialization": "canonical_json",
            },
            "training": self.config.public_dict(split_unit="preassigned_root_lineage"),
            "validation": {
                "accuracy": self.accuracy,
                "macro_f1": self.macro_f1,
                "per_slot_recall": list(self.per_slot_recall),
                "cross_entropy": self.cross_entropy,
                "uniform_legal_cross_entropy": self.uniform_legal_cross_entropy,
                "majority_accuracy": self.majority_accuracy,
                "training_accuracy": self.training_accuracy,
                "legal_choice_rate": self.legal_choice_rate,
                "free_choice_accuracy": self.free_choice_accuracy,
                "free_choice_majority_accuracy": self.free_choice_majority_accuracy,
                "forced_choice_accuracy": self.forced_choice_accuracy,
                "novel_visible_accuracy": self.novel_visible_accuracy,
                "novel_visible_cross_entropy": self.novel_visible_cross_entropy,
                "confidence": self.confidence.public_dict(),
            },
            "qualification": {
                "freeze_eligible": self.freeze_eligible,
                "held_out_validation": True,
                "test_partition_opened": False,
                "held_out_test_evaluation": False,
                "learned_policy_rollout": False,
                "promotion_eligible": False,
                "reasons": list(self.reasons),
            },
        }


def train_diagnostic_battle_ranker(
    dataset: BattleEpisodeDataset,
    *,
    config: BattleTrainingConfig | None = None,
) -> BattleDiagnosticResult:
    """Fit a ranker and evaluate it with whole-group diagnostic cross-validation.

    This function never upgrades the evidence to held-out status.  A single recorded
    root lineage cannot become held out after collection, regardless of how rows are
    divided.
    """

    if not isinstance(dataset, BattleEpisodeDataset):
        raise TypeError("dataset must be a BattleEpisodeDataset")
    if config is None:
        config = BattleTrainingConfig()
    if not isinstance(config, BattleTrainingConfig):
        raise TypeError("config must be a BattleTrainingConfig")
    choices = tuple(_choice(example) for example in dataset.examples)
    folds = grouped_diagnostic_folds(dataset, fold_count=config.folds)

    true_slots: list[int] = []
    predicted_slots: list[int] = []
    baseline_slots: list[int] = []
    free_true_slots: list[int] = []
    free_predicted_slots: list[int] = []
    forced_true_slots: list[int] = []
    forced_predicted_slots: list[int] = []
    unobserved_context_decisions = 0
    total_loss = 0.0
    total_test = 0
    legal_predictions = 0
    fold_metrics: list[BattleFoldMetrics] = []

    for fold_index, fold in enumerate(folds):
        train_choices = tuple(choices[index] for index in fold.train_indices)
        test_choices = tuple(choices[index] for index in fold.test_indices)
        model = _fit(
            dataset.feature_names,
            train_choices,
            config=config,
            seed=config.seed + fold_index,
        )
        fold_predictions: list[int] = []
        fold_truth: list[int] = []
        majority_slot = _majority_slot(dataset.examples[index] for index in fold.train_indices)
        fold_baseline: list[int] = []

        for index in fold.test_indices:
            example = dataset.examples[index]
            choice = choices[index]
            predicted_candidate = model.predict(
                choice.candidate_features,
                legal_mask=choice.legal_mask,
                current_pp=choice.current_pp,
            )
            predicted_slot = example.features.slot_indices[predicted_candidate]
            true_slot = example.features.slot_indices[choice.chosen_index]
            baseline_slot = _legal_baseline_slot(example, majority_slot)
            fold_predictions.append(predicted_slot)
            fold_truth.append(true_slot)
            fold_baseline.append(baseline_slot)
            if example.policy_context is None:
                unobserved_context_decisions += 1
            elif example.policy_context.forced_choice:
                forced_true_slots.append(true_slot)
                forced_predicted_slots.append(predicted_slot)
            else:
                free_true_slots.append(true_slot)
                free_predicted_slots.append(predicted_slot)
            if choice.usable_mask[predicted_candidate]:
                legal_predictions += 1

        fold_accuracy = _accuracy(fold_truth, fold_predictions)
        fold_majority = _accuracy(fold_truth, fold_baseline)
        fold_loss = mean_listwise_cross_entropy(model, test_choices)
        fold_metrics.append(
            BattleFoldMetrics(
                fold_index=fold_index,
                train_decisions=len(fold.train_indices),
                test_decisions=len(fold.test_indices),
                train_groups=fold.train_groups,
                test_groups=fold.test_groups,
                accuracy=fold_accuracy,
                cross_entropy=fold_loss,
                majority_accuracy=fold_majority,
            )
        )
        true_slots.extend(fold_truth)
        predicted_slots.extend(fold_predictions)
        baseline_slots.extend(fold_baseline)
        total_loss += fold_loss * len(fold.test_indices)
        total_test += len(fold.test_indices)

    final_model = _fit(
        dataset.feature_names,
        choices,
        config=config,
        seed=config.seed,
    )
    reasons = set(dataset.diagnostic_reasons)
    reasons.add("single_recorded_root_lineage")
    reasons.add("grouped_cross_validation_is_not_held_out")
    model_json = final_model.to_json().encode("ascii")
    return BattleDiagnosticResult(
        model=final_model,
        config=config,
        dataset_manifest_sha256=dataset.manifest_sha256,
        decisions=len(dataset.examples),
        groups=len(dataset.group_ids),
        folds=tuple(fold_metrics),
        accuracy=_accuracy(true_slots, predicted_slots),
        macro_f1=_macro_f1(true_slots, predicted_slots, labels=(0, 1, 2, 3)),
        per_slot_recall=_per_label_recall(
            true_slots,
            predicted_slots,
            labels=(0, 1, 2, 3),
        ),
        cross_entropy=total_loss / total_test,
        majority_accuracy=_accuracy(true_slots, baseline_slots),
        training_accuracy=choice_accuracy(final_model, choices),
        legal_choice_rate=legal_predictions / total_test,
        free_choice_decisions=len(free_true_slots),
        forced_choice_decisions=len(forced_true_slots),
        unobserved_context_decisions=unobserved_context_decisions,
        free_choice_accuracy=_optional_accuracy(
            free_true_slots,
            free_predicted_slots,
        ),
        forced_choice_accuracy=_optional_accuracy(
            forced_true_slots,
            forced_predicted_slots,
        ),
        model_sha256=hashlib.sha256(model_json).hexdigest(),
        promotion_eligible=False,
        reasons=tuple(sorted(reasons)),
    )


def train_preassigned_battle_ranker(
    train_datasets: Sequence[BattleEpisodeDataset],
    validation_datasets: Sequence[BattleEpisodeDataset],
    *,
    config: BattleTrainingConfig | None = None,
) -> BattlePreassignedValidationResult:
    """Fit on declared train roots and evaluate only on declared validation roots.

    This lane deliberately has no test-dataset parameter.  Test episodes remain
    sealed until the returned model, optimizer configuration, and confidence
    threshold have been frozen into a separately authenticated artifact.
    """

    train = tuple(train_datasets)
    validation = tuple(validation_datasets)
    if config is None:
        config = BattleTrainingConfig()
    if not isinstance(config, BattleTrainingConfig):
        raise TypeError("config must be a BattleTrainingConfig")
    _require_preassigned_corpus(train, validation)

    train_examples = tuple(example for dataset in train for example in dataset.examples)
    validation_examples = tuple(
        example for dataset in validation for example in dataset.examples
    )
    train_choices = tuple(_choice(example) for example in train_examples)
    validation_choices = tuple(_choice(example) for example in validation_examples)
    model = _fit(
        train[0].feature_names,
        train_choices,
        config=config,
        seed=config.seed,
    )
    majority_slot = _majority_slot(train_examples)

    truth: list[int] = []
    predictions: list[int] = []
    baseline: list[int] = []
    free_truth: list[int] = []
    free_predictions: list[int] = []
    free_baseline: list[int] = []
    forced_truth: list[int] = []
    forced_predictions: list[int] = []
    confidences: list[tuple[float, bool]] = []
    legal_predictions = 0
    unobserved_context_decisions = 0

    for example, choice in zip(validation_examples, validation_choices, strict=True):
        probabilities = model.predict_proba(
            choice.candidate_features,
            legal_mask=choice.legal_mask,
            current_pp=choice.current_pp,
        )
        predicted_candidate = int(np.argmax(probabilities))
        predicted_slot = example.features.slot_indices[predicted_candidate]
        true_slot = example.features.slot_indices[choice.chosen_index]
        baseline_slot = _legal_baseline_slot(example, majority_slot)
        truth.append(true_slot)
        predictions.append(predicted_slot)
        baseline.append(baseline_slot)
        if choice.usable_mask[predicted_candidate]:
            legal_predictions += 1
        if example.policy_context is None:
            unobserved_context_decisions += 1
        elif example.policy_context.forced_choice:
            forced_truth.append(true_slot)
            forced_predictions.append(predicted_slot)
        else:
            free_truth.append(true_slot)
            free_predictions.append(predicted_slot)
            free_baseline.append(baseline_slot)
            confidences.append(
                (
                    float(probabilities[predicted_candidate]),
                    predicted_slot == true_slot,
                )
            )

    train_snapshots = frozenset(
        example.snapshot_sha256 for example in train_examples
    )
    validation_snapshots = frozenset(
        example.snapshot_sha256 for example in validation_examples
    )
    novel_indices = tuple(
        index
        for index, example in enumerate(validation_examples)
        if example.snapshot_sha256 not in train_snapshots
    )
    novel_truth = tuple(truth[index] for index in novel_indices)
    novel_predictions = tuple(predictions[index] for index in novel_indices)
    novel_choices = tuple(validation_choices[index] for index in novel_indices)

    accuracy = _accuracy(truth, predictions)
    majority_accuracy = _accuracy(truth, baseline)
    cross_entropy = mean_listwise_cross_entropy(model, validation_choices)
    uniform_cross_entropy = math.fsum(
        math.log(int(np.count_nonzero(choice.usable_mask)))
        for choice in validation_choices
    ) / len(validation_choices)
    free_accuracy = _optional_accuracy(free_truth, free_predictions)
    free_majority_accuracy = _optional_accuracy(free_truth, free_baseline)
    confidence = _select_confidence_threshold(
        confidences,
        baseline_accuracy=free_majority_accuracy,
    )
    reasons: set[str] = set()
    if legal_predictions != len(validation_choices):
        reasons.add("validation_prediction_not_legal")
    if unobserved_context_decisions:
        reasons.add("validation_policy_context_unobserved")
    if accuracy <= majority_accuracy:
        reasons.add("validation_accuracy_not_above_majority")
    if cross_entropy >= uniform_cross_entropy:
        reasons.add("validation_cross_entropy_not_below_uniform")
    if free_accuracy is None or free_majority_accuracy is None:
        reasons.add("validation_free_choice_population_missing")
    elif free_accuracy <= free_majority_accuracy:
        reasons.add("validation_free_choice_not_above_majority")
    if not confidence.eligible:
        reasons.add("validation_confidence_threshold_not_qualified")

    roster_payload = json.dumps(
        {
            "schema": "battle-preassigned-corpus-roster-v1",
            "train_manifest_sha256": sorted(dataset.manifest_sha256 for dataset in train),
            "validation_manifest_sha256": sorted(
                dataset.manifest_sha256 for dataset in validation
            ),
        },
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    model_sha256 = hashlib.sha256(model.to_json().encode("ascii")).hexdigest()
    return BattlePreassignedValidationResult(
        model=model,
        config=config,
        corpus_manifest_roster_sha256=hashlib.sha256(roster_payload).hexdigest(),
        train_episodes=len(train),
        train_root_lineages=len({dataset.root_lineage_id for dataset in train}),
        train_decisions=len(train_examples),
        train_groups=len({example.group_id for example in train_examples}),
        validation_episodes=len(validation),
        validation_root_lineages=len(
            {dataset.root_lineage_id for dataset in validation}
        ),
        validation_decisions=len(validation_examples),
        validation_groups=len(
            {example.group_id for example in validation_examples}
        ),
        visible_snapshot_overlap_count=len(train_snapshots & validation_snapshots),
        novel_visible_decisions=len(novel_indices),
        accuracy=accuracy,
        macro_f1=_macro_f1(truth, predictions, labels=(0, 1, 2, 3)),
        per_slot_recall=_per_label_recall(
            truth,
            predictions,
            labels=(0, 1, 2, 3),
        ),
        cross_entropy=cross_entropy,
        uniform_legal_cross_entropy=uniform_cross_entropy,
        majority_accuracy=majority_accuracy,
        training_accuracy=choice_accuracy(model, train_choices),
        legal_choice_rate=legal_predictions / len(validation_choices),
        free_choice_decisions=len(free_truth),
        forced_choice_decisions=len(forced_truth),
        unobserved_context_decisions=unobserved_context_decisions,
        free_choice_accuracy=free_accuracy,
        free_choice_majority_accuracy=free_majority_accuracy,
        forced_choice_accuracy=_optional_accuracy(forced_truth, forced_predictions),
        novel_visible_accuracy=_optional_accuracy(novel_truth, novel_predictions),
        novel_visible_cross_entropy=(
            mean_listwise_cross_entropy(model, novel_choices)
            if novel_choices
            else None
        ),
        confidence=confidence,
        model_sha256=model_sha256,
        freeze_eligible=not reasons,
        reasons=tuple(sorted(reasons)),
    )


def _require_preassigned_corpus(
    train: tuple[BattleEpisodeDataset, ...],
    validation: tuple[BattleEpisodeDataset, ...],
) -> None:
    if not train or not validation:
        raise BattleTrainingError("preassigned training requires train and validation episodes")
    datasets = (*train, *validation)
    if any(not isinstance(dataset, BattleEpisodeDataset) for dataset in datasets):
        raise TypeError("preassigned corpora must contain BattleEpisodeDataset values")
    for dataset in train:
        if dataset.partition != "train":
            raise BattleTrainingError("train corpus contains a non-train episode")
    for dataset in validation:
        if dataset.partition != "validation":
            raise BattleTrainingError("validation corpus contains a non-validation episode")
    if any(not dataset.episode_qualified for dataset in datasets):
        raise BattleTrainingError("preassigned corpus contains an unqualified episode")
    if any(
        example.policy_context is None
        for dataset in datasets
        for example in dataset.examples
    ):
        raise BattleTrainingError("preassigned corpus lacks observed policy context")
    expected_game = train[0].game_id
    expected_features = train[0].feature_names
    if any(dataset.game_id != expected_game for dataset in datasets):
        raise BattleTrainingError("preassigned corpus mixes game identities")
    if any(dataset.feature_names != expected_features for dataset in datasets):
        raise BattleTrainingError("preassigned corpus mixes feature schemas")
    for values, label in (
        ((dataset.episode_id for dataset in datasets), "episode identity"),
        ((dataset.manifest_sha256 for dataset in datasets), "episode manifest"),
        ((dataset.root_lineage_id for dataset in datasets), "root lineage"),
    ):
        materialized = tuple(values)
        if len(set(materialized)) != len(materialized):
            raise BattleTrainingError(f"preassigned corpus reuses an {label}")


def _select_confidence_threshold(
    decisions: Sequence[tuple[float, bool]],
    *,
    baseline_accuracy: float | None,
) -> BattleConfidenceSelection:
    target = min(
        1.0,
        max(
            BATTLE_VALIDATION_MIN_SELECTIVE_ACCURACY,
            (baseline_accuracy or 0.0) + 0.05,
        ),
    )
    if not decisions:
        return BattleConfidenceSelection(None, target, None, 0.0, False)
    candidates: list[tuple[float, float, float]] = []
    for threshold in sorted({confidence for confidence, _ in decisions}):
        selected = tuple(correct for confidence, correct in decisions if confidence >= threshold)
        coverage = len(selected) / len(decisions)
        accuracy = sum(selected) / len(selected)
        if (
            coverage >= BATTLE_VALIDATION_MIN_SELECTIVE_COVERAGE
            and accuracy >= target
        ):
            candidates.append((coverage, accuracy, threshold))
    if not candidates:
        return BattleConfidenceSelection(None, target, None, 0.0, False)
    coverage, accuracy, threshold = max(
        candidates,
        key=lambda item: (item[0], item[1], -item[2]),
    )
    return BattleConfidenceSelection(threshold, target, accuracy, coverage, True)


def _choice(example: BattleDecisionExample) -> BattleChoiceExample:
    return BattleChoiceExample(
        np.asarray(example.features.candidate_vectors, dtype=np.float64),
        np.asarray(example.features.legal_mask, dtype=np.bool_),
        np.asarray(example.features.current_pp, dtype=np.float64),
        example.chosen_candidate_index,
    )


def _fit(
    feature_names: Sequence[str],
    choices: Sequence[BattleChoiceExample],
    *,
    config: BattleTrainingConfig,
    seed: int,
) -> MaskedLinearMoveRanker:
    return MaskedLinearMoveRanker.fit(
        feature_names=feature_names,
        examples=choices,
        seed=seed,
        epochs=config.epochs,
        learning_rate=config.learning_rate,
        l2=config.l2,
    )


def _majority_slot(examples: Iterable[BattleDecisionExample]) -> int:
    counts: Counter[int] = Counter(
        example.features.slot_indices[example.chosen_candidate_index] for example in examples
    )
    if not counts:
        raise BattleTrainingError("majority baseline requires training examples")
    return min(counts, key=lambda slot: (-counts[slot], slot))


def _legal_baseline_slot(example: BattleDecisionExample, preferred_slot: int) -> int:
    candidates = [
        (slot, pp)
        for slot, legal, pp in zip(
            example.features.slot_indices,
            example.features.legal_mask,
            example.features.current_pp,
            strict=True,
        )
        if legal and pp > 0
    ]
    if not candidates:
        raise BattleTrainingError("battle example has no usable candidate")
    if any(slot == preferred_slot for slot, _ in candidates):
        return preferred_slot
    return min(slot for slot, _ in candidates)


def _accuracy(truth: Sequence[int], predictions: Sequence[int]) -> float:
    if not truth or len(truth) != len(predictions):
        raise BattleTrainingError("accuracy requires equally sized non-empty sequences")
    correct = sum(actual == predicted for actual, predicted in zip(truth, predictions, strict=True))
    return correct / len(truth)


def _optional_accuracy(
    truth: Sequence[int],
    predictions: Sequence[int],
) -> float | None:
    if not truth and not predictions:
        return None
    return _accuracy(truth, predictions)


def _per_label_recall(
    truth: Sequence[int],
    predictions: Sequence[int],
    *,
    labels: Sequence[int],
) -> tuple[float | None, ...]:
    recalls: list[float | None] = []
    for label in labels:
        support = sum(actual == label for actual in truth)
        if support == 0:
            recalls.append(None)
            continue
        true_positive = sum(
            actual == label and predicted == label
            for actual, predicted in zip(truth, predictions, strict=True)
        )
        recalls.append(true_positive / support)
    return tuple(recalls)


def _macro_f1(
    truth: Sequence[int],
    predictions: Sequence[int],
    *,
    labels: Sequence[int],
) -> float:
    scores: list[float] = []
    for label in labels:
        true_positive = sum(
            actual == label and predicted == label
            for actual, predicted in zip(truth, predictions, strict=True)
        )
        false_positive = sum(
            actual != label and predicted == label
            for actual, predicted in zip(truth, predictions, strict=True)
        )
        false_negative = sum(
            actual == label and predicted != label
            for actual, predicted in zip(truth, predictions, strict=True)
        )
        denominator = 2 * true_positive + false_positive + false_negative
        scores.append(0.0 if denominator == 0 else (2 * true_positive) / denominator)
    return math.fsum(scores) / len(scores)
