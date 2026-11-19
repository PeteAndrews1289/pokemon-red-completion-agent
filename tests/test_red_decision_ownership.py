import pytest

from red_teacher_closeout import classify_decision_ownership


@pytest.mark.parametrize("choice,owner,queries", [
    ({"branch_recovery": {"parent_model_queries": 1}}, "parent_model", 1),
    ({"model_queries": 0, "comparative_choice": False}, "disclosed_support", 0),
    ({"schema": "pokemon.red.live-mixed-option-choice.v1", "mode": "model_greedy"}, "parent_model", 1),
    ({"schema": "pokemon.red.live-mixed-option-choice.v1", "mode": "model_exploration"}, "parent_model", 1),
    ({"schema": "pokemon.red.live-mixed-option-choice.v1", "mode": "equivalent_exploration"}, "disclosed_support", 0),
    ({"schema": "pokemon.red.live-mixed-option-choice.v1", "mode": "deterministic_safety"}, "disclosed_support", 0),
    ({"schema": "pokemon.red.live-mixed-option-choice.v1", "mode": "forced_singleton_support"}, "disclosed_support", 0),
    ({}, "unknown", None),
])
def test_branchless_and_singleton_rows_are_not_dropped_or_invented(choice, owner, queries):
    result = classify_decision_ownership(choice)
    assert result["owner"] == owner
    assert result["parent_queries"] == queries


@pytest.mark.parametrize("value", [True, -1, 0.5, "1"])
def test_query_counts_are_exact_nonnegative_integers(value):
    with pytest.raises(ValueError):
        classify_decision_ownership({"model_queries": value})


def test_child_override_is_disclosed_without_erasing_parent_query():
    result = classify_decision_ownership({"branch_recovery": {
        "parent_model_queries": 1, "child_model_queries": 1,
        "child_overrode_parent_binding": True,
    }})
    assert result == {"owner": "parent_model", "parent_queries": 1,
                      "child_queries": 1, "child_overrode": True}
