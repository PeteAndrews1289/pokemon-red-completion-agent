from dataclasses import replace

import pytest
from test_goal_resource_quote import _quote, _quoted_question, _supply_model

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_player_exploration import (
    DETERMINISTIC_POLICY_ID,
    EXPLORATION_POLICY_ID,
    ExploringLivingDexGoalPolicy,
)


def test_full_support_sampling_replays_and_retains_exact_model_projection():
    question = _quoted_question(_quote())
    first = ExploringLivingDexGoalPolicy(_supply_model(), seed=17)
    second = ExploringLivingDexGoalPolicy(_supply_model(), seed=17)
    selections = []
    for _ in range(20):
        chosen = first.select(question)
        assert second.select(question) == chosen
        metadata = first.selection_metadata()
        assert metadata == second.selection_metadata()
        probabilities = metadata["candidate_probabilities"]
        assert sum(probabilities) == pytest.approx(1.0)
        assert all(p >= 0.125 for p in probabilities)
        assert metadata["selected_probability"] == probabilities[chosen.selected_index]
        assert metadata["behavior_policy_id"] == EXPLORATION_POLICY_ID
        assert first.training_eligible
        assert first.last_menu.policy_sha256 == first.last_decision.menu_sha256
        assert first.last_decision.selected_candidate_index == chosen.selected_index
        selections.append(chosen.kind)
    assert set(selections) == {GoalKind.ACQUIRE_SPECIES, GoalKind.RESUPPLY}


def test_critical_supply_is_disclosed_as_nontraining_without_randomization():
    question = _quoted_question(_quote(funds=1100))
    emergency = replace(question, situation=replace(question.situation, resource_pressure=0.99))
    policy = ExploringLivingDexGoalPolicy(_supply_model(), seed=19)
    untouched = ExploringLivingDexGoalPolicy(_supply_model(), seed=19)
    assert policy.select(emergency).kind is GoalKind.RESUPPLY
    assert not policy.training_eligible
    assert policy.last_menu is None and policy.option_probabilities == ()
    assert policy.selection_metadata()["behavior_policy_id"] == DETERMINISTIC_POLICY_ID
    assert policy.selection_metadata()["candidate_probabilities"] == [0.0, 1.0]
    assert policy.select(question) == untouched.select(question)


def test_returned_metadata_cannot_mutate_the_logged_distribution():
    policy = ExploringLivingDexGoalPolicy(_supply_model(), seed=0)
    with pytest.raises(ValueError):
        policy.selection_metadata()
    policy.select(_quoted_question(_quote()))
    metadata = policy.selection_metadata()
    metadata["candidate_probabilities"][0] = 0
    assert policy.selection_metadata()["candidate_probabilities"][0] > 0


def test_training_cannot_silently_omit_an_available_purchase_quote():
    question = _quoted_question(_quote())
    question = replace(
        question,
        opportunities=tuple(replace(item, resource_quote=None) for item in question.opportunities),
    )
    policy = ExploringLivingDexGoalPolicy(_supply_model(), seed=0)
    with pytest.raises(ValueError, match="quoted resupply"):
        policy.select(question)
    assert policy.decisions == 0


@pytest.mark.parametrize("seed", [-1, True, 1.5])
def test_invalid_seed_is_rejected(seed):
    with pytest.raises(ValueError):
        ExploringLivingDexGoalPolicy(_supply_model(), seed=seed)
