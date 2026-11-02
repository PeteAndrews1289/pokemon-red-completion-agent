"""ROM-free replenishment contracts with synthetic evidence and no game fixtures."""

from dataclasses import replace

import numpy as np
import pytest
from test_living_dex_economy_head import _candidate, _econ_context

from pokemon_red_completion.goal_resource_quote import GoalResourceReserve
from pokemon_red_completion.living_dex_option_value import (
    LivingDexEconomyHead,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexReplenishmentExample,
    LivingDexReplenishmentHead,
    fit_living_dex_replenishment_head,
    option_feature_names,
)
from pokemon_red_completion.resource_economy_observation import (
    EconomyMode,
    EconomyOffer,
    EconomyReplenishmentOffer,
    EconomySnapshot,
    economy_features,
    quoted_replenishment_gain,
)


def _offer(*, available=1, target=8, purchased=7, resource="capture", spend=4200):
    return EconomyOffer(
        EconomyMode.PURCHASE,
        planned_spend=spend,
        replenishment=EconomyReplenishmentOffer(
            (GoalResourceReserve(resource, available, target, purchased),)
        ),
    )


def _row(index=1, *, offer=None, before=1, after=8, target=8, probability=0.5, partition="train"):
    return LivingDexReplenishmentExample(
        decision_sha256=f"{index:064x}",
        partition=partition,
        offer=_offer() if offer is None else offer,
        before_stock=(("capture", before),),
        after_stock=(("capture", after),),
        targets=(("capture", target),),
        selected_probability=probability,
        evidence_sha256=f"{index + 100:064x}",
    )


def _fit(rows):
    rows = tuple(rows)
    return fit_living_dex_replenishment_head(
        rows,
        attestation_sha256="a" * 64,
        expected_decision_sha256s=tuple(r.decision_sha256 for r in rows),
        ridge=0.25,
        maximum_importance_weight=4.0,
    )


def _cash_head():
    width = len(option_feature_names(4))
    return LivingDexEconomyHead(
        coefficients=np.zeros((width, 2)),
        intercept=np.array([0.4, 0.3]),
        feature_mean=np.zeros(width),
        feature_scale=np.ones(width),
        evidence_digest="b" * 64,
        qualified_examples=2,
        ridge=0.25,
        maximum_importance_weight=4.0,
    )


@pytest.mark.parametrize(
    "available,target,purchased,expected",
    [
        (1, 8, 7, 7 / 8),
        (1, 8, 3, 3 / 8),
        (7, 8, 7, 1 / 8),
        (8, 8, 7, 0.0),
        (9, 8, 7, 0.0),
        (0, 0, 7, 0.0),
    ],
)
def test_quote_uses_before_deficit_and_saturates(available, target, purchased, expected):
    assert (
        quoted_replenishment_gain(_offer(available=available, target=target, purchased=purchased))
        == expected
    )


def test_only_supported_capture_purchase_has_gain():
    unknown = EconomyOffer(EconomyMode.PURCHASE, planned_spend=4200)
    earn = EconomyOffer(EconomyMode.EARN, conditional_income=650)
    recovery = _offer(resource="recovery")
    mixed = EconomyOffer(
        EconomyMode.PURCHASE,
        planned_spend=5000,
        replenishment=EconomyReplenishmentOffer(
            (GoalResourceReserve("capture", 1, 8, 7), GoalResourceReserve("recovery", 0, 4, 2))
        ),
    )
    assert unknown.replenishment is None
    for offer in (None, unknown, earn, recovery, mixed, EconomyOffer(EconomyMode.OTHER)):
        assert quoted_replenishment_gain(offer) == 0.0


def test_refresh_after_purchase_cannot_keep_rewarding_same_stock():
    first = _offer(available=1, target=8, purchased=7)
    refreshed = _offer(available=8, target=8, purchased=7)
    assert quoted_replenishment_gain(first) == 7 / 8
    assert quoted_replenishment_gain(refreshed) == 0.0


@pytest.mark.parametrize(
    "reserves",
    [
        (),
        [GoalResourceReserve("capture", 1, 8, 7)],
        (GoalResourceReserve("capture", 1, 8, 7), GoalResourceReserve("capture", 2, 8, 6)),
    ],
)
def test_descriptor_refuses_empty_mutable_or_ambiguous_classes(reserves):
    with pytest.raises((TypeError, ValueError)):
        EconomyReplenishmentOffer(reserves)


@pytest.mark.parametrize("mode", [EconomyMode.EARN, EconomyMode.OTHER])
def test_nonpurchase_cannot_claim_stock_quote(mode):
    with pytest.raises((TypeError, ValueError)):
        EconomyOffer(mode, replenishment=_offer().replenishment)


