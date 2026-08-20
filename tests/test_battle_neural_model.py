from __future__ import annotations

import numpy as np
import pytest

from pokemon_red_completion.battle_model import (
    BATTLE_MODEL_FORMAT_VERSION,
    BattleChoiceExample,
    BattleModelValidationError,
)
from pokemon_red_completion.battle_neural_model import (
    BATTLE_MLP_MODEL_ID,
    MaskedMLPMoveRanker,
)


def _xor_examples() -> tuple[BattleChoiceExample, ...]:
    return tuple(
        BattleChoiceExample(
            candidate_features=[positive, negative],
            legal_mask=[True, True],
            current_pp=[10, 10],
            chosen_index=0,
        )
        for positive, negative in (
            ((1.0, 1.0), (1.0, -1.0)),
            ((-1.0, -1.0), (-1.0, 1.0)),
            ((1.0, 1.0), (-1.0, 1.0)),
            ((-1.0, -1.0), (1.0, -1.0)),
        )
    )


def test_mlp_learns_nonlinear_candidate_preference_deterministically() -> None:
    first = MaskedMLPMoveRanker.fit(
        feature_names=("first", "second"),
        examples=_xor_examples(),
        seed=1289,
        hidden_units=8,
        epochs=500,
        learning_rate=0.03,
    )
    second = MaskedMLPMoveRanker.fit(
        feature_names=("first", "second"),
        examples=_xor_examples(),
        seed=1289,
        hidden_units=8,
        epochs=500,
        learning_rate=0.03,
    )

    assert first.to_json() == second.to_json()
    assert all(
        first.predict(
            example.candidate_features,
            legal_mask=example.legal_mask,
            current_pp=example.current_pp,
        )
        == example.chosen_index
        for example in _xor_examples()
    )


def test_mlp_masks_illegal_and_zero_pp_candidates() -> None:
    model = MaskedMLPMoveRanker(
        feature_names=("signal",),
        input_weights=[[1.0], [-1.0]],
        hidden_bias=[0.0, 0.0],
        output_weights=[1.0, -1.0],
        output_bias=0.0,
    )
    probabilities = model.predict_proba(
        [[0.1], [100.0], [200.0]],
        legal_mask=[True, False, True],
        current_pp=[1, 1, 0],
    )

    assert probabilities.tolist() == [1.0, 0.0, 0.0]
    assert model.predict(
        [[0.1], [100.0], [200.0]],
        legal_mask=[True, False, True],
        current_pp=[1, 1, 0],
    ) == 0


def test_mlp_serialization_round_trip_and_validation() -> None:
    model = MaskedMLPMoveRanker.fit(
        feature_names=("first", "second"),
        examples=_xor_examples(),
        seed=7,
        hidden_units=4,
        epochs=10,
    )

    assert MaskedMLPMoveRanker.from_dict(model.to_dict()).to_json() == model.to_json()
    invalid = model.to_dict()
    invalid["format_version"] = BATTLE_MODEL_FORMAT_VERSION + 1
    with pytest.raises(BattleModelValidationError, match="format version"):
        MaskedMLPMoveRanker.from_dict(invalid)
    assert model.model_id == BATTLE_MLP_MODEL_ID
    assert np.isfinite(model.scores([[1.0, 1.0]])).all()
