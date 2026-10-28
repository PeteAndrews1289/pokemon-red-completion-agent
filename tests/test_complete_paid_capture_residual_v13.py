"""Scoped paid-capture residuals: no ROM, native process or real dataset."""
import copy
from dataclasses import replace

import numpy as np
import pytest
from test_capture_invocation_v12 import candidate
from test_living_dex_option_value import _context, _example, _settled
from test_success_head_retention import parent as legacy_parent

import pokemon_red_completion.living_dex_option_value as m
from pokemon_red_completion.living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY
from pokemon_red_completion.player_option_capture_invocation import (
    OptionCaptureInvocation, complete_paid_capture_vector,
)


def parent():
    base = m.upgrade_option_value_model_for_capture_invocation(legacy_parent())
    # Exercise frozen, nonzero success slopes and nontrivial normalizers too.
    coefficients = base.coefficients.copy()
    coefficients[:, 0] = np.linspace(-.0003, .0007, len(coefficients))
    return replace(base, coefficients=coefficients)


def row(i, *, cap=6, complete=True, success=False, known=True, version=12):
    arm = candidate(OptionCaptureInvocation(cap, complete) if known else None)
    return m.LivingDexCurriculumOutcomeExample(
        f"{i:064x}", "train", version,
        arm.vector(_context(), feature_version=version),
        _settled(success=success, completion=.1, unlock=.2, action_cost=.3),
    )


def samples():
    return (row(1), row(2, cap=500), row(3),
            row(4, cap=500, success=True))


def fit(rows=None, *, basis=m.CompletePaidSuccessBasis.HORIZON, base=None, **kwargs):
    return m.fit_living_dex_option_value(
        (), curriculum_examples=samples() if rows is None else rows,
        feature_version=13, frozen_success_base=parent() if base is None else base,
        complete_paid_success_basis=basis, **kwargs,
    )


def raw(base, arm):
    return base.raw_predictions(arm.vector(_context(), feature_version=base.feature_version))


def test_v13_is_derived_from_original_descriptor_without_changing_v12_menu_identity():
    base = candidate(OptionCaptureInvocation(6, True))
    menu = m.LivingDexOptionMenu(_context(), (base, replace(base, binding_ref="second")))
    before = copy.deepcopy(menu.policy_dict())
    assert menu.feature_version == 12
    v12 = base.vector(menu.context, feature_version=12)
    v13 = base.vector(menu.context, feature_version=13)
    assert v13[:-2] == v12 and v13[-2:] == (1., 6 / 106)
    assert m.option_feature_names(13)[:-2] == m.option_feature_names(12)
    assert menu.policy_dict() == before
    assert replace(base, binding_ref="new-private-id").vector(
        menu.context, feature_version=13) == v13


@pytest.mark.parametrize("cap", [1, 6, 500, 1000000])
@pytest.mark.parametrize("known", [False, True])
def test_unknown_and_partial_paid_inputs_have_exact_zero_delta(cap, known):
    base = parent()
    extended = m.upgrade_option_value_model_for_complete_paid_capture(base)
    coeff = extended.coefficients.copy()
    coeff[-2:, 0] = (1e8, -1e8)
    local = replace(extended, coefficients=coeff)
    arm = candidate(OptionCaptureInvocation(cap, False) if known else None)
    assert arm.vector(_context(), feature_version=13)[-2:] == (0., 0.)
    np.testing.assert_array_equal(raw(local, arm), raw(base, arm))
    assert local.predict_candidate(_context(), arm) == base.predict_candidate(_context(), arm)


@pytest.mark.parametrize("kind", list(m.LivingDexOptionKind))
def test_no_invocation_on_every_kind_is_gate_zero(kind):
    arm = candidate()
    arm = replace(arm, features=replace(arm.features, kind=kind))
    assert arm.vector(_context(), feature_version=13)[-2:] == (0., 0.)


def test_zero_extension_has_exact_raw_retention_for_vector_and_batch():
    base = parent(); before = copy.deepcopy(base.to_dict())
    model = m.upgrade_option_value_model_for_complete_paid_capture(base)
    arms = [candidate(), candidate(OptionCaptureInvocation(6, False)),
            candidate(OptionCaptureInvocation(6, True)), candidate(OptionCaptureInvocation(500, True))]
    v12 = np.asarray([a.vector(_context(), feature_version=12) for a in arms])
    v13 = np.asarray([a.vector(_context(), feature_version=13) for a in arms])
    np.testing.assert_array_equal(model.raw_predictions(v13), base.raw_predictions(v12))
    for arm in arms:
        np.testing.assert_array_equal(raw(model, arm), raw(base, arm))
    assert base.to_dict() == before
    assert model.economy_head is base.economy_head
    assert m.upgrade_option_value_model_for_complete_paid_capture(model) is model
    assert m.LivingDexOptionValueModel.from_dict(base.to_dict()).to_dict() == before


