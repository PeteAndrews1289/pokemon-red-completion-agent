"""ROM-free counterexamples for economy prediction envelopes.

No optimizer, corpus, cartridge, emulator, or native state is used. Synthetic
constant heads isolate the existing net-outcome contract and runtime clipping.
"""
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest

import pokemon_red_completion.living_dex_option_value as m
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu
from pokemon_red_completion.resource_economy_observation import (
    EconomyMode, EconomyOffer, EconomySnapshot, economy_outcome,
)
from test_living_dex_economy_head import _candidate, _econ_context, _utility
from test_living_dex_goal_policy import _model
from test_living_dex_option_value import _menu


def _head(raw=(0.8, 0.9)):
    width = len(m.option_feature_names(4))
    return m.LivingDexEconomyHead(
        coefficients=np.zeros((width, 2)), intercept=np.array(raw, dtype=float),
        feature_mean=np.linspace(0.0, 0.2, width),
        feature_scale=np.linspace(0.5, 1.5, width),
        evidence_digest="b" * 64, qualified_examples=2,
        ridge=0.25, maximum_importance_weight=4.0)


def _predict(cash, target, raw=(0.8, 0.9), offer=None):
    context = _econ_context(cash=cash, target_cash=target)
    candidate = _candidate("private-option", offer=offer)
    return _head(raw).predict_candidate(context, candidate)


@pytest.mark.parametrize("cash", [0, 1, 250, 999999])
def test_zero_target_cannot_produce_useful_liquidity(cash):
    result = _predict(cash, 0)
    assert result.useful_liquidity_gain == 0.0
    # Target zero does not erase an observed nonzero wallet or its possible loss.
    assert result.cash_loss == (0.0 if cash == 0 else 0.9)


@pytest.mark.parametrize("cash", [1000, 1001, 999999])
def test_met_or_exceeded_target_cannot_produce_useful_liquidity(cash):
    result = _predict(cash, 1000)
    assert result.useful_liquidity_gain == 0.0
    assert result.cash_loss == 0.9


@pytest.mark.parametrize("cash,target,expected", [
    (250, 1000, (0.75, 0.25)),
    (750, 1000, (0.25, 0.75)),
    (999, 1000, (0.001, 0.9)),
    (1, 2000, (0.8, 0.0005)),
])
def test_partial_shortfall_and_existing_wallet_bound_each_output(cash, target, expected):
    assert _predict(cash, target).vector() == pytest.approx(expected)


@pytest.mark.parametrize("target", [0, 1, 1000, 999999])
def test_zero_wallet_never_predicts_positive_net_cash_loss(target):
    result = _predict(0, target)
    assert result.cash_loss == 0.0
    assert result.useful_liquidity_gain == (0.0 if target == 0 else 0.8)


@pytest.mark.parametrize("cash", [0, 1, 250, 1000, 1500])
@pytest.mark.parametrize("target", [0, 1, 1000, 2000])
def test_prediction_ceiling_equals_existing_label_envelope_over_many_after_cash_values(cash, target):
    before = EconomySnapshot(cash, (("existing-item", 2),))
    # Includes the extremal after=0 and after>=target, plus losses, stasis,
    # gains, over-target balances, and an unchanged item ledger.
    after_values = sorted({0, 1, 2, 100, 249, 250, 251, 999, 1000, 1001,
                           1999, 2000, 999999, max(0, cash-1), cash, cash+1, target})
    observed = [economy_outcome(before, EconomySnapshot(after, before.inventory),
                                target_cash=target) for after in after_values]
    assert all(outcome is not None for outcome in observed)
    maximum = (
        max(outcome.useful_liquidity_gain for outcome in observed),
        max(outcome.cash_loss for outcome in observed),
    )
    capped = _predict(cash, target, raw=(7.0, 9.0)).vector()
    assert capped == pytest.approx(maximum)
    for outcome in observed:
        assert 0 <= outcome.useful_liquidity_gain <= capped[0]
        assert 0 <= outcome.cash_loss <= capped[1]
        assert outcome.cash_delta >= -cash
    # These are per-output envelopes, not a fabricated joint future outcome.


@pytest.mark.parametrize("raw,expected", [
    ((-0.4, -0.8), (0.0, 0.0)),
    ((0.2, 0.3), (0.2, 0.3)),
    ((0.6, 0.7), (0.5, 0.5)),
])
def test_feasible_interior_and_lower_clipping_are_retained(raw, expected):
    assert _predict(500, 1000, raw).vector() == pytest.approx(expected)


