"""Independent ROM-free checks for the opt-in success residual update.

Copy into Code/tests before pytest collection.  This uses the existing synthetic
parent from test_success_head_retention and the existing option-value fixtures;
it reads no corpus, model artifact, ROM or save.  Constant feature vectors give a
closed-form optimum: keep all parent slopes and shift the unpenalized intercept
to the capped-IPS/unit-curriculum weighted success mean.
"""

from dataclasses import replace

import numpy as np
import pytest

import pokemon_red_completion.living_dex_option_value as m
from test_living_dex_option_value import _example, _settled
from test_success_head_retention import parent


def _constant_feature_evidence():
    success = _settled(success=True, completion=.1, unlock=.2, action_cost=.1)
    failure = _settled(success=False, completion=.1, unlock=.2, action_cost=.1)
    rows = (
        _example(700, selected=0, outcome=success,
                 behavior_probabilities=(.1, .45, .45, 0.)),
        _example(701, selected=0, outcome=failure,
                 behavior_probabilities=(.8, .1, .1, 0.)),
    )
    vector = rows[0].menu.candidate_vector(0, feature_version=9)
    assert vector == rows[1].menu.candidate_vector(0, feature_version=9)
    curriculum = m.LivingDexCurriculumOutcomeExample(
        'd' * 64, 'train', 9, vector, failure,
    )
    return rows, curriculum, np.asarray(vector, dtype=np.float64)


def _fit(base, rows, curriculum, *, cap):
    return m.fit_living_dex_option_value(
        rows, feature_version=9, frozen_success_base=base,
        curriculum_examples=(curriculum,), maximum_importance_weight=cap,
    )


def test_success_residual_uses_capped_ips_and_unit_curriculum_weight():
    rows, curriculum, vector = _constant_feature_evidence()
    base = parent()
    capped = _fit(base, rows, curriculum, cap=4.)
    uncapped = _fit(base, rows, curriculum, cap=20.)

    # The observed success has p=.1, the observed failure p=.8.  The third
    # failure is an executed curriculum lesson and has weight ONE, not IPS.
    expected_capped = 4. / (4. + 1.25 + 1.)
    expected_uncapped = 10. / (10. + 1.25 + 1.)
    normalized = (vector - base.feature_mean) / base.feature_scale
    for result, expected in ((capped, expected_capped),
                             (uncapped, expected_uncapped)):
        raw = result.model.intercept[0] + normalized @ result.model.coefficients[:, 0]
        assert raw == pytest.approx(expected, abs=1e-10)
        predicted = result.model.predict_candidate(rows[0].menu.context,
                                                    rows[0].menu.candidates[0])
        assert predicted.vector()[0] == pytest.approx(expected, abs=1e-10)
    assert expected_capped != pytest.approx(expected_uncapped)
    assert capped.model.train_dataset_sha256 == uncapped.model.train_dataset_sha256


@pytest.mark.parametrize('parent_raw', [-.35, 1.4])
def test_success_residual_anchors_nonzero_slopes_and_uses_unclipped_parent(parent_raw):
    rows, curriculum, vector = _constant_feature_evidence()
    initial = parent()
    coefficients = initial.coefficients.copy()
    coefficients[:, 0] = np.linspace(-.02, .03, len(vector))
    normalized = (vector - initial.feature_mean) / initial.feature_scale
    intercept = initial.intercept.copy()
    intercept[0] = parent_raw - normalized @ coefficients[:, 0]
    base = replace(initial, coefficients=coefficients, intercept=intercept)
    assert base.intercept[0] + normalized @ base.coefficients[:, 0] == pytest.approx(parent_raw)

    result = _fit(base, rows, curriculum, cap=4.)
    model = result.model
    expected_mean = 4. / (4. + 1.25 + 1.)

    # This is the exact normal-equation solution for identical vectors and an
    # unpenalized intercept: delta slopes are zero, delta intercept is ybar-raw.
    # A fresh fit would discard the nonzero slopes.  Subtracting a clipped
    # parent would leave the final raw score offset by parent_raw-clip(raw).
    np.testing.assert_allclose(model.coefficients[:, 0], base.coefficients[:, 0],
                               rtol=0., atol=1e-10)
    assert model.intercept[0] - base.intercept[0] == pytest.approx(
        expected_mean - parent_raw, abs=1e-10)
    raw_after = model.intercept[0] + normalized @ model.coefficients[:, 0]
    assert raw_after == pytest.approx(expected_mean, abs=1e-10)
    assert model.predict_candidate(rows[0].menu.context,
                                   rows[0].menu.candidates[0]).vector()[0] == pytest.approx(
                                       expected_mean, abs=1e-10)
    np.testing.assert_array_equal(model.feature_mean, base.feature_mean)
    np.testing.assert_array_equal(model.feature_scale, base.feature_scale)
    np.testing.assert_array_equal(model.coefficients[:, 1:], base.coefficients[:, 1:])
    np.testing.assert_array_equal(model.intercept[1:], base.intercept[1:])
    assert model.economy_head is base.economy_head
