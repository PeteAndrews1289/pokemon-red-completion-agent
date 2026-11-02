from dataclasses import replace

import pytest

from pokemon_red_completion.party import MoveObservation, PartyMemberObservation
from pokemon_red_completion.party_preparation import (
    ObservedOpponent,
    PreparationAttempt,
    PreparationBudget,
    PreparationMember,
    build_preparation_plan,
    next_preparation_decision,
)
from pokemon_red_completion.party_preparation import (
    PreparationPurpose as Purpose,
)
from pokemon_red_completion.team_training import TeamTrainingDirective as Directive


def team(*levels):
    return tuple(
        PreparationMember(
            f"specimen-{i}",
            PartyMemberObservation(i, i, level, 50, 50, moves=(MoveObservation(33, 20),)),
            Purpose.COMBAT,
            "intended combat team",
        )
        for i, level in enumerate(levels, 1)
    )


def enemies(*levels):
    return tuple(ObservedOpponent("observed-battle", i, level) for i, level in enumerate(levels, 1))


def attempt(ref="specimen-2", **changes):
    values = dict(
        specimen_ref=ref,
        level_before=22,
        level_after=22,
        xp_gained=10,
        actions=50,
        frames=500,
        elapsed_seconds=2,
    )
    return PreparationAttempt(**(values | changes))


def test_carry_does_not_mask_reserves_or_set_their_target():
    members = team(45, 22, 22, 25)
    plan = build_preparation_plan(members, enemies(37, 38, 35, 35, 40))
    assert plan.opposition_level == 37
    assert plan.combat_median == 23.5 and plan.combat_spread == 23
    assert plan.targets == (("specimen-2", 34), ("specimen-3", 34), ("specimen-4", 34))
    assert next_preparation_decision(plan, members).target_slot == 2


def test_uniformly_underleveled_team_triggers_without_internal_spread():
    plan = build_preparation_plan(team(20, 20, 20), enemies(30))
    assert len(plan.targets) == 3 and set(dict(plan.targets).values()) == {27}


@pytest.mark.parametrize("purpose", [Purpose.UNDECIDED, Purpose.COLLECTION, Purpose.FIELD_UTILITY])
def test_new_catch_and_noncombat_members_do_not_trigger_training(purpose):
    members = team(40, 39, 3)
    members = members[:2] + (replace(members[2], purpose=purpose),)
    plan = build_preparation_plan(members, enemies(40))
    assert not plan.targets
    assert next_preparation_decision(plan, members).reason == "level preparation not needed"


def test_ready_team_stops_even_with_extreme_carry_spread():
    members = team(80, 37, 37)
    assert not build_preparation_plan(members, enemies(40)).targets


def test_rotation_counts_failed_attempts_and_does_not_repeat_weakest():
    members = team(45, 22, 22, 25)
    plan = build_preparation_plan(members, enemies(37))
    first = attempt(failed=True, xp_gained=0)
    assert next_preparation_decision(plan, members, (first,)).target_slot == 3
    second = attempt("specimen-3")
    assert next_preparation_decision(plan, members, (first, second)).target_slot == 4


def test_finishing_one_reserve_does_not_finish_the_team():
    members = team(45, 22, 22, 25)
    plan = build_preparation_plan(members, enemies(37))
    improved = (
        members[0],
        replace(members[1], observation=replace(members[1].observation, level=34)),
        *members[2:],
    )
    assert next_preparation_decision(plan, improved).target_slot == 3
    ready = tuple(
        replace(m, observation=replace(m.observation, level=max(34, m.observation.level)))
        for m in members
    )
    assert next_preparation_decision(plan, ready).reason == "all preparation targets reached"


