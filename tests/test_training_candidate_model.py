from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from pokemon_red_completion.training_candidate_dataset import TrainingCandidateExample
from pokemon_red_completion.training_candidate_model import (
    CandidateShapeBaseline,
    TrainingCandidateMLP,
    TrainingCandidateModelError,
    TrainingCandidateShadowAudit,
    canonical_training_candidate_model_sha256,
    evaluate_training_candidate_model,
    load_training_candidate_model,
)
from pokemon_red_completion.training_candidate_rank import (
    TRAINING_CANDIDATE_FEATURE_NAMES,
    TrainingCandidate,
    TrainingCandidateDecision,
    TrainingCandidateSet,
    TrainingChoiceKind,
)


def _example(
    index: int,
    kind: TrainingChoiceKind,
    values: tuple[float, ...],
    *,
    select_highest: bool,
) -> TrainingCandidateExample:
    feature_name = (
        "candidate.level"
        if kind is TrainingChoiceKind.TRAINEE
        else "venue.minimum_level"
    )
    feature_index = TRAINING_CANDIDATE_FEATURE_NAMES.index(feature_name)
    candidates = []
    for candidate_index, value in enumerate(values):
        features = [0.0] * len(TRAINING_CANDIDATE_FEATURE_NAMES)
        features[0] = float(kind is TrainingChoiceKind.TRAINEE)
        features[feature_index] = value
        candidates.append(TrainingCandidate(candidate_index, tuple(features)))
    selected = int(np.argmax(values) if select_highest else np.argmin(values))
    return TrainingCandidateExample(
        lineage_id="synthetic",
        segment="balance",
        decision_index=index,
        selected_candidate_index=selected,
        observation=TrainingCandidateSet(kind, tuple(candidates)),
        reason="synthetic",
    )


def _examples() -> tuple[TrainingCandidateExample, ...]:
    rows: list[TrainingCandidateExample] = []
    for index in range(80):
        low = 0.1 + (index % 5) * 0.02
        high = 0.7 + (index % 7) * 0.02
        trainee_values = (low, high) if index % 2 else (high, low)
        venue_values = (
            (low, 0.4, high) if index % 3 else (high, low, 0.4)
        )
        rows.append(
            _example(
                len(rows),
                TrainingChoiceKind.TRAINEE,
                trainee_values,
                select_highest=False,
            )
        )
        rows.append(
            _example(
                len(rows),
                TrainingChoiceKind.VENUE,
                venue_values,
                select_highest=True,
            )
        )
    return tuple(rows)


def test_shared_scorer_learns_two_state_dependent_choice_kinds() -> None:
    examples = _examples()
    baseline = CandidateShapeBaseline.fit(examples)

    model = TrainingCandidateMLP.fit(
        examples,
        hidden_units=8,
        epochs=300,
        learning_rate=0.02,
        seed=1289,
    )
    metrics = evaluate_training_candidate_model(model, examples, baseline=baseline)

    assert metrics.accuracy == 1.0
    assert metrics.correct == metrics.examples
    assert metrics.shape_baseline_correct < metrics.examples
    assert metrics.genuine_accuracy == 1.0
    assert metrics.genuine_correct == metrics.multi_candidate_examples
    assert (
        metrics.genuine_shape_baseline_correct < metrics.multi_candidate_examples
    )
    assert metrics.shape_baseline_accuracy < 0.6
    assert metrics.genuine_shape_baseline_accuracy < 0.6
    assert dict(metrics.kind_accuracy) == {"trainee": 1.0, "venue": 1.0}
    assert dict(metrics.genuine_kind_accuracy) == {"trainee": 1.0, "venue": 1.0}
    assert metrics.candidate_count_results == ((2, 80, 80), (3, 80, 80))


