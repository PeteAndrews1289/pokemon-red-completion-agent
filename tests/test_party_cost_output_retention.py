"""Synthetic-only tests of retaining prior party forecasts during correction."""
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

import pokemon_red_completion.living_dex_option_value as m
from test_living_dex_option_value import _example, _settled
from test_success_head_retention import parent

PARTY = m.LIVING_DEX_OPTION_OUTCOME_NAMES.index("party_cost")
OTHER = [i for i in range(9) if i != PARTY]


def evidence():
    """Two normal typed observations and a deliberately new synthetic direction."""
    rows = tuple(_example(i, selected=i, outcome=replace(_settled(
        success=True, completion=.1, unlock=.1, action_cost=.1), party_cost=.8))
        for i in range(2))
    old = rows[0].menu.candidate_vector(0, feature_version=9)
    novel = list(old)
    # A synthetic admitted vector; this is not a native semantic observation.
    novel[-1] = 1.
    lesson = m.LivingDexCurriculumOutcomeExample('a' * 64, 'train', 9,
        tuple(novel), replace(rows[0].outcome, party_cost=.05))
    base = parent()
    coefficient = base.coefficients.copy(); intercept = base.intercept.copy()
    coefficient[:, PARTY] = 0.; intercept[PARTY] = .8
    return replace(base, coefficients=coefficient, intercept=intercept), rows, (lesson,)


def run(base, rows, curriculum, **kwargs):
    return m.fit_living_dex_option_value(rows, curriculum_examples=curriculum,
        feature_version=9, frozen_party_cost_base=base, **kwargs)


def test_retains_raw_old_forecasts_while_new_direction_learns_and_other_heads_stay_exact():
    base, rows, curriculum = evidence(); old_document = base.to_dict()
    protected = tuple(row.decision_sha256 for row in rows)
    result = run(base, rows, curriculum, party_cost_retention_decision_sha256s=protected)
    model = result.model
    vectors = np.array([row.menu.candidate_vector(row.selected_candidate_index, feature_version=9)
                        for row in rows] + [curriculum[0].features])
    before = base.raw_predictions(vectors); after = model.raw_predictions(vectors)
    np.testing.assert_allclose(after[:2, PARTY], before[:2, PARTY], atol=1e-10, rtol=0)
    assert abs(after[2, PARTY] - .05) < abs(before[2, PARTY] - .05) / 2
    np.testing.assert_array_equal(after[:, OTHER], before[:, OTHER])
    np.testing.assert_array_equal(model.coefficients[:, OTHER], base.coefficients[:, OTHER])
    np.testing.assert_array_equal(model.intercept[OTHER], base.intercept[OTHER])
    np.testing.assert_array_equal(model.feature_mean, base.feature_mean)
    np.testing.assert_array_equal(model.feature_scale, base.feature_scale)
    assert model.economy_head is base.economy_head
    assert base.to_dict() == old_document
    assert model.train_dataset_sha256 == m.living_dex_option_train_dataset_sha256(
        rows, curriculum_examples=curriculum)
    report = result.report.public_dict()
    assert report['objective'] == m.LIVING_DEX_PARTY_COST_RETAINED_OUTPUT_OBJECTIVE
    assert report['fitted_outcome_names'] == ['party_cost']
    retained = report['party_cost_retention']
    assert retained['protected_count'] == 2 and retained['design_rank'] == 2
    assert retained['projected_design_rank'] == 1
    assert retained['maximum_raw_output_error'] <= retained['raw_output_absolute_tolerance']
    assert retained['intercept_penalized'] is False


def test_protected_curriculum_selection_and_order_have_identical_provenance():
    base, rows, curriculum = evidence()
    ids = (rows[0].decision_sha256, curriculum[0].decision_sha256)
    first = run(base, rows, curriculum, party_cost_retention_decision_sha256s=ids)
    second = run(base, tuple(reversed(rows)), tuple(reversed(curriculum)),
                 party_cost_retention_decision_sha256s=list(reversed(ids)))
    assert first.model.model_sha256 == second.model.model_sha256
    assert first.report.public_dict() == second.report.public_dict()
    vectors = np.array([rows[0].menu.candidate_vector(0, feature_version=9), curriculum[0].features])
    np.testing.assert_allclose(first.model.raw_predictions(vectors)[:, PARTY],
        base.raw_predictions(vectors)[:, PARTY], atol=1e-10, rtol=0)


