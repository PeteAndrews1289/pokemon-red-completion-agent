from __future__ import annotations

import pytest

from pokemon_red_completion.evaluation_design import (
    EvaluationDesignError,
    PairedExactDesign,
    minimum_paired_contexts,
    minimum_paired_contexts_with_forced_losses,
    paired_one_sided_exact_p,
    paired_one_sided_exact_power,
    paired_one_sided_exact_power_with_forced_losses,
    zero_loss_conjunction_power,
)


def test_one_sided_exact_test_uses_only_discordant_pairs() -> None:
    assert paired_one_sided_exact_p(5, 0) == pytest.approx(0.03125)
    assert paired_one_sided_exact_p(6, 0) == pytest.approx(0.015625)
    assert paired_one_sided_exact_p(0, 0) == 1.0
    assert paired_one_sided_exact_p(7, 2) == pytest.approx(0.08984375)


def test_power_reproduces_the_reviewers_old_zero_loss_falsifier() -> None:
    assert zero_loss_conjunction_power(
        9,
        minimum_wins=6,
        win_probability=0.70,
        loss_probability=0.10,
    ) == pytest.approx(0.341770345)
    assert zero_loss_conjunction_power(
        27,
        minimum_wins=6,
        win_probability=0.70,
        loss_probability=0.10,
    ) < 0.06


def test_minimum_sample_size_and_design_are_computed_not_asserted() -> None:
    minimum = minimum_paired_contexts(
        win_probability=0.70,
        loss_probability=0.10,
        alpha=0.05,
        target_power=0.80,
    )
    assert paired_one_sided_exact_power(
        minimum,
        win_probability=0.70,
        loss_probability=0.10,
    ) >= 0.80
    if minimum > 1:
        assert paired_one_sided_exact_power(
            minimum - 1,
            win_probability=0.70,
            loss_probability=0.10,
        ) < 0.80

    design = PairedExactDesign(
        independent_contexts=minimum,
        alpha=0.05,
        smallest_useful_win_probability=0.70,
        smallest_useful_loss_probability=0.10,
        target_power=0.80,
    )
    assert design.minimum_contexts == minimum
    assert design.adequately_powered
    assert design.public_dict()["decision_rule"].startswith("promote only")


def test_worst_case_censoring_power_counts_missing_pairs_as_losses() -> None:
    assert paired_one_sided_exact_power_with_forced_losses(
        105,
        forced_losses=3,
        win_probability=0.30,
        loss_probability=0.10,
    ) == pytest.approx(0.8321468701455965)
    assert paired_one_sided_exact_power_with_forced_losses(
        98,
        forced_losses=3,
        win_probability=0.30,
        loss_probability=0.10,
    ) < 0.80


def test_minimum_sample_size_with_forced_losses_is_computed_not_asserted() -> None:
    minimum = minimum_paired_contexts_with_forced_losses(
        forced_losses=3,
        win_probability=0.30,
        loss_probability=0.10,
        alpha=0.05,
        target_power=0.80,
    )
    assert minimum == 100
    assert paired_one_sided_exact_power_with_forced_losses(
        minimum,
        forced_losses=3,
        win_probability=0.30,
        loss_probability=0.10,
    ) == pytest.approx(0.8053956642931617)
    assert paired_one_sided_exact_power_with_forced_losses(
        minimum - 1,
        forced_losses=3,
        win_probability=0.30,
        loss_probability=0.10,
    ) == pytest.approx(0.7996299998823)


def test_forced_loss_sizing_rejects_an_exhausted_search_budget() -> None:
    with pytest.raises(EvaluationDesignError, match="exhaust"):
        minimum_paired_contexts_with_forced_losses(
            forced_losses=10,
            win_probability=0.30,
            loss_probability=0.10,
            maximum_contexts=10,
        )


@pytest.mark.parametrize(
    ("wins", "losses"),
    ((-1, 0), (0, -1), (1.5, 0)),
)
def test_exact_p_rejects_invalid_counts(wins: object, losses: object) -> None:
    with pytest.raises(EvaluationDesignError):
        paired_one_sided_exact_p(wins, losses)  # type: ignore[arg-type]


def test_power_rejects_an_unfavorable_or_impossible_design() -> None:
    with pytest.raises(EvaluationDesignError, match="favorable"):
        minimum_paired_contexts(win_probability=0.2, loss_probability=0.2)
    with pytest.raises(EvaluationDesignError, match="exceed"):
        paired_one_sided_exact_power(
            12,
            win_probability=0.8,
            loss_probability=0.3,
        )


def test_cached_exact_design_functions_preserve_typed_input_validation() -> None:
    assert paired_one_sided_exact_p(0, 0) == 1.0
    with pytest.raises(EvaluationDesignError):
        paired_one_sided_exact_p(False, 0)

    assert paired_one_sided_exact_power(
        1,
        win_probability=0.0,
        loss_probability=0.0,
    ) == 0.0
    with pytest.raises(EvaluationDesignError):
        paired_one_sided_exact_power(
            1,
            win_probability=False,
            loss_probability=0.0,
        )
