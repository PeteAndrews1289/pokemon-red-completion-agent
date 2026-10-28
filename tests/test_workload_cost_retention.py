"""Retain legacy forecasts while teaching observed cost residuals, ROM-free."""

import copy
from dataclasses import replace

import numpy as np
import pytest
from test_living_dex_goal_policy import _model
from test_living_dex_option_value import _example, _menu, _settled
from test_observed_level_workload import candidate

from pokemon_red_completion.living_dex_option_value import (
    LivingDexCurriculumOutcomeExample,
    LivingDexOptionKind,
    LivingDexOptionValueError,
    curriculum_features,
    fit_living_dex_option_value,
    living_dex_option_train_dataset_sha256,
    upgrade_option_value_model_for_kind_effort,
    upgrade_option_value_model_for_level_workload,
)
from pokemon_red_completion.player_option_level_workload import OptionLevelWorkload


def samples():
    anchor = _example(99, selected=0, outcome=_settled(success=True, completion=.1,
                                                    unlock=0, action_cost=.1))
    curriculum = []
    for i, (xp, cost) in enumerate([(1000, .1), (10000, .3), (30000, .7)]):
        row = candidate(OptionLevelWorkload(13, 21, xp))
        curriculum.append(LivingDexCurriculumOutcomeExample(
            f'{i + 1:064x}', 'train', 9, row.vector(_menu().context, feature_version=9),
            _settled(success=i != 2, completion=.1 if i != 2 else 0, unlock=0, action_cost=cost),
        ))
    return (anchor,), tuple(curriculum)


def test_costs_learn_without_changing_old_inputs_or_any_other_head():
    base = upgrade_option_value_model_for_kind_effort(_model())
    before = copy.deepcopy(base.to_dict())
    observed, curriculum = samples()
    originals = [copy.deepcopy(row.public_dict()) for row in curriculum]
    fit = fit_living_dex_option_value(observed, feature_version=9, curriculum_examples=curriculum,
                                    frozen_level_workload_base=base)
    model = fit.model
    assert model.feature_version == 9 and model.settled_examples == 4
    np.testing.assert_array_equal(model.coefficients[:365], base.coefficients)
    np.testing.assert_array_equal(model.feature_mean[:365], base.feature_mean)
    np.testing.assert_array_equal(model.feature_scale[:365], base.feature_scale)
    np.testing.assert_array_equal(model.intercept, base.intercept)
    assert np.all(model.feature_mean[365:] == 0.)
    assert np.any(model.coefficients[365:, 3:5] != 0.)
    assert np.all(model.coefficients[365:, :3] == 0.)
    assert np.all(model.coefficients[365:, 5:] == 0.)
    for kind in LivingDexOptionKind:
        for effort in (0., .1, .9):
            row = replace(candidate(), features=replace(candidate().features, kind=kind,
                                                       execution_effort=effort))
            np.testing.assert_allclose(model.predict_candidate(_menu().context, row).vector(),
                                       base.predict_candidate(_menu().context, row).vector(),
                                       rtol=0, atol=1e-12)
    low = candidate(OptionLevelWorkload(13, 21, 1000))
    high = candidate(OptionLevelWorkload(13, 21, 30000))
    a = model.predict_candidate(_menu().context, low)
    b = model.predict_candidate(_menu().context, high)
    assert a.action_cost < b.action_cost and a.frame_cost < b.frame_cost
    assert abs(a.action_cost - .1) < .1 and abs(b.action_cost - .7) < .2
    assert fit.report.weighted_mse_after < fit.report.weighted_mse_before
    assert model.train_dataset_sha256 == living_dex_option_train_dataset_sha256(
        observed, curriculum_examples=curriculum)
    assert [row.public_dict() for row in curriculum] == originals and base.to_dict() == before
    assert model.economy_head is base.economy_head


def test_failed_native_style_outcome_and_old_unknown_rows_are_retained():
    observed, known = samples()
    unknown = LivingDexCurriculumOutcomeExample(
        'f' * 64, 'train', 7, candidate().vector(_menu().context, feature_version=7),
        _settled(success=False, completion=0, unlock=0, action_cost=.9),
    )
    fit = fit_living_dex_option_value(observed, feature_version=9,
                                    curriculum_examples=(*known, unknown),
                                    frozen_level_workload_base=_model())
    assert fit.model.settled_examples == 5 and fit.report.successful_examples == 3
    assert curriculum_features(unknown, 9)[-5:] == (0.,) * 5


@pytest.mark.parametrize('fault', ['legacy_version', 'missing_base_type',
                                 'all_unknown', 'one_known', 'same_known', 'development'])
def test_invalid_or_uninformative_retention_fit_refuses(fault):
    observed, rows = samples()
    base = _model()
    version = 9
    if fault == 'legacy_version':
        version = 8
        rows = ()
    elif fault == 'missing_base_type':
        base = object()
    elif fault == 'all_unknown':
        rows = tuple(replace(row, features=(*row.features[:365], *((0.,) * 5))) for row in rows)
    elif fault == 'one_known':
        rows = rows[:1]
    elif fault == 'same_known':
        rows = (rows[0], replace(rows[0], decision_sha256='e' * 64))
    else:
        observed = (replace(observed[0], partition='development'),)
    with pytest.raises((LivingDexOptionValueError, TypeError, ValueError)):
        fit_living_dex_option_value(observed, feature_version=version, curriculum_examples=rows,
                                   frozen_level_workload_base=base)