def test_model_codec_and_zero_extension_preserve_constrained_objective():
    base, rows, curriculum = evidence()
    fitted = run(base, rows, curriculum,
        party_cost_retention_decision_sha256s=[rows[0].decision_sha256]).model
    restored = m.LivingDexOptionValueModel.from_dict(fitted.to_dict())
    assert restored.model_sha256 == fitted.model_sha256
    extended = m.upgrade_option_value_model_for_move_change(restored)
    assert extended.objective == fitted.objective and extended.feature_version == 10
    assert m.LivingDexOptionValueModel.from_dict(extended.to_dict()).model_sha256 == extended.model_sha256
    with pytest.raises(m.LivingDexOptionValueError):
        m.fit_living_dex_option_value(rows, feature_version=10, frozen_party_cost_base=extended,
            party_cost_retention_decision_sha256s=[rows[0].decision_sha256])


def test_default_and_explicit_none_never_enter_constrained_solver(monkeypatch):
    base, rows, curriculum = evidence()
    monkeypatch.setattr(m, '_fit_party_cost_with_retained_outputs',
                        lambda *a, **k: pytest.fail('default entered constrained solver'))
    first = run(base, rows, curriculum)
    second = run(base, rows, curriculum, party_cost_retention_decision_sha256s=None)
    assert first.model.model_sha256 == second.model.model_sha256
    assert first.report.public_dict() == second.report.public_dict()
    assert first.model.objective == m.LIVING_DEX_PARTY_COST_RESIDUAL_OBJECTIVE
    assert 'party_cost_retention' not in first.report.public_dict()


def small_base(width):
    coefficients = np.zeros((width, 9)); intercept = np.zeros(9); intercept[PARTY] = .2
    return SimpleNamespace(coefficients=coefficients, intercept=intercept,
                           feature_mean=np.zeros(width), feature_scale=np.ones(width))


def mathematical_fit(features, costs, indices, weights=None):
    targets = np.zeros((len(features), 9)); targets[:, PARTY] = costs
    return m._fit_party_cost_with_retained_outputs(np.asarray(features, dtype=float), targets,
        np.ones(len(features)) if weights is None else np.asarray(weights, dtype=float),
        small_base(len(features[0])), .25, tuple(indices), tuple(f'{i + 1:064x}' for i in indices))


def test_transformed_penalty_preserves_unpenalized_intercept_analytical_solution():
    # Protect b + w1 = 0. The free prediction change t = b + w2 has minimum
    # coefficient penalty t^2 / 2 at b=w2=t/2, w1=-t/2 (not an identity penalty).
    mean, scale, intercept, coefficients, _, _, report = mathematical_fit(
        [[1., 0.], [0., 1.]], [.2, .8], [0], weights=[1., 2.])
    expected_change = 2. * .6 / (2. + .25 / 2.)
    assert intercept[PARTY] - .2 == pytest.approx(expected_change / 2., abs=1e-12)
    np.testing.assert_allclose(coefficients[:, PARTY],
        [-expected_change / 2., expected_change / 2.], atol=1e-12, rtol=0)
    assert report['maximum_raw_output_error'] < 1e-12


def test_full_protected_rank_returns_noop_without_optimizer(monkeypatch):
    monkeypatch.setattr(np.linalg, 'solve', lambda *a, **k: pytest.fail('no freedom to fit'))
    _, _, intercept, coefficients, _, _, report = mathematical_fit(
        [[0., 0.], [1., 0.], [0., 1.]], [.9, .1, .7], [0, 1, 2])
    np.testing.assert_array_equal(coefficients, small_base(2).coefficients)
    np.testing.assert_array_equal(intercept, small_base(2).intercept)
    assert report['design_rank'] == 3 and report['nullspace_dimension'] == 0
    assert report['projected_design_rank'] == 0 and report['correction_l2_norm'] == 0


def test_no_new_observable_direction_returns_noop_even_with_parameter_nullspace(monkeypatch):
    monkeypatch.setattr(np.linalg, 'solve', lambda *a, **k: pytest.fail('no evidence in free space'))
    _, _, intercept, coefficients, _, _, report = mathematical_fit(
        [[1., 0.], [1., 0.]], [.9, .1], [0])
    assert report['nullspace_dimension'] == 2 and report['projected_design_rank'] == 0
    np.testing.assert_array_equal(coefficients, small_base(2).coefficients)
    np.testing.assert_array_equal(intercept, small_base(2).intercept)


