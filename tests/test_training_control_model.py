from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from pokemon_red_completion.training_control import (
    TRAINING_CONTROL_CLASS_REFS,
    TRAINING_CONTROL_FEATURE_NAMES,
    TrainingControlAction,
    TrainingControlObservation,
    TrainingControlPhase,
)
from pokemon_red_completion.training_control_dataset import (
    TrainingControlDataset,
    TrainingControlExample,
)
from pokemon_red_completion.training_control_model import (
    TrainingControlMLP,
    TrainingControlModelError,
    fit_training_control_candidate,
)


def _observation(action: TrainingControlAction, variation: int) -> TrainingControlObservation:
    battle = action in {TrainingControlAction.FIGHT, TrainingControlAction.FLEE}
    phase = TrainingControlPhase.BATTLE if battle else TrainingControlPhase.OVERWORLD
    candidates = (
        (TrainingControlAction.FIGHT, TrainingControlAction.FLEE)
        if battle
        else (
            TrainingControlAction.SEEK,
            TrainingControlAction.HEAL,
            TrainingControlAction.STOP,
        )
    )
    values = np.zeros(len(TRAINING_CONTROL_FEATURE_NAMES), dtype=np.float64)
    values[0] = float(battle)
    values[1 + TRAINING_CONTROL_CLASS_REFS.index(action.value)] = 0.8
    values[-1] = variation / 100.0
    return TrainingControlObservation(phase, tuple(values), candidates)


def _dataset(lineage: str, partition: str, state: str) -> TrainingControlDataset:
    examples = []
    for action in TrainingControlAction:
        for variation in range(6):
            examples.append(
                TrainingControlExample(
                    lineage_id=lineage,
                    segment="balance",
                    decision_index=len(examples),
                    action=action,
                    observation=_observation(action, variation),
                    reason="synthetic separable example",
                )
            )
    return TrainingControlDataset(
        lineage_id=lineage,
        partition=partition,
        artifact_sha256=("a" if partition == "train" else "b") * 64,
        state_sha256=state * 64,
        source_commit="c" * 40,
        source_dirty=False,
        status="ok",
        error=None,
        examples=tuple(examples),
    )


def test_candidate_uses_whole_lineage_validation_and_class_balancing() -> None:
    candidate = fit_training_control_candidate(
        (_dataset("train-root", "train", "1"),),
        (_dataset("validation-root", "validation", "2"),),
        epochs=350,
        seed=1289,
    )

    assert candidate.training.balanced_accuracy > 0.99
    assert candidate.validation.balanced_accuracy > 0.99
    assert candidate.training_lineages == ("train-root",)
    assert candidate.validation_lineages == ("validation-root",)
    assert candidate.public_summary()["promotion_eligible"] is False


def test_prediction_masks_actions_illegal_in_the_current_phase() -> None:
    hidden = 2
    model = TrainingControlMLP(
        class_refs=TRAINING_CONTROL_CLASS_REFS,
        input_weights=np.zeros((hidden, len(TRAINING_CONTROL_FEATURE_NAMES))),
        hidden_bias=np.zeros(hidden),
        output_weights=np.zeros((hidden, len(TRAINING_CONTROL_CLASS_REFS))),
        # HEAL dominates globally but is illegal in battle; FIGHT is next.
        output_bias=np.asarray([0.0, 5.0, 1.0, 100.0, 0.0]),
    )
    battle = _observation(TrainingControlAction.FIGHT, 0)

    probabilities = model.probabilities(battle)

    assert probabilities["heal"] == 0.0
    assert model.predict(battle) is TrainingControlAction.FIGHT


def test_candidate_rejects_same_root_state_across_train_and_validation() -> None:
    train = _dataset("train-root", "train", "1")
    validation = _dataset("validation-root", "validation", "1")
    validation = replace(validation, artifact_sha256="d" * 64)

    with pytest.raises(TrainingControlModelError, match="state_overlap"):
        fit_training_control_candidate((train,), (validation,), epochs=2)
