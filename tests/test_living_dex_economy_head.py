from __future__ import annotations

from dataclasses import replace
from typing import cast

import numpy as np
import pytest

from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_ECONOMY_HEAD_SCHEMA,
    LivingDexCensorReason,
    LivingDexEconomyHead,
    LivingDexObservedArmExample,
    LivingDexObservedOutcome,
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOptionUnavailableReason,
    LivingDexOptionUtility,
    LivingDexOptionValueError,
    LivingDexOptionValueModel,
    LivingDexOutcomeStatus,
    LivingDexPredictedEconomyOutcome,
    fit_living_dex_economy_head,
    fit_living_dex_option_value,
    qualified_economy_rows,
    uniform_behavior_probabilities,
)
from pokemon_red_completion.resource_economy_observation import (
    EconomyMode,
    EconomyOffer,
    EconomyOutcome,
    EconomySnapshot,
)


def _econ_context(*, cash: int = 500, target_cash: int = 1000) -> LivingDexOptionContext:
    return LivingDexOptionContext(
        collection_pressure=0.8,
        dependency_pressure=0.7,
        access_pressure=0.4,
        resource_pressure=0.3,
        storage_pressure=0.5,
        party_pressure=0.4,
        knowledge_pressure=0.2,
        economy_snapshot=EconomySnapshot(cash=cash, inventory=()),
        target_cash=target_cash,
    )


def _candidate(
    name: str,
    kind: LivingDexOptionKind = LivingDexOptionKind.ACQUIRE,
    *,
    offer: EconomyOffer | None = None,
    available: LivingDexOptionAvailability = LivingDexOptionAvailability.AVAILABLE,
    reason: LivingDexOptionUnavailableReason | None = None,
) -> LivingDexOptionCandidate:
    features = LivingDexOptionFeatures(
        kind=kind,
        completion_gain=0.8,
        dependency_unlock_gain=0.5,
        travel_effort=0.3,
        execution_effort=0.3,
        resource_cost=0.1,
        storage_cost=0.1,
        party_risk=0.1,
        irreversibility_risk=0.0,
        uncertainty=0.1,
    )
    return LivingDexOptionCandidate(
        name, features, available, unavailable_reason=reason, economy_offer=offer
    )


def _menu_2options(context: LivingDexOptionContext | None = None) -> LivingDexOptionMenu:
    ctx = _econ_context() if context is None else context
    return LivingDexOptionMenu(
        context=ctx,
        candidates=(
            _candidate(
                "opt_earn",
                LivingDexOptionKind.ACQUIRE,
                offer=EconomyOffer(mode=EconomyMode.EARN, conditional_income=200),
            ),
            _candidate(
                "opt_buy",
                LivingDexOptionKind.RESUPPLY,
                offer=EconomyOffer(mode=EconomyMode.PURCHASE, planned_spend=100),
            ),
        ),
    )


def _example(
    idx: int,
    *,
    selected: int = 0,
    menu: LivingDexOptionMenu | None = None,
    econ: EconomyOutcome | None = None,
    status: LivingDexOutcomeStatus = LivingDexOutcomeStatus.SETTLED,
    partition: str = "train",
) -> LivingDexObservedArmExample:
    m = _menu_2options() if menu is None else menu
    if status is LivingDexOutcomeStatus.SETTLED:
        outcome = LivingDexObservedOutcome(
            status=LivingDexOutcomeStatus.SETTLED,
            verified_success=True,
            completion_gain=0.5,
            dependency_unlock_gain=0.3,
            action_cost=0.2,
            frame_cost=0.2,
            resource_cost=0.1,
            party_cost=0.1,
            storage_cost=0.1,
            irreversible_loss=0.0,
            economy=econ,
        )
    else:
        outcome = LivingDexObservedOutcome(
            status=LivingDexOutcomeStatus.CENSORED,
            censor_reason=LivingDexCensorReason.EXTERNAL_INTERRUPTION,
            economy=econ,
        )
    return LivingDexObservedArmExample(
        decision_sha256=f"{idx + 1:064x}",
        partition=partition,
        menu=m,
        selected_candidate_index=selected,
        behavior_probabilities=uniform_behavior_probabilities(m),
        outcome=outcome,
    )


