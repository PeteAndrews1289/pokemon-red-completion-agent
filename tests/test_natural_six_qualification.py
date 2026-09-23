from copy import deepcopy
import pytest
from run_red_natural_six_qualification import actual_slots, summarize


def rows():
    return [{"boot": boot, "timing": timing, "arm": arm, "stop_reason": "battle_won",
        "battle_won": True, "final_state_verified": True, "log_verified": True,
        "teacher_queries": 0, "memory_write_actions": 0, "actual_slots": [1, 6],
        "metrics": {"invalid_action_failures": 0, "party_faints": 2}}
        for boot in (3700, 3900) for timing in (0, 4) for arm in ("J", "K")]


def test_natural_six_gate_does_not_require_perfect_wins_or_no_faints():
    data = rows()
    for row in data:
        if row["timing"] == 4:
            row.update(stop_reason="party_defeated", battle_won=False)
    result = summarize(data)
    assert result["qualified"]
    assert result["totals"]["K"]["faints"] == 8
    assert not result["funding_qualified"]


@pytest.mark.parametrize("change", [
    {"stop_reason": "decision_limit"}, {"teacher_queries": 1}, {"memory_write_actions": 1},
    {"final_state_verified": False}, {"log_verified": False},
    {"metrics": {"invalid_action_failures": 1}},
])
def test_each_invalid_or_unretained_cell_prevents_qualification(change):
    data = rows()
    data[0].update(change)
    assert not summarize(data)["qualified"]


def test_model_must_reach_late_slots_and_win_on_both_origins_without_regression():
    for change in ({"actual_slots": [1, 2, 3]}, {"battle_won": False, "stop_reason": "party_defeated"}):
        data = rows()
        for row in data:
            if row["boot"] == 3900 and row["arm"] == "K":
                row.update(change)
        assert not summarize(data)["qualified"]
    data = rows()
    data[-1].update(battle_won=False, stop_reason="party_defeated")
    assert not summarize(data)["checks"]["K_wins_no_regression"]


def test_duplicate_or_missing_cells_never_manufacture_independence():
    data = rows()
    with pytest.raises(ValueError):
        summarize(data[:-1])
    data[-1] = deepcopy(data[0])
    with pytest.raises(ValueError):
        summarize(data)


def test_slot_selection_is_not_actual_slot_execution():
    assert actual_slots({"decisions": [{"party_slot": 6}]}) == []
    assert actual_slots({"decisions": [{"state_before": {"active_party_slot": 1},
        "state_after": {"active_party_slot": 6}}]}) == [1, 6]
    assert actual_slots({"decisions": [{"state_before": {"active_party_slot": 6},
        "state_after": {"active_party_slot": None}}]}) == [6]
    with pytest.raises(ValueError):
        actual_slots({"decisions": [{"state_after": {"active_party_slot": 7}}]})
