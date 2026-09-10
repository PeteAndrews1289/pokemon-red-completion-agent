"""Codex adversarial checks independent of Flash's prototype fixtures."""

from dataclasses import replace

import pytest

from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_capture_lead import RedCaptureLeadError, plan_capture_lead


def observation(*, move=1, hp=30, pp=5):
    return PartyObservation((PartyMemberObservation(
        1, 25, 20, hp, 60, moves=(MoveObservation(move, pp),),
    ),))


@pytest.mark.parametrize('move', (120, 153))
def test_self_destruct_only_is_not_a_sustainable_escort(move):
    with pytest.raises(RedCaptureLeadError):
        plan_capture_lead(observation(move=move))


def test_unknown_usable_move_uses_the_preparation_error_contract():
    with pytest.raises(RedCaptureLeadError):
        plan_capture_lead(observation(move=999))


def test_threshold_equality_and_one_hp_below_are_distinguishable():
    assert not plan_capture_lead(observation(hp=30)).requires_swap
    with pytest.raises(RedCaptureLeadError):
        plan_capture_lead(observation(hp=29))


@pytest.mark.parametrize(
    'status', tuple(s for s in StatusCondition if s is not StatusCondition.HEALTHY),
)
def test_every_nonhealthy_status_is_rejected(status):
    before = observation()
    member = replace(before.members[0], status=status)
    with pytest.raises(RedCaptureLeadError):
        plan_capture_lead(replace(before, members=(member,)))


def test_same_species_and_moves_but_different_hp_detect_no_swap():
    before = observation(hp=0)
    healthy = replace(before.members[0], slot=2, hp=60)
    before = replace(before, members=(*before.members, healthy))
    plan = plan_capture_lead(before)
    assert plan.target_index == 1
    with pytest.raises(RedCaptureLeadError):
        plan.require_result(before)
    after = replace(before, members=(replace(healthy, slot=1), replace(before.members[0], slot=2)))
    plan.require_result(after)
    assert before.members[0].hp == 0 and before.members[1].hp == 60


def test_noop_plan_still_rejects_stale_pp():
    before = observation()
    plan = plan_capture_lead(before)
    changed = replace(before, members=(replace(before.members[0], moves=(MoveObservation(1, 4),)),))
    with pytest.raises(RedCaptureLeadError):
        plan.require_current(changed)
    with pytest.raises(RedCaptureLeadError):
        plan.require_result(changed)


def test_empty_party_cannot_supply_an_escort():
    with pytest.raises(RedCaptureLeadError):
        plan_capture_lead(PartyObservation(()))


def test_unbounded_integer_threshold_is_rejected_without_numeric_overflow():
    with pytest.raises(ValueError):
        plan_capture_lead(observation(), minimum_hp_ratio=10 ** 1000)


def test_candidate_order_changes_invalidate_a_planned_swap():
    weak = observation(move=106).members[0]
    low = replace(observation().members[0], slot=2, level=20)
    high = replace(low, slot=3, level=50)
    before = PartyObservation((weak, low, high))
    plan = plan_capture_lead(before)
    reordered = PartyObservation((weak, replace(high, slot=2), replace(low, slot=3)))
    with pytest.raises(RedCaptureLeadError):
        plan.require_current(reordered)


def test_species_identity_does_not_select_the_escort():
    weak = observation(move=106).members[0]
    low = replace(observation().members[0], slot=2, species_id=28, level=20)
    high = replace(low, slot=3, species_id=48, level=50)
    before = PartyObservation((weak, low, high))
    relabeled = replace(
        before, members=(weak, replace(low, species_id=48), replace(high, species_id=28)),
    )
    assert plan_capture_lead(before).target_index == plan_capture_lead(relabeled).target_index == 2
