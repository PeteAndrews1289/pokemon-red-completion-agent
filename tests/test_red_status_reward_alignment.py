from copy import deepcopy

import pytest
from audit_red_status_reward_alignment import return_components
from test_red_status_closed_loop_returns import episode

from pokemon_red_completion.red_status_closed_loop_returns import closed_loop_return


@pytest.mark.parametrize("won", [False, True])
def test_components_reproduce_frozen_reward(won):
    row = episode()
    if won:
        row["stop_reason"] = "battle_won"
    before = deepcopy(row)
    parts = return_components(row)
    assert sum(parts.values()) == pytest.approx(closed_loop_return(row))
    assert row == before


def test_frozen_reward_prefers_shorter_otherwise_equal_losses():
    short = episode(33)
    long = deepcopy(short)
    long["decisions"] *= 3
    a, b = return_components(short), return_components(long)
    assert a["terminal"] == b["terminal"] == -10.
    assert a["turn_cost"] - b["turn_cost"] == pytest.approx(.2)
    assert closed_loop_return(short) - closed_loop_return(long) == pytest.approx(.2)