def _utility() -> LivingDexOptionUtility:
    return LivingDexOptionUtility(
        success_weight=1.0,
        completion_gain_weight=1.0,
        dependency_unlock_weight=1.0,
        action_cost_weight=0.1,
        frame_cost_weight=0.1,
        resource_cost_weight=0.1,
        party_cost_weight=0.1,
        storage_cost_weight=0.1,
        irreversible_loss_weight=1.0,
    )


def test_predicted_economy_outcome_frozen_dataclass() -> None:
    pred = LivingDexPredictedEconomyOutcome(useful_liquidity_gain=0.7, cash_loss=0.2)
    assert pred.useful_liquidity_gain == 0.7 and pred.cash_loss == 0.2
    assert pred.vector() == (0.7, 0.2)
    with pytest.raises(LivingDexOptionValueError):
        LivingDexPredictedEconomyOutcome(useful_liquidity_gain=1.5, cash_loss=0.0)
    with pytest.raises(LivingDexOptionValueError):
        LivingDexPredictedEconomyOutcome(useful_liquidity_gain=0.0, cash_loss=-0.1)
    with pytest.raises(LivingDexOptionValueError):
        LivingDexPredictedEconomyOutcome(useful_liquidity_gain=cast(float, True), cash_loss=0.0)


def test_qualified_economy_rows_filtering_and_singleton_menu() -> None:
    earn_econ = EconomyOutcome(
        cash_delta=100,
        net_item_decrease=0,
        net_item_increase=0,
        useful_liquidity_gain=0.5,
        cash_loss=0.0,
    )
    valid_row = _example(0, econ=earn_econ)
    dev_row = _example(1, econ=earn_econ, partition="development")
    censored_row = _example(2, econ=None, status=LivingDexOutcomeStatus.CENSORED)
    no_econ_row = _example(3, econ=None)
    plain_ctx = LivingDexOptionContext(
        collection_pressure=0.8,
        dependency_pressure=0.7,
        access_pressure=0.4,
        resource_pressure=0.3,
        storage_pressure=0.5,
        party_pressure=0.4,
        knowledge_pressure=0.2,
    )
    no_ctx_row = _example(4, menu=_menu_2options(plain_ctx), econ=earn_econ)
    # The existing menu boundary rejects forced choices before any fit can see them.
    with pytest.raises(LivingDexOptionValueError, match="two executable candidates"):
        LivingDexOptionMenu(
            context=_econ_context(),
            candidates=(
                _candidate("only_choice", LivingDexOptionKind.ACQUIRE),
                _candidate(
                    "blocked",
                    LivingDexOptionKind.TRADE,
                    available=LivingDexOptionAvailability.UNAVAILABLE,
                    reason=LivingDexOptionUnavailableReason.MISSING_CAPABILITY,
                ),
            ),
        )

    qualified = qualified_economy_rows((valid_row, dev_row, censored_row, no_econ_row, no_ctx_row))
    assert qualified == (valid_row,)


