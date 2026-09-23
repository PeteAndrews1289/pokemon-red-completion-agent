from dataclasses import replace

import pytest
from test_living_dex_option_value import _example, _settled

from pokemon_red_completion.living_dex_option_value import (
    LivingDexCurriculumOutcomeExample,
    fit_living_dex_option_value,
)
from pokemon_red_completion.living_dex_retention_fit import fit_retaining_prior


def inputs():
    rows = tuple(
        _example(
            i,
            selected=i % 2,
            outcome=_settled(
                success=bool(i % 2), completion=0.1 * (i % 2), unlock=0, action_cost=0.2
            ),
            variant=i / 100,
        )
        for i in range(6)
    )
    prior = fit_living_dex_option_value(rows).model
    lesson = LivingDexCurriculumOutcomeExample(
        "f" * 64, "train", 1, rows[1].menu.candidate_vector(1), rows[1].outcome
    )
    return rows, prior, lesson


def test_bounded_selection_retains_prior_and_never_reads_heldout():
    rows, prior, lesson = inputs()
    result, report = fit_retaining_prior(prior, rows, (lesson,))
    assert len(report["candidates"]) == 5 and report["heldout_queries"] == 0
    assert result is not None
    chosen = next(r for r in report["candidates"] if r["model_sha256"] == result.model.model_sha256)
    assert chosen["old_mse"] <= report["prior_mse"] * 1.02
    assert chosen["new_train_mse"] == min(
        r["new_train_mse"] for r in report["candidates"] if r["retained"]
    )
    assert result.model.economy_head is prior.economy_head


def test_rejects_development_without_fitting():
    rows, prior, lesson = inputs()
    with pytest.raises(ValueError, match="TRAIN"):
        fit_retaining_prior(
            prior, (replace(rows[0], partition="development"), *rows[1:]), (lesson,)
        )
