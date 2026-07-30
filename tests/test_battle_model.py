from __future__ import annotations

import json

import numpy as np
import pytest

from pokemon_red_completion.battle_model import (
    BATTLE_FEATURE_SCHEMA_ID,
    BATTLE_MODEL_FORMAT_VERSION,
    BATTLE_MODEL_ID,
    BattleChoiceExample,
    BattleModelValidationError,
    MaskedLinearMoveRanker,
    choice_accuracy,
    mean_listwise_cross_entropy,
)

FEATURE_NAMES = ("move.effective_power", "move.accuracy", "move.is_status")


def _model(weights: tuple[float, ...] = (2.0, 0.5, -1.0)) -> MaskedLinearMoveRanker:
    return MaskedLinearMoveRanker(feature_names=FEATURE_NAMES, weights=weights)


def test_predictions_are_equivariant_to_move_slot_permutations() -> None:
    features = np.array(
        [
            [0.2, 1.0, 0.0],
            [0.8, 0.8, 0.0],
            [0.0, 1.0, 1.0],
            [0.5, 0.6, 0.0],
        ]
    )
    legal = np.array([True, True, True, True])
    pp = np.array([10, 7, 5, 3])
    permutation = np.array([2, 0, 3, 1])

    original = _model().predict_proba(features, legal_mask=legal, current_pp=pp)
    permuted = _model().predict_proba(
        features[permutation],
        legal_mask=legal[permutation],
        current_pp=pp[permutation],
    )

    assert np.allclose(permuted, original[permutation])
    permuted_choice = _model().predict(
        features[permutation],
        legal_mask=legal[permutation],
        current_pp=pp[permutation],
    )
    assert permutation[permuted_choice] == _model().predict(
        features,
        legal_mask=legal,
        current_pp=pp,
    )


def test_illegal_and_zero_pp_moves_have_zero_probability() -> None:
    features = np.array(
        [
            [1.0, 0.0, 0.0],
            [100.0, 0.0, 0.0],
            [200.0, 0.0, 0.0],
            [0.5, 0.0, 0.0],
        ]
    )

    probabilities = _model().predict_proba(
        features,
        legal_mask=[True, False, True, True],
        current_pp=[10, 10, 0, 2],
    )

    assert probabilities[1] == 0.0
    assert probabilities[2] == 0.0
    assert probabilities.sum() == pytest.approx(1.0)
    assert (
        _model().predict(
            features,
            legal_mask=[True, False, True, True],
            current_pp=[10, 10, 0, 2],
        )
        == 0
    )


def test_softmax_remains_stable_for_large_finite_scores() -> None:
    model = MaskedLinearMoveRanker(feature_names=("signal",), weights=[1.0])
    probabilities = model.predict_proba(
        [[1001.0], [1000.0], [-1000.0]],
        legal_mask=[True, True, True],
        current_pp=[1, 1, 1],
    )

    assert np.all(np.isfinite(probabilities))
    assert probabilities.sum() == pytest.approx(1.0)
    assert probabilities[0] > probabilities[1] > probabilities[2]


def test_training_is_deterministic_and_improves_synthetic_choices() -> None:
    examples = (
        BattleChoiceExample(
            [[2.0, 0.2], [-1.0, 0.0], [0.5, 1.0]],
            [True, True, True],
            [10, 10, 10],
            0,
        ),
        BattleChoiceExample(
            [[-2.0, 1.0], [3.0, 0.0]],
            [True, True],
            [5, 5],
            1,
        ),
        BattleChoiceExample(
            [[-3.0, 0.0], [0.1, 1.0], [1.5, 0.2], [9.0, 0.0]],
            [True, True, True, False],
            [3, 3, 3, 3],
            2,
        ),
        BattleChoiceExample(
            [[4.0, 0.0], [-1.0, 1.0], [20.0, 0.0]],
            [True, True, True],
            [1, 1, 0],
            0,
        ),
    )
    untrained = MaskedLinearMoveRanker(
        feature_names=("effective_power", "status"),
        weights=[0.0, 0.0],
    )

    first = MaskedLinearMoveRanker.fit(
        feature_names=("effective_power", "status"),
        examples=examples,
        seed=1289,
        epochs=300,
    )
    second = MaskedLinearMoveRanker.fit(
        feature_names=("effective_power", "status"),
        examples=examples,
        seed=1289,
        epochs=300,
    )

    assert np.array_equal(first.weights, second.weights)
    assert first.to_json() == second.to_json()
    assert choice_accuracy(first, examples) == 1.0
    assert mean_listwise_cross_entropy(first, examples) < mean_listwise_cross_entropy(
        untrained, examples
    )