@pytest.mark.parametrize("offer", [
    None,
    EconomyOffer(EconomyMode.OTHER),
    EconomyOffer(EconomyMode.EARN, conditional_income=1),
    EconomyOffer(EconomyMode.PURCHASE, planned_spend=1),
])
def test_net_label_envelopes_do_not_treat_mode_or_conditional_quote_as_certain_cash(offer):
    # A quote is not a proved upper bound on compound net cash change.
    assert _predict(500, 1000, (0.4, 0.3), offer).vector() == pytest.approx((0.4, 0.3))


def test_raw_diagnostics_and_all_serialized_learned_quantities_remain_exact():
    head = _head()
    model = replace(m.upgrade_option_value_model_for_economy(_model()), economy_head=head)
    context = _econ_context(cash=750, target_cash=1000)
    menu = m.LivingDexOptionMenu(context, (
        _candidate("a", offer=EconomyOffer(EconomyMode.EARN, conditional_income=999)),
        _candidate("b", offer=None),
    ))
    document = deepcopy(model.to_dict())
    digest = model.model_sha256
    head_document = deepcopy(head.to_dict())
    diagnostic = model.diagnose_menu(menu, _utility(), selected_index=0)
    for row in diagnostic["candidates"]:
        assert row["economy"]["raw_predictions"] == {
            "useful_liquidity_gain": 0.8, "cash_loss": 0.9}
        assert row["economy"]["bounded_predictions"] == {
            "useful_liquidity_gain": 0.25, "cash_loss": 0.75}
        assert row["economy"]["score_adjustment"] == -0.5
    assert tuple(row["score"] for row in diagnostic["candidates"]) == model.scores(menu, _utility())
    assert model.to_dict() == document and model.model_sha256 == digest
    assert head.to_dict() == head_document
    for field in ("coefficients", "intercept", "feature_mean", "feature_scale"):
        assert not getattr(head, field).flags.writeable
    restored_head = m.LivingDexEconomyHead.from_dict(head_document)
    restored_model = m.LivingDexOptionValueModel.from_dict(document)
    assert restored_head.to_dict() == head_document
    assert restored_model.to_dict() == document and restored_model.model_sha256 == digest
    assert restored_head.predict_candidate(context, menu.candidates[0]).vector() == (0.25, 0.75)
    restored_menu = restore_living_dex_policy_menu(menu.policy_dict())
    assert restored_menu.policy_dict() == menu.policy_dict()
    assert restored_model.scores(restored_menu, _utility()) == model.scores(menu, _utility())


def test_absent_economy_context_remains_unknown_and_does_not_gain_new_policy_fields():
    base = m.upgrade_option_value_model_for_economy(_model())
    model = replace(base, economy_head=_head())
    menu = _menu()
    before_menu = deepcopy(menu.policy_dict())
    assert menu.context.economy_snapshot is None and menu.context.target_cash is None
    assert "economy_cash" not in before_menu["context"]
    assert "target_cash" not in before_menu["context"]
    for candidate in menu.candidates:
        assert model.predict_economy_candidate(menu.context, candidate) is None
    with pytest.raises(m.LivingDexOptionValueError, match="requires economy context"):
        model.economy_head.predict_candidate(menu.context, menu.candidates[0])
    assert model.scores(menu, _utility()) == base.scores(menu, _utility())
    assert all(row["economy"] is None for row in model.diagnose_menu(menu, _utility())["candidates"]
               if row["available"])
    assert menu.policy_dict() == before_menu


def test_absent_economy_head_stays_absent_even_with_observed_cash():
    model = m.upgrade_option_value_model_for_economy(_model())
    context = _econ_context(cash=0, target_cash=0)
    candidate = _candidate("ordinary", offer=None)
    document = deepcopy(model.to_dict())
    assert model.predict_economy_candidate(context, candidate) is None
    assert model.to_dict() == document
    assert m.LivingDexOptionValueModel.from_dict(document).economy_head is None


def test_compound_income_then_spending_uses_net_loss_not_gross_turnover():
    # A compound action could earn900 and spend1000 from initial100, ending0.
    # The existing label records100 net loss; gross spending is not this target.
    before = EconomySnapshot(100, ())
    after = EconomySnapshot(0, (("purchased-item", 1),))
    outcome = economy_outcome(before, after, target_cash=1000)
    assert outcome.cash_delta == -100 and outcome.cash_loss == 0.1
    assert outcome.useful_liquidity_gain == 0.0 and outcome.net_item_increase == 1
    assert _predict(100, 1000, raw=(2.0, 2.0)).cash_loss == outcome.cash_loss