def test_genuine_metrics_are_not_inflated_by_singleton_choices() -> None:
    genuine = _example(
        0,
        TrainingChoiceKind.TRAINEE,
        (0.8, 0.1),
        select_highest=False,
    )
    singletons = tuple(
        _example(
            index + 1,
            TrainingChoiceKind.VENUE,
            (0.5,),
            select_highest=True,
        )
        for index in range(99)
    )
    rows = (genuine, *singletons)
    width = len(TRAINING_CANDIDATE_FEATURE_NAMES)
    always_zero = TrainingCandidateMLP(
        weights1=np.zeros((width, 1)),
        bias1=np.zeros(1),
        weights2=np.zeros(1),
        feature_mean=np.zeros(width),
        feature_scale=np.ones(width),
        training_seed=1,
    )

    metrics = evaluate_training_candidate_model(
        always_zero,
        rows,
        baseline=CandidateShapeBaseline.fit(rows),
    )

    assert metrics.accuracy == 0.99
    assert metrics.genuine_accuracy == 0.0
    assert metrics.genuine_shape_baseline_accuracy == 1.0


def test_candidate_scores_follow_candidates_when_the_set_is_permuted() -> None:
    examples = _examples()
    model = TrainingCandidateMLP.fit(examples, hidden_units=8, epochs=250, seed=1289)
    original = examples[1].observation
    reversed_candidates = tuple(
        TrainingCandidate(index, candidate.features)
        for index, candidate in enumerate(reversed(original.candidates))
    )
    reversed_observation = TrainingCandidateSet(original.kind, reversed_candidates)

    assert model.predict(original) == 0
    assert model.predict(reversed_observation) == 2
    assert np.allclose(
        model.probabilities(original)[::-1],
        model.probabilities(reversed_observation),
    )


def test_model_round_trip_preserves_scores_and_canonical_identity() -> None:
    examples = _examples()
    model = TrainingCandidateMLP.fit(examples, hidden_units=4, epochs=50, seed=7)
    restored = TrainingCandidateMLP.from_dict(model.to_dict())

    assert canonical_training_candidate_model_sha256(model) == (
        canonical_training_candidate_model_sha256(restored)
    )
    assert np.array_equal(
        model.probabilities(examples[0].observation),
        restored.probabilities(examples[0].observation),
    )


def test_fit_rejects_only_singleton_choices() -> None:
    example = _example(
        0,
        TrainingChoiceKind.VENUE,
        (0.5,),
        select_highest=True,
    )

    with pytest.raises(TrainingCandidateModelError, match="genuine choices"):
        TrainingCandidateMLP.fit((example,))


def test_file_loader_authenticates_the_exact_model(tmp_path) -> None:
    model = TrainingCandidateMLP.fit(_examples(), hidden_units=4, epochs=10, seed=7)
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(model.to_dict(), indent=2, sort_keys=True) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    restored = load_training_candidate_model(path, expected_sha256=digest)

    assert canonical_training_candidate_model_sha256(restored) == (
        canonical_training_candidate_model_sha256(model)
    )
    path.write_text(path.read_text() + " ")
    with pytest.raises(TrainingCandidateModelError, match="authentication"):
        load_training_candidate_model(path, expected_sha256=digest)


def test_candidate_shadow_audit_separates_genuine_choices_by_kind() -> None:
    examples = _examples()
    model = TrainingCandidateMLP.fit(examples, hidden_units=8, epochs=250, seed=1289)
    audit = TrainingCandidateShadowAudit(model)
    correct = examples[0]
    wrong = examples[1]
    wrong_prediction = model.predict(wrong.observation)
    wrong_label = (wrong_prediction + 1) % len(wrong.observation.candidates)
    audit.observe(
        TrainingCandidateDecision(
            0,
            correct.selected_candidate_index,
            correct.observation,
            "teacher",
        )
    )
    audit.observe(
        TrainingCandidateDecision(1, wrong_label, wrong.observation, "teacher")
    )

    summary = audit.public_dict()
    assert summary["decisions"] == 2
    assert summary["agreements"] == 1
    assert summary["disagreements"] == 1
    assert summary["genuine_decisions"] == 2
    assert summary["genuine_accuracy"] == 0.5
    assert summary["genuine_kind_counts"] == {"trainee": 1, "venue": 1}
    assert summary["genuine_kind_accuracy"] == {"trainee": 1.0, "venue": 0.0}
    assert summary["model_had_execution_authority"] is False
