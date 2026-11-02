"""Synthetic utility-contract tests; no game fixtures or fitted model."""
from dataclasses import replace
import numpy as np
import pytest
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionValueModel, LivingDexOptionKind, LivingDexOptionMenu,
    LivingDexOptionUtility, LivingDexPredictedOutcome, option_feature_names,
    pure_income_success_saturated, _score_with_income_saturation,
)
from pokemon_red_completion.resource_economy_observation import EconomyMode,EconomyOffer
from test_living_dex_economy_head import _candidate,_econ_context as _legacy_econ_context

def _econ_context(**kwargs):
    return replace(_legacy_econ_context(**kwargs),cash_target_known=True)


def _earn():
    return _candidate("funding",LivingDexOptionKind.RESUPPLY,
        offer=EconomyOffer(EconomyMode.EARN,conditional_income=650))


def _utility():
    return LivingDexOptionUtility(4.,2.,3.,.1,.2,.3,.4,.5,.6)


def _model():
    width=len(option_feature_names(4))
    return LivingDexOptionValueModel(coefficients=np.zeros((width,9)),
        intercept=np.array([.8,.1,.2,.3,.4,.5,.6,.7,.8]),
        feature_mean=np.zeros(width),feature_scale=np.ones(width),
        train_dataset_sha256="a"*64,settled_examples=2,censored_examples=0,
        ridge=.25,maximum_importance_weight=4.,feature_version=4)


@pytest.mark.parametrize("cash,target",[(1,0),(21380,0),(1000,1000),(1200,1000)])
def test_only_fulfilled_known_positive_cash_need_saturates(cash,target):
    assert pure_income_success_saturated(_econ_context(cash=cash,target_cash=target),_earn())


@pytest.mark.parametrize("cash,target",[(0,0),(0,1000),(999,1000)])
def test_zero_cash_or_real_shortfall_keeps_original_success(cash,target):
    assert not pure_income_success_saturated(_econ_context(cash=cash,target_cash=target),_earn())


def test_unknown_budget_is_not_zero_demand():
    context=replace(_econ_context(),economy_snapshot=None,target_cash=None,cash_target_known=False)
    assert not pure_income_success_saturated(context,_earn())


@pytest.mark.parametrize("kind",[LivingDexOptionKind.ACQUIRE,LivingDexOptionKind.DEVELOP,
    LivingDexOptionKind.RESTORE,LivingDexOptionKind.UNLOCK_ACCESS])
def test_nonincome_purposes_preserve_success_even_if_income_is_present(kind):
    candidate=replace(_earn(),features=replace(_earn().features,kind=kind))
    assert not pure_income_success_saturated(_econ_context(cash=1000,target_cash=0),candidate)


@pytest.mark.parametrize("offer",[None,EconomyOffer(EconomyMode.OTHER),
    EconomyOffer(EconomyMode.PURCHASE,planned_spend=100),
    EconomyOffer(EconomyMode.EARN,conditional_income=650,planned_spend=1),
    EconomyOffer(EconomyMode.EARN,conditional_income=0)])
def test_unknown_purchase_or_mixed_funded_transactions_keep_original_value(offer):
    candidate=replace(_earn(),economy_offer=offer)
    assert not pure_income_success_saturated(_econ_context(cash=1000,target_cash=0),candidate)


def test_exactly_generic_success_is_removed_all_other_terms_preserved():
    outcome=LivingDexPredictedOutcome(.8,.1,.2,.3,.4,.5,.6,.7,.8)
    utility=_utility();context=_econ_context(cash=1000,target_cash=0)
    score,active,removed=_score_with_income_saturation(context,_earn(),utility,outcome)
    assert active and removed==utility.success_weight*outcome.verified_success
    assert score==utility.score(outcome)-removed
    assert outcome.verified_success==.8
    expected=replace(utility,success_weight=0).score(outcome)
    assert score==pytest.approx(expected,rel=0,abs=1e-15)
    assert score<0  # Verified success no longer manufactures positive utility over actual costs.


def test_every_offscope_scalar_score_is_bit_exact():
    outcome=LivingDexPredictedOutcome(.8,.1,.2,.3,.4,.5,.6,.7,.8);utility=_utility()
    for context,candidate in [(_econ_context(cash=1,target_cash=1000),_earn()),
        (_econ_context(cash=1000,target_cash=0),replace(_earn(),economy_offer=None)),
        (replace(_econ_context(),economy_snapshot=None,target_cash=None,cash_target_known=False),_earn())]:
        score,active,removed=_score_with_income_saturation(context,candidate,utility,outcome)
        assert score==utility.score(outcome) and not active and removed==0.


def test_scoring_diagnostics_agree_without_changing_predictions_or_availability():
    context=_econ_context(cash=1000,target_cash=0)
    story=_candidate("story",LivingDexOptionKind.UNLOCK_ACCESS,offer=EconomyOffer(EconomyMode.OTHER))
    menu=LivingDexOptionMenu(context,(_earn(),story));model=_model();utility=_utility()
    before=model.predict_candidate(context,menu.candidates[0])
    scores=model.scores(menu,utility);diagnostic=model.diagnose_menu(menu,utility)
    rows=diagnostic["candidates"]
    assert rows[0]["score"]==scores[0] and rows[1]["score"]==scores[1]
    assert rows[0]["bounded_predictions"]["verified_success"]==before.verified_success
    assert rows[0]["utility_terms"]["verified_success"]==0.
    assert rows[0]["pure_income_success_saturation"]["action_still_available"] is True
    assert "pure_income_success_saturation" not in rows[1]
    assert menu.available_indices==(0,1)
    assert before==model.predict_candidate(context,menu.candidates[0])