@pytest.mark.parametrize("target_cash", [0, 1000, 50000])
def test_reserve_facts_do_not_rewrite_cash_coordinates(target_cash):
    snapshot = EconomySnapshot(21380, ())
    legacy = EconomyOffer(EconomyMode.PURCHASE, planned_spend=4200)
    assert economy_features(snapshot, _offer(), target_cash=target_cash) == (
        economy_features(snapshot, legacy, target_cash=target_cash)
    )


@pytest.mark.parametrize("version", range(4, 17))
def test_reserve_facts_leave_every_existing_parent_vector_exact(version):
    context = _econ_context(cash=21380, target_cash=0)
    old = _candidate("purchase", offer=EconomyOffer(EconomyMode.PURCHASE, planned_spend=4200))
    new = replace(old, economy_offer=_offer())
    assert old.vector(context, feature_version=version) == new.vector(
        context, feature_version=version
    )


def test_predicted_stock_gain_cannot_exceed_legitimate_quote():
    head, _ = _fit((_row(1), _row(2)))
    assert 0 < head.predict_offer(_offer()) <= quoted_replenishment_gain(_offer())
    for available in (7, 8, 9):
        offer = _offer(available=available)
        assert 0 <= head.predict_offer(offer) <= quoted_replenishment_gain(offer)
    assert head.predict_offer(_offer(resource="recovery")) == 0.0
    assert head.predict_offer(EconomyOffer(EconomyMode.EARN, conditional_income=650)) == 0.0


def test_actual_zero_stock_gain_is_not_quote_as_success():
    with pytest.raises(ValueError, match="informative"):
        _fit((_row(1, after=1), _row(2, after=1)))
    positive, _ = _fit((_row(1), _row(2)))
    mixed, _ = _fit((_row(1), _row(2, after=1)))
    assert _row(2, after=1).measured_pair()[1] == 0.0
    assert 0 < mixed.coefficient < positive.coefficient


def test_partial_actual_purchase_uses_measured_gain_not_full_quote():
    full, _ = _fit((_row(1), _row(2)))
    partial, _ = _fit((_row(1, after=4), _row(2, after=4)))
    assert 0 < partial.predict_offer(_offer()) < full.predict_offer(_offer())


def test_no_intercept_prevents_positive_earn_controls_creating_free_bonus():
    earn = EconomyOffer(EconomyMode.EARN, conditional_income=650)
    rows = (_row(1), _row(2, offer=earn, before=1, after=1))
    head, _ = _fit(rows)
    assert head.predict_offer(earn) == 0.0
    assert head.predict_offer(EconomyOffer(EconomyMode.PURCHASE, planned_spend=4200)) == 0.0
    assert head.predict_offer(_offer(available=8)) == 0.0


def test_fit_rejects_development_duplicate_or_missing_membership():
    for rows in ((_row(1, partition="development"), _row(2)), (_row(1), _row(1))):
        with pytest.raises((TypeError, ValueError)):
            _fit(rows)
    rows = (_row(1), _row(2))
    with pytest.raises((TypeError, ValueError)):
        fit_living_dex_replenishment_head(
            rows,
            attestation_sha256="a" * 64,
            expected_decision_sha256s=(rows[0].decision_sha256,),
            ridge=0.25,
            maximum_importance_weight=4.0,
        )


@pytest.mark.parametrize("probability", [0.0, -1.0, 1.1, float("nan"), True])
def test_invalid_propensity_never_reaches_fit(probability):
    with pytest.raises((TypeError, ValueError)):
        _fit((_row(1, probability=probability), _row(2)))


def test_quote_and_before_state_must_agree():
    for kwargs in ({"before": 2}, {"target": 9}):
        with pytest.raises((TypeError, ValueError)):
            _fit((_row(1, **kwargs), _row(2)))


def test_new_head_preserves_both_cash_outputs_and_healthy_party_independence():
    head, _ = _fit((_row(1), _row(2)))
    old = _cash_head()
    new = replace(old, replenishment_head=head, schema="pokemon.core.living-dex-economy-head.v2")
    candidate = _candidate("purchase", offer=_offer())
    for cash, target in ((21380, 0), (100, 1000), (5000, 1000)):
        context = _econ_context(cash=cash, target_cash=target)
        assert (
            new.predict_candidate(context, candidate).vector()
            == old.predict_candidate(context, candidate).vector()
        )
    for name in ("coefficients", "intercept", "feature_mean", "feature_scale"):
        assert np.array_equal(getattr(old, name), getattr(new, name))
    assert new.cash_loss_weight == old.cash_loss_weight == 1.0
    assert new.useful_liquidity_gain_weight == old.useful_liquidity_gain_weight == 1.0
    assert new.predict_replenishment_candidate(candidate) == head.predict_offer(
        candidate.economy_offer
    )


def test_exact_capped_ips_ridge_is_not_mean_normalized():
    rows = (_row(1, probability=0.1), _row(2, after=4, probability=0.5))
    head, report = _fit(rows)
    x = 7 / 8
    expected = (4 * x * x + 2 * x * (3 / 8)) / (4 * x * x + 2 * x * x + 0.25)
    assert head.coefficient == pytest.approx(expected, rel=0, abs=1e-15)
    assert report["fitted_parameters"] == 1


