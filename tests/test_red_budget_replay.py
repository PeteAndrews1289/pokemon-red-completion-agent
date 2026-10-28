"""Opt-in complete retention replay; no native inputs or private fit data."""

from dataclasses import replace

import numpy as np
import pytest
from test_red_switch_control_examples import composed_case
from test_red_trainer_budgeted_fit import case
from test_red_trainer_retention import unit_head

from pokemon_red_completion import red_switch_control_curriculum as curriculum
from pokemon_red_completion.red_trainer_budgeted_fit import (
    RegretBudget,
    fit_budgeted_head,
    pairwise_loss_gradient,
    selected_regret,
    unique_budget_replay,
)

MODE = "unique_budget_cases_v1"


def extra_case():
    return replace(
        case(),
        candidate_vectors=((0.8, 0.1), (0.1, 0.8)),
        mean_returns=tuple(reversed(case().mean_returns)),
    )


def run(budgets, *, replay=MODE, objective="pairwise_regret", epochs=3):
    return fit_budgeted_head(
        unit_head(),
        (case(),),
        (case(),),
        budgets,
        epochs=epochs,
        objective=objective,
        retention_replay=replay,
    )


def test_union_includes_non_anchor_budget_rows_without_mutation():
    anchor, extra = case(), extra_case()
    budget = RegretBudget("outside", (extra, extra), 3.0, 0.2)
    pool = unique_budget_replay((anchor,), (budget,))
    assert len(pool) == 2 and extra in pool and anchor in pool
    assert budget.cases == (extra, extra) and budget.offset == 0.2


def test_overlap_and_order_do_not_weight_the_optimization_twice():
    a, b = case(), extra_case()
    first = (RegretBudget("first", (a, b), 10),)
    duplicate = (RegretBudget("second", (b, b, a), 10), *first)
    m1, r1 = run(first)
    m2, r2 = run(duplicate)
    assert m1.to_dict() == m2.to_dict()
    assert unique_budget_replay((a,), first) == unique_budget_replay((a,), duplicate)
    assert r1["retention_replay"]["unique_replay_cases"] == 2
    assert r2["retention_replay"]["budget_cases"] == 5
    assert [h["terminal_expected_regret"] for h in r1["history"]] == [
        h["terminal_expected_regret"] for h in r2["history"]
    ]


def test_metadata_does_not_duplicate_a_measured_objective():
    row = case()
    duplicate = replace(row, best_indices=(0, 1), target_probabilities=(0.5, 0.5))
    assert len(unique_budget_replay((row,), (RegretBudget("meta", (duplicate,), 3),))) == 1


def test_different_measured_returns_are_not_silently_averaged():
    row = case()
    different = replace(row, mean_returns=(1.0, 1.0))
    pool = unique_budget_replay((row,), (RegretBudget("different", (different,), 3),))
    assert len(pool) == 2 and row in pool and different in pool


def test_non_anchor_case_changes_the_actual_update():
    budget = (RegretBudget("outside", (extra_case(),), 10),)
    _, old = run(budget, replay="anchors", epochs=1)
    _, new = run(budget, epochs=1)
    # History includes the iterate after the one real Adam update, irrespective
    # of which feasible checkpoint is returned. Same budgets in both runs.
    assert new["history"][-1]["terminal_expected_regret"] != pytest.approx(
        old["history"][-1]["terminal_expected_regret"], abs=1e-12
    )
    assert new["retention_replay"] == dict(
        mode=MODE,
        anchor_cases=1,
        budget_cases=1,
        unique_replay_cases=2,
        fresh_weight=0.5,
        replay_weight=0.5,
    )


@pytest.mark.parametrize("objective", ["pairwise_regret", "expected_regret"])
def test_impossible_budgets_still_fail_closed(objective):
    model, report = run((RegretBudget("impossible", (case(),), -1),), objective=objective)
    assert model is None and report["selected_epoch"] is None
    assert report["feasible_checkpoints"] == 0


def test_replay_never_relaxes_actual_retention_or_offset():
    opposite = replace(case(), mean_returns=tuple(reversed(case().mean_returns)))
    initial = selected_regret(unit_head(), (opposite,))
    model, report = run((RegretBudget("hard", (opposite,), initial + 0.4, 0.4),), epochs=80)
    assert model is not None and selected_regret(model, (opposite,)) <= initial
    assert all(h["budgets"]["hard"] <= initial + 0.4 for h in report["history"] if h["selected"])


def test_default_mode_is_exactly_legacy_mode():
    budgets = (RegretBudget("old", (case(),), 10),)
    implicit = fit_budgeted_head(unit_head(), (case(),), (case(),), budgets, epochs=3)
    explicit = run(budgets, replay="anchors", objective="expected_regret")
    assert implicit[0].to_dict() == explicit[0].to_dict()
    assert implicit[1] == explicit[1] and "retention_replay" not in implicit[1]


def test_replay_loss_with_padding_and_ties_is_uniform_over_unique_examples():
    from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample

    tied = TrainerHeadExample(((0.5, 0.2), (0.2, 0.4), (0.8, 0.1)), (0, 1), mean_returns=(2, 2, -1))
    pool = unique_budget_replay((case(),), (RegretBudget("ties", (tied, case(), tied), 10),))
    actual_loss, actual_gradient = pairwise_loss_gradient(unit_head(), pool)
    separate = [pairwise_loss_gradient(unit_head(), (r,)) for r in (case(), tied)]
    assert actual_loss == pytest.approx(sum(x[0] for x in separate) / 2)
    np.testing.assert_allclose(actual_gradient, sum(x[1] for x in separate) / 2, atol=1e-12)


def test_curriculum_passes_all_budgets_and_rebuilds_control(monkeypatch):
    target, model = composed_case()
    changed = replace(model.switch, weights2=-model.switch.weights2)
    calls = []

    def fit(initial, terminal, anchors, budgets, **kw):
        calls.append((terminal, budgets, kw))
        return (changed if len(calls) == 1 else initial), {}

    monkeypatch.setattr(curriculum, "fit_budgeted_head", fit)
    candidate, report = curriculum.fit_switch_control_once(
        model,
        [target],
        {"anchors": [target], "non-anchor": [target]},
        epochs=3,
        learning_rate=0.005,
        retention_replay=MODE,
    )
    assert len(calls) == 2 and all(c[2]["retention_replay"] == MODE for c in calls)
    assert all({b.name for b in c[1]} == {"anchors", "non-anchor"} for c in calls)
    expected = curriculum.build_switch_control_examples([target], replace(model, switch=changed))
    assert calls[1][0] == tuple(expected["control"])
    assert candidate.move.to_dict() == model.move.to_dict()
    assert candidate.damage_reference.to_dict() == model.damage_reference.to_dict()
    assert report["retention_replay"] == MODE and report["fits"] == 1


def test_unknown_replay_modes_rejected_before_fitting():
    with pytest.raises(ValueError, match="replay"):
        run((RegretBudget("old", (case(),), 10),), replay="typo")
    target, model = composed_case()
    with pytest.raises(ValueError, match="replay"):
        curriculum.fit_switch_control_once(
            model,
            [target],
            {"anchors": [target]},
            epochs=3,
            learning_rate=0.005,
            retention_replay="typo",
        )
