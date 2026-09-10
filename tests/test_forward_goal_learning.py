"""Literal conditional-choice, cost, propensity and abstention falsifiers."""

from dataclasses import replace

import pytest

from pokemon_red_completion.forward_goal import (
    ForwardGoalChoice,
    ForwardGoalCounters,
    ForwardGoalOutcome,
    ForwardGoalPlan,
    ForwardGoalTerminal,
)
from pokemon_red_completion.forward_goal_learning import (
    ForwardGoalPrediction,
    ForwardGoalSelectionBounds,
    fit_forward_goal,
    forward_goal_features,
    select_forward_goal,
)


def plan():
    return ForwardGoalPlan("story", "a" * 64, "b" * 64, 100, 1000, 4, 2)


def row(number, *, readiness, selected, success, counters=None, **changes):
    choice = ForwardGoalChoice(
        f"{number:064x}",
        f"{number + 100:064x}",
        "train",
        ("readiness",),
        (readiness,),
        ("restore",),
        ((0.0,), (1.0,)),
        selected,
        (0.5, 0.5),
    )
    return replace(
        ForwardGoalOutcome(
            plan(),
            choice,
            ForwardGoalTerminal.REACHED if success else ForwardGoalTerminal.STOPPED,
            counters or ForwardGoalCounters(30, 300, 0, 1),
            success,
        ),
        **changes,
    )


def examples():
    return (
        row(1, readiness=1.0, selected=0, success=True),
        row(
            2, readiness=1.0, selected=1, success=True, counters=ForwardGoalCounters(40, 500, 2, 2)
        ),
        row(3, readiness=0.0, selected=0, success=False),
        row(
            4, readiness=0.0, selected=1, success=True, counters=ForwardGoalCounters(40, 500, 2, 2)
        ),
    )


def predictions(model, readiness, *, candidates=((0.0,), (1.0,)), declared=None):
    return model.predict(
        plan=declared or plan(),
        context_names=("readiness",),
        context=(readiness,),
        candidate_names=("restore",),
        candidates=candidates,
    )


def test_cross_terms_allow_a_fitted_preference_reversal_without_changing_candidates():
    fit = fit_forward_goal(examples(), ridge=0.001)
    assert fit.model.settled_examples == fit.distinct_inputs == fit.settled_roots == 4
    assert fit.model.censored_examples == 0
    assert fit.mse_after[0] < fit.mse_before[0] / 1000
    assert fit.mse_after[1] < fit.mse_before[1] / 1000
    bounds = ForwardGoalSelectionBounds(0.005, 0.005, 0.03, 0.8)
    ready = predictions(fit.model, 1.0)
    depleted = predictions(fit.model, 0.0)
    assert ready[0].completion > 0.999 and ready[1].completion > 0.999
    assert ready[0].cost == pytest.approx(0.2, abs=0.001)
    assert ready[1].cost == pytest.approx(7 / 15, abs=0.001)
    assert depleted[0].completion < 0.001 and depleted[1].completion > 0.999
    assert select_forward_goal(ready, supported=(True, True), bounds=bounds) == 0
    assert select_forward_goal(depleted, supported=(True, True), bounds=bounds) == 1
    assert (
        select_forward_goal(
            predictions(fit.model, 1.0, candidates=((1.0,), (0.0,))),
            supported=(True, True),
            bounds=bounds,
        )
        == 1
    )
    assert select_forward_goal(ready, supported=(True, True)) is None


def test_every_observed_context_and_budget_has_candidate_cross_terms():
    left = forward_goal_features(plan(), (0.1,), (1.0,))
    right = forward_goal_features(plan(), (0.9,), (1.0,))
    # Five state values, one candidate, then five cross terms: literal widths/order.
    assert len(left) == len(right) == 11
    assert left[0] == 0.1 and right[0] == 0.9
    assert left[6] == 0.1 and right[6] == 0.9
    assert left[5] == right[5] == 1
    assert left[7] == pytest.approx(1 / 11)
    no_restore = forward_goal_features(plan(), (0.9,), (0.0,))
    assert no_restore[6:] == (0, 0, 0, 0, 0)


def test_censored_root_changes_receipt_not_parameters_or_settled_coverage():
    rows = examples()
    censored = row(
        99,
        readiness=0.7,
        selected=0,
        success=False,
        terminal=ForwardGoalTerminal.INTERRUPTED,
        observed_goal=None,
        counters=ForwardGoalCounters(900, 9000, 20, 10),
    )
    first = fit_forward_goal(rows)
    next_fit = fit_forward_goal((*rows, censored))
    assert first.model.coefficients == next_fit.model.coefficients
    assert first.model.intercept == next_fit.model.intercept
    assert first.mse_after == next_fit.mse_after
    assert next_fit.model.dataset_sha256 != first.model.dataset_sha256
    assert next_fit.recorded_roots == 5 and next_fit.settled_roots == 4
    assert next_fit.model.censored_examples == 1


def test_settled_failures_train_cost_and_uncensored_overruns_are_not_clipped():
    rows = (
        row(
            1,
            readiness=0.5,
            selected=0,
            success=False,
            counters=ForwardGoalCounters(200, 2000, 8, 3),
        ),
        row(
            2,
            readiness=0.5,
            selected=0,
            success=True,
            counters=ForwardGoalCounters(100, 1000, 4, 2),
        ),
    )
    model = fit_forward_goal(rows).model
    result = predictions(model, 0.5)[0]
    assert result.completion == pytest.approx(0.5)
    assert result.cost == pytest.approx(1.5)