def test_incompatible_identical_new_inputs_remain_measured_residual_error():
    _, _, intercept, coefficients, before, after, report = mathematical_fit(
        [[1., 0.], [0., 1.], [0., 1.]], [.2, 0., 1.], [0])
    predictions = intercept[PARTY] + np.array([[1., 0.], [0., 1.], [0., 1.]]) @ coefficients[:, PARTY]
    assert predictions[0] == pytest.approx(.2, abs=1e-12)
    assert predictions[1] == predictions[2]
    assert .2 < predictions[1] < .5
    assert after > 0 and report['projected_design_rank'] == 1


@pytest.mark.parametrize('fault', ['empty', 'duplicate', 'missing', 'invalid_sha',
    'string', 'set', 'boolean', 'censored', 'development', 'no_parent', 'success_mode'])
def test_retention_ids_refuse_before_any_linear_algebra(monkeypatch, fault):
    base, rows, curriculum = evidence(); ids = [rows[0].decision_sha256]
    kwargs = dict(feature_version=9, frozen_party_cost_base=base)
    if fault == 'empty': ids = []
    elif fault == 'duplicate': ids *= 2
    elif fault == 'missing': ids = ['f' * 64]
    elif fault == 'invalid_sha': ids = ['not-a-digest']
    elif fault == 'string': ids = ids[0]
    elif fault == 'set': ids = set(ids)
    elif fault == 'boolean': ids = [True]
    elif fault == 'censored':
        rows = (replace(rows[0], outcome=m.LivingDexObservedOutcome(
            m.LivingDexOutcomeStatus.CENSORED,
            censor_reason=m.LivingDexCensorReason.EXTERNAL_INTERRUPTION)), *rows[1:])
    elif fault == 'development': rows = (replace(rows[0], partition='development'), *rows[1:])
    elif fault == 'no_parent': kwargs.pop('frozen_party_cost_base')
    elif fault == 'success_mode': kwargs['frozen_success_base'] = base
    monkeypatch.setattr(np.linalg, 'svd', lambda *a, **k: pytest.fail('invalid evidence reached SVD'))
    monkeypatch.setattr(np.linalg, 'solve', lambda *a, **k: pytest.fail('invalid evidence reached solve'))
    with pytest.raises(m.LivingDexOptionValueError):
        m.fit_living_dex_option_value(rows, curriculum_examples=curriculum,
            party_cost_retention_decision_sha256s=ids, **kwargs)


def test_numerical_projection_failure_is_refused_not_published(monkeypatch):
    original = np.linalg.solve
    def broken(*args, **kwargs):
        result = original(*args, **kwargs)
        return np.full_like(result, np.nan)
    monkeypatch.setattr(np.linalg, 'solve', broken)
    with pytest.raises(m.LivingDexOptionValueError, match='nonfinite'):
        mathematical_fit([[1., 0.], [0., 1.]], [.2, .8], [0])

def test_finite_bad_nullspace_cannot_escape_raw_output_retention_check(monkeypatch):
    original = np.linalg.svd
    def incorrect_basis(value, **kwargs):
        answer = original(value, **kwargs)
        if value.shape == (1, 3) and kwargs.get('compute_uv', True):
            u, singular, right = answer
            return u, singular, np.eye(3)
        return answer
    monkeypatch.setattr(np.linalg, 'svd', incorrect_basis)
    with pytest.raises(m.LivingDexOptionValueError, match='raw-output tolerance'):
        mathematical_fit([[1., 0.], [1., 1.]], [.8, .8], [0])


def test_protected_targets_do_not_override_retained_parent_forecasts():
    one = mathematical_fit([[1., 0.], [0., 1.]], [0., .8], [0])
    two = mathematical_fit([[1., 0.], [0., 1.]], [1., .8], [0])
    np.testing.assert_allclose(one[2], two[2], atol=1e-12, rtol=0)
    np.testing.assert_allclose(one[3], two[3], atol=1e-12, rtol=0)
    assert one[6]['maximum_raw_output_error'] < 1e-12
    assert two[6]['maximum_raw_output_error'] < 1e-12