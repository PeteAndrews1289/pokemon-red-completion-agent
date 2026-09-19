from copy import deepcopy

import numpy as np
import pytest
from test_red_trainer_practice_fit import _target

from pokemon_red_completion.red_trainer_practice_fit import (
    TrainerPracticeThreeHeadModel,
    fit_trainer_practice_three_heads,
    summarize_trainer_practice_training,
)
from pokemon_red_completion.red_trainer_practice_head import (
    TrainerHeadError,
    TrainerHeadExample,
    TrainerHeadModel,
    expected_regret_loss_gradient,
)
from pokemon_red_completion.red_trainer_proposed_control import PROPOSED_CONTROL_SCHEMA


def test_return_gradient_matches_finite_difference_and_scales_with_cost():
    logits = np.array([0.2, -0.4, 0.7])
    rewards = (0.99, 9.14, 2.0)

    def loss(x):
        p = np.exp(x - x.max())
        p /= p.sum()
        return expected_regret_loss_gradient(p, rewards)

    value, gradient = loss(logits)
    numeric = []
    for i in range(len(logits)):
        delta = np.zeros_like(logits)
        delta[i] = 1e-6
        numeric.append((loss(logits + delta)[0] - loss(logits - delta)[0]) / 2e-6)
    np.testing.assert_allclose(gradient, numeric, atol=1e-8)
    assert gradient[1] < 0  # Descent increases the best-return logit.
    p = np.exp(logits - logits.max())
    p /= p.sum()
    shifted = expected_regret_loss_gradient(p, tuple(r + 100 for r in rewards))
    scaled = expected_regret_loss_gradient(p, tuple(r * 10 for r in rewards))
    assert shifted[0] == pytest.approx(value)
    np.testing.assert_allclose(shifted[1], gradient)
    np.testing.assert_allclose(scaled[1], gradient * 10)


def test_expected_regret_fit_preserves_objective_and_requires_measured_returns():
    case = TrainerHeadExample(((1.0, 0.0), (0.0, 1.0)), (1,), mean_returns=(0.0, 8.0))
    model = TrainerHeadModel.fit(
        schema_id="unit",
        feature_names=("x", "y"),
        examples=[case],
        seed=9,
        epochs=100,
        training_objective="expected_regret",
    )
    assert model.predict_index(case.candidate_vectors) == 1
    assert model.training_objective == "expected_regret"
    assert (
        TrainerHeadModel.from_dict(
            model.to_dict(), schema_id="unit", feature_names=("x", "y")
        ).to_dict()
        == model.to_dict()
    )
    missing = TrainerHeadExample(case.candidate_vectors, (1,))
    with pytest.raises(TrainerHeadError, match="measured returns"):
        TrainerHeadModel.fit(
            schema_id="unit",
            feature_names=("x", "y"),
            examples=[missing],
            seed=9,
            training_objective="expected_regret",
        )


def test_three_head_return_fit_and_diagnostics_use_same_objective():
    target = _target()
    target["heads"]["control"] = {
        "choice_refs": target["heads"]["move"]["choice_refs"]
        + target["heads"]["switch"]["choice_refs"],
        "returns": [0.8, 1.0, 0.4, 0.7],
        "best_indices": [1],
    }
    model = fit_trainer_practice_three_heads(
        [target],
        seed=9,
        epochs=30,
        require_corpus_floor=False,
        control_target_mode="fitted_components",
        control_input_schema=PROPOSED_CONTROL_SCHEMA,
        training_objective="expected_regret",
    )
    assert all(
        getattr(model, name).training_objective == "expected_regret"
        for name in ("move", "control", "switch")
    )
    assert TrainerPracticeThreeHeadModel.from_dict(model.to_dict()).to_dict() == model.to_dict()
    reports = summarize_trainer_practice_training([target], model)
    assert reports["move"]["final_expected_regret"] < reports["move"]["initial_expected_regret"]
    invalid = deepcopy(model.to_dict())
    invalid["move"]["training_objective"] = "unknown"
    with pytest.raises(ValueError):
        TrainerPracticeThreeHeadModel.from_dict(invalid)


def test_return_successor_recipe_is_fixed_and_leaves_source_unchanged():
    from run_red_trainer_proposed_control import fresh_recipe

    original = {
        "practice": {
            "actor_hp": 42,
            "opponent_hp": 56,
            "opponent_level": 30,
            "opponent_reserves": [{"level": 30}],
        }
    }
    changed = fresh_recipe(original, expected_return=True)
    assert changed["practice"]["actor_hp"] == 40
    assert changed["practice"]["opponent_hp"] == 58
    assert original["practice"]["actor_hp"] == 42
