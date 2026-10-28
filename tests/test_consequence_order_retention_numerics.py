"""ROM-free numerical fixtures; never read project TRAIN/model/native artifacts."""
from types import SimpleNamespace
import numpy as np
import pytest
import scipy.optimize as optimizer
import pokemon_red_completion.player_challenge_consequence as module
fit = module._fit_order_retained
U = np.asarray((0., 1., -.1, -.1, -.25, 0., -.05, -.5, .25))


def examples():
    z = np.asarray([[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]])
    y = np.asarray([
        [1., 0., .2, .2, 1., 0., .25, 0., .2],
        [1., 1., .1, .1, 0., .3, 0., 0., 1.],
        [1., 0., .3, .3, 1., 0., .5, 0., .1],
        [1., 1., .2, .2, 0., .5, .25, 0., .9],
    ])
    return z, y


def public(values):
    values = np.maximum(values, 0.)
    values[:, :2] = np.clip(values[:, :2], 0., 1.)
    values[:, 1] = np.minimum(values[:, 0], values[:, 1])
    values[:, 7:] = np.clip(values[:, 7:], 0., 1.)
    return values


def test_fits_observed_orders_public_bounds_and_forced_boundary_columns():
    z, y = examples()
    pairs = ((1, 0), (3, 2))
    coefficients, ym = fit(z, y, pairs, U)
    assert coefficients.shape == (2, 9)
    assert np.array_equal(ym, np.nanmean(y, axis=0))
    assert np.array_equal(coefficients[:, [0, 7]], np.zeros((2, 2)))
    raw = z @ coefficients + ym
    clipped = public(raw.copy())
    assert np.max(np.abs(raw - clipped)) <= 1e-8
    for winner, loser in pairs:
        gap = float((y[winner] - y[loser]) @ U)
        assert (clipped[winner] - clipped[loser]) @ U >= min(.01, .1 * gap) - 1e-8


def test_coefficient_ridge_uses_orthonormal_basis_not_row_predictions():
    z, y = examples()
    # Duplicating a feature divides its minimum-norm coefficient across copies.
    # This has a genuinely smaller coefficient penalty than the original input.
    c, ym = fit(z, y, ((1, 0),), U)
    doubled = np.column_stack([z, z])
    d, dm = fit(doubled, y, ((1, 0),), U)
    assert np.allclose(d[:2], d[2:], atol=1e-9, rtol=0.)
    assert np.allclose(dm, ym, atol=0., rtol=0.)
    assert not np.allclose(z @ c, doubled @ d, atol=1e-7, rtol=0.)


def test_positive_constant_cost_can_vary_under_coupled_order_constraint():
    z = np.asarray([[-1e-4], [1e-4]])
    y = np.asarray([[1., 0., 1., 1., 1., 1., 1., 0., .4],
                    [1., 0., 1., 1., 1., 1., 1., 0., .6]])
    c, ym = fit(z, y, ((1, 0),), U)
    assert abs(c[0, 4]) > 1e-7
    assert (public(z @ c + ym)[1] - public(z @ c + ym)[0]) @ U >= .005 - 1e-8


def test_finite_channel_masks_do_not_invent_missing_nonpair_label():
    z, y = examples()
    y[0, 2] = np.nan
    c, ym = fit(z, y, ((3, 2),), U)
    assert ym[2] == np.mean(y[1:, 2])
    assert np.isfinite(c).all()


@pytest.mark.parametrize('pairs', [((0, 1),), ((1, 0), (1, 0)),
                                    ((1, 0), (0, 1)), ((True, 0),), ((1, 1),)])
def test_invalid_or_duplicate_inverse_orders_fail_before_optimizer(monkeypatch, pairs):
    z, y = examples()
    monkeypatch.setattr(optimizer, 'minimize', lambda *a, **k: pytest.fail('optimizer must not run'))
    with pytest.raises(ValueError):
        fit(z, y, pairs, U)


def test_pair_with_missing_label_is_rejected_before_optimizer(monkeypatch):
    z, y = examples(); y[1, 5] = np.nan
    monkeypatch.setattr(optimizer, 'minimize', lambda *a, **k: pytest.fail('optimizer must not run'))
    with pytest.raises(ValueError, match='all nine'):
        fit(z, y, ((1, 0),), U)


def test_identical_input_wrong_order_cannot_be_fitted(monkeypatch):
    z, y = examples(); z[1] = z[0]; z -= z.mean(axis=0)
    monkeypatch.setattr(optimizer, 'minimize', lambda *a, **k: pytest.fail('optimizer must not run'))
    with pytest.raises(ValueError, match='identifiable feature direction'):
        fit(z, y, ((1, 0),), U)


def test_feature_order_contradiction_fails_closed():
    z = np.asarray([[-1.], [0.], [1.]])
    y = np.asarray([[1., 0., .1, .1, 1., 0., 0., 0., .1],
                    [1., 1., .1, .1, 0., 0., 0., 0., 1.],
                    [1., 0., .1, .1, 1., 0., 0., 0., .1]])
    with pytest.raises(ValueError, match='did not converge|violates'):
        fit(z, y, ((1, 0), (1, 2)), U)


def test_rank_threshold_instability_fails_before_optimizer(monkeypatch):
    z = np.asarray([[-1., 0.], [1., 0.], [0., -1e-9], [0., 1e-9]])
    _, y = examples()
    monkeypatch.setattr(optimizer, 'minimize', lambda *a, **k: pytest.fail('optimizer must not run'))
    with pytest.raises(ValueError, match='rank is numerically unstable'):
        fit(z, y, ((1, 0),), U)


@pytest.mark.parametrize('kind', ['noncentered', 'infinite_input', 'infinite_target',
                                  'negative_target', 'probability_target', 'all_missing'])
def test_invalid_inputs_fail_closed(kind):
    z, y = examples()
    if kind == 'noncentered': z += 1.
    elif kind == 'infinite_input': z[0, 0] = np.inf
    elif kind == 'infinite_target': y[0, 2] = np.inf
    elif kind == 'negative_target': y[0, 2] = -.1
    elif kind == 'probability_target': y[0, 8] = 1.1
    elif kind == 'all_missing': y[:, 5] = np.nan
    with pytest.raises(ValueError):
        fit(z, y, ((1, 0),), U)


def test_optimizer_failure_or_false_success_is_rejected(monkeypatch):
    z, y = examples()
    monkeypatch.setattr(optimizer, 'minimize', lambda *a, **k: SimpleNamespace(
        success=True, x=np.zeros_like(a[1])))
    with pytest.raises(ValueError, match='violates its linear constraints'):
        fit(z, y, ((1, 0),), U)
    monkeypatch.setattr(optimizer, 'minimize', lambda *a, **k: SimpleNamespace(
        success=False, x=np.zeros_like(a[1])))
    with pytest.raises(ValueError, match='did not converge'):
        fit(z, y, ((1, 0),), U)


def test_numerical_time_limit_is_not_reset(monkeypatch):
    z, y = examples()
    times = iter((0., 61.))
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(times))
    with pytest.raises(TimeoutError, match='60 numerical seconds'):
        fit(z, y, ((1, 0),), U)


def test_default_contract_disallows_new_reward_or_ridge():
    z, y = examples()
    with pytest.raises(ValueError, match='feedback-two utility'):
        fit(z, y, ((1, 0),), U + .01)
    with pytest.raises(ValueError, match='ridge one'):
        fit(z, y, ((1, 0),), U, ridge=.1)
