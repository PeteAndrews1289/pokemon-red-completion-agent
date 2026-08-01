import pytest

from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    PartyRole,
    StatusCondition,
)
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    GrindingArea,
    RosterSlot,
    TeamRosterPlan,
    TeamTrainingDecision,
    TeamTrainingDirective,
    TeamTrainingProgress,
    TrainingException,
    choose_grinding_area,
    is_matchup_acceptable,
    plan_team_training,
    summarize_team_readiness,
)

POLICY = BalancedTeamPolicy()


def move(move_id: int = 55, current_pp: int = 15) -> MoveObservation:
    return MoveObservation(move_id=move_id, current_pp=current_pp, max_pp=15)


def member(slot: int, level: int = 50, **changes: object) -> PartyMemberObservation:
    values: dict[str, object] = {
        "slot": slot,
        "species_id": slot,
        "level": level,
        "hp": 150,
        "max_hp": 160,
        "moves": (move(), move(57)),
    }
    values.update(changes)
    return PartyMemberObservation(**values)  # type: ignore[arg-type]


def party(*levels: int) -> PartyObservation:
    return PartyObservation(
        members=tuple(member(index, level) for index, level in enumerate(levels, start=1))
    )


def decide(*levels: int, **kwargs: object) -> TeamTrainingDecision:
    return plan_team_training(party(*levels), POLICY, **kwargs)  # type: ignore[arg-type]


# --- core directive ordering ------------------------------------------------


def test_empty_party_recruits_the_first_member() -> None:
    decision = plan_team_training(PartyObservation(), POLICY)
    assert decision.directive is TeamTrainingDirective.RECRUIT_MEMBER
    assert decision.target_slot == 1
    assert "empty" in decision.reason


def test_incomplete_party_recruits_into_the_next_open_slot() -> None:
    decision = decide(50, 51, 52)
    assert decision.directive is TeamTrainingDirective.RECRUIT_MEMBER
    assert decision.target_slot == 4
    assert "3 of 6" in decision.reason


def test_fainted_member_restores_the_team_before_any_training() -> None:
    subject = PartyObservation(
        members=(
            member(1, 50),
            member(2, 44, hp=0),
            *(member(index, 50) for index in range(3, 7)),
        )
    )
    decision = plan_team_training(subject, POLICY)
    assert decision.directive is TeamTrainingDirective.RESTORE_TEAM
    assert "1 member(s) fainted" in decision.reason


def test_balanced_full_party_stops() -> None:
    decision = decide(50, 51, 52, 53, 54, 55)
    assert decision.directive is TeamTrainingDirective.STOP
    assert not decision.used_exception
    assert "level floor and spread" in decision.reason


def test_lead_below_the_floor_is_trained_in_place() -> None:
    decision = decide(46, 50, 50, 50, 50, 50)
    assert decision.directive is TeamTrainingDirective.TRAIN_MEMBER
    assert decision.target_slot == 1
    assert "below the level floor" in decision.reason


def test_weakest_member_outside_the_lead_triggers_a_switch() -> None:
    decision = decide(52, 51, 44, 53, 54, 55)
    assert decision.directive is TeamTrainingDirective.SWITCH_TRAINEE
    assert decision.target_slot == 3
    assert "weakest trainable" in decision.reason


def test_excess_spread_trains_the_trailing_member_even_above_the_floor() -> None:
    decision = decide(51, 58, 59, 60, 60, 60)
    assert decision.directive is TeamTrainingDirective.TRAIN_MEMBER
    assert decision.target_slot == 1
    assert "trails the party" in decision.reason


# --- safety and recovery ----------------------------------------------------


@pytest.mark.parametrize(
    "unsafe",
    (
        {"hp": 40},
        {"status": StatusCondition.POISON},
        {"moves": (move(55, 1), move(57, 0))},
    ),
)
def test_unsafe_trainee_restores_the_team_instead_of_training(unsafe: dict[str, object]) -> None:
    subject = PartyObservation(
        members=(member(1, 44, **unsafe), *(member(index, 50) for index in range(2, 7)))
    )
    decision = plan_team_training(subject, POLICY)
    assert decision.directive is TeamTrainingDirective.RESTORE_TEAM
    assert decision.target_slot == 1
    assert "not safe to train" in decision.reason


