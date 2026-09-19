from copy import deepcopy

import pytest
from run_red_trainer_natural_team import MODEL_SHA, TEAM_BOOT_FRAMES, TIMINGS, summarize


def rows():
    return [
        {
            "boot": boot,
            "timing": timing,
            "arm": arm,
            "battle_won": timing != 8,
            "stop_reason": "battle_won" if timing != 8 else "party_defeated",
            "teacher_queries": 0,
            "memory_write_actions": 0,
            "metrics": {"invalid_action_failures": 0, "party_faints": 1, "party_hp_lost": 20},
            "final_state_verified": True,
            "reserve_used": timing == 0,
            "decision_count": 5,
            "action_counts": {"attack": 4, "forced_switch": 1},
        }
        for boot in TEAM_BOOT_FRAMES
        for timing in TIMINGS
        for arm in MODEL_SHA
    ]


def test_natural_team_accepts_losses_not_perfect_win_requirement():
    result = summarize(rows())
    assert result["natural_team_gate_passed"]
    assert result["totals"]["J"]["wins"] == 4
    assert not result["final_player_ready"]
    assert not result["multiple_forced_target_choice_qualified"]


def test_natural_team_needs_actual_reserve_use_not_just_full_roster():
    data = rows()
    for row in data:
        row["reserve_used"] = False
        row["action_counts"] = {"switch_prompt": 3}
    result = summarize(data)
    assert not result["natural_team_gate_passed"]
    assert result["checks"]["all_terminal_unassisted_with_endpoints"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("teacher_queries", 1),
        ("memory_write_actions", 1),
        ("final_state_verified", False),
        ("stop_reason", "decision_budget"),
    ],
)
def test_natural_team_rejects_assistance_unretained_and_nonterminal(field, value):
    data = rows()
    data[0][field] = value
    assert not summarize(data)["natural_team_gate_passed"]


def test_natural_team_rejects_missing_and_duplicate_cells():
    data = rows()
    for invalid in (data[:-1], data + [data[0]], data[:-1] + [data[0]]):
        with pytest.raises(ValueError, match="unique declared"):
            summarize(invalid)


def test_natural_team_win_regression_stops_gate():
    data = deepcopy(rows())
    next(r for r in data if r["arm"] == "J")["battle_won"] = False
    assert not summarize(data)["checks"]["wins_no_regression"]
