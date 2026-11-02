from dataclasses import replace

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
from pokemon_red_completion.living_dex_option_value import (
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.player_decision_probe import (
    PlayerDecisionProbe,
    compare_player_decision_pair,
    probe_player_decision,
)
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def question(*, team=0.1, safety=0.0, second=GoalKind.DEVELOP_TEAM, identity="red-private"):
    return GoalManagerQuestion(
        GoalSituation(story_pressure=0.5, collection_pressure=0.4, team_pressure=team,
                      evolution_pressure=0.0, safety_pressure=safety, resource_pressure=0.0,
                      storage_pressure=0.0, recovery_pressure=0.0, exploration_pressure=0.0),
        tuple(GoalOpportunity(f"{identity}-{i}", kind, GoalAvailability.AVAILABLE,
                              estimated_effort=0.2, estimated_risk=0.25)
              for i, kind in enumerate((GoalKind.ADVANCE_STORY, second))),
    )


def probe(q, version=4):
    return probe_player_decision(q, economy_snapshot=EconomySnapshot(1000, ()),
                                 target_cash=3000, feature_version=version)


def compare(a, b):
    return compare_player_decision_pair(probe(a), probe(b), before_pair=(0, 1), after_pair=(0, 1))


def test_exact_runtime_projection_not_a_second_teacher_vector():
    q = question()
    result = probe(q)
    context = living_dex_option_context_from_goal_situation(
        q.situation, economy_snapshot=EconomySnapshot(1000, ()), target_cash=3000)
    for index, vector in zip(result.indices, result.vectors, strict=True):
        candidate = project_living_dex_goal_candidate(q, index, feature_version=4,
                                                    binding_ref="different-private-binding")
        assert vector == candidate.vector(context, feature_version=4)


def test_binding_identity_and_title_renaming_cannot_manufacture_variation():
    report = compare(question(), question(identity="crystal-private"))
    assert report["identical_pair_inputs"]
    assert report["identical_linear_contrast"]
    assert "private" not in str(report)
    assert not report["learned_advantage_demonstrated"]


def test_readiness_common_mode_change_does_not_teach_linear_preference():
    # An actual limitation of V4 with equal risk estimates, not a desired reward.
    report = compare(question(team=0.0), question(team=1.0))
    assert report["changed_input_features"]
    assert report["identical_linear_contrast"]


def test_recovery_pressure_can_change_the_relative_representation():
    report = compare(question(second=GoalKind.RESTORE_TEAM, safety=0.0),
                     question(second=GoalKind.RESTORE_TEAM, safety=1.0))
    assert not report["identical_pair_inputs"]
    assert not report["identical_linear_contrast"]
    assert not report["learned_advantage_demonstrated"]


def test_original_indices_survive_masking_and_reordering():
    q = question()
    hidden = GoalOpportunity("hidden", GoalKind.EXPLORE, GoalAvailability.UNAVAILABLE,
                             unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
    a = probe(replace(q, opportunities=(hidden, *q.opportunities)))
    b = probe(replace(q, opportunities=tuple(reversed(q.opportunities))))
    report = compare_player_decision_pair(a, b, before_pair=(1, 2), after_pair=(1, 0))
    assert a.indices == (1, 2)
    assert report["identical_pair_inputs"]


@pytest.mark.parametrize("pair", [(0, 0), (0, 8), (True, 0), (0,), [0, 1]])
def test_bad_pairs_fail_closed(pair):
    p = probe(question())
    with pytest.raises(ValueError, match="two available indices"):
        compare_player_decision_pair(p, p, before_pair=pair, after_pair=(0, 1))


def test_singletons_are_not_choice_evidence():
    q = question()
    unavailable = GoalOpportunity("unavailable", GoalKind.DEVELOP_TEAM,
                                  GoalAvailability.UNAVAILABLE,
                                  unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
    with pytest.raises(ValueError, match="multi-option"):
        probe(replace(q, opportunities=(q.opportunities[0], unavailable)))


def test_unsupported_available_capability_is_not_silently_omitted():
    with pytest.raises(ValueError, match="unsupported"):
        probe(question(second=GoalKind.RECOVER_CONTROL))


def test_mismatched_roles_and_versions_rejected():
    p = probe(question())
    with pytest.raises(ValueError, match="roles"):
        compare_player_decision_pair(p, p, before_pair=(0, 1), after_pair=(1, 0))
    with pytest.raises(ValueError, match="versions"):
        compare_player_decision_pair(p, probe(question(), 3),
                                     before_pair=(0, 1), after_pair=(0, 1))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_nonfinite_or_boolean_feature_not_admitted(value):
    p = probe(question())
    with pytest.raises(ValueError, match="finite"):
        PlayerDecisionProbe(4, p.indices, p.kinds, ((value, *p.vectors[0][1:]), p.vectors[1]))


@pytest.mark.parametrize("mutation", ["version", "indices", "kinds", "vectors", "row"])
def test_probe_cannot_change_after_inspection(mutation):
    p = probe(question())
    values = dict(feature_version=p.feature_version, indices=p.indices,
                  kinds=p.kinds, vectors=p.vectors)
    if mutation == "version":
        values["feature_version"] = True
    elif mutation == "row":
        values["vectors"] = (list(p.vectors[0]), p.vectors[1])
    else:
        values[mutation] = list(values[mutation])
    with pytest.raises(ValueError, match="immutable"):
        PlayerDecisionProbe(**values)