def test_v9_cost_update_retains_prior_parameters_and_all_non_cost_predictions():
    observed, rows = samples()
    base = fit_living_dex_option_value(
        observed, feature_version=9, curriculum_examples=rows,
        frozen_level_workload_base=_model(),
    ).model
    before = copy.deepcopy(base.to_dict())
    revised = tuple(replace(row, outcome=replace(
        row.outcome, action_cost=row.outcome.action_cost / 2,
        frame_cost=row.outcome.frame_cost / 2,
    )) for row in rows)

    fit = fit_living_dex_option_value(
        observed, feature_version=9, curriculum_examples=revised,
        frozen_level_workload_base=base,
    )

    non_cost = (0, 1, 2, 5, 6, 7, 8)
    np.testing.assert_array_equal(fit.model.coefficients[:365], base.coefficients[:365])
    np.testing.assert_array_equal(fit.model.coefficients[:, non_cost], base.coefficients[:, non_cost])
    np.testing.assert_array_equal(fit.model.intercept, base.intercept)
    np.testing.assert_array_equal(fit.model.feature_mean, base.feature_mean)
    np.testing.assert_array_equal(fit.model.feature_scale, base.feature_scale)
    assert fit.report.weighted_mse_after < fit.report.weighted_mse_before
    assert np.any(fit.model.coefficients[365:, 3:5] != base.coefficients[365:, 3:5])
    for workload in (None, OptionLevelWorkload(13, 21, 1000), OptionLevelWorkload(13, 21, 30000)):
        row = candidate(workload)
        old = np.asarray(base.predict_candidate(_menu().context, row).vector())
        new = np.asarray(fit.model.predict_candidate(_menu().context, row).vector())
        np.testing.assert_array_equal(new[list(non_cost)], old[list(non_cost)])
        if workload is None:
            np.testing.assert_array_equal(new, old)
    assert base.to_dict() == before
    assert fit.model.economy_head is base.economy_head


def test_v9_zero_residual_keeps_already_learned_workload_costs():
    from pokemon_red_completion.living_dex_option_value import _fit_level_workload_cost_residuals

    observed, rows = samples()
    base = fit_living_dex_option_value(
        observed, feature_version=9, curriculum_examples=rows,
        frozen_level_workload_base=_model(),
    ).model
    features = np.asarray([row.features for row in rows])
    targets = base.intercept + ((features - base.feature_mean) / base.feature_scale) @ base.coefficients

    mean, scale, intercept, coefficients, _, _ = _fit_level_workload_cost_residuals(
        features, targets, np.ones(len(rows)), base, 1.0,
    )

    np.testing.assert_array_equal(coefficients, base.coefficients)
    np.testing.assert_array_equal(intercept, base.intercept)
    np.testing.assert_array_equal(mean, base.feature_mean)
    np.testing.assert_array_equal(scale, base.feature_scale)


def test_v9_cost_update_retains_unknown_predictions_with_centered_workload_features():
    observed, rows = samples()
    base = fit_living_dex_option_value(
        observed, feature_version=9, curriculum_examples=rows,
        frozen_level_workload_base=_model(),
    ).model
    means, scales, coefficients = (base.feature_mean.copy(), base.feature_scale.copy(),
                                    base.coefficients.copy())
    means[365:] = (.1, .2, .15, .05, .001)
    scales[365:] = (1.1, .3, .4, .1, .02)
    coefficients[365:, 0] = (.01, .02, .01, .02, .03)
    base = replace(base, feature_mean=means, feature_scale=scales, coefficients=coefficients)
    before = copy.deepcopy(base.to_dict())

    fit = fit_living_dex_option_value(
        observed, feature_version=9, curriculum_examples=rows,
        frozen_level_workload_base=base,
    )

    np.testing.assert_array_equal(fit.model.feature_mean, base.feature_mean)
    np.testing.assert_array_equal(fit.model.feature_scale, base.feature_scale)
    non_cost = (0, 1, 2, 5, 6, 7, 8)
    np.testing.assert_array_equal(fit.model.coefficients[:, non_cost], base.coefficients[:, non_cost])
    np.testing.assert_array_equal(fit.model.intercept[list(non_cost)], base.intercept[list(non_cost)])
    for kind in LivingDexOptionKind:
        for effort in (0., .1, .9):
            row = replace(candidate(), features=replace(candidate().features, kind=kind,
                                                       execution_effort=effort))
            np.testing.assert_allclose(fit.model.predict_candidate(_menu().context, row).vector(),
                                       base.predict_candidate(_menu().context, row).vector(),
                                       rtol=0, atol=1e-12)
    assert base.to_dict() == before