def test_team_without_any_usable_move_restores_rather_than_stalling() -> None:
    subject = PartyObservation(
        members=tuple(
            member(index, 44, moves=(move(55, 0),)) for index in range(1, 7)
        )
    )
    decision = plan_team_training(subject, POLICY)
    assert decision.directive is TeamTrainingDirective.RESTORE_TEAM
    assert "no member can currently act" in decision.reason


def test_capped_team_with_one_spent_member_reports_nobody_left_to_train() -> None:
    """The only member still needing levels is out of PP; everyone else is capped."""

    subject = PartyObservation(
        members=(
            member(1, 100),
            member(2, 44, moves=(move(55, 0),)),
            *(member(index, 100) for index in range(3, 7)),
        )
    )
    decision = plan_team_training(subject, POLICY)
    assert decision.directive is TeamTrainingDirective.RESTORE_TEAM
    assert "no member can currently gain experience" in decision.reason


@pytest.mark.parametrize(
    ("progress", "expected"),
    (
        (TeamTrainingProgress(battles_completed=400), "battle budget"),
        (TeamTrainingProgress(steps_taken=40_000), "step budget"),
        (TeamTrainingProgress(healing_trips=40), "healing budget"),
        (TeamTrainingProgress(faints=4), "faint budget"),
    ),
)
def test_exhausted_effort_bounds_stop_the_block(
    progress: TeamTrainingProgress, expected: str
) -> None:
    decision = decide(20, 20, 20, 20, 20, 20, progress=progress)
    assert decision.directive is TeamTrainingDirective.STOP
    assert expected in decision.reason


# --- recorded exceptions ----------------------------------------------------


def test_incomplete_party_exception_allows_progress_and_records_its_reason() -> None:
    allowance = TrainingException(
        "Fly is required before the sixth member is reachable",
        allows_incomplete_party=True,
    )
    decision = decide(44, 50, 50, exception=allowance)
    assert decision.directive is TeamTrainingDirective.TRAIN_MEMBER
    assert decision.used_exception
    assert decision.exception_reason == allowance.reason


def test_level_shortfall_exception_stops_instead_of_grinding() -> None:
    allowance = TrainingException(
        "badge gate must open before the safe area is reachable",
        allows_level_shortfall=True,
    )
    decision = decide(44, 45, 46, 47, 48, 49, exception=allowance)
    assert decision.directive is TeamTrainingDirective.STOP
    assert decision.exception_reason == allowance.reason


def test_spread_exception_tolerates_a_wide_party() -> None:
    allowance = TrainingException("newly caught member joins mid-route", allows_level_spread=True)
    decision = decide(50, 51, 52, 53, 54, 62, exception=allowance)
    assert decision.directive is TeamTrainingDirective.STOP
    assert decision.exception_reason == allowance.reason


def test_exception_requires_a_reason_and_at_least_one_allowance() -> None:
    with pytest.raises(ValueError, match="non-empty reason"):
        TrainingException("   ", allows_level_spread=True)
    with pytest.raises(ValueError, match="at least one deviation"):
        TrainingException("no deviation requested")


def test_unrelated_exception_does_not_suppress_a_different_rule() -> None:
    allowance = TrainingException("spread only", allows_level_spread=True)
    decision = decide(44, 50, 50, 50, 50, 50, exception=allowance)
    assert decision.directive is TeamTrainingDirective.TRAIN_MEMBER
    assert "below the level floor" in decision.reason


# --- roster plan ------------------------------------------------------------


def test_roster_plan_reports_missing_species_and_substitutions() -> None:
    plan = TeamRosterPlan(
        (
            RosterSlot(PartyRole.LEAD_ATTACKER, 9),
            RosterSlot(PartyRole.PHYSICAL_SWEEPER, 51),
            RosterSlot(
                PartyRole.FIELD_UTILITY,
                83,
                is_substitution=True,
                substitution_reason="traded in-game; arrives with Fly access",
            ),
        )
    )
    assert plan.species_ids == (9, 51, 83)
    assert len(plan.substitutions) == 1
    assert plan.substitutions[0].substitution_reason is not None

    current = PartyObservation(members=(member(1, 50, species_id=9), member(2, 50, species_id=25)))
    assert tuple(slot.species_id for slot in plan.missing_from(current)) == (51, 83)
    assert plan.unplanned_in(current) == (25,)


