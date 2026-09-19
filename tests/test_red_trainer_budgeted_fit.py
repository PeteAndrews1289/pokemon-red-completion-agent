from dataclasses import replace

import numpy as np
import pytest
from test_red_trainer_retention import unit_head

from pokemon_red_completion.red_trainer_budgeted_fit import (
    RegretBudget,
    fit_budgeted_head,
    pairwise_loss_gradient,
    selected_regret,
)
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel


def case():
    initial = unit_head()
    vectors = ((1.0, 0.0), (0.0, 1.0))
    selected = initial.predict_index(vectors)
    return TrainerHeadExample(
        vectors, (1 - selected,), mean_returns=(0.0, 2.0) if selected == 0 else (2.0, 0.0)
    )


def test_old_wrong_choice_can_improve_without_relaxing_budget():
    row = case()
    fitted, receipt = fit_budgeted_head(
        unit_head(), (row,), (row,), (RegretBudget("old", (row,), 2.0),), epochs=100
    )
    assert fitted is not None
    assert selected_regret(fitted, (row,)) == 0
    assert receipt["final_selected_regret"] < receipt["initial_selected_regret"]


def test_selected_checkpoint_cannot_violate_numeric_budget():
    terminal = case()
    anchor = replace(terminal, mean_returns=tuple(reversed(terminal.mean_returns)))
    fitted, receipt = fit_budgeted_head(
        unit_head(), (terminal,), (anchor,), (RegretBudget("old", (anchor,), 0.0),), epochs=100
    )
    assert fitted is not None
    assert selected_regret(fitted, (anchor,)) == 0
    assert receipt["feasible_checkpoints"] > 0


def test_no_feasible_checkpoint_fails_closed():
    row = case()
    fitted, receipt = fit_budgeted_head(
        unit_head(), (row,), (row,), (RegretBudget("old", (row,), -1.0),), epochs=2
    )
    assert fitted is None
    assert receipt["selected_epoch"] is None


def test_offset_is_part_of_constraint():
    row = case()
    fitted, _ = fit_budgeted_head(
        unit_head(), (row,), (row,), (RegretBudget("composed", (row,), 0.9, 1.0),), epochs=100
    )
    assert fitted is None


@pytest.mark.parametrize("epochs,rate", [(0, 0.1), (True, 0.1), (1, float("nan")), (1, 0)])
def test_invalid_schedule_rejected(epochs, rate):
    row = case()
    with pytest.raises(ValueError, match="schedule"):
        fit_budgeted_head(
            unit_head(),
            (row,),
            (row,),
            (RegretBudget("a", (row,), 1.0),),
            epochs=epochs,
            learning_rate=rate,
        )


def test_pairwise_gradient_matches_finite_differences_with_padding_and_ties():
    model = unit_head()
    cases = (
        case(),
        TrainerHeadExample(
            ((0.5, 0.2), (0.2, 0.4), (0.8, 0.1)), (0, 1), mean_returns=(2.0, 2.0, -1.0)
        ),
    )
    packed = np.concatenate((model.weights1.ravel(), model.bias1, model.weights2))
    size, width = model.weights1.size, model.bias1.size

    def unpack(p):
        return replace(
            model,
            weights1=p[:size].reshape(model.weights1.shape),
            bias1=p[size : size + width],
            weights2=p[size + width :],
        )

    loss, gradient = pairwise_loss_gradient(model, cases)
    assert np.isfinite(loss)
    for index in range(len(packed)):
        delta = np.zeros_like(packed)
        delta[index] = 1e-6
        numerical = (
            pairwise_loss_gradient(unpack(packed + delta), cases)[0]
            - pairwise_loss_gradient(unpack(packed - delta), cases)[0]
        ) / 2e-6
        assert gradient[index] == pytest.approx(numerical, abs=1e-7)


def test_confidently_wrong_pairwise_gradient_does_not_vanish():
    from pokemon_red_completion.red_trainer_retention import batch_loss_gradient

    model = TrainerHeadModel("test", ("a", "b"), np.eye(2), np.zeros(2), np.array([80.0, -80.0]), 1)
    row = TrainerHeadExample(((1.0, 0.0), (0.0, 1.0)), (1,), mean_returns=(0.0, 2.0))
    assert model.probabilities(row.candidate_vectors)[1] < 1e-40
    assert np.linalg.norm(batch_loss_gradient(model, (row,))[1]) < 1e-40
    assert np.linalg.norm(pairwise_loss_gradient(model, (row,))[1]) > 1
    fitted, receipt = fit_budgeted_head(
        model,
        (row,),
        (row,),
        (RegretBudget("old", (row,), 2.0),),
        epochs=200,
        objective="pairwise_regret",
    )
    assert fitted is not None and selected_regret(fitted, (row,)) == 0
    assert receipt["objective"] == "pairwise_regret"
    assert (
        TrainerHeadModel.from_dict(
            fitted.to_dict(), schema_id=model.schema_id, feature_names=model.feature_names
        ).training_objective
        == "pairwise_regret"
    )
