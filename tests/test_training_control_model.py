from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from pokemon_red_completion.training_control import (
    TRAINING_CONTROL_CLASS_REFS,
    TRAINING_CONTROL_FEATURE_NAMES,
    TrainingControlAction,
    TrainingControlDecision,
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
    TrainingControlShadowAudit,
    fit_training_control_candidate,
    load_training_control_model,
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
    assert candidate.validation.genuine_examples == 30
    assert candidate.validation.genuine_accuracy > 0.99
    assert candidate.validation.operational_errors == {
        "unnecessary_heal": 0,
        "missed_required_heal": 0,
        "premature_stop": 0,
        "missed_stop": 0,
    }
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

    referee_masked = replace(battle, candidate_actions=(TrainingControlAction.FLEE,))
    assert model.predict(referee_masked) is TrainingControlAction.FLEE


def test_fit_does_not_train_on_singleton_referee_decisions() -> None:
    shared = _observation(TrainingControlAction.FIGHT, 0)
    safe_fight = TrainingControlExample(
        lineage_id="train-root",
        segment="balance",
        decision_index=0,
        action=TrainingControlAction.FIGHT,
        observation=shared,
        reason="genuine choice",
    )
    forced_flees = tuple(
        TrainingControlExample(
            lineage_id="train-root",
            segment="balance",
            decision_index=index + 1,
            action=TrainingControlAction.FLEE,
            observation=replace(shared, candidate_actions=(TrainingControlAction.FLEE,)),
            reason="referee-only action",
        )
        for index in range(100)
    )

    model = TrainingControlMLP.fit((safe_fight, *forced_flees), epochs=100)

    assert model.predict(shared) is TrainingControlAction.FIGHT
    assert model.predict(forced_flees[0].observation) is TrainingControlAction.FLEE


def test_candidate_rejects_same_root_state_across_train_and_validation() -> None:
    train = _dataset("train-root", "train", "1")
    validation = _dataset("validation-root", "validation", "1")
    validation = replace(validation, artifact_sha256="d" * 64)

    with pytest.raises(TrainingControlModelError, match="state_overlap"):
        fit_training_control_candidate((train,), (validation,), epochs=2)


def test_private_model_loading_authenticates_and_round_trips(tmp_path: Path) -> None:
    candidate = fit_training_control_candidate(
        (_dataset("train-root", "train", "1"),),
        (_dataset("validation-root", "validation", "2"),),
        epochs=2,
    )
    path = tmp_path / "model.json"
    payload = json.dumps(candidate.model.to_dict(), sort_keys=True).encode()
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    loaded = load_training_control_model(path, expected_sha256=digest)

    assert loaded.to_dict() == candidate.model.to_dict()
    path.write_bytes(payload + b"\n")
    with pytest.raises(TrainingControlModelError, match="authentication"):
        load_training_control_model(path, expected_sha256=digest)


def test_shadow_audit_observes_without_model_authority() -> None:
    hidden = 2
    model = TrainingControlMLP(
        class_refs=TRAINING_CONTROL_CLASS_REFS,
        input_weights=np.zeros((hidden, len(TRAINING_CONTROL_FEATURE_NAMES))),
        hidden_bias=np.zeros(hidden),
        output_weights=np.zeros((hidden, len(TRAINING_CONTROL_CLASS_REFS))),
        output_bias=np.asarray([5.0, 5.0, 1.0, 1.0, 0.0]),
    )
    audit = TrainingControlShadowAudit(model)
    for index, action in enumerate((TrainingControlAction.SEEK, TrainingControlAction.FLEE)):
        audit.observe(
            TrainingControlDecision(index, action, _observation(action, index), "teacher")
        )

    summary = audit.public_dict()
    assert summary["decisions"] == 2
    assert summary["agreements"] == 1
    assert summary["accuracy"] == 0.5
    assert summary["balanced_accuracy"] == 0.5
    assert summary["forced_decisions"] == 0
    assert summary["genuine_decisions"] == 2
    assert summary["genuine_accuracy"] == 0.5
    assert summary["candidate_counts"] == {"fight/flee": 1, "seek/heal/stop": 1}
    assert summary["operational_errors"] == {
        "unnecessary_heal": 0,
        "missed_required_heal": 0,
        "premature_stop": 0,
        "missed_stop": 0,
    }
    assert summary["model_had_execution_authority"] is False
