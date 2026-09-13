"""Tests for bounded opt-in economy learning integration.

Verifies:
1. Frozen legacy vectors, model bytes, and replay probabilities unchanged.
2. Different incomes and shortfalls vary new features without identity dependence.
3. Quoted success cannot masquerade as earned cash (liquidity gain strictly 0 if delta <= 0).
4. Failure cash loss, unknown observation, and interrupted handling.
5. Forced/singleton examples excluded from fits.
6. Synthetic unit-fit demonstrating feature-representation capability only (synthetic only).
7. Earning does not bypass safety gates.
8. Codec rejects partial schema, mutable, and malformed payloads.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace

import numpy as np
import pytest
from test_living_dex_goal_policy import _model, _question
from test_living_dex_option_value import _example, _features, _menu, _settled, _utility

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerError,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_resource_quote import GoalResourceQuote
from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalJournalError,
    restore_living_dex_observed_outcome,
)
from pokemon_red_completion.living_dex_goal_policy import (
    LivingDexGoalDecisionMode,
    LivingDexGoalShadowPolicy,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexObservedOutcome,
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOptionValueError,
    LivingDexOptionValueModel,
    LivingDexOutcomeStatus,
    fit_living_dex_option_value,
    option_feature_names,
    upgrade_option_value_model_for_economy,
    upgrade_option_value_model_for_optional_recovery,
    upgrade_option_value_model_for_search_history,
)
from pokemon_red_completion.living_dex_player_exploration import (
    DETERMINISTIC_POLICY_ID,
    ECONOMY_EXPLORATION_POLICY_ID,
    ExploringLivingDexGoalPolicy,
    exploration_policy_id,
)
from pokemon_red_completion.living_dex_policy_codec import (
    LivingDexPolicyCodecError,
    restore_living_dex_policy_menu,
)
from pokemon_red_completion.red_economy_learning import (
    declared_useful_supply_budget,
    economy_offer_from_opportunity,
    is_earning_opportunity,
    is_purchase_opportunity,
    red_registered_economy_outcome,
)
from pokemon_red_completion.resource_economy_observation import (
    ECONOMY_FEATURE_NAMES,
    EconomyMode,
    EconomyOffer,
    EconomyOutcome,
    EconomySnapshot,
    economy_features,
    economy_outcome,
)


def _earning_question(*, resource_pressure: float = 0.2) -> GoalManagerQuestion:
    base = _question()
    situation = replace(base.situation, resource_pressure=resource_pressure)
    opportunities = (
        GoalOpportunity(
            "private:acquire",
            GoalKind.ACQUIRE_SPECIES,
            GoalAvailability.AVAILABLE,
            0.4,
            0.1,
        ),
        GoalOpportunity(
            "private:resupply-earn",
            GoalKind.RESUPPLY,
            GoalAvailability.AVAILABLE,
            0.3,
            0.1,
            resource_quote=GoalResourceQuote(
                available_funds=100,
                purchase_cost=0,
                reserves=(),
                expected_income=800,
            ),
        ),
    )
    return GoalManagerQuestion(situation, opportunities)


# ---------------------------------------------------------------------------
# Test 1: Frozen legacy vectors/model bytes/replay probabilities unchanged
# ---------------------------------------------------------------------------
def test_frozen_legacy_vectors_model_bytes_and_replay_probabilities_unchanged():
    assert len(option_feature_names(1)) == 24
    assert len(option_feature_names(2)) == 29
    assert len(option_feature_names(3)) == 31
    assert len(option_feature_names(4)) == 37
    assert option_feature_names(4) == (*option_feature_names(3), *ECONOMY_FEATURE_NAMES)

    v1_model = _model()
    v2_model = upgrade_option_value_model_for_search_history(v1_model)
    v3_model = upgrade_option_value_model_for_optional_recovery(v2_model)
    v3_dict = copy.deepcopy(v3_model.to_dict())

    v4_model = upgrade_option_value_model_for_economy(v3_model)
    # Original model dict remains unmodified
    assert v3_model.to_dict() == v3_dict
    assert v4_model.feature_version == 4
    assert v4_model.settled_examples == v3_model.settled_examples
    assert v4_model.train_dataset_sha256 == v3_model.train_dataset_sha256

    # New coefficients zero-padded; mean padded with 0, scale with 1
    np.testing.assert_array_equal(v4_model.coefficients[:-6], v3_model.coefficients)
    np.testing.assert_array_equal(v4_model.coefficients[-6:], 0.0)
    assert list(v4_model.feature_mean[-6:]) == [0.0] * 6
    assert list(v4_model.feature_scale[-6:]) == [1.0] * 6

    # Idempotent upgrade
    assert upgrade_option_value_model_for_economy(v4_model) is v4_model

    # Model serialization and restoration hash identity
    restored = LivingDexOptionValueModel.from_dict(v4_model.to_dict())
    assert restored.model_sha256 == v4_model.model_sha256

    # Candidate vectors on legacy menus remain exact
    menu = _menu()
    expected_legacy_vector_0 = (
        1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        0.9, 0.7, 0.6, 0.6, 0.1, 0.1, 0.1, 0.0, 0.1,
        0.72, 0.49, 0.24, 0.03, 0.05, 0.04, 0.02,
    )
    assert menu.candidates[0].vector(menu.context, feature_version=1) == pytest.approx(
        expected_legacy_vector_0
    )
    for candidate in menu.candidates:
        assert candidate.vector(menu.context, feature_version=3) == (
            *candidate.vector(menu.context, feature_version=2),
            0.0,
            0.0,
        )
        assert candidate.vector(menu.context, feature_version=4) == (
            *candidate.vector(menu.context, feature_version=3),
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        )
        assert v4_model.predict_candidate(menu.context, candidate).vector() == pytest.approx(
            v3_model.predict_candidate(menu.context, candidate).vector(), abs=1e-14
        )

    # Exploration policy IDs
    assert exploration_policy_id(1) == "living-dex-player-supported-menu-v2"
    assert exploration_policy_id(2) == "living-dex-player-supported-menu-v2"
    assert exploration_policy_id(3) == "living-dex-player-optional-recovery-v4"
    assert exploration_policy_id(4) == ECONOMY_EXPLORATION_POLICY_ID


# ---------------------------------------------------------------------------
# Test 2: Different incomes/shortfalls vary new features without identity
# ---------------------------------------------------------------------------
def test_different_incomes_and_shortfalls_vary_new_features_without_identity():
    snapshot = EconomySnapshot(cash=200, inventory=(("red-item-001", 3),))
    target = 1200

    offer_earn_1000 = EconomyOffer(mode=EconomyMode.EARN, conditional_income=1000)
    offer_earn_400 = EconomyOffer(mode=EconomyMode.EARN, conditional_income=400)
    offer_purchase_600 = EconomyOffer(mode=EconomyMode.PURCHASE, planned_spend=600)
    offer_other = EconomyOffer(mode=EconomyMode.OTHER)

    f_earn_1000 = economy_features(snapshot, offer_earn_1000, target_cash=target)
    f_earn_400 = economy_features(snapshot, offer_earn_400, target_cash=target)
    f_purchase = economy_features(snapshot, offer_purchase_600, target_cash=target)
    f_other = economy_features(snapshot, offer_other, target_cash=target)

    # Earning 1000: shortfall=1000/1200, income=1000/1200, product=25/36
    expected_earn_1000 = (1.0, 0.0, 1000 / 1200, 1000 / 1200, 0.0, (1000 / 1200) ** 2)
    assert f_earn_1000 == pytest.approx(expected_earn_1000)

    # Earning 400: shortfall=1000/1200, income=400/1200, product=(5/6)*(1/3)
    expected_earn_400 = (1.0, 0.0, 1000 / 1200, 400 / 1200, 0.0, (1000 / 1200) * (400 / 1200))
    assert f_earn_400 == pytest.approx(expected_earn_400)

    # Purchase 600: spend=600/1200 = 0.5
    expected_purchase = (0.0, 1.0, 1000 / 1200, 0.0, 600 / 1200, 0.0)
    assert f_purchase == pytest.approx(expected_purchase)

    # Other: no earning, no purchasing, no spend
    expected_other = (0.0, 0.0, 1000 / 1200, 0.0, 0.0, 0.0)
    assert f_other == pytest.approx(expected_other)

    # Budget function respects unmet supplies without arbitrary hoarding
    budget = declared_useful_supply_budget(unmet_balls=5, unmet_potions=2, minimum_reserve=100)
    assert budget == 5 * 200 + 2 * 300 + 100 == 1700

    # Offers derived from opportunities without game identity
    opp_earn = GoalOpportunity(
        "private:trainer-12",
        GoalKind.RESUPPLY,
        GoalAvailability.AVAILABLE,
        0.5,
        0.1,
        resource_quote=GoalResourceQuote(
            available_funds=0,
            purchase_cost=0,
            reserves=(),
            expected_income=1500,
        ),
    )
    assert is_earning_opportunity(opp_earn)
    assert not is_purchase_opportunity(opp_earn)
    assert economy_offer_from_opportunity(opp_earn) == EconomyOffer(
        mode=EconomyMode.EARN, conditional_income=1500, planned_spend=0
    )

    # Earn-with-cost preserves both income and planned spend
    @dataclass(frozen=True, slots=True)
    class _EarnWithCostQuote(GoalResourceQuote):
        def __post_init__(self) -> None:
            pass

    opp_earn_with_cost = GoalOpportunity(
        "private:trainer-fee",
        GoalKind.RESUPPLY,
        GoalAvailability.AVAILABLE,
        0.4,
        0.1,
        resource_quote=_EarnWithCostQuote(
            available_funds=500,
            purchase_cost=200,
            reserves=(),
            expected_income=1000,
        ),
    )
    assert is_earning_opportunity(opp_earn_with_cost)
    assert is_purchase_opportunity(opp_earn_with_cost)
    offer_with_cost = economy_offer_from_opportunity(opp_earn_with_cost)
    assert offer_with_cost == EconomyOffer(
        mode=EconomyMode.EARN, conditional_income=1000, planned_spend=200
    )
    f_with_cost = economy_features(snapshot, offer_with_cost, target_cash=target)
    # Mode is EARN (1.0), conditional_income=1000/1200, planned_spend=200/1200 (not erased!)
    assert f_with_cost == pytest.approx(
        (1.0, 0.0, 1000 / 1200, 1000 / 1200, 200 / 1200, (1000 / 1200) ** 2)
    )


# ---------------------------------------------------------------------------
# Test 3: Quoted success cannot masquerade as earned cash
# ---------------------------------------------------------------------------
def test_quoted_success_cannot_masquerade_as_earned_cash():
    before = EconomySnapshot(cash=500, inventory=())
    after_same = EconomySnapshot(cash=500, inventory=())
    after_less = EconomySnapshot(cash=400, inventory=())

    # Even when goal claims success, zero cash delta proves zero liquidity gain
    outcome_same = economy_outcome(before, after_same, target_cash=1000, interrupted=False)
    assert outcome_same is not None
    assert outcome_same.cash_delta == 0
    assert outcome_same.useful_liquidity_gain == 0.0
    assert outcome_same.cash_loss == 0.0

    # Even when goal claims success, negative delta proves cash loss, zero liquidity gain
    outcome_loss = economy_outcome(before, after_less, target_cash=1000, interrupted=False)
    assert outcome_loss is not None
    assert outcome_loss.cash_delta == -100
    assert outcome_loss.useful_liquidity_gain == 0.0
    assert outcome_loss.cash_loss == pytest.approx(100 / 1000)

    # Construction of invalid claims raises ValueError
    with pytest.raises(ValueError, match="nonpositive cash change"):
        EconomyOutcome(
            cash_delta=0,
            net_item_decrease=0,
            net_item_increase=0,
            useful_liquidity_gain=0.25,
            cash_loss=0.0,
        )

    with pytest.raises(ValueError, match="nonnegative cash change"):
        EconomyOutcome(
            cash_delta=100,
            net_item_decrease=0,
            net_item_increase=0,
            useful_liquidity_gain=0.1,
            cash_loss=0.1,
        )


# ---------------------------------------------------------------------------
# Test 4: Failure cash loss / unknown / interrupted handling
# ---------------------------------------------------------------------------
def test_failure_cash_loss_unknown_and_interrupted_handling():
    before = EconomySnapshot(cash=800, inventory=())
    after = EconomySnapshot(cash=400, inventory=())

    # Actual loss on failed battle / blackout is retained
    loss_outcome = economy_outcome(before, after, target_cash=1000, interrupted=False)
    assert loss_outcome is not None
    assert loss_outcome.cash_delta == -400
    assert loss_outcome.cash_loss == 0.4
    assert loss_outcome.useful_liquidity_gain == 0.0

    # Missing observation returns None
    assert economy_outcome(None, after, target_cash=1000) is None
    assert economy_outcome(before, None, target_cash=1000) is None

    # Interrupted trial censors without fabricating outcome
    assert economy_outcome(before, after, target_cash=1000, interrupted=True) is None

    registered_censored = red_registered_economy_outcome(
        {},
        {},
        selected_kind=GoalKind.RESUPPLY,
        succeeded=False,
        actions=10,
        frames=100,
        maximum_actions=100,
        maximum_frames=1000,
        before_economy=before,
        after_economy=after,
        target_cash=1000,
        interrupted=True,
    )
    assert registered_censored.status is LivingDexOutcomeStatus.CENSORED
    assert registered_censored.censor_reason is LivingDexCensorReason.EXTERNAL_INTERRUPTION
    assert registered_censored.economy is None
    assert registered_censored.target_vector is None

    # Missing observation censors the prospective economy bridge with OBSERVATION_FAILED
    registered_missing_before = red_registered_economy_outcome(
        {},
        {},
        selected_kind=GoalKind.RESUPPLY,
        succeeded=True,
        actions=10,
        frames=100,
        maximum_actions=100,
        maximum_frames=1000,
        before_economy=None,
        after_economy=after,
        target_cash=1000,
    )
    assert registered_missing_before.status is LivingDexOutcomeStatus.CENSORED
    assert registered_missing_before.censor_reason is LivingDexCensorReason.OBSERVATION_FAILED
    assert registered_missing_before.economy is None
    assert registered_missing_before.target_vector is None

    registered_missing_after = red_registered_economy_outcome(
        {},
        {},
        selected_kind=GoalKind.RESUPPLY,
        succeeded=True,
        actions=10,
        frames=100,
        maximum_actions=100,
        maximum_frames=1000,
        before_economy=before,
        after_economy=None,
        target_cash=1000,
    )
    assert registered_missing_after.status is LivingDexOutcomeStatus.CENSORED
    assert registered_missing_after.censor_reason is LivingDexCensorReason.OBSERVATION_FAILED
    assert registered_missing_after.economy is None
    assert registered_missing_after.target_vector is None


# ---------------------------------------------------------------------------
# Test 5: Forced/singleton examples excluded from fits
# ---------------------------------------------------------------------------
def test_forced_and_singleton_examples_excluded_from_fits():
    # When question has only one available option, it cannot train a multi-choice model
    singleton_question = replace(
        _question(),
        opportunities=(
            GoalOpportunity(
                "private:only-option",
                GoalKind.ACQUIRE_SPECIES,
                GoalAvailability.AVAILABLE,
                0.2,
                0.1,
            ),
            GoalOpportunity(
                "private:unavailable",
                GoalKind.RESUPPLY,
                GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY,
            ),
        ),
    )
    v4_model = upgrade_option_value_model_for_economy(
        upgrade_option_value_model_for_optional_recovery(
            upgrade_option_value_model_for_search_history(_model())
        )
    )
    # Pass real context so the test specifically isolates the singleton gate
    policy = ExploringLivingDexGoalPolicy(
        v4_model,
        seed=123,
        economy_snapshot=EconomySnapshot(cash=500, inventory=()),
        target_cash=1000,
    )
    selection = policy.select(singleton_question)
    assert selection.selected_index == 0
    assert not policy.training_eligible
    assert policy.last_decision.mode is LivingDexGoalDecisionMode.DETERMINISTIC_UNSUPPORTED
    assert policy.last_decision.scores == ()
    assert policy.selection_metadata()["behavior_policy_id"] == DETERMINISTIC_POLICY_ID

    # Multi-choice question with missing economy context fails closed to DETERMINISTIC_UNSUPPORTED
    # without fabricating poverty or scoring invented cash=0
    policy_no_context = ExploringLivingDexGoalPolicy(v4_model, seed=123)
    two_choice_question = _earning_question()
    policy_no_context.select(two_choice_question)
    assert not policy_no_context.training_eligible
    assert (
        policy_no_context.last_decision.mode
        is LivingDexGoalDecisionMode.DETERMINISTIC_UNSUPPORTED
    )
    assert policy_no_context.last_decision.scores == ()
    assert (
        policy_no_context.selection_metadata()["behavior_policy_id"]
        == DETERMINISTIC_POLICY_ID
    )


# ---------------------------------------------------------------------------
# Test 6: Synthetic unit-fit demonstrates feature-representation capability only
# ---------------------------------------------------------------------------
def test_synthetic_unit_fit_demonstrates_feature_representation_capability_only():
    """Verify linear separability and feature-representation capacity of the regression model.

    CRITICAL HONEST BOUNDARY:
    This synthetic unit-fit uses hand-authored legacy targets (_settled), NOT the
    registered economy bridge or actual cash outcomes. It demonstrates that the
    model parameters can fit the feature interactions, but DOES NOT prove learning
    from actual cash outcomes or constitute an operational income learner.
    """
    context_high_shortfall = LivingDexOptionContext(
        0.8,
        0.7,
        0.4,
        0.9,
        0.5,
        0.4,
        0.2,
        economy_snapshot=EconomySnapshot(cash=100, inventory=()),
        target_cash=1000,
    )
    context_low_shortfall = LivingDexOptionContext(
        0.8,
        0.7,
        0.4,
        0.1,
        0.5,
        0.4,
        0.2,
        economy_snapshot=EconomySnapshot(cash=950, inventory=()),
        target_cash=1000,
    )

    candidate_earn = LivingDexOptionCandidate(
        "synthetic.resupply-earn",
        _features(LivingDexOptionKind.RESUPPLY, completion=0.0, unlock=0.0, effort=0.2),
        LivingDexOptionAvailability.AVAILABLE,
        economy_offer=EconomyOffer(mode=EconomyMode.EARN, conditional_income=900),
    )
    candidate_other = LivingDexOptionCandidate(
        "synthetic.explore-other",
        _features(LivingDexOptionKind.EXPLORE, completion=0.1, unlock=0.1, effort=0.2),
        LivingDexOptionAvailability.AVAILABLE,
        economy_offer=EconomyOffer(mode=EconomyMode.OTHER),
    )

    def make_menu(high_shortfall: bool) -> LivingDexOptionMenu:
        ctx = context_high_shortfall if high_shortfall else context_low_shortfall
        return LivingDexOptionMenu(ctx, (candidate_earn, candidate_other))

    fitted_models = []
    for reverse in (False, True):
        rows = []
        for index in range(24):
            high = bool((index // 2) % 2)
            selected = index % 2
            success = (selected == 0 if high else selected == 1) != reverse
            row = _example(
                index,
                selected=selected,
                outcome=_settled(
                    success=success,
                    completion=0.0,
                    unlock=0.0,
                    action_cost=0.2,
                ),
            )
            rows.append(
                replace(
                    row,
                    menu=make_menu(high),
                    behavior_probabilities=(0.5, 0.5),
                )
            )
        fitted = fit_living_dex_option_value(rows, feature_version=4).model
        fitted_models.append(fitted)

    # In forward model: high shortfall prefers candidate 0 (earn), low shortfall prefers candidate 1
    assert fitted_models[0].select(make_menu(True), _utility()) == 0
    assert fitted_models[0].select(make_menu(False), _utility()) == 1

    # In reversed model: preferences flip
    assert fitted_models[1].select(make_menu(True), _utility()) == 1
    assert fitted_models[1].select(make_menu(False), _utility()) == 0


# ---------------------------------------------------------------------------
# Test 7: Earning does not bypass safety gates
# ---------------------------------------------------------------------------
def test_earning_does_not_bypass_safety_gates():
    v4_model = upgrade_option_value_model_for_economy(
        upgrade_option_value_model_for_optional_recovery(
            upgrade_option_value_model_for_search_history(_model())
        )
    )
    policy = LivingDexGoalShadowPolicy(
        v4_model,
        allow_earning_exploration=True,
        economy_snapshot=EconomySnapshot(cash=50, inventory=()),
        target_cash=1000,
    )

    earning_opp = GoalOpportunity(
        "private:earn",
        GoalKind.RESUPPLY,
        GoalAvailability.AVAILABLE,
        0.3,
        0.1,
        resource_quote=GoalResourceQuote(
            available_funds=50,
            purchase_cost=0,
            reserves=(),
            expected_income=1000,
        ),
    )

    # 1. Recovery gate cannot be bypassed by earning
    q_recovery = GoalManagerQuestion(
        GoalSituation(
            story_pressure=0.5,
            collection_pressure=0.5,
            team_pressure=0.5,
            evolution_pressure=0.5,
            safety_pressure=0.5,
            resource_pressure=0.9,
            storage_pressure=0.5,
            recovery_pressure=0.99,  # Critical control loss
            exploration_pressure=0.5,
        ),
        (
            GoalOpportunity(
                "private:recover",
                GoalKind.RECOVER_CONTROL,
                GoalAvailability.AVAILABLE,
                0.1,
                0.0,
            ),
            earning_opp,
        ),
    )
    sel = policy.select(q_recovery)
    assert sel.kind is GoalKind.RECOVER_CONTROL
    assert policy.last_decision.mode is LivingDexGoalDecisionMode.DETERMINISTIC_SAFETY

    # 2. Critical party safety gate cannot be bypassed
    q_safety = GoalManagerQuestion(
        GoalSituation(
            story_pressure=0.5,
            collection_pressure=0.5,
            team_pressure=0.5,
            evolution_pressure=0.5,
            safety_pressure=0.99,  # Party faint emergency
            resource_pressure=0.9,
            storage_pressure=0.5,
            recovery_pressure=0.0,
            exploration_pressure=0.5,
        ),
        (
            GoalOpportunity(
                "private:restore",
                GoalKind.RESTORE_TEAM,
                GoalAvailability.AVAILABLE,
                0.1,
                0.0,
            ),
            earning_opp,
        ),
    )
    sel = policy.select(q_safety)
    assert sel.kind is GoalKind.RESTORE_TEAM
    assert policy.last_decision.mode is LivingDexGoalDecisionMode.DETERMINISTIC_SAFETY

    # 3. Critical storage gate cannot be bypassed
    q_storage = GoalManagerQuestion(
        GoalSituation(
            story_pressure=0.5,
            collection_pressure=0.5,
            team_pressure=0.5,
            evolution_pressure=0.5,
            safety_pressure=0.1,
            resource_pressure=0.9,
            storage_pressure=0.99,  # Full box emergency
            recovery_pressure=0.0,
            exploration_pressure=0.5,
        ),
        (
            GoalOpportunity(
                "private:storage",
                GoalKind.MANAGE_STORAGE,
                GoalAvailability.AVAILABLE,
                0.1,
                0.0,
            ),
            earning_opp,
        ),
    )
    sel = policy.select(q_storage)
    assert sel.kind is GoalKind.MANAGE_STORAGE
    assert policy.last_decision.mode is LivingDexGoalDecisionMode.DETERMINISTIC_SAFETY

    # Default policy forces resupply when resource pressure is high.
    default_policy = LivingDexGoalShadowPolicy(v4_model, allow_earning_exploration=False)
    q_resource = GoalManagerQuestion(
        GoalSituation(
            story_pressure=0.1,
            collection_pressure=0.5,
            team_pressure=0.1,
            evolution_pressure=0.1,
            safety_pressure=0.1,
            resource_pressure=0.95,  # High resource pressure
            storage_pressure=0.1,
            recovery_pressure=0.0,
            exploration_pressure=0.1,
        ),
        (
            GoalOpportunity(
                "private:acquire",
                GoalKind.ACQUIRE_SPECIES,
                GoalAvailability.AVAILABLE,
                0.5,
                0.1,
            ),
            earning_opp,
        ),
    )
    assert default_policy.select(q_resource).kind is GoalKind.RESUPPLY
    assert default_policy.last_decision.mode is LivingDexGoalDecisionMode.DETERMINISTIC_SAFETY

    # When allow_earning_exploration=True, it evaluates options via model
    policy.select(q_resource)
    assert policy.last_decision.mode is LivingDexGoalDecisionMode.MODEL_SHADOW
    assert len(policy.last_decision.scores) == 2

    # An unavailable positive quote may NOT relax cash-pressure forcing
    policy_unavailable_earn = LivingDexGoalShadowPolicy(
        v4_model,
        allow_earning_exploration=True,
        economy_snapshot=EconomySnapshot(cash=50, inventory=()),
        target_cash=1000,
    )
    # The upstream typed contract already rejects unavailable income quotes.
    with pytest.raises(GoalManagerError, match="resource quote"):
        replace(earning_opp, availability=GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY)
    q_unavailable_earn = GoalManagerQuestion(
        q_resource.situation,
        (
            GoalOpportunity(
                "private:acquire",
                GoalKind.ACQUIRE_SPECIES,
                GoalAvailability.AVAILABLE,
                0.5,
                0.1,
            ),
            replace(earning_opp, resource_quote=None),
        ),
    )
    assert policy_unavailable_earn.select(q_unavailable_earn).kind is GoalKind.RESUPPLY
    assert (
        policy_unavailable_earn.last_decision.mode
        is LivingDexGoalDecisionMode.DETERMINISTIC_SAFETY
    )

    # Zero shortfall (cash >= target_cash) may NOT relax cash-pressure forcing
    policy_no_shortfall = LivingDexGoalShadowPolicy(
        v4_model,
        allow_earning_exploration=True,
        economy_snapshot=EconomySnapshot(cash=1000, inventory=()),
        target_cash=1000,
    )
    assert policy_no_shortfall.select(q_resource).kind is GoalKind.RESUPPLY
    assert (
        policy_no_shortfall.last_decision.mode
        is LivingDexGoalDecisionMode.DETERMINISTIC_SAFETY
    )

    # Fewer than two qualified available candidates may NOT relax cash-pressure forcing
    q_single_earn = GoalManagerQuestion(
        q_resource.situation,
        (
            earning_opp,
            GoalOpportunity(
                "private:unsupported-kind",
                GoalKind.RECOVER_CONTROL,  # Not a learned collection candidate
                GoalAvailability.AVAILABLE,
                0.5,
                0.1,
            ),
        ),
    )
    assert policy.select(q_single_earn).kind is GoalKind.RESUPPLY
    assert policy.last_decision.mode is LivingDexGoalDecisionMode.DETERMINISTIC_SAFETY


# ---------------------------------------------------------------------------
# Test 8: Codec rejects partial schema, mutable, and malformed payloads
# ---------------------------------------------------------------------------
def test_codec_rejects_partial_schema_and_malformed_payloads():
    snapshot = EconomySnapshot(cash=300, inventory=(("red-item-001", 2),))
    context = LivingDexOptionContext(
        0.8,
        0.7,
        0.4,
        0.3,
        0.5,
        0.4,
        0.2,
        economy_snapshot=snapshot,
        target_cash=1000,
    )
    candidate_earn = LivingDexOptionCandidate(
        "candidate.earn",
        _features(LivingDexOptionKind.RESUPPLY, completion=0.1, unlock=0.0, effort=0.2),
        LivingDexOptionAvailability.AVAILABLE,
        economy_offer=EconomyOffer(mode=EconomyMode.EARN, conditional_income=500),
    )
    candidate_other = LivingDexOptionCandidate(
        "candidate.other",
        _features(LivingDexOptionKind.EXPLORE, completion=0.2, unlock=0.1, effort=0.3),
        LivingDexOptionAvailability.AVAILABLE,
        economy_offer=EconomyOffer(mode=EconomyMode.OTHER),
    )
    menu = LivingDexOptionMenu(context, (candidate_earn, candidate_other))

    # Menu v4 roundtrip
    doc = menu.policy_dict()
    assert doc["schema"] == "pokemon.core.living-dex-option-menu.v4"
    assert doc["context"]["schema"] == "pokemon.core.living-dex-option-context.v2"
    restored_menu = restore_living_dex_policy_menu(doc)
    assert restored_menu.policy_dict() == doc

    # Outcome v2 roundtrip with economy
    outcome = LivingDexObservedOutcome(
        status=LivingDexOutcomeStatus.SETTLED,
        verified_success=True,
        completion_gain=0.1,
        dependency_unlock_gain=0.0,
        action_cost=0.2,
        frame_cost=0.2,
        resource_cost=0.1,
        party_cost=0.0,
        storage_cost=0.0,
        irreversible_loss=0.0,
        economy=EconomyOutcome(
            cash_delta=400,
            net_item_decrease=0,
            net_item_increase=2,
            useful_liquidity_gain=0.4,
            cash_loss=0.0,
        ),
    )
    out_doc = outcome.public_dict()
    assert out_doc["schema"] == "pokemon.core.living-dex-observed-outcome.v2"
    assert out_doc["economy"]["schema"] == "pokemon.core.resource-economy-outcome.v1"
    restored_outcome = restore_living_dex_observed_outcome(out_doc)
    assert restored_outcome.public_dict() == out_doc

    # Codec rejects context v2 with missing fields
    bad_ctx = copy.deepcopy(doc["context"])
    del bad_ctx["target_cash"]
    with pytest.raises(LivingDexPolicyCodecError):
        restore_living_dex_policy_menu({**doc, "context": bad_ctx})

    bad_ctx2 = copy.deepcopy(doc["context"])
    del bad_ctx2["economy_cash"]
    with pytest.raises(LivingDexPolicyCodecError):
        restore_living_dex_policy_menu({**doc, "context": bad_ctx2})

    bad_ctx3 = copy.deepcopy(doc["context"])
    bad_ctx3["target_cash"] = -10
    with pytest.raises(LivingDexPolicyCodecError):
        restore_living_dex_policy_menu({**doc, "context": bad_ctx3})

    # Codec rejects v4 menu lacking economy context
    v1_ctx = {
        "schema": "pokemon.core.living-dex-option-context.v1",
        "collection_pressure": 0.8,
        "dependency_pressure": 0.7,
        "access_pressure": 0.4,
        "resource_pressure": 0.3,
        "storage_pressure": 0.5,
        "party_pressure": 0.4,
        "knowledge_pressure": 0.2,
    }
    with pytest.raises(LivingDexPolicyCodecError):
        restore_living_dex_policy_menu({**doc, "context": v1_ctx})

    # Codec rejects mismatched schema (pre-v4 menu with economy context)
    with pytest.raises(LivingDexPolicyCodecError):
        restore_living_dex_policy_menu({**doc, "schema": "pokemon.core.living-dex-option-menu.v3"})

    # Codec rejects bools in integer fields
    bad_bool_cash = copy.deepcopy(doc["context"])
    bad_bool_cash["target_cash"] = True
    with pytest.raises(LivingDexPolicyCodecError):
        restore_living_dex_policy_menu({**doc, "context": bad_bool_cash})

    bad_bool_snap = copy.deepcopy(doc["context"])
    bad_bool_snap["economy_cash"] = True
    with pytest.raises(LivingDexPolicyCodecError):
        restore_living_dex_policy_menu({**doc, "context": bad_bool_snap})

    # Codec rejects negative/malformed economy offer payloads
    bad_cand_spend = copy.deepcopy(doc["candidates"][0])
    bad_cand_spend["economy_offer"]["planned_spend"] = -1
    with pytest.raises(LivingDexPolicyCodecError):
        restore_living_dex_policy_menu(
            {**doc, "candidates": [bad_cand_spend, doc["candidates"][1]]}
        )

    # No inventory identity may be added to the learner-visible cash context.
    bad_inv = copy.deepcopy(doc["context"])
    bad_inv["inventory"] = [["item", 1]]
    with pytest.raises(LivingDexPolicyCodecError):
        restore_living_dex_policy_menu({**doc, "context": bad_inv})

    # Codec rejects malformed economy outcome
    bad_out = copy.deepcopy(out_doc)
    bad_out["economy"]["gross_income"] = 500  # Gross flows forbidden
    with pytest.raises(LivingDexCausalJournalError):
        restore_living_dex_observed_outcome(bad_out)

    bad_out2 = copy.deepcopy(out_doc)
    bad_out2["economy"]["net_item_decrease"] = -1
    with pytest.raises(LivingDexCausalJournalError):
        restore_living_dex_observed_outcome(bad_out2)

    # Rejects v1 schema carrying economy key
    bad_v1 = copy.deepcopy(out_doc)
    bad_v1["schema"] = "pokemon.core.living-dex-observed-outcome.v1"
    with pytest.raises(LivingDexCausalJournalError):
        restore_living_dex_observed_outcome(bad_v1)

    # Censored outcome carrying economy payload rejected by journal restore
    bad_censored = copy.deepcopy(out_doc)
    bad_censored["status"] = "censored"
    bad_censored["censor_reason"] = "observation_failed"
    bad_censored["target_values"] = None
    with pytest.raises(LivingDexCausalJournalError):
        restore_living_dex_observed_outcome(bad_censored)

    # Censored LivingDexObservedOutcome cannot retain economy targets
    with pytest.raises(LivingDexOptionValueError, match="cannot retain economy targets"):
        LivingDexObservedOutcome(
            status=LivingDexOutcomeStatus.CENSORED,
            censor_reason=LivingDexCensorReason.OBSERVATION_FAILED,
            economy=EconomyOutcome(
                cash_delta=100,
                net_item_decrease=0,
                net_item_increase=0,
                useful_liquidity_gain=0.1,
                cash_loss=0.0,
            ),
        )
