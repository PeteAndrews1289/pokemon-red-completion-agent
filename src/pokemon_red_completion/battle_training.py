"""Deterministic diagnostic training for the transferable battle move ranker."""

from __future__ import annotations

import hashlib
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


@dataclass(frozen=True, slots=True)
class BattleTrainingConfig:
    """Frozen optimizer and grouping configuration for one diagnostic run."""

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

    def public_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "folds": self.folds,
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "l2": self.l2,
            "split_unit": "diagnostic_battle_group",
        }


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