def test_fit_living_dex_economy_head_validation_entry_point() -> None:
    econ1 = EconomyOutcome(
        cash_delta=100,
        net_item_decrease=0,
        net_item_increase=0,
        useful_liquidity_gain=0.6,
        cash_loss=0.0,
    )
    econ2 = EconomyOutcome(
        cash_delta=-50,
        net_item_decrease=0,
        net_item_increase=1,
        useful_liquidity_gain=0.0,
        cash_loss=0.4,
    )
    row1, row2 = _example(0, econ=econ1), _example(1, econ=econ2)

    with pytest.raises(LivingDexOptionValueError, match="partition"):
        fit_living_dex_economy_head((row1, _example(1, econ=econ2, partition="development")))
    with pytest.raises(LivingDexOptionValueError, match="repeat"):
        fit_living_dex_economy_head((row1, row1))

    with pytest.raises(LivingDexOptionValueError, match="at least two qualified examples"):
        fit_living_dex_economy_head((row1, _example(2, econ=None)))

    with pytest.raises(LivingDexOptionValueError, match="useful_liquidity_gain_weight"):
        fit_living_dex_economy_head((row1, row2), useful_liquidity_gain_weight=2.0)
    with pytest.raises(LivingDexOptionValueError, match="cash_loss_weight"):
        fit_living_dex_economy_head((row1, row2), cash_loss_weight=cast(float, True))

    head = fit_living_dex_economy_head((row1, row2))
    assert head.schema == LIVING_DEX_ECONOMY_HEAD_SCHEMA
    assert head.qualified_examples == 2
    assert head.useful_liquidity_gain_weight == 1.0 and head.cash_loss_weight == 1.0


def test_strict_codec_rejects_mutations() -> None:
    econ1 = EconomyOutcome(
        cash_delta=100,
        net_item_decrease=0,
        net_item_increase=0,
        useful_liquidity_gain=0.8,
        cash_loss=0.0,
    )
    econ2 = EconomyOutcome(
        cash_delta=-80,
        net_item_decrease=0,
        net_item_increase=1,
        useful_liquidity_gain=0.0,
        cash_loss=0.6,
    )
    head = fit_living_dex_economy_head((_example(0, econ=econ1), _example(1, econ=econ2)))
    base_dict = head.to_dict()

    d_unknown = dict(base_dict, unauthorized_meta=True)
    with pytest.raises(LivingDexOptionValueError):
        LivingDexEconomyHead.from_dict(d_unknown)

    d_bool_coef = dict(base_dict)
    bad_coef = [list(row) for row in cast(list[list[float]], base_dict["coefficients"])]
    bad_coef[0][0] = cast(float, True)
    d_bool_coef["coefficients"] = bad_coef
    with pytest.raises(LivingDexOptionValueError):
        LivingDexEconomyHead.from_dict(d_bool_coef)

    d_str_coef = dict(base_dict)
    bad_coef_str = [list(row) for row in cast(list[list[float]], base_dict["coefficients"])]
    bad_coef_str[0][0] = cast(float, "0.5")
    d_str_coef["coefficients"] = bad_coef_str
    with pytest.raises(LivingDexOptionValueError):
        LivingDexEconomyHead.from_dict(d_str_coef)

    d_nan = dict(base_dict)
    bad_intercept = list(cast(list[float], base_dict["intercept"]))
    bad_intercept[0] = float("nan")
    d_nan["intercept"] = bad_intercept
    with pytest.raises(LivingDexOptionValueError):
        LivingDexEconomyHead.from_dict(d_nan)

    d_scale_zero = dict(base_dict)
    bad_scale = list(cast(list[float], base_dict["feature_scale"]))
    bad_scale[0] = 0.0
    d_scale_zero["feature_scale"] = bad_scale
    with pytest.raises(LivingDexOptionValueError):
        LivingDexEconomyHead.from_dict(d_scale_zero)

    d_bad_weight = dict(base_dict, useful_liquidity_gain_weight=1.5)
    with pytest.raises(LivingDexOptionValueError):
        LivingDexEconomyHead.from_dict(d_bad_weight)


def test_head_count_greater_than_parent_settled_count_rejected() -> None:
    econ1 = EconomyOutcome(
        cash_delta=100,
        net_item_decrease=0,
        net_item_increase=0,
        useful_liquidity_gain=0.8,
        cash_loss=0.0,
    )
    econ2 = EconomyOutcome(
        cash_delta=-80,
        net_item_decrease=0,
        net_item_increase=1,
        useful_liquidity_gain=0.0,
        cash_loss=0.6,
    )
    rows = (_example(0, econ=econ1), _example(1, econ=econ2))
    fit = fit_living_dex_option_value(rows, feature_version=4)
    model = fit.model
    assert model.economy_head is not None and model.economy_head.qualified_examples == 2

    with pytest.raises(LivingDexOptionValueError, match="exceed settled examples"):
        replace(model, economy_head=replace(model.economy_head, qualified_examples=3))

    model_dict = model.to_dict()
    model_dict["economy_head"] = replace(model.economy_head, qualified_examples=3).to_dict()
    with pytest.raises(LivingDexOptionValueError):
        LivingDexOptionValueModel.from_dict(model_dict)