def test_roster_substitution_without_a_reason_is_rejected() -> None:
    with pytest.raises(ValueError, match="requires a recorded reason"):
        RosterSlot(PartyRole.SPECIAL_SWEEPER, 135, is_substitution=True)
    with pytest.raises(ValueError, match="only meaningful for a substitution"):
        RosterSlot(PartyRole.SPECIAL_SWEEPER, 135, substitution_reason="unused")


def test_roster_plan_rejects_duplicate_roles_and_species() -> None:
    with pytest.raises(ValueError, match="repeat a role"):
        TeamRosterPlan(
            (
                RosterSlot(PartyRole.LEAD_ATTACKER, 9),
                RosterSlot(PartyRole.LEAD_ATTACKER, 51),
            )
        )
    with pytest.raises(ValueError, match="repeat a species"):
        TeamRosterPlan(
            (
                RosterSlot(PartyRole.LEAD_ATTACKER, 9),
                RosterSlot(PartyRole.PHYSICAL_SWEEPER, 9),
            )
        )


# --- matchup and area selection ---------------------------------------------


def test_matchup_selection_rejects_overmatched_and_unknown_opponents() -> None:
    trainee = member(1, 50)
    assert is_matchup_acceptable(trainee, 54, POLICY)
    assert not is_matchup_acceptable(trainee, 55, POLICY)
    assert not is_matchup_acceptable(trainee, None, POLICY)
    assert not is_matchup_acceptable(member(1, 50, hp=40), 50, POLICY)


def test_grinding_area_selection_prefers_the_fastest_safe_band() -> None:
    areas = (
        GrindingArea("slow_but_safe", 20, 24),
        GrindingArea("fast_and_safe", 40, 54),
        GrindingArea("too_strong", 55, 60),
    )
    chosen = choose_grinding_area(areas, member(1, 50), POLICY)
    assert chosen is not None
    assert chosen.area_id == "fast_and_safe"


def test_grinding_area_selection_can_require_a_nearby_healer() -> None:
    areas = (GrindingArea("remote", 40, 50, has_nearby_healer=False),)
    assert choose_grinding_area(areas, member(1, 50), POLICY) is None
    assert choose_grinding_area(areas, member(1, 50), POLICY, require_healer=False) is not None


def test_grinding_area_selection_returns_none_when_every_band_is_unsafe() -> None:
    areas = (GrindingArea("deep", 60, 70),)
    assert choose_grinding_area(areas, member(1, 50), POLICY) is None


def test_grinding_area_validates_its_band() -> None:
    with pytest.raises(ValueError, match="cannot be below the minimum"):
        GrindingArea("inverted", 40, 30)
    with pytest.raises(ValueError, match="non-empty semantic label"):
        GrindingArea("  ", 10, 20)


# --- readiness receipt ------------------------------------------------------


def test_readiness_receipt_passes_only_for_a_complete_balanced_healthy_team() -> None:
    ready = summarize_team_readiness(party(50, 51, 52, 53, 54, 55), POLICY)
    assert ready.passed
    assert ready.has_full_party
    assert ready.meets_level_floor
    assert ready.is_balanced

    short = summarize_team_readiness(party(50, 51, 52), POLICY)
    assert not short.passed
    assert not short.has_full_party

    low = summarize_team_readiness(party(44, 50, 50, 50, 50, 50), POLICY)
    assert not low.passed
    assert not low.meets_level_floor

    wide = summarize_team_readiness(party(50, 51, 52, 53, 54, 62), POLICY)
    assert not wide.passed
    assert not wide.is_balanced


def test_readiness_receipt_records_exception_reasons() -> None:
    report = summarize_team_readiness(
        party(50, 51, 52, 53, 54, 55), POLICY, ("Fly gate deferred the sixth member",)
    )
    assert report.exception_reasons == ("Fly gate deferred the sixth member",)


def test_empty_party_receipt_fails_every_gate() -> None:
    report = summarize_team_readiness(PartyObservation(), POLICY)
    assert not report.passed
    assert not report.meets_level_floor
    assert not report.is_balanced


# --- policy validation ------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "match"),
    (
        ("minimum_level", 1, "minimum_level"),
        ("maximum_level_spread", -1, "maximum_level_spread"),
        ("required_size", 7, "required_size"),
        ("retreat_hp_ratio", 0.0, "retreat_hp_ratio"),
        ("max_faints", -1, "max_faints"),
    ),
)
def test_policy_rejects_invalid_configuration(field: str, value: object, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        BalancedTeamPolicy(**{field: value})  # type: ignore[arg-type]