def test_propensities_produce_literal_selected_arm_weighted_mean_and_cap():
    first = row(1, readiness=0.5, selected=0, success=False)
    second = row(
        2, readiness=0.5, selected=0, success=True, counters=ForwardGoalCounters(60, 600, 0, 1)
    )
    first = replace(first, choice=replace(first.choice, probabilities=(0.25, 0.75)))
    second = replace(second, choice=replace(second.choice, probabilities=(0.75, 0.25)))
    # Weights 2 and 2/3; literal target averages .25 success, .25 cost.
    value = predictions(fit_forward_goal((first, second)).model, 0.5)[0]
    assert (value.completion, value.cost) == pytest.approx((0.25, 0.25))
    capped = predictions(fit_forward_goal((first, second), importance_cap=1).model, 0.5)[0]
    assert (capped.completion, capped.cost) == pytest.approx((0.4, 0.28))


def test_data_order_and_private_identity_do_not_choose_an_option():
    fit = fit_forward_goal(examples())
    reversed_fit = fit_forward_goal(reversed(examples()))
    assert fit.model.sha256 == reversed_fit.model.sha256
    renamed = tuple(
        replace(
            r,
            choice=replace(
                r.choice, decision_sha256=f"{index + 40:064x}", root_sha256=f"{index + 400:064x}"
            ),
        )
        for index, r in enumerate(examples())
    )
    changed = fit_forward_goal(renamed)
    assert fit.model.dataset_sha256 != changed.model.dataset_sha256
    assert fit.model.coefficients == changed.model.coefficients
    assert predictions(fit.model, 0.3) == predictions(changed.model, 0.3)


@pytest.mark.parametrize(
    "change",
    [
        {"goal_family": "collection"},
        {"verifier_sha256": "c" * 64},
        {"continuation_sha256": "d" * 64},
    ],
)
def test_fit_and_prediction_cannot_silently_change_the_goal_or_continuation(change):
    rows = examples()
    altered = replace(rows[0], plan=replace(rows[0].plan, **change))
    with pytest.raises(ValueError, match="contracts"):
        fit_forward_goal((altered, *rows[1:]))
    with pytest.raises(ValueError, match="contract"):
        predictions(fit_forward_goal(rows).model, 1, declared=altered.plan)


def test_fit_rejects_development_duplicate_and_insufficient_evidence():
    rows = examples()
    with pytest.raises(ValueError, match="train-only"):
        fit_forward_goal(
            (replace(rows[0], choice=replace(rows[0].choice, partition="development")), *rows[1:])
        )
    with pytest.raises(ValueError, match="repeat"):
        fit_forward_goal((*rows, rows[0]))
    with pytest.raises(ValueError, match="two settled"):
        fit_forward_goal(rows[:1])


def test_deterministic_development_probe_is_recorded_honestly_and_never_fitted():
    rows = examples()
    probe = replace(
        rows[0], choice=replace(rows[0].choice, partition="development", probabilities=(1.0, 0.0))
    )
    assert probe.choice.probabilities == (1.0, 0.0)
    with pytest.raises(ValueError, match="train-only"):
        fit_forward_goal((probe, *rows[1:]))
    with pytest.raises(ValueError, match="support"):
        replace(probe.choice, partition="train")


def test_tiny_probability_difference_does_not_override_meaningful_cost():
    bounds = ForwardGoalSelectionBounds(0.01, 0.01, 0.05, 0.8)
    choices = (ForwardGoalPrediction(0.901, 0.7), ForwardGoalPrediction(0.900, 0.2))
    assert select_forward_goal(choices, supported=(True, True), bounds=bounds) == 1
    assert (
        select_forward_goal(
            choices, supported=(True, True), bounds=replace(bounds, completion_error=0.04)
        )
        is None
    )
    assert select_forward_goal(choices, supported=(False, True), bounds=bounds) is None
    assert (
        select_forward_goal(
            (ForwardGoalPrediction(0.1, 0.01), ForwardGoalPrediction(0.1, 0.5)),
            supported=(True, True),
            bounds=bounds,
        )
        is None
    )


def test_selector_abstains_on_exact_ties_and_incomparable_tradeoffs():
    bounds = ForwardGoalSelectionBounds(0.01, 0.01, 0.05, 0.8)
    assert (
        select_forward_goal(
            (ForwardGoalPrediction(0.9, 0.2),) * 2, supported=(True, True), bounds=bounds
        )
        is None
    )
    assert (
        select_forward_goal(
            (ForwardGoalPrediction(0.95, 0.7), ForwardGoalPrediction(0.9, 0.2)),
            supported=(True, True),
            bounds=bounds,
        )
        is None
    )


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf")])
def test_predictions_reject_nonfinite_and_boolean_values(value):
    with pytest.raises(ValueError):
        ForwardGoalPrediction(value, 0.1)
    with pytest.raises(ValueError):
        ForwardGoalPrediction(0.9, value)


@pytest.mark.parametrize(
    "changes",
    [
        {"dataset_sha256": "bad"},
        {"settled_examples": True},
        {"censored_examples": -1},
        {"contract": ("story", "bad", "b" * 64)},
        {"ridge": 0},
        {"context_names": ("readiness", "readiness")},
        {"importance_cap": float("nan")},
    ],
)
def test_model_metadata_cannot_make_invalid_fit_claims(changes):
    with pytest.raises(ValueError):
        replace(fit_forward_goal(examples()).model, **changes)
