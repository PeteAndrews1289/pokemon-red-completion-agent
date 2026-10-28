"""Finite preparation never invents an evolution endpoint or outcome label."""
from dataclasses import replace
import pytest
from pokemon_red_completion.party_development_rank import (
    CandidateCompletionSemantics, EvolutionRouteKind, EvolutionSemantics,
    PartyDevelopmentContext, PartyDevelopmentGoal, PartyDevelopmentFeatureError,
    augment_training_candidate_set,
)
from pokemon_red_completion.player_option_level_workload import OptionLevelWorkload
from pokemon_red_completion.team_training import BalancedTeamPolicy, GrindingArea
from pokemon_red_completion.training_candidate_rank import project_venue_choice_set, project_trainee_choice_set, TrainingChoiceKind
from test_party_development_outcomes import _before_party


def projection(*, target=21, xp=93, evolution=None, goal=PartyDevelopmentGoal.BALANCE,
               declared=True, include=True, levels=None, declared_work=None, kind=None):
    party = _before_party()
    party = replace(party, members=(replace(party.members[0], level=20, experience=9168), party.members[1]))
    base = project_venue_choice_set(party, party.members[0],
        BalancedTeamPolicy(minimum_level=target, required_size=2),
        (GrindingArea("private-near", 12, 18), GrindingArea("private-far", 18, 24)))[1]
    if kind is not None:
        assert kind is TrainingChoiceKind.TRAINEE
        base = project_trainee_choice_set(party, BalancedTeamPolicy(minimum_level=50, required_size=2),
            (GrindingArea("private-near", 12, 18), GrindingArea("private-far", 18, 24)))[1]
    context = PartyDevelopmentContext(goal=goal, party_size=2, below_floor_count=1,
        evolution_needed_count=0, registration_needed_count=0, living_needed_count=0,
        role_gap_count=0, registration_completion_ratio=.5, living_completion_ratio=.5,
        role_coverage_ratio=1., healthy_trainable_count=2, exhausted_count=0, fainted_count=0)
    semantic = CandidateCompletionSemantics(evolution=evolution or
        EvolutionSemantics(False, 0, EvolutionRouteKind.NONE))
    work = OptionLevelWorkload(20, target, xp)
    return augment_training_candidate_set(base, context, (semantic, semantic),
        include_workload=include, level_workloads=(levels or (work, work)) if include else None,
        fixed_level_target=(declared_work if declared_work is not None else work) if declared else None)


@pytest.mark.parametrize("target,xp", [(21,93),(23,2999),(30,17832)])
def test_explicit_balance_workload_preserves_fixed_target_across_venues(target,xp):
    menu=projection(target=target,xp=xp)
    rows=[dict(zip(menu.feature_names,c.features,strict=True)) for c in menu.candidates]
    for row in rows:
        assert row["level_workload.current_level"]==.2
        assert row["level_workload.target_level"]==target/100
        assert row["level_workload.remaining_xp"]==xp/2_000_000
        assert row["candidate.evolution_method.none"]==1
    assert rows[0]["level_workload.remaining_xp"]==rows[1]["level_workload.remaining_xp"]


def test_natural_evolution_distance_remains_independent_of_preparation_target():
    evolution=EvolutionSemantics(True,1,EvolutionRouteKind.LEVEL,levels_to_next=1)
    menu=projection(target=23,xp=2999,evolution=evolution)
    row=dict(zip(menu.feature_names,menu.candidates[0].features,strict=True))
    assert row["candidate.evolution_level_distance"]==1/99
    assert row["level_workload.level_gain"]==.03
    with pytest.raises(PartyDevelopmentFeatureError,match="contradicts"):
        projection(target=23,xp=2999,evolution=evolution,declared=False)


def test_legacy_non_evolution_workload_still_requires_explicit_target():
    with pytest.raises(PartyDevelopmentFeatureError,match="contradicts"):
        projection(declared=False)


@pytest.mark.parametrize("goal",[PartyDevelopmentGoal.EVOLUTION,PartyDevelopmentGoal.COLLECTION,
                                  PartyDevelopmentGoal.ROLE_COVERAGE])
def test_fixed_target_cannot_bypass_other_goal_semantics(goal):
    with pytest.raises(PartyDevelopmentFeatureError,match="declared balance"):
        projection(goal=goal)


@pytest.mark.parametrize("kwargs",[
    {"include":False}, {"declared_work":True}, {"kind":TrainingChoiceKind.TRAINEE},
    {"levels":(OptionLevelWorkload(20,21,94),)*2}, {"levels":(None,None)},
])
def test_fixed_target_requires_explicit_matching_typed_venue_workload(kwargs):
    with pytest.raises(PartyDevelopmentFeatureError,match="declared balance"):
        projection(**kwargs)


def test_fixed_target_does_not_weaken_observed_level_or_shared_workload_checks():
    wrong=OptionLevelWorkload(19,21,100)
    with pytest.raises(PartyDevelopmentFeatureError,match="contradicts"):
        projection(levels=(wrong,wrong),declared_work=wrong)
    with pytest.raises(PartyDevelopmentFeatureError,match="one observed trainee"):
        projection(levels=(OptionLevelWorkload(20,21,93),OptionLevelWorkload(20,23,2999)))


def test_explicit_and_legacy_matching_evolution_projection_are_byte_identical():
    evolution=EvolutionSemantics(True,1,EvolutionRouteKind.LEVEL,levels_to_next=1)
    assert projection(evolution=evolution).public_dict()==projection(evolution=evolution,declared=False).public_dict()
