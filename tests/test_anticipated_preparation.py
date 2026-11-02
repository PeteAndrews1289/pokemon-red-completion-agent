from dataclasses import replace

import pytest

from pokemon_red_completion.party import MoveObservation, PartyMemberObservation
from pokemon_red_completion.party_preparation import (
    ObservedOpponent,
    PreparationAttempt,
    PreparationBudget,
    PreparationMember,
    PreparationPurpose,
    build_preparation_plan,
    build_preview_preparation_plan,
    next_preparation_decision,
)


def team(*levels):
    return tuple(
        PreparationMember(
            f"member-{i}",
            PartyMemberObservation(i, i, level, 100, 100, moves=(MoveObservation(33, 30),)),
            PreparationPurpose.COMBAT,
            "declared combat role",
        )
        for i, level in enumerate(levels, 1)
    )


def preview(members, levels=(54, 53, 54, 56, 56), **kwargs):
    return build_preview_preparation_plan(
        members, levels, forecast_ref="authenticated-upcoming-challenge", **kwargs
    )


def test_prepare_before_first_battle_without_fabricating_observations():
    members = team(43, 43, 52, 42, 38)
    assert not build_preparation_plan(members, ()).targets
    plan = preview(members)
    assert plan.observed_opponents == 0 and plan.anticipated_opponents == 5
    assert plan.evidence_basis == "cartridge_preview"
    assert plan.opposition_level == 54
    assert dict(plan.targets) == {"member-1": 51, "member-2": 51, "member-4": 51, "member-5": 51}
    assert next_preparation_decision(plan, members).target_slot == 5


@pytest.mark.parametrize(
    "purpose",
    [
        PreparationPurpose.UNDECIDED,
        PreparationPurpose.COLLECTION,
        PreparationPurpose.FIELD_UTILITY,
    ],
)
def test_low_new_catch_does_not_trigger_grinding(purpose):
    members = team(52, 51, 3)
    members = (*members[:2], replace(members[2], purpose=purpose))
    assert not preview(members).targets


def test_preview_does_not_change_observed_rule_or_refill_budget():
    members = team(43, 38)
    observed = build_preparation_plan(members, (ObservedOpponent("past", 1, 43),))
    assert not observed.targets and observed.evidence_basis == "observed"
    plan = preview(members, budget=PreparationBudget(max_attempts=1))
    receipt = PreparationAttempt("member-2", 38, 39, 100, 20, 1000, 1)
    assert next_preparation_decision(plan, members, (receipt,)).reason == "attempt budget"
    with pytest.raises(ValueError, match="preview"):
        replace(plan, observed_opponents=5)
    with pytest.raises(ValueError, match="observed"):
        replace(plan, evidence_basis="observed")


@pytest.mark.parametrize("levels", [(), (True,), (0,), (101,), (3.5,), (20,) * 7])
def test_invalid_preview_refused(levels):
    with pytest.raises(ValueError):
        preview(team(20), levels)


def test_reference_and_budget_required_and_uncertified_model_source_refused():
    with pytest.raises(ValueError):
        build_preview_preparation_plan(team(20), (40,), forecast_ref="")
    with pytest.raises(ValueError):
        preview(team(20), budget="unbounded")
    with pytest.raises(ValueError):
        replace(preview(team(20)), evidence_basis="learned_forecast")


def test_readiness_is_role_sensitive_and_stops_at_frozen_targets():
    plan = preview(team(30, 31, 65), (42, 44, 43))
    assert set(dict(plan.targets).values()) == {40}
    ready = tuple(
        replace(m, observation=replace(m.observation, level=max(40, m.observation.level)))
        for m in plan.roster
    )
    assert next_preparation_decision(plan, ready).reason == "all preparation targets reached"
