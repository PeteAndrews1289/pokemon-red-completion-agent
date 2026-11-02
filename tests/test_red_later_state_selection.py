from copy import deepcopy

import pytest

from pokemon_red_completion.red_switch_control_curriculum import later_state_capture_matches


def boundary(phase="main", hp=(0, 40, 30), slots=(2, 3)):
    return {
        "event": "decision_started", "mode": phase,
        "state_before": {"party_hp": list(hp)}, "legal_party_slots": list(slots),
    }


@pytest.mark.parametrize("phase", ["main", "forced_switch"])
def test_selects_after_faints_without_outcome_or_status_filtering(phase):
    event = boundary(phase)
    original = deepcopy(event)
    assert later_state_capture_matches(event, phase=phase)
    assert event == original
    for outcome in ("battle_won", "party_defeated"):
        assert later_state_capture_matches({**event, "future_outcome": outcome}, phase=phase)


@pytest.mark.parametrize("hp", [(), (30, 40, 20), (0, 0, 40), (0, -1, 40), (False, 40, 30)])
def test_rejects_missing_attrition_or_insufficient_living_options(hp):
    assert not later_state_capture_matches(boundary(hp=hp), phase="main")


@pytest.mark.parametrize("slots", [(2,), (2, 2), (1, 2), (2, 4), (True, 2)])
def test_forced_selection_requires_distinct_living_legal_reserves(slots):
    assert not later_state_capture_matches(
        boundary("forced_switch", slots=slots), phase="forced_switch"
    )


def test_minimum_not_exact_bucket_and_phase_are_prospective():
    e = boundary(hp=(0, 0, 40, 30))
    assert later_state_capture_matches(e, phase="main", minimum_faints=1)
    assert later_state_capture_matches(e, phase="main", minimum_faints=2)
    assert not later_state_capture_matches(e, phase="main", minimum_faints=3)
    assert not later_state_capture_matches(e, phase="forced_switch")
    assert not later_state_capture_matches({**e, "event": "decision_completed"}, phase="main")


@pytest.mark.parametrize(
    "phase,count", [("switch_prompt", 1), ("main", 0), ("main", 5), ("main", None), ("main", True)]
)
def test_invalid_declaration_fails(phase, count):
    with pytest.raises(ValueError):
        later_state_capture_matches(boundary(), phase=phase, minimum_faints=count)
