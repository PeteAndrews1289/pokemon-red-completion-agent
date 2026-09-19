from dataclasses import replace

import pytest
from test_red_trainer_retention import unit_head

from pokemon_red_completion.red_trainer_budgeted_fit import (
    RegretBudget,
    fit_budgeted_head,
    selected_regret,
)
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample


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
