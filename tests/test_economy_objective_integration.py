"""Codex-owned checks: recorded cash affects selection, not just attached logs.

All examples are synthetic unit fixtures. No game-learning evidence is created.
"""

from dataclasses import replace

import pytest
from test_living_dex_option_value import _example, _menu, _settled, _utility
from test_red_economy_learning import _earning_question

from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexObservedOutcome,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOptionValueError,
    LivingDexOptionValueModel,
    LivingDexOutcomeStatus,
    fit_living_dex_option_value,
)
from pokemon_red_completion.living_dex_player_exploration import ExploringLivingDexGoalPolicy
from pokemon_red_completion.resource_economy_observation import (
    EconomyMode,
    EconomyOffer,
    EconomySnapshot,
    economy_outcome,
)


def _rows(*, earns: bool):
    base = _menu()
    before = EconomySnapshot(500, ())
    context = replace(base.context, economy_snapshot=before, target_cash=1000)
    common = replace(base.candidates[0].features, completion_gain=0.0, dependency_unlock_gain=0.0)
    candidates = (
        replace(
            base.candidates[0],
            features=replace(common, kind=LivingDexOptionKind.RESUPPLY),
            economy_offer=EconomyOffer(EconomyMode.EARN, conditional_income=500),
        ),
        replace(
            base.candidates[1],
            features=replace(common, kind=LivingDexOptionKind.EXPLORE),
            economy_offer=EconomyOffer(EconomyMode.OTHER),
        ),
    )
    menu = LivingDexOptionMenu(context, candidates)
    legacy_outcome = _settled(success=True, completion=0.0, unlock=0.0, action_cost=0.2)
    rows = []
    for index, selected in enumerate((0, 1, 0, 1)):
        cash_after = 1000 if earns and selected == 0 else 500
        observed = replace(
            legacy_outcome,
            economy=economy_outcome(
                before,
                EconomySnapshot(cash_after, ()),
                target_cash=1000,
            ),
        )
        row = _example(index, selected=selected, outcome=observed)
        rows.append(replace(row, menu=menu, behavior_probabilities=(0.5, 0.5)))
    return tuple(rows)


def _fit(rows):
    return fit_living_dex_option_value(rows, feature_version=4, ridge=0.01).model


def test_measured_income_changes_utility_with_other_targets_held_fixed():
    gain_rows, zero_rows = _rows(earns=True), _rows(earns=False)
    gained, unchanged = _fit(gain_rows), _fit(zero_rows)
    menu = gain_rows[0].menu
    assert gained.to_dict().get("economy_head") is not None
    for candidate in menu.candidates:
        assert gained.predict_candidate(menu.context, candidate).vector() == pytest.approx(
            unchanged.predict_candidate(menu.context, candidate).vector(),
            abs=1e-12,
        )
    with_gain = gained.scores(menu, _utility())
    no_gain = unchanged.scores(menu, _utility())
    assert with_gain[0] > no_gain[0] + 0.4
    assert with_gain[0] > with_gain[1] + 0.4


def test_missing_historical_money_is_masked_not_trained_as_zero():
    rows = _rows(earns=True)
    missing = _example(
        50,
        selected=0,
        outcome=_settled(
            success=False,
            completion=0,
            unlock=0,
            action_cost=1,
        ),
    )
    original = _fit(rows).to_dict()["economy_head"]
    appended = _fit((*rows, missing)).to_dict()["economy_head"]
    assert appended == original


def test_censored_money_does_not_enter_economy_head():
    rows = _rows(earns=True)
    censored = replace(
        rows[0],
        decision_sha256="e" * 64,
        outcome=LivingDexObservedOutcome(
            LivingDexOutcomeStatus.CENSORED,
            censor_reason=LivingDexCensorReason.EXTERNAL_INTERRUPTION,
        ),
    )
    assert (
        _fit((*rows, censored)).to_dict()["economy_head"] == (_fit(rows).to_dict()["economy_head"])
    )