def test_headless_v4_report_serialization() -> None:
    plain_row1, plain_row2 = _example(0, econ=None), _example(1, econ=None)

    fit_zero = fit_living_dex_option_value((plain_row1, plain_row2), feature_version=4)
    assert fit_zero.model.economy_head is None
    assert "economy_qualified_examples" not in fit_zero.report.public_dict()

    econ_single = EconomyOutcome(
        cash_delta=100,
        net_item_decrease=0,
        net_item_increase=0,
        useful_liquidity_gain=0.5,
        cash_loss=0.0,
    )
    one_econ_row = _example(2, econ=econ_single)
    fit_one = fit_living_dex_option_value((plain_row1, plain_row2, one_econ_row), feature_version=4)
    assert fit_one.model.economy_head is None
    assert fit_one.report.public_dict().get("economy_qualified_examples") == 1

    econ_two = EconomyOutcome(
        cash_delta=-50,
        net_item_decrease=0,
        net_item_increase=1,
        useful_liquidity_gain=0.0,
        cash_loss=0.3,
    )
    second_econ_row = _example(3, econ=econ_two)
    fit_two = fit_living_dex_option_value(
        (plain_row1, plain_row2, one_econ_row, second_econ_row), feature_version=4
    )
    assert fit_two.model.economy_head is not None
    assert fit_two.report.public_dict().get("economy_qualified_examples") == 2


def test_measured_outcomes_change_score_with_legacy_labels_fixed() -> None:
    util, menu = _utility(), _menu_2options()
    econ_gain = EconomyOutcome(
        cash_delta=200,
        net_item_decrease=0,
        net_item_increase=0,
        useful_liquidity_gain=0.9,
        cash_loss=0.0,
    )
    econ_loss = EconomyOutcome(
        cash_delta=-100,
        net_item_decrease=0,
        net_item_increase=1,
        useful_liquidity_gain=0.0,
        cash_loss=0.8,
    )
    rows_measured = (
        _example(0, selected=0, menu=menu, econ=econ_gain),
        _example(1, selected=1, menu=menu, econ=econ_loss),
    )

    econ_neutral = EconomyOutcome(
        cash_delta=0,
        net_item_decrease=0,
        net_item_increase=0,
        useful_liquidity_gain=0.0,
        cash_loss=0.0,
    )
    rows_neutral = (
        _example(0, selected=0, menu=menu, econ=econ_neutral),
        _example(1, selected=1, menu=menu, econ=econ_neutral),
    )

    fit_active = fit_living_dex_option_value(rows_measured, feature_version=4)
    fit_neutral = fit_living_dex_option_value(rows_neutral, feature_version=4)

    legacy_pred_active = fit_active.model.predict_candidate(
        menu.context, menu.candidates[0]
    ).vector()
    legacy_pred_neutral = fit_neutral.model.predict_candidate(
        menu.context, menu.candidates[0]
    ).vector()
    assert np.allclose(legacy_pred_active, legacy_pred_neutral)

    scores_active = fit_active.model.scores(menu, util)
    scores_neutral = fit_neutral.model.scores(menu, util)

    assert scores_active[0] is not None and scores_neutral[0] is not None
    assert scores_active[1] is not None and scores_neutral[1] is not None

    assert scores_active[0] > scores_neutral[0]
    assert scores_active[1] < scores_neutral[1]
    assert fit_active.model.select(menu, util) == 0
