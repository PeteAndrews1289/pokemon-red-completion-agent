from __future__ import annotations

import pytest

from pokemon_red_completion.red_trainer_practice_head import (
    TrainerHeadError,
    TrainerHeadExample,
    TrainerHeadModel,
)


def test_listwise_head_fits_and_round_trips_only_matching_schema():
    examples = [TrainerHeadExample(((1.0, 0.0), (0.0, 1.0)), (0,))] * 8
    model = TrainerHeadModel.fit(
        schema_id="unit-stats-v1", feature_names=("a", "b"),
        examples=examples, seed=17, epochs=450,
    )
    candidates = examples[0].candidate_vectors
    assert model.predict_index(candidates) == 0
    restored = TrainerHeadModel.from_dict(
        model.to_dict(), schema_id="unit-stats-v1", feature_names=("a", "b")
    )
    assert restored.probabilities(candidates).tolist() == model.probabilities(candidates).tolist()
    with pytest.raises(TrainerHeadError, match="incompatible"):
        TrainerHeadModel.from_dict(
            model.to_dict(), schema_id="unit-stats-v2", feature_names=("a", "b")
        )


def test_listwise_tie_target_is_valid_without_fabricating_a_winner():
    tied = TrainerHeadExample(((1.0,), (0.0,)), (0, 1))
    assert tied.best_indices == (0, 1)