@pytest.mark.parametrize("basis", (m.CompletePaidSuccessBasis.CONSTANT, m.CompletePaidSuccessBasis.HORIZON))
def test_local_fit_changes_only_allowed_suffix_success_coefficients(basis):
    base = parent(); before = copy.deepcopy(base.to_dict())
    result = fit(base=base, basis=basis); model = result.model
    prefix = len(m.option_feature_names(12))
    np.testing.assert_array_equal(model.coefficients[:prefix], base.coefficients)
    np.testing.assert_array_equal(model.intercept, base.intercept)
    np.testing.assert_array_equal(model.feature_mean[:prefix], base.feature_mean)
    np.testing.assert_array_equal(model.feature_scale[:prefix], base.feature_scale)
    np.testing.assert_array_equal(model.coefficients[prefix:, 1:], np.zeros((2, 8)))
    np.testing.assert_array_equal(model.feature_mean[prefix:], (0., 0.))
    np.testing.assert_array_equal(model.feature_scale[prefix:], (1., 1.))
    assert model.economy_head is base.economy_head and base.to_dict() == before
    if basis is m.CompletePaidSuccessBasis.CONSTANT:
        assert model.coefficients[-1, 0] == 0.
    report = result.report.public_dict()
    assert report["complete_paid_success_basis"] == basis.value
    assert report["complete_paid_settled_examples"] == 4
    assert report["complete_paid_distinct_horizons"] == 2
    assert report["frozen_parent_model_sha256"] == base.model_sha256
    restored = m.LivingDexOptionValueModel.from_dict(model.to_dict())
    assert restored.to_dict() == model.to_dict()
    assert restored.model_sha256 == model.model_sha256


def test_fit_uses_raw_parent_targets_and_penalizes_local_bias():
    base = parent(); rows = samples()
    result = fit(base=base)
    x = np.array([(1., r.features[-2]) for r in rows])
    raw_parent = base.raw_predictions(np.asarray([r.features for r in rows]))[:, 0]
    y = np.array([float(r.outcome.verified_success) for r in rows])
    expected = np.linalg.solve(x.T @ x + .25 * np.eye(2), x.T @ (y - raw_parent))
    np.testing.assert_array_equal(result.model.coefficients[-2:, 0], expected)
    constant = fit(rows, basis=m.CompletePaidSuccessBasis.CONSTANT, base=base)
    assert constant.model.coefficients[-2, 0] == pytest.approx(np.sum(y - raw_parent) / (len(rows) + .25), abs=1e-15)


def test_labels_outside_success_or_outside_gate_cannot_change_parameters():
    source = samples()
    altered = tuple(replace(r, outcome=replace(
        r.outcome, completion_gain=.9, action_cost=.9, frame_cost=.8,
        resource_cost=.7, party_cost=.6)) for r in source)
    a = fit(source).model; b = fit(altered).model
    np.testing.assert_array_equal(a.coefficients, b.coefficients)
    negative = row(10, complete=False, success=False)
    c = fit((*source, negative)).model
    d = fit((*source, replace(negative, outcome=replace(
        negative.outcome, verified_success=True)))).model
    np.testing.assert_array_equal(a.coefficients, c.coefficients)
    np.testing.assert_array_equal(c.coefficients, d.coefficients)


def test_censored_and_order_contracts_are_retained():
    rows = samples()
    censored = replace(rows[0], decision_sha256="e" * 64,
        outcome=m.LivingDexObservedOutcome(m.LivingDexOutcomeStatus.CENSORED,
            censor_reason=m.LivingDexCensorReason.EXTERNAL_INTERRUPTION))
    a = fit(rows); b = fit((*rows, censored)); reverse = fit(tuple(reversed(rows)))
    np.testing.assert_array_equal(a.model.coefficients, b.model.coefficients)
    assert b.report.censored_examples == 1 and b.report.total_examples == 5
    assert b.model.train_dataset_sha256 != a.model.train_dataset_sha256
    assert a.model.to_dict() == reverse.model.to_dict()


@pytest.mark.parametrize("version", [7, 9, 10, 11, 12, 13])
def test_curriculum_projection_keeps_old_unknown_and_exact_known_suffix(version):
    source = row(7, known=version >= 12, version=version)
    before = copy.deepcopy(source.public_dict())
    projected = m.curriculum_features(source, 13)
    expected = (1., 6 / 106) if version >= 12 else (0., 0.)
    assert projected[-2:] == expected
    assert source.public_dict() == before