def test_replenishment_head_serialization_preserves_contract_and_predictions():
    head, _ = _fit((_row(1), _row(2)))
    encoded = head.to_dict()
    decoded = LivingDexReplenishmentHead.from_dict(encoded)
    assert decoded.to_dict() == encoded
    assert decoded.predict_offer(_offer()) == head.predict_offer(_offer())
    for field, value in (
        ("utility_weight", 2.0),
        ("qualified_resources", ["recovery"]),
        ("normalization", "other"),
        ("unexpected", 1),
    ):
        with pytest.raises(ValueError):
            LivingDexReplenishmentHead.from_dict({**encoded, field: value})


def test_augmented_private_and_policy_menu_codec_roundtrip_is_exact():
    from pokemon_red_completion.living_dex_policy_codec import (
        living_dex_private_menu_dict,
        restore_living_dex_policy_menu,
        restore_living_dex_private_menu,
    )

    menu = LivingDexOptionMenu(
        _econ_context(cash=21380, target_cash=0),
        (
            _candidate("purchase", LivingDexOptionKind.RESUPPLY, offer=_offer()),
            _candidate(
                "earn",
                LivingDexOptionKind.RESUPPLY,
                offer=EconomyOffer(EconomyMode.EARN, conditional_income=650),
            ),
        ),
    )
    assert restore_living_dex_private_menu(living_dex_private_menu_dict(menu)) == menu
    assert restore_living_dex_policy_menu(menu.policy_dict()).policy_dict() == menu.policy_dict()


def test_generic_projection_is_legacy_by_default_and_explicitly_opted_in():
    from test_living_dex_goal_policy import _question

    from pokemon_red_completion.goal_manager import (
        GoalAvailability,
        GoalKind,
        GoalManagerQuestion,
        GoalOpportunity,
    )
    from pokemon_red_completion.goal_resource_quote import GoalResourceQuote
    from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate

    opportunity = GoalOpportunity(
        binding_ref="private:purchase",
        kind=GoalKind.RESUPPLY,
        availability=GoalAvailability.AVAILABLE,
        estimated_effort=0.1,
        estimated_risk=0.1,
        resource_quote=GoalResourceQuote(21380, 4200, _offer().replenishment.reserves),
    )
    base = _question()
    opportunities = tuple(
        opportunity if o.kind is GoalKind.RESUPPLY else o for o in base.opportunities
    )
    question = GoalManagerQuestion(base.situation, opportunities)
    index = next(i for i, o in enumerate(opportunities) if o.kind is GoalKind.RESUPPLY)
    kwargs = dict(feature_version=16, binding_ref=opportunity.binding_ref)
    legacy = project_living_dex_goal_candidate(question, index, **kwargs)
    explicit = project_living_dex_goal_candidate(
        question, index, include_replenishment=True, **kwargs
    )
    assert legacy.economy_offer.replenishment is None
    assert explicit.economy_offer.replenishment == _offer().replenishment
    assert legacy.vector(_econ_context(), feature_version=16) == explicit.vector(
        _econ_context(), feature_version=16
    )


@pytest.mark.parametrize(
    "offer",
    [
        EconomyOffer(EconomyMode.EARN, conditional_income=650),
        EconomyOffer(EconomyMode.OTHER),
        EconomyOffer(EconomyMode.PURCHASE, planned_spend=0),
    ],
)
def test_live_attachment_does_not_turn_funded_earn_or_zero_spend_into_stock_gain(offer):
    from test_red_live_option_menu import _binding, _ordinary_bindings, _situation

    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.goal_resource_quote import GoalResourceQuote
    from pokemon_red_completion.red_live_option_menu import (
        build_red_live_option_set,
        supplemental_live_option,
    )

    calls = []
    quote = GoalResourceQuote(21380, 4200, _offer().replenishment.reserves)
    binding = _binding(
        GoalKind.RESUPPLY, binding_ref="private:funded-supplement", calls=calls, quote=quote
    )
    candidate = _candidate(binding.binding_ref, LivingDexOptionKind.RESUPPLY, offer=offer)
    options = build_red_live_option_set(
        situation=_situation(),
        binding_set=_ordinary_bindings(calls),
        supplements=(supplemental_live_option(binding, candidate),),
        model_feature_version=16,
        ordering_seed_sha256="a" * 64,
        economy_snapshot=EconomySnapshot(21380, ()),
        target_cash=0,
        force_resource_safety=False,
    )
    observed = next(c for c in options.menu.candidates if c.binding_ref == binding.binding_ref)
    assert observed.economy_offer == offer
    assert quoted_replenishment_gain(observed.economy_offer) == 0.0
    assert calls == []