def test_reordering_and_evolution_keep_the_same_target_identity():
    members = team(45, 22, 22, 25)
    plan = build_preparation_plan(members, enemies(37))
    reordered = tuple(
        replace(m, observation=replace(m.observation, slot=i, species_id=100 + i))
        for i, m in enumerate((members[1], members[0], *members[2:]), 1)
    )
    decision = next_preparation_decision(plan, reordered)
    assert decision.directive == Directive.TRAIN_MEMBER and decision.target_slot == 1
    assert next_preparation_decision(plan, reordered, (attempt(),)).target_slot == 3


def test_repeated_turns_do_not_overweight_one_enemy():
    seen = enemies(20, 40, 40)
    plan = build_preparation_plan(team(25, 25), seen + (seen[0],) * 100)
    assert plan.opposition_level == 40 and plan.observed_opponents == 3
    with pytest.raises(ValueError, match="conflicting"):
        build_preparation_plan(team(25), seen + (replace(seen[0], level=30),))


def test_unknown_opposition_is_not_inferred_from_carry():
    members = team(50, 5)
    plan = build_preparation_plan(members, ())
    assert not plan.targets and plan.opposition_level is None
    assert next_preparation_decision(plan, members).reason == "opposition evidence required"


def test_frozen_plan_rejects_corrupt_or_noncombat_targets():
    plan = build_preparation_plan(team(45, 22), enemies(37))
    for changes in (
        {"targets": (("specimen-1", 46),)},
        {"targets": (("specimen-2", 99),)},
        {"targets": plan.targets * 2},
        {"opposition_level": None},
        {"observed_opponents": 0},
    ):
        with pytest.raises(ValueError):
            replace(plan, **changes)


def test_milestone_can_trigger_but_cannot_overlevel():
    members = team(30)
    members = (replace(members[0], milestone_level=31),)
    assert build_preparation_plan(members, enemies(32)).targets == (("specimen-1", 31),)
    with pytest.raises(ValueError, match="exceeds"):
        build_preparation_plan(members, enemies(25))


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("max_attempts", 1, "attempt budget"),
        ("max_actions", 50, "action budget"),
        ("max_frames", 500, "frame budget"),
        ("max_seconds", 2, "time budget"),
        ("max_heals", 1, "healing budget"),
    ],
)
def test_all_resource_limits_retain_failure_costs(field, value, reason):
    members = team(45, 22)
    plan = build_preparation_plan(
        members, enemies(37), budget=replace(PreparationBudget(), **{field: value})
    )
    assert (
        next_preparation_decision(plan, members, (attempt(failed=True, heals=1),)).reason == reason
    )


def test_no_progress_stops_and_fainting_requests_recovery():
    members = team(45, 22)
    plan = build_preparation_plan(members, enemies(37))
    failed = (attempt(xp_gained=0, failed=True),) * 3
    assert "no XP progress" in next_preparation_decision(plan, members, failed).reason
    fainted = (replace(members[0], observation=replace(members[0].observation, hp=0)), members[1])
    assert next_preparation_decision(plan, fainted).directive == Directive.RESTORE_TEAM


def test_no_role_evasion_or_identity_aliasing():
    members = team(45, 22)
    plan = build_preparation_plan(members, enemies(37))
    with pytest.raises(ValueError, match="role"):
        next_preparation_decision(
            plan, (members[0], replace(members[1], purpose=Purpose.COLLECTION))
        )
    with pytest.raises(ValueError, match="roster"):
        next_preparation_decision(plan, (replace(members[0], specimen_ref="new"), members[1]))
    with pytest.raises(ValueError, match="ambiguous"):
        build_preparation_plan(
            (members[0], replace(members[1], specimen_ref="specimen-1")), enemies(37)
        )
    with pytest.raises(ValueError, match="frozen"):
        next_preparation_decision(plan, members, (attempt("specimen-1"),))


@pytest.mark.parametrize(
    "changes",
    [
        dict(xp_gained=-1),
        dict(elapsed_seconds=float("nan")),
        dict(elapsed_seconds=True),
        dict(failed=1),
        dict(frames=True),
    ],
)
def test_malformed_receipts_rejected(changes):
    with pytest.raises(ValueError):
        attempt(**changes)
