from dataclasses import replace

import pytest

from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_battle_catalog import RedBattleCatalogError
from pokemon_red_completion.red_capture_lead import RedCaptureLeadError, plan_capture_lead


def member(slot, *, species_id=25, level=20, hp=50, max_hp=50,
           status=StatusCondition.HEALTHY, moves=(MoveObservation(1, 35),)):
    return PartyMemberObservation(slot, species_id, level, hp, max_hp, status=status, moves=moves)


def party(*members):
    return PartyObservation(members)


def test_invalid_threshold():
    for invalid in (True, False, 0., -.1, 1.1, float('nan'), float('inf'), '0.5'):
        with pytest.raises(ValueError):
            plan_capture_lead(party(member(1)), minimum_hp_ratio=invalid)


def test_qualified_current_lead_requires_no_swap():
    before = party(member(1, level=25), member(2, level=30))
    plan = plan_capture_lead(before)
    assert plan.target_index == 0 and not plan.requires_swap
    assert plan.target_member == before.members[0]
    plan.require_current(before)
    plan.require_result(before)


def test_harden_only_lead_and_helper_present():
    before = party(member(1, moves=(MoveObservation(106, 30),)), member(2, level=13))
    plan = plan_capture_lead(before)
    assert plan.target_index == 1 and plan.requires_swap


def test_fainted_lead_and_nonlead_guarded_recovery():
    before = party(member(1, hp=0), member(2, hp=0), member(3))
    assert plan_capture_lead(before).target_index == 2


def test_exhausted_pp_disqualifies_member():
    exhausted = member(1, moves=(MoveObservation(1, 0),))
    assert plan_capture_lead(party(exhausted, member(2))).target_index == 1
    with pytest.raises(RedCaptureLeadError):
        plan_capture_lead(party(exhausted))


def test_hp_ratio_and_status_disqualification():
    before = party(member(1, status=StatusCondition.SLEEP), member(2, hp=10), member(3))
    assert plan_capture_lead(before).target_index == 2


def test_deterministic_ranking_level_hp_pp_slot():
    lead = member(1, moves=(MoveObservation(106, 30),))
    second = member(2, level=20, moves=(MoveObservation(1, 10),))
    assert plan_capture_lead(party(lead, second, member(3, level=25, hp=30))).target_index == 2
    assert plan_capture_lead(party(lead, second, member(3, hp=40))).target_index == 1
    assert plan_capture_lead(party(lead, second, member(3))).target_index == 2
    assert plan_capture_lead(party(lead, second, replace(second, slot=3))).target_index == 1


def test_duplicate_same_species_distinct_permutation_and_fields():
    lead = member(1, moves=(MoveObservation(106, 30),))
    a = member(2, hp=30, moves=(MoveObservation(1, 10),))
    b = member(3, moves=(MoveObservation(1, 25),))
    before = party(lead, a, b)
    plan = plan_capture_lead(before)
    assert plan.target_index == 2
    with pytest.raises(RedCaptureLeadError):
        plan.require_current(party(lead, replace(a, hp=29), b))
    with pytest.raises(RedCaptureLeadError):
        plan.require_current(party(lead, a, replace(b, moves=(MoveObservation(1, 24),))))
    plan.require_result(party(replace(b, slot=1), a, replace(lead, slot=3)))
    with pytest.raises(RedCaptureLeadError):
        plan.require_result(party(replace(a, slot=1), replace(b, slot=2), replace(lead, slot=3)))


def test_require_result_changed_order_or_values():
    lead = member(1, moves=(MoveObservation(106, 30),))
    helper = member(2, moves=(MoveObservation(1, 20),))
    plan = plan_capture_lead(party(lead, helper))
    plan.require_result(party(replace(helper, slot=1), replace(lead, slot=2)))
    with pytest.raises(RedCaptureLeadError):
        plan.require_result(party(replace(helper, slot=1, hp=49), replace(lead, slot=2)))
    with pytest.raises(RedCaptureLeadError):
        plan.require_result(party(replace(helper, slot=1, moves=(MoveObservation(1, 19),)),
                                  replace(lead, slot=2)))


def test_all_unqualified_rejected():
    with pytest.raises(RedCaptureLeadError):
        plan_capture_lead(party(member(1, hp=0), member(2, moves=(MoveObservation(106, 30),))))


def test_unknown_move_catalog_fails_closed():
    with pytest.raises(RedBattleCatalogError):
        plan_capture_lead(party(member(1, moves=(MoveObservation(999, 10),))))
