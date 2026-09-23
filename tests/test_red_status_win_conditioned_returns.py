from copy import deepcopy

import pytest
from test_red_status_closed_loop_returns import episode

from pokemon_red_completion.red_status_closed_loop_returns import closed_loop_return
from pokemon_red_completion.red_status_win_conditioned_returns import win_conditioned_return


def test_shorter_loss_cannot_profit_from_avoided_costs():
    short = episode(79, "paralysis", "paralysis")
    long = deepcopy(short)
    long["decisions"] *= 40
    long["metrics"]["party_pp_spent"] = 40
    assert closed_loop_return(short) > closed_loop_return(long)
    assert win_conditioned_return(short) == win_conditioned_return(long)


def test_more_damage_not_overridden_by_longer_loss():
    short = episode(33)
    long = deepcopy(short)
    long["decisions"] = [deepcopy(short["decisions"][0]) for _ in range(20)]
    long["decisions"][-1]["opponent_hp_after"] = 50
    assert win_conditioned_return(long) - win_conditioned_return(short) == pytest.approx(.25)


def test_wins_dominate_nonwins_and_efficient_wins_are_better():
    good = episode(79, "paralysis", "paralysis")
    good["stop_reason"] = "battle_won"
    bad = deepcopy(good)
    bad["decisions"] *= 40
    bad["metrics"]["party_pp_spent"] = 40
    assert win_conditioned_return(good) > win_conditioned_return(bad)
    for stop in ("party_defeated", "player_turn_budget"):
        nonwin = episode(33)
        nonwin["stop_reason"] = stop
        nonwin["decisions"][0]["state_after"]["party_hp"] = [100]
        nonwin["decisions"][0]["opponent_hp_after"] = 0
        assert win_conditioned_return(bad) > win_conditioned_return(nonwin)


@pytest.mark.parametrize("move", [50, 105, 156])
def test_unknown_effects_are_not_fabricated_and_source_is_immutable(move):
    row = episode(move)
    row["stop_reason"] = "battle_won"
    before = deepcopy(row)
    assert win_conditioned_return(row) == pytest.approx(10.25 - .1/40 - .01/40)
    assert row == before


@pytest.mark.parametrize("kind", ["empty", "long", "stop", "nan", "cap", "hp", "pp"])
def test_invalid_reward_inputs_rejected(kind):
    row = episode()
    if kind == "empty":
        row["decisions"] = []
    elif kind == "long":
        row["decisions"] *= 41
    elif kind == "stop":
        row["stop_reason"] = "error"
    elif kind == "nan":
        row["decisions"][0]["opponent_hp_after"] = float("nan")
    elif kind == "cap":
        row["decisions"][0]["observation"]["features"]["battle"]["opponent_max_hp"] = 0
    elif kind == "hp":
        row["decisions"][0]["state_after"]["party_hp"] = [101]
    else:
        row["metrics"]["party_pp_spent"] = -1
    with pytest.raises(ValueError):
        win_conditioned_return(row)