@pytest.mark.parametrize("suffix", [(1., 1.), (0., 0.), (1., 0.), (1., float("nan"))])
def test_forged_v13_suffix_never_reaches_optimizer(monkeypatch, suffix):
    monkeypatch.setattr(np.linalg, "solve", lambda *a, **k: pytest.fail("optimizer ran"))
    source = row(7, version=13)
    with pytest.raises(m.LivingDexOptionValueError):
        forged = replace(source, features=(*source.features[:-2], *suffix))
        fit((*samples(), forged))


@pytest.mark.parametrize("descriptor", [(0., 1., .5, 1.), (1., 0., .5, 1.),
    (1., 1., 0., 1.), (1., 1., .5, .2), (True, 1., .5, 1.)])
def test_malformed_descriptor_is_rejected(descriptor):
    with pytest.raises(ValueError):
        complete_paid_capture_vector(descriptor, acquire=True)


@pytest.mark.parametrize("fault", ["basis_string", "missing_base", "wrong_version",
                                  "non_train", "duplicate", "one_scope_class", "one_horizon"])
def test_invalid_fit_contracts_fail_before_optimizer(monkeypatch, fault):
    monkeypatch.setattr(np.linalg, "solve", lambda *a, **k: pytest.fail("optimizer ran"))
    with pytest.raises(m.LivingDexOptionValueError):
        if fault == "basis_string":
            fit(basis="horizon")
        elif fault == "missing_base":
            m.fit_living_dex_option_value((), curriculum_examples=samples(), feature_version=13,
                complete_paid_success_basis=m.CompletePaidSuccessBasis.HORIZON)
        elif fault == "wrong_version":
            fit(base=legacy_parent())
        elif fault == "non_train":
            bad = replace(_example(0, selected=0, outcome=row(99).outcome), partition="development")
            m.fit_living_dex_option_value((bad,), curriculum_examples=samples(), feature_version=13,
                frozen_success_base=parent(),
                complete_paid_success_basis=m.CompletePaidSuccessBasis.HORIZON)
        elif fault == "duplicate":
            fit((*samples(), samples()[0]))
        elif fault == "one_scope_class":
            fit((row(1), row(2, cap=500), row(3, known=False, success=True)))
        else:
            fit((row(1), row(2, success=True)))


def test_same_version_suffix_is_validated_in_predict_coverage_and_eval():
    source = row(8, version=13)
    model = m.upgrade_option_value_model_for_complete_paid_capture(parent())
    forged = (*source.features[:-2], 1., .99)
    with pytest.raises(m.LivingDexOptionValueError, match="suffix"):
        model.raw_predictions(forged)
    with pytest.raises(m.LivingDexOptionValueError, match="suffix"):
        model.diagnose_training_coverage((_example(90, selected=0, outcome=row(99).outcome),), curriculum_examples=(
            replace(source, features=forged),))


def test_scoring_diagnostics_and_curriculum_evaluation_use_one_raw_contract():
    model = fit().model
    arm = candidate(OptionCaptureInvocation(500, True))
    menu = m.LivingDexOptionMenu(_context(), (arm, replace(candidate(), binding_ref="other")))
    diagnostic = model.diagnose_menu(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY)
    for i, member in enumerate(menu.candidates):
        expected = model.predict_candidate(menu.context, member).vector()
        assert tuple(diagnostic["candidates"][i]["bounded_predictions"].values()) == expected
    assert model.scores(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY) == tuple(
        r["score"] for r in diagnostic["candidates"])
    # A real observed TRAIN row supplies the evaluator's existing nonempty guard.
    observed = _example(90, selected=0, outcome=row(99).outcome)
    curriculum = samples()
    result = m.evaluate_living_dex_option_value(
        model, (observed,), expected_partition="train", curriculum_examples=curriculum)
    expected = []
    weights = []
    for item in (observed, *curriculum):
        if isinstance(item, m.LivingDexCurriculumOutcomeExample):
            vector = m.curriculum_features(item, 13); weights.append(1.)
        else:
            vector = item.menu.candidate_vector(item.selected_candidate_index, feature_version=13)
            weights.append(item.importance_weight(model.maximum_importance_weight))
        expected.append((np.clip(model.raw_predictions(vector), 0., 1.) -
                         np.asarray(item.outcome.target_vector)) ** 2)
    np.testing.assert_array_equal(result.per_outcome_weighted_mse,
                                  np.average(expected, axis=0, weights=weights))


def test_codec_rejects_scoped_noncanonical_suffix_parameters():
    doc = fit().model.to_dict()
    for field, value in [("feature_mean", .1), ("feature_scale", 2.)]:
        bad = copy.deepcopy(doc); bad[field][-1] = value
        with pytest.raises(m.LivingDexOptionValueError):
            m.LivingDexOptionValueModel.from_dict(bad)
    bad = copy.deepcopy(doc); bad["coefficients"][-1][1] = .2
    with pytest.raises(m.LivingDexOptionValueError):
        m.LivingDexOptionValueModel.from_dict(bad)