def test_model_round_trips_through_canonical_json() -> None:
    model = MaskedLinearMoveRanker(
        feature_names=FEATURE_NAMES,
        weights=[0.125, -2.5, 3.0],
        training_seed=1289,
    )

    encoded = model.to_json()
    restored = MaskedLinearMoveRanker.from_json(encoded.encode("utf-8"))

    assert encoded == json.dumps(
        json.loads(encoded),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert restored.feature_schema_id == BATTLE_FEATURE_SCHEMA_ID
    assert restored.model_id == BATTLE_MODEL_ID
    assert restored.training_seed == 1289
    assert restored.feature_names == model.feature_names
    assert np.array_equal(restored.weights, model.weights)
    assert restored.to_dict()["format_version"] == BATTLE_MODEL_FORMAT_VERSION
    assert restored.to_json() == encoded


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "feature_names": ["power"],
            "feature_schema_id": BATTLE_FEATURE_SCHEMA_ID,
            "format_version": 99,
            "model_id": BATTLE_MODEL_ID,
            "training_seed": 0,
            "weights": [1.0],
        },
        {
            "feature_names": ["power"],
            "feature_schema_id": "wrong-schema",
            "format_version": BATTLE_MODEL_FORMAT_VERSION,
            "model_id": BATTLE_MODEL_ID,
            "training_seed": 0,
            "weights": [1.0],
        },
        {
            "feature_names": ["power", "accuracy"],
            "feature_schema_id": BATTLE_FEATURE_SCHEMA_ID,
            "format_version": BATTLE_MODEL_FORMAT_VERSION,
            "model_id": BATTLE_MODEL_ID,
            "training_seed": 0,
            "weights": [1.0],
        },
        {
            "feature_names": ["slot_index"],
            "feature_schema_id": BATTLE_FEATURE_SCHEMA_ID,
            "format_version": BATTLE_MODEL_FORMAT_VERSION,
            "model_id": BATTLE_MODEL_ID,
            "training_seed": 0,
            "weights": [1.0],
        },
    ],
)
def test_malformed_model_payloads_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(BattleModelValidationError):
        MaskedLinearMoveRanker.from_dict(payload)


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff",
        '{"weights":[NaN]}',
        '{"model_id":"first","model_id":"duplicate"}',
        "[]",
    ],
)
def test_malformed_model_json_is_rejected(payload: str | bytes) -> None:
    with pytest.raises(BattleModelValidationError):
        MaskedLinearMoveRanker.from_json(payload)


@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -np.inf])
def test_nonfinite_features_are_rejected(bad_value: float) -> None:
    with pytest.raises(BattleModelValidationError, match="finite"):
        _model().predict_proba(
            [[1.0, 0.0, 0.0], [bad_value, 1.0, 0.0]],
            legal_mask=[True, True],
            current_pp=[1, 1],
        )


@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -np.inf])
def test_nonfinite_weights_are_rejected(bad_value: float) -> None:
    with pytest.raises(BattleModelValidationError, match="finite"):
        MaskedLinearMoveRanker(
            feature_names=("power",),
            weights=[bad_value],
        )


def test_choice_rejects_unusable_label_and_inference_rejects_empty_mask() -> None:
    with pytest.raises(BattleModelValidationError, match="chosen move"):
        BattleChoiceExample([[1.0], [2.0]], [True, True], [1, 0], 1)

    with pytest.raises(BattleModelValidationError, match="At least one legal move"):
        MaskedLinearMoveRanker(feature_names=("power",), weights=[1.0]).predict_proba(
            [[1.0], [2.0]],
            legal_mask=[False, True],
            current_pp=[1, 0],
        )
