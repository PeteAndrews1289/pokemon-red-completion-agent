from dataclasses import replace

import pytest
from test_living_dex_goal_policy import _model, _question

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
    GoalOpportunity,
)
from pokemon_red_completion.goal_resource_quote import GoalResourceQuote, GoalResourceReserve
from pokemon_red_completion.living_dex_goal_policy import LivingDexGoalShadowPolicy
from pokemon_red_completion.living_dex_option_value import LIVING_DEX_OPTION_FEATURE_NAMES


def _quote(*, funds=10_000, stock=0):
    return GoalResourceQuote(funds, 1_000, (GoalResourceReserve("capture", stock, 10, 10),))


def _quoted_question(quote):
    acquire = next(x for x in _question().opportunities if x.kind is GoalKind.ACQUIRE_SPECIES)
    supply = GoalOpportunity(
        "hidden-mart", GoalKind.RESUPPLY, GoalAvailability.AVAILABLE, 0.2, 0.1, resource_quote=quote
    )
    return GoalManagerQuestion(_question().situation, (acquire, supply))


def _supply_model():
    model = _model(acquire_success=0.65)
    weights = model.coefficients.copy()
    weights[LIVING_DEX_OPTION_FEATURE_NAMES.index("kind.resupply"), 0] = 0.75
    return replace(model, coefficients=weights)


def test_costs_distinguish_budgets_and_excess_without_changing_predictions():
    decisions = []
    for quote, expected in (
        (_quote(), GoalKind.RESUPPLY),
        (_quote(funds=1_100), GoalKind.ACQUIRE_SPECIES),
        (_quote(stock=9), GoalKind.ACQUIRE_SPECIES),
    ):
        policy = LivingDexGoalShadowPolicy(_supply_model())
        assert policy.select(_quoted_question(quote)).kind is expected
        decisions.append(policy.last_decision)
    rich, poor, excess = decisions
    assert rich.scores[1].utility == pytest.approx(2.95)
    assert poor.scores[1].utility == pytest.approx(3.0 - 0.5 * 1000 / 1100)
    assert excess.scores[1].utility == pytest.approx(2.5)
    assert rich.scores[1].predicted_outcomes == poor.scores[1].predicted_outcomes
    assert rich.scores[1].predicted_outcomes == excess.scores[1].predicted_outcomes
    assert rich.menu_sha256 == poor.menu_sha256 == excess.menu_sha256
    assert len({x.economic_input_sha256 for x in decisions}) == 3
    public = rich.public_dict()
    assert public["economic_contract"] == "known-spend-and-excess-reserve-v1"
    assert public["scores"][1]["predicted_utility"] == pytest.approx(3.0)
    assert "hidden-mart" not in str(public)


def test_quote_does_not_override_critical_supply_safety():
    question = _quoted_question(_quote(funds=1_100))
    question = replace(question, situation=replace(question.situation, resource_pressure=0.95))
    policy = LivingDexGoalShadowPolicy(_supply_model())
    assert policy.select(question).kind is GoalKind.RESUPPLY
    assert policy.last_decision.mode.value == "deterministic_safety"
    assert policy.model_decisions == 0


def test_quote_v2_roundtrip_and_identity_free_permutation():
    question = _quoted_question(_quote())
    assert question.policy_input["schema"] == "pokemon.core.goal-manager-input.v2"
    restored = GoalManagerQuestion.from_policy_input(question.policy_input)
    assert restored.policy_context_sha256 == question.policy_context_sha256
    assert restored.opportunities[1].resource_quote == _quote()
    shuffled = replace(question, opportunities=tuple(reversed(question.opportunities)))
    assert shuffled.policy_context_sha256 == question.policy_context_sha256
    policy = LivingDexGoalShadowPolicy(_supply_model())
    assert policy.select(shuffled).kind is GoalKind.RESUPPLY
    assert policy.last_decision.selected_candidate_index == 0


def test_legacy_question_and_decision_remain_unquoted_v1():
    question = _question()
    assert question.policy_input["schema"] == "pokemon.core.goal-manager-input.v1"
    assert all("resource_quote" not in x for x in question.policy_input["candidates"])
    policy = LivingDexGoalShadowPolicy(_model())
    policy.select(question)
    assert "economic_input_sha256" not in policy.last_decision.public_dict()
    assert all(
        "known_resource_cost_penalty" not in x.public_dict() for x in policy.last_decision.scores
    )
    assert (
        GoalManagerQuestion.from_policy_input(question.policy_input).policy_context_sha256
        == question.policy_context_sha256
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("available_funds", True),
        ("available_funds", 999),
        ("purchase_cost", -1),
        ("purchase_cost", 0),
        ("purchase_cost", 1.5),
    ],
)
def test_invalid_or_unaffordable_quote_rejected(field, value):
    with pytest.raises(ValueError):
        replace(_quote(), **{field: value})


def test_parser_rejects_hidden_identity_and_version_downgrade():
    public = _quote().public_dict()
    public["map_id"] = 1
    with pytest.raises(ValueError):
        GoalResourceQuote.from_public_dict(public)
    question = dict(_quoted_question(_quote()).policy_input)
    question["schema"] = "pokemon.core.goal-manager-input.v1"
    with pytest.raises(ValueError):
        GoalManagerQuestion.from_policy_input(question)
    question = dict(_question().policy_input)
    question["schema"] = "pokemon.core.goal-manager-input.v2"
    with pytest.raises(ValueError):
        GoalManagerQuestion.from_policy_input(question)


def test_quote_only_attaches_to_available_supply_and_duplicate_resources_fail():
    with pytest.raises(ValueError):
        replace(_quoted_question(_quote()).opportunities[0], resource_quote=_quote())
    with pytest.raises(ValueError):
        replace(_quote(), reserves=_quote().reserves * 2)


def test_mixed_reserves_excess_is_only_newly_purchased_excess():
    quote = GoalResourceQuote(
        10_000,
        2_000,
        (
            GoalResourceReserve("recovery", 20, 8, 2),
            GoalResourceReserve("capture", 2, 10, 8),
        ),
    )
    assert quote.cost_units == pytest.approx(0.4)
    assert quote.reserves[0].resource == "capture"
    assert GoalResourceQuote.from_public_dict(quote.public_dict()) == quote
