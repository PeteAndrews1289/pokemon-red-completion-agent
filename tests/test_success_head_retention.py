"""A new success lesson must not silently retrain costs or economy, ROM-free."""
import copy
from dataclasses import replace

import numpy as np
import pytest
from test_living_dex_goal_policy import _model
from test_living_dex_option_value import _example, _menu, _settled

import pokemon_red_completion.living_dex_option_value as m


def parent():
    base = m.upgrade_option_value_model_for_level_workload(_model())
    width = len(base.feature_mean)
    coefficients = np.arange(width * 9, dtype=float).reshape(width, 9) / 1_000_000
    coefficients[:, 0] = 0.
    n = len(m.option_feature_names(4))
    economy = m.LivingDexEconomyHead(
        np.full((n, 2), .001), np.array([.2, .3]), np.zeros(n), np.ones(n),
        'b' * 64, 2, .25, 4.,
    )
    return replace(base, coefficients=coefficients,
                   intercept=np.linspace(.8, .2, 9),
                   feature_mean=np.linspace(.03, .17, width),
                   feature_scale=np.linspace(.2, 1.1, width), economy_head=economy)


def samples():
    return tuple(_example(i, selected=i % 2, variant=i * .02,
                         outcome=_settled(success=bool(i % 2), completion=.1,
                                          unlock=.2, action_cost=.1 + i * .1))
                 for i in range(6))


def fit(base=None, rows=None, **kwargs):
    return m.fit_living_dex_option_value(
        samples() if rows is None else rows, feature_version=9,
        frozen_success_base=parent() if base is None else base, **kwargs)


def test_new_success_observations_preserve_every_other_learned_quantity():
    base = parent(); original = copy.deepcopy(base.to_dict()); rows = samples()
    rows_before = [copy.deepcopy(r.public_dict()) for r in rows]
    result = fit(base, rows); model = result.model
    assert model.objective == m.LIVING_DEX_SUCCESS_RESIDUAL_OBJECTIVE
    assert model.economy_head is base.economy_head
    np.testing.assert_array_equal(model.feature_mean, base.feature_mean)
    np.testing.assert_array_equal(model.feature_scale, base.feature_scale)
    np.testing.assert_array_equal(model.coefficients[:, 1:], base.coefficients[:, 1:])
    np.testing.assert_array_equal(model.intercept[1:], base.intercept[1:])
    assert np.any(model.coefficients[:, 0] != base.coefficients[:, 0])
    assert result.report.weighted_mse_after < result.report.weighted_mse_before
    for row in rows:
        for candidate in row.menu.candidates:
            old = base.predict_candidate(row.menu.context, candidate).vector()
            new = model.predict_candidate(row.menu.context, candidate).vector()
            np.testing.assert_array_equal(new[1:], old[1:])
    doc = result.report.public_dict()
    assert doc['frozen_parent_model_sha256'] == base.model_sha256
    assert doc['fitted_outcome_names'] == ['verified_success']
    assert doc['outcome_balance_required'] and doc['normalization_retained']
    assert doc['economy_head_retained'] and doc['counterfactual_targets'] == 0
    assert base.to_dict() == original
    assert [r.public_dict() for r in rows] == rows_before
    restored = m.LivingDexOptionValueModel.from_dict(model.to_dict())
    assert restored.model_sha256 == model.model_sha256
    assert restored.economy_head.to_dict() == base.economy_head.to_dict()


def test_success_fit_is_independent_of_other_outcome_labels():
    rows = samples(); changed = tuple(replace(r, outcome=replace(
        r.outcome, completion_gain=.9, action_cost=.9, frame_cost=.7,
        party_cost=.8, resource_cost=.8)) for r in rows)
    one, two = fit(rows=rows).model, fit(rows=changed).model
    np.testing.assert_array_equal(one.coefficients, two.coefficients)
    np.testing.assert_array_equal(one.intercept, two.intercept)
    assert one.train_dataset_sha256 != two.train_dataset_sha256


def test_row_order_does_not_change_success_fit():
    one, two = fit(rows=samples()), fit(rows=tuple(reversed(samples())))
    assert one.model.model_sha256 == two.model.model_sha256
    assert one.report.public_dict() == two.report.public_dict()


def test_censored_outcomes_remain_in_denominator_without_false_targets():
    rows = samples(); censored = replace(rows[0], decision_sha256='e' * 64,
        outcome=m.LivingDexObservedOutcome(m.LivingDexOutcomeStatus.CENSORED,
            censor_reason=m.LivingDexCensorReason.EXTERNAL_INTERRUPTION))
    one, two = fit(rows=rows), fit(rows=(*rows, censored))
    np.testing.assert_array_equal(one.model.coefficients, two.model.coefficients)
    np.testing.assert_array_equal(one.model.intercept, two.model.intercept)
    assert two.report.total_examples == 7 and two.report.censored_examples == 1
    assert two.model.train_dataset_sha256 != one.model.train_dataset_sha256


def test_observed_and_curriculum_rows_share_existing_weight_contract():
    rows = samples(); c = m.LivingDexCurriculumOutcomeExample(
        'c' * 64, 'train', 9,
        rows[0].menu.candidate_vector(0, feature_version=9), rows[0].outcome)
    result = fit(rows=rows, curriculum_examples=(c,))
    assert result.report.total_examples == 7
    assert result.model.train_dataset_sha256 == m.living_dex_option_train_dataset_sha256(
        rows, curriculum_examples=(c,))
    assert result.report.public_dict()['fitted_outcome_names'] == ['verified_success']


@pytest.mark.parametrize('partition', ['development', 'validation', 'test', 'adaptation'])
def test_non_train_rows_refuse_before_optimizer(monkeypatch, partition):
    monkeypatch.setattr(np.linalg, 'solve', lambda *a, **k: pytest.fail('optimizer ran'))
    rows = (replace(samples()[0], partition=partition), *samples()[1:])
    with pytest.raises(m.LivingDexOptionValueError): fit(rows=rows)


@pytest.mark.parametrize('success', [False, True])
def test_one_outcome_class_is_not_a_success_calibration_lesson(monkeypatch, success):
    monkeypatch.setattr(np.linalg, 'solve', lambda *a, **k: pytest.fail('optimizer ran'))
    rows = tuple(replace(r, outcome=replace(r.outcome, verified_success=success)) for r in samples())
    with pytest.raises(m.LivingDexOptionValueError, match='successes and failures'): fit(rows=rows)


@pytest.mark.parametrize('fault', ['wrong_type', 'version', 'both_modes'])
def test_retention_configuration_fails_closed(monkeypatch, fault):
    monkeypatch.setattr(np.linalg, 'solve', lambda *a, **k: pytest.fail('optimizer ran'))
    base = object() if fault == 'wrong_type' else _model() if fault == 'version' else parent()
    kwargs = dict(frozen_level_workload_base=parent()) if fault == 'both_modes' else {}
    with pytest.raises(m.LivingDexOptionValueError): fit(base=base, **kwargs)


def test_legacy_fit_report_has_no_retention_fields():
    result = m.fit_living_dex_option_value(samples(), feature_version=9)
    doc = result.report.public_dict()
    assert 'frozen_parent_model_sha256' not in doc
    assert 'fitted_outcome_names' not in doc and not doc['outcome_balance_required']
    assert result.model.objective == m.LIVING_DEX_OPTION_OBJECTIVE