def test_actual_exploration_distribution_uses_measured_economy_predictions():
    """The native goal policy consumes the new scores, not just a model API."""
    question = _earning_question()
    before = EconomySnapshot(100, ())
    probe = ExploringLivingDexGoalPolicy(
        _fit(_rows(earns=False)),
        seed=1,
        allow_earning_exploration=True,
        economy_snapshot=before,
        target_cash=1000,
    )
    probe.select(question)
    assert probe.training_eligible
    menu = probe.last_menu
    assert menu is not None
    fitted = []
    for earns in (False, True):
        rows = []
        for index, selected in enumerate((0, 1, 0, 1)):
            observed = economy_outcome(
                before,
                EconomySnapshot(900 if earns and selected == 1 else 100, ()),
                target_cash=1000,
            )
            row = _example(
                index,
                selected=selected,
                outcome=replace(
                    _settled(success=True, completion=0, unlock=0, action_cost=0.2),
                    economy=observed,
                ),
            )
            rows.append(replace(row, menu=menu, behavior_probabilities=(0.5, 0.5)))
        policy = ExploringLivingDexGoalPolicy(
            _fit(rows),
            seed=1,
            allow_earning_exploration=True,
            economy_snapshot=before,
            target_cash=1000,
        )
        policy.select(question)
        assert policy.training_eligible
        fitted.append(policy)
    assert fitted[1].option_probabilities[1] > fitted[0].option_probabilities[1] + 0.1


def test_economy_model_roundtrip_identity_and_unknown_context():
    model = _fit(_rows(earns=True))
    restored = LivingDexOptionValueModel.from_dict(model.to_dict())
    menu = _rows(earns=True)[0].menu
    assert restored.model_sha256 == model.model_sha256
    assert restored.scores(menu, _utility()) == model.scores(menu, _utility())
    assert restored.economy_head is not None
    with pytest.raises(ValueError, match="read-only"):
        restored.economy_head.coefficients[0, 0] = 9
    unknown = replace(menu.context, economy_snapshot=None, target_cash=None)
    assert restored.predict_economy_candidate(unknown, menu.candidates[0]) is None
    # An explicit quote without its cash context is already invalid upstream.
    with pytest.raises(LivingDexOptionValueError, match="economy-bearing context"):
        restored.scores(replace(menu, context=unknown), _utility())
    unknown_menu = replace(
        menu,
        context=unknown,
        candidates=tuple(replace(candidate, economy_offer=None) for candidate in menu.candidates),
    )
    assert restored.scores(unknown_menu, _utility()) == replace(
        restored,
        economy_head=None,
    ).scores(unknown_menu, _utility())
    doc = model.to_dict()
    doc["schema"] = "pokemon.core.living-dex-option-value-model.v3"
    with pytest.raises(LivingDexOptionValueError, match="only feature_version 4"):
        LivingDexOptionValueModel.from_dict(doc)


def test_head_identity_is_order_independent_and_changes_with_observed_income():
    rows = _rows(earns=True)
    model = _fit(rows)
    assert _fit(tuple(reversed(rows))).economy_head.to_dict() == model.economy_head.to_dict()
    assert (
        _fit(_rows(earns=False)).economy_head.evidence_digest != model.economy_head.evidence_digest
    )


def test_failed_outcome_retains_cash_loss_as_a_prediction():
    rows = _rows(earns=False)
    failed = replace(
        rows[0],
        outcome=replace(
            rows[0].outcome,
            verified_success=False,
            economy=economy_outcome(
                EconomySnapshot(500, ()), EconomySnapshot(0, ()), target_cash=1000
            ),
        ),
    )
    model = _fit((failed, rows[1]))
    prediction = model.predict_economy_candidate(failed.menu.context, failed.menu.candidates[0])
    assert prediction.useful_liquidity_gain == pytest.approx(0, abs=1e-12)
    assert prediction.cash_loss > 0.4
