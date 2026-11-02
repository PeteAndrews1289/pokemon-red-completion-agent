"""Report explicit aggregate native work without inferring trips or participation."""

from copy import deepcopy

import pytest

from pokemon_red_completion.red_player_lesson_runtime import player_outcome_diagnostics


def outcome(*, routed=False):
    prep = dict(
        battles=42,
        completed_battles_across_doses=47,
        total_battle_allowance=64,
        repeat_health_limited_zero_progress=True,
        retained_doses=[dict(ordinal=0, result=dict(battles=5)),
                         dict(ordinal=1, result=dict(battles=42))],
    )
    evidence = dict(mechanic="routed_preparation", preparation=prep) if routed else prep
    return dict(
        selected_kind="develop_team", choice={}, evidence=evidence,
        before=dict(cash=100, restoration_attempts=7, nested_restoration_attempts=5,
                    training_healing_attempts=0),
        after=dict(cash=100, restoration_attempts=9, nested_restoration_attempts=7,
                   training_healing_attempts=0),
        observed_cost=dict(actions=5, frames=50, cash_spent=0),
    )


@pytest.mark.parametrize("routed", [False, True])
def test_preparation_summary_reports_all_native_doses_and_preserves_uncertainty(routed):
    value = outcome(routed=routed)
    before = deepcopy(value)
    actual = player_outcome_diagnostics(value)["preparation_efficiency"]
    assert actual["reported_training_battles"] == 47
    assert actual["reported_training_battle_source"] == (
        "preparation.completed_battles_across_doses" if routed
        else "completed_battles_across_doses"
    )
    assert actual["observed_restoration_attempts"] == dict(
        restoration_attempts=2, nested_restoration_attempts=2, training_healing_attempts=0)
    assert actual["reported_healing_trips"] is None
    assert actual["battle_count"] is None and actual["healing_interaction_count"] is None
    assert actual["participation_not_inferred"] is True
    assert value == before


@pytest.mark.parametrize("fault", ["sum", "boolean", "negative", "missing_total",
    "missing_result", "boolean_dose", "duplicate_ordinal", "wrong_ordinal_type",
    "disabled_format", "empty_doses", "allowance", "foreign_wrapper"])
def test_unsupported_or_inconsistent_dose_aggregate_is_not_reported(fault):
    value = outcome(routed=True)
    prep = value["evidence"]["preparation"]
    if fault == "sum":
        prep["completed_battles_across_doses"] = 48
    elif fault == "boolean":
        prep["completed_battles_across_doses"] = True
    elif fault == "negative":
        prep["completed_battles_across_doses"] = -1
    elif fault == "missing_total":
        prep.pop("completed_battles_across_doses")
    elif fault == "missing_result":
        prep["retained_doses"][0].pop("result")
    elif fault == "boolean_dose":
        prep["retained_doses"][0]["result"]["battles"] = True
    elif fault == "duplicate_ordinal":
        prep["retained_doses"][1]["ordinal"] = 0
    elif fault == "wrong_ordinal_type":
        prep["retained_doses"][0]["ordinal"] = False
    elif fault == "disabled_format":
        prep["repeat_health_limited_zero_progress"] = False
    elif fault == "empty_doses":
        prep["retained_doses"] = []
    elif fault == "allowance":
        prep["total_battle_allowance"] = 46
    elif fault == "foreign_wrapper":
        value["evidence"]["mechanic"] = "unrelated"
    actual = player_outcome_diagnostics(value)["preparation_efficiency"]
    assert actual["reported_training_battles"] is None
    assert actual["reported_training_battle_source"] is None
