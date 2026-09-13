from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerError,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
    bind_goal_selection,
)
from pokemon_red_completion.goal_manager_runtime import (
    CompletionFirstGoalTeacher,
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_resource_quote import (
    GoalResourceQuote,
    GoalResourceReserve,
)

_SITUATION_PRESSURES = {
    "story_progress": 0.20,
    "collection_progress": 0.20,
    "team_readiness": 0.20,
    "evolution_progress": 0.20,
    "safety": 0.10,
    "resources": 0.10,
    "storage_capacity": 0.10,
    "control_recovery": 0.0,
    "world_knowledge": 0.20,
}

V1_LITERAL: dict[str, object] = {
    "schema": "pokemon.core.goal-manager-input.v1",
    "situation": {
        "schema": "pokemon.core.goal-situation.v1",
        "need_pressures": _SITUATION_PRESSURES,
    },
    "candidates": [
        {
            "kind": "advance_story",
            "availability": "available",
            "addressed_needs": ["story_progress"],
            "estimated_effort": 0.20,
            "estimated_risk": 0.10,
            "unavailable_reason": None,
        },
        {
            "kind": "restore_team",
            "availability": "available",
            "addressed_needs": ["safety"],
            "estimated_effort": 0.10,
            "estimated_risk": 0.05,
            "unavailable_reason": None,
        },
    ],
}

V2_LITERAL: dict[str, object] = {
    "schema": "pokemon.core.goal-manager-input.v2",
    "situation": {
        "schema": "pokemon.core.goal-situation.v1",
        "need_pressures": _SITUATION_PRESSURES,
    },
    "candidates": [
        {
            "kind": "advance_story",
            "availability": "available",
            "addressed_needs": ["story_progress"],
            "estimated_effort": 0.20,
            "estimated_risk": 0.10,
            "unavailable_reason": None,
        },
        {
            "kind": "resupply",
            "availability": "available",
            "addressed_needs": ["resources"],
            "estimated_effort": 0.10,
            "estimated_risk": 0.02,
            "unavailable_reason": None,
            "resource_quote": {
                "schema": "pokemon.core.goal-resource-quote.v1",
                "available_funds": 1168,
                "purchase_cost": 200,
                "reserves": [
                    {
                        "resource": "capture",
                        "available": 0,
                        "target": 10,
                        "purchased": 1,
                    }
                ],
            },
        },
    ],
}

V3_LITERAL: dict[str, object] = {
    "schema": "pokemon.core.goal-manager-input.v3",
    "situation": {
        "schema": "pokemon.core.goal-situation.v1",
        "need_pressures": _SITUATION_PRESSURES,
    },
    "candidates": [
        {
            "kind": "acquire_species",
            "availability": "available",
            "addressed_needs": ["collection_progress"],
            "estimated_effort": 0.30,
            "estimated_risk": 0.10,
            "unavailable_reason": None,
            "search_history": {
                "schema": "pokemon.core.search-history.v1",
                "coverage": "since_tracking_started",
                "earlier_history_known": False,
                "attempts": 2,
                "exhausted": 1,
                "actions": 17,
                "frames": 250,
            },
        },
        {
            "kind": "advance_story",
            "availability": "available",
            "addressed_needs": ["story_progress"],
            "estimated_effort": 0.20,
            "estimated_risk": 0.10,
            "unavailable_reason": None,
        },
    ],
}


def _situation(**overrides: float) -> GoalSituation:
    values = {
        "story_pressure": 0.20,
        "collection_pressure": 0.20,
        "team_pressure": 0.20,
        "evolution_pressure": 0.20,
        "safety_pressure": 0.10,
        "resource_pressure": 0.10,
        "storage_pressure": 0.10,
        "recovery_pressure": 0.0,
        "exploration_pressure": 0.20,
    }
    values.update(overrides)
    return GoalSituation(**values)


def _story_opportunity(binding_ref: str = "test:story") -> GoalOpportunity:
    return GoalOpportunity(
        binding_ref=binding_ref,
        kind=GoalKind.ADVANCE_STORY,
        availability=GoalAvailability.AVAILABLE,
        estimated_effort=0.20,
        estimated_risk=0.10,
    )


def _earning_resupply_opportunity(
    binding_ref: str = "test:resupply:earn",
    *,
    expected_income: int = 725,
    available_funds: int = 1168,
    effort: float = 0.30,
    risk: float = 0.15,
) -> GoalOpportunity:
    quote = GoalResourceQuote(
        available_funds=available_funds,
        purchase_cost=0,
        reserves=(),
        expected_income=expected_income,
    )
    return GoalOpportunity(
        binding_ref=binding_ref,
        kind=GoalKind.RESUPPLY,
        availability=GoalAvailability.AVAILABLE,
        estimated_effort=effort,
        estimated_risk=risk,
        resource_quote=quote,
    )


def _purchase_resupply_opportunity(
    binding_ref: str = "test:resupply:buy",
    *,
    purchase_cost: int = 200,
    available_funds: int = 1168,
    effort: float = 0.10,
    risk: float = 0.02,
) -> GoalOpportunity:
    reserve = GoalResourceReserve(
        "capture", available=0, target=10, purchased=1
    )
    quote = GoalResourceQuote(
        available_funds=available_funds,
        purchase_cost=purchase_cost,
        reserves=(reserve,),
    )
    return GoalOpportunity(
        binding_ref=binding_ref,
        kind=GoalKind.RESUPPLY,
        availability=GoalAvailability.AVAILABLE,
        estimated_effort=effort,
        estimated_risk=risk,
        resource_quote=quote,
    )


def test_old_duplicate_resupply_rejected() -> None:
    situation = _situation()
    story = _story_opportunity()
    earn = _earning_resupply_opportunity()
    buy = _purchase_resupply_opportunity()

    # Default False rejects duplicate RESUPPLY with historical error
    with pytest.raises(GoalManagerError, match="one option per kind"):
        GoalManagerQuestion(situation, (story, earn, buy))

    with pytest.raises(GoalManagerError, match="one option per kind"):
        GoalManagerQuestion(
            situation, (story, earn, buy), allow_resource_variants=False
        )

    # Default False also rejects >2 duplicates with SAME historical error
    buy_extra = _purchase_resupply_opportunity("test:resupply:buy2")
    with pytest.raises(GoalManagerError, match="one option per kind"):
        GoalManagerQuestion(
            situation, (story, earn, buy, buy_extra), allow_resource_variants=False
        )

    # GoalBindingSet.question without opt-in also rejects duplicate kinds
    binding_story = ExecutableGoalBinding(
        binding_ref=story.binding_ref,
        kind=story.kind,
        estimated_effort=story.estimated_effort,
        estimated_risk=story.estimated_risk,
        execute=lambda: GoalExecutionReport(1, 1, {}),
        verify=lambda _r: GoalVerification.succeeded(),
    )
    binding_earn = ExecutableGoalBinding(
        binding_ref=earn.binding_ref,
        kind=earn.kind,
        estimated_effort=earn.estimated_effort,
        estimated_risk=earn.estimated_risk,
        resource_quote=earn.resource_quote,
        execute=lambda: GoalExecutionReport(1, 1, {}),
        verify=lambda _r: GoalVerification.succeeded(),
    )
    binding_buy = ExecutableGoalBinding(
        binding_ref=buy.binding_ref,
        kind=buy.kind,
        estimated_effort=buy.estimated_effort,
        estimated_risk=buy.estimated_risk,
        resource_quote=buy.resource_quote,
        execute=lambda: GoalExecutionReport(1, 1, {}),
        verify=lambda _r: GoalVerification.succeeded(),
    )
    binding_set = GoalBindingSet(
        (story, earn, buy),
        (binding_story, binding_earn, binding_buy),
    )
    with pytest.raises(GoalManagerError, match="one option per kind"):
        binding_set.question(situation)


def test_opt_in_earning_and_buying_survives_both_orders_and_roundtrip() -> None:
    situation = _situation()
    story = _story_opportunity()
    earn = _earning_resupply_opportunity()
    buy = _purchase_resupply_opportunity()

    q_earn_buy = GoalManagerQuestion(
        situation,
        (story, earn, buy),
        allow_resource_variants=True,
    )
    q_buy_earn = GoalManagerQuestion(
        situation,
        (story, buy, earn),
        allow_resource_variants=True,
    )

    assert q_earn_buy.policy_input["schema"] == (
        "pokemon.core.goal-manager-input.v4"
    )
    assert q_buy_earn.policy_input["schema"] == (
        "pokemon.core.goal-manager-input.v4"
    )

    assert q_earn_buy.policy_context_sha256 == q_buy_earn.policy_context_sha256

    restored_earn_buy = GoalManagerQuestion.from_policy_input(
        q_earn_buy.policy_input
    )
    restored_buy_earn = GoalManagerQuestion.from_policy_input(
        q_buy_earn.policy_input
    )

    assert restored_earn_buy.policy_input == q_earn_buy.policy_input
    assert restored_buy_earn.policy_input == q_buy_earn.policy_input
    assert restored_earn_buy.allow_resource_variants is True
    assert restored_buy_earn.allow_resource_variants is True
    assert (
        restored_earn_buy.policy_context_sha256
        == q_earn_buy.policy_context_sha256
    )

    assert (
        q_earn_buy.ordered_policy_input_sha256
        != q_buy_earn.ordered_policy_input_sha256
    )

    binding_story = ExecutableGoalBinding(
        binding_ref=story.binding_ref,
        kind=story.kind,
        estimated_effort=story.estimated_effort,
        estimated_risk=story.estimated_risk,
        execute=lambda: GoalExecutionReport(1, 1, {}),
        verify=lambda _r: GoalVerification.succeeded(),
    )
    binding_earn = ExecutableGoalBinding(
        binding_ref=earn.binding_ref,
        kind=earn.kind,
        estimated_effort=earn.estimated_effort,
        estimated_risk=earn.estimated_risk,
        resource_quote=earn.resource_quote,
        execute=lambda: GoalExecutionReport(1, 1, {}),
        verify=lambda _r: GoalVerification.succeeded(),
    )
    binding_buy = ExecutableGoalBinding(
        binding_ref=buy.binding_ref,
        kind=buy.kind,
        estimated_effort=buy.estimated_effort,
        estimated_risk=buy.estimated_risk,
        resource_quote=buy.resource_quote,
        execute=lambda: GoalExecutionReport(1, 1, {}),
        verify=lambda _r: GoalVerification.succeeded(),
    )
    binding_set = GoalBindingSet(
        (story, earn, buy),
        (binding_story, binding_earn, binding_buy),
    )
    q_from_binding_set = binding_set.question(
        situation, allow_resource_variants=True
    )
    assert q_from_binding_set.allow_resource_variants is True
    assert q_from_binding_set.policy_input["schema"] == (
        "pokemon.core.goal-manager-input.v4"
    )


def test_both_bind_and_execute_independently_by_selected_index() -> None:
    executed: list[str] = []

    def execute_earn() -> GoalExecutionReport:
        executed.append("earn")
        return GoalExecutionReport(
            actions_executed=5,
            frames_executed=300,
            evidence={"action": "earn"},
        )

    def execute_buy() -> GoalExecutionReport:
        executed.append("buy")
        return GoalExecutionReport(
            actions_executed=2,
            frames_executed=120,
            evidence={"action": "buy"},
        )

    story = _story_opportunity()
    earn = _earning_resupply_opportunity(
        binding_ref="private:red:resupply:earn"
    )
    buy = _purchase_resupply_opportunity(
        binding_ref="private:red:resupply:buy"
    )

    binding_story = ExecutableGoalBinding(
        binding_ref=story.binding_ref,
        kind=story.kind,
        estimated_effort=story.estimated_effort,
        estimated_risk=story.estimated_risk,
        execute=lambda: GoalExecutionReport(1, 1, {}),
        verify=lambda _r: GoalVerification.succeeded(),
    )
    binding_earn = ExecutableGoalBinding(
        binding_ref=earn.binding_ref,
        kind=earn.kind,
        estimated_effort=earn.estimated_effort,
        estimated_risk=earn.estimated_risk,
        resource_quote=earn.resource_quote,
        execute=execute_earn,
        verify=lambda _r: GoalVerification.succeeded(),
    )
    binding_buy = ExecutableGoalBinding(
        binding_ref=buy.binding_ref,
        kind=buy.kind,
        estimated_effort=buy.estimated_effort,
        estimated_risk=buy.estimated_risk,
        resource_quote=buy.resource_quote,
        execute=execute_buy,
        verify=lambda _r: GoalVerification.succeeded(),
    )
    binding_set = GoalBindingSet(
        (story, earn, buy),
        (binding_story, binding_earn, binding_buy),
    )
    question = binding_set.question(
        situation=_situation(), allow_resource_variants=True
    )

    earn_index = next(
        i
        for i, opp in enumerate(question.opportunities)
        if opp.binding_ref == earn.binding_ref
    )
    buy_index = next(
        i
        for i, opp in enumerate(question.opportunities)
        if opp.binding_ref == buy.binding_ref
    )

    bound_earn = bind_goal_selection(question, earn_index)
    assert bound_earn.binding_ref == "private:red:resupply:earn"
    assert bound_earn.kind is GoalKind.RESUPPLY
    target_earn = binding_set.require(bound_earn.binding_ref)
    report_earn = target_earn.execute()
    assert report_earn.evidence["action"] == "earn"
    assert executed == ["earn"]

    bound_buy = bind_goal_selection(question, buy_index)
    assert bound_buy.binding_ref == "private:red:resupply:buy"
    assert bound_buy.kind is GoalKind.RESUPPLY
    target_buy = binding_set.require(bound_buy.binding_ref)
    report_buy = target_buy.execute()
    assert report_buy.evidence["action"] == "buy"
    assert executed == ["earn", "buy"]


def test_ambiguous_duplicates_fail() -> None:
    situation = _situation()
    story = _story_opportunity()

    # Two earning variants rejected
    earn_1 = _earning_resupply_opportunity("earn_1", expected_income=500)
    earn_2 = _earning_resupply_opportunity("earn_2", expected_income=725)
    with pytest.raises(GoalManagerError, match="reject two earning options"):
        GoalManagerQuestion(
            situation, (story, earn_1, earn_2), allow_resource_variants=True
        )

    # Two purchase variants rejected
    buy_1 = _purchase_resupply_opportunity("buy_1", purchase_cost=200)
    buy_2 = _purchase_resupply_opportunity("buy_2", purchase_cost=400)
    with pytest.raises(GoalManagerError, match="reject two purchase options"):
        GoalManagerQuestion(
            situation, (story, buy_1, buy_2), allow_resource_variants=True
        )

    # Missing resource quote rejected
    buy_no_quote = GoalOpportunity(
        binding_ref="buy_no_quote",
        kind=GoalKind.RESUPPLY,
        availability=GoalAvailability.AVAILABLE,
        estimated_effort=0.10,
        estimated_risk=0.05,
    )
    with pytest.raises(
        GoalManagerError, match="require distinct semantic resource quotes"
    ):
        GoalManagerQuestion(
            situation,
            (story, earn_1, buy_no_quote),
            allow_resource_variants=True,
        )

    # Contradictory cash / differing available funds rejected
    earn_diff_cash = _earning_resupply_opportunity(
        "earn_diff", available_funds=999
    )
    buy_diff_cash = _purchase_resupply_opportunity(
        "buy_diff", available_funds=1168
    )
    with pytest.raises(
        GoalManagerError, match="agree on available funds"
    ):
        GoalManagerQuestion(
            situation,
            (story, earn_diff_cash, buy_diff_cash),
            allow_resource_variants=True,
        )

    # Unavailable variant rejected
    unavail_resupply = GoalOpportunity(
        binding_ref="unavail_resupply",
        kind=GoalKind.RESUPPLY,
        availability=GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
    )
    with pytest.raises(GoalManagerError, match="must both be available"):
        GoalManagerQuestion(
            situation,
            (story, earn_1, unavail_resupply),
            allow_resource_variants=True,
        )

    # Three RESUPPLY variants rejected under opt-in with new diagnostic
    with pytest.raises(GoalManagerError, match="at most two options"):
        GoalManagerQuestion(
            situation,
            (story, earn_1, buy_1, buy_2),
            allow_resource_variants=True,
        )

    # Duplicate of any other kind rejected
    story_2 = _story_opportunity("story_2")
    with pytest.raises(GoalManagerError, match="one option per kind"):
        GoalManagerQuestion(
            situation,
            (story, story_2, earn_1),
            allow_resource_variants=True,
        )

    # Duplicate binding refs rejected
    earn_dup_ref = _earning_resupply_opportunity("same_ref")
    buy_dup_ref = _purchase_resupply_opportunity("same_ref")
    with pytest.raises(GoalManagerError, match="bindings must be unique"):
        GoalManagerQuestion(
            situation,
            (story, earn_dup_ref, buy_dup_ref),
            allow_resource_variants=True,
        )


def test_teacher_safety_uses_semantics_not_candidate_order() -> None:
    teacher = CompletionFirstGoalTeacher(resource_gate=0.75)
    emergency_situation = _situation(resource_pressure=0.90)
    story = _story_opportunity()

    # Contrast 1: Low-risk purchase beats high-risk zero-spend earning
    earn_risky = _earning_resupply_opportunity(
        "earn_risky",
        effort=0.20,
        risk=0.40,
    )
    buy_safe = _purchase_resupply_opportunity(
        "buy_safe",
        effort=0.10,
        risk=0.05,
    )

    q1_a = GoalManagerQuestion(
        emergency_situation,
        (story, earn_risky, buy_safe),
        allow_resource_variants=True,
    )
    sel1_a = teacher.select(q1_a)
    assert sel1_a.binding_ref == "buy_safe"
    assert sel1_a.selected_index == 2

    q1_b = GoalManagerQuestion(
        emergency_situation,
        (story, buy_safe, earn_risky),
        allow_resource_variants=True,
    )
    sel1_b = teacher.select(q1_b)
    assert sel1_b.binding_ref == "buy_safe"
    assert sel1_b.selected_index == 1

    # Contrast 2: Genuinely lower-risk earning beats higher-risk purchase
    earn_safe = _earning_resupply_opportunity(
        "earn_safe",
        effort=0.20,
        risk=0.02,
    )
    buy_risky = _purchase_resupply_opportunity(
        "buy_risky",
        effort=0.10,
        risk=0.20,
    )

    q2_a = GoalManagerQuestion(
        emergency_situation,
        (story, earn_safe, buy_risky),
        allow_resource_variants=True,
    )
    sel2_a = teacher.select(q2_a)
    assert sel2_a.binding_ref == "earn_safe"
    assert sel2_a.selected_index == 1

    q2_b = GoalManagerQuestion(
        emergency_situation,
        (story, buy_risky, earn_safe),
        allow_resource_variants=True,
    )
    sel2_b = teacher.select(q2_b)
    assert sel2_b.binding_ref == "earn_safe"
    assert sel2_b.selected_index == 2


def test_old_unique_kind_serialization_unchanged() -> None:
    # 1. Round-trip hand-written literal v1 expectation
    q1 = GoalManagerQuestion.from_policy_input(V1_LITERAL)
    assert q1.allow_resource_variants is False
    assert q1.policy_input["schema"] == "pokemon.core.goal-manager-input.v1"
    restored_v1 = GoalManagerQuestion.from_policy_input(q1.policy_input)
    assert {**restored_v1.policy_input,
            "candidates": list(restored_v1.policy_input["candidates"])} == V1_LITERAL
    assert restored_v1.allow_resource_variants is False

    # 2. Round-trip hand-written literal v2 expectation
    q2 = GoalManagerQuestion.from_policy_input(V2_LITERAL)
    assert q2.allow_resource_variants is False
    assert q2.policy_input["schema"] == "pokemon.core.goal-manager-input.v2"
    restored_v2 = GoalManagerQuestion.from_policy_input(q2.policy_input)
    assert {**restored_v2.policy_input,
            "candidates": list(restored_v2.policy_input["candidates"])} == V2_LITERAL
    assert restored_v2.allow_resource_variants is False

    # 3. Round-trip hand-written literal v3 expectation
    q3 = GoalManagerQuestion.from_policy_input(V3_LITERAL)
    assert q3.allow_resource_variants is False
    assert q3.policy_input["schema"] == "pokemon.core.goal-manager-input.v3"
    restored_v3 = GoalManagerQuestion.from_policy_input(q3.policy_input)
    assert {**restored_v3.policy_input,
            "candidates": list(restored_v3.policy_input["candidates"])} == V3_LITERAL
    assert restored_v3.allow_resource_variants is False

    # 4. Attempting to deserialize a v4 payload with duplicate resupply as v2 fails
    v4_q = GoalManagerQuestion(
        _situation(),
        (
            _story_opportunity(),
            _earning_resupply_opportunity(),
            _purchase_resupply_opportunity(),
        ),
        allow_resource_variants=True,
    )
    tampered = dict(v4_q.policy_input)
    tampered["schema"] = "pokemon.core.goal-manager-input.v2"
    with pytest.raises(GoalManagerError, match="one option per kind"):
        GoalManagerQuestion.from_policy_input(tampered)


@pytest.mark.parametrize("value", [1, "true", None])
def test_variant_opt_in_requires_boolean(value: object) -> None:
    with pytest.raises(GoalManagerError, match="must be a bool"):
        GoalManagerQuestion(
            _situation(), (_story_opportunity(), _purchase_resupply_opportunity()),
            allow_resource_variants=value,
        )


def test_consumption_allowance_is_not_a_purchase_variant() -> None:
    # Existing per-opportunity validation already rejects this before a menu.
    with pytest.raises(GoalManagerError, match="requires its available resupply or story"):
        replace(_purchase_resupply_opportunity(), resource_quote=GoalResourceQuote(
            0, 0, (), available_recovery_units=3, maximum_recovery_consumption=1,
        ))


def test_nonemergency_resource_tie_is_permutation_invariant() -> None:
    earn = _earning_resupply_opportunity(effort=0.1, risk=0.1)
    buy = _purchase_resupply_opportunity(effort=0.1, risk=0.1)
    teacher = CompletionFirstGoalTeacher()
    for offers in ((earn, buy), (buy, earn)):
        question = GoalManagerQuestion(_situation(), offers, allow_resource_variants=True)
        # Equal goal utility; quoted spending breaks the tie, not menu order.
        assert teacher.select(question).binding_ref == earn.binding_ref


def test_resource_variants_reach_distinct_existing_economy_features() -> None:
    from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate

    question = GoalManagerQuestion(
        _situation(), (_earning_resupply_opportunity(), _purchase_resupply_opportunity()),
        allow_resource_variants=True,
    )
    projected = tuple(project_living_dex_goal_candidate(
        question, index, feature_version=4, binding_ref=f"row:{index}",
    ) for index in (0, 1))
    earn, buy = projected
    assert earn is not None and buy is not None
    assert earn.economy_offer.conditional_income == 725
    assert earn.economy_offer.planned_spend == 0
    assert buy.economy_offer.conditional_income == 0
    assert buy.economy_offer.planned_spend == 200
    assert earn.economy_offer.mode != buy.economy_offer.mode
    changed = replace(question, opportunities=(
        _earning_resupply_opportunity(expected_income=900), question.opportunities[1],
    ))
    assert changed.policy_context_sha256 != question.policy_context_sha256


def test_both_resource_variants_have_positive_learned_behavior_probability() -> None:
    from test_economy_objective_integration import _fit, _rows

    from pokemon_red_completion.living_dex_player_exploration import ExploringLivingDexGoalPolicy
    from pokemon_red_completion.resource_economy_observation import EconomySnapshot

    model = _fit(_rows(earns=False))  # Synthetic fixture, not game-learning evidence.
    offers = (_earning_resupply_opportunity(), _purchase_resupply_opportunity())
    for ordered in (offers, tuple(reversed(offers))):
        policy = ExploringLivingDexGoalPolicy(
            model, seed=3, allow_earning_exploration=True,
            economy_snapshot=EconomySnapshot(1168, ()), target_cash=3000,
        )
        question = GoalManagerQuestion(
            _situation(resource_pressure=0.9), ordered, allow_resource_variants=True,
        )
        policy.select(question)
        assert policy.training_eligible
        probabilities = policy.selection_metadata()["candidate_probabilities"]
        assert len(probabilities) == 2
        assert all(value > 0 for value in probabilities)
        assert sum(probabilities) == pytest.approx(1.0)
