"""Party-only learning on synthetic observations, never real study data."""
import copy
from dataclasses import replace

import numpy as np
import pytest
from test_success_head_retention import parent
from test_living_dex_option_value import _example, _settled
import pokemon_red_completion.living_dex_option_value as m
from pokemon_red_completion.player_option_challenge import OptionChallenge

PARTY = m.LIVING_DEX_OPTION_OUTCOME_NAMES.index("party_cost")
OTHER = tuple(i for i in range(len(m.LIVING_DEX_OPTION_OUTCOME_NAMES)) if i != PARTY)


def samples():
    result = []
    for i, (own, opposition, cost) in enumerate(((45, 15, .05), (40, 20, .15),
            (30, 20, .25), (20, 30, .45), (20, 40, .55), (15, 45, .65))):
        row = _example(i, selected=0, outcome=replace(_settled(
            success=True, completion=.1, unlock=.1, action_cost=.1), party_cost=cost))
        candidate = replace(row.menu.candidates[0],
            features=replace(row.menu.candidates[0].features, kind=m.LivingDexOptionKind.UNLOCK_ACCESS),
            challenge=OptionChallenge.from_levels(combat_levels=(own,), opponent_levels=(opposition,)))
        row = replace(row, menu=replace(row.menu, candidates=(candidate, *row.menu.candidates[1:])))
        result.append(row)
    curriculum = tuple(m.LivingDexCurriculumOutcomeExample(f'{100+i:064x}', 'train', 9,
        row.menu.candidate_vector(0, feature_version=9), row.outcome)
        for i, row in enumerate(result[:3]))
    return tuple(result), curriculum


def base_model():
    base = parent(); c = base.coefficients.copy(); b = base.intercept.copy()
    c[:, PARTY] = 0.; b[PARTY] = .8
    # Deliberately wrong synthetic negative-deficit extrapolation.
    j = m.option_feature_names(9).index('challenge.unlock_access_x_maximum_level_deficit')
    c[j, PARTY] = -.5
    return replace(base, coefficients=c, intercept=b)


def fit(base=None, rows=None, curriculum=None, **kwargs):
    default_rows, default_curriculum = samples()
    return m.fit_living_dex_option_value(default_rows if rows is None else rows,
        curriculum_examples=default_curriculum if curriculum is None else curriculum,
        feature_version=9, frozen_party_cost_base=base_model() if base is None else base,
        **kwargs)


def test_negative_deficit_calibration_changes_only_party_cost_with_exact_retention():
    base = base_model(); rows, curriculum = samples()
    old = copy.deepcopy(base.to_dict()); evidence = [r.public_dict() for r in (*rows, *curriculum)]
    result = fit(base, rows, curriculum); model = result.model
    np.testing.assert_array_equal(model.feature_mean, base.feature_mean)
    np.testing.assert_array_equal(model.feature_scale, base.feature_scale)
    np.testing.assert_array_equal(model.coefficients[:, OTHER], base.coefficients[:, OTHER])
    np.testing.assert_array_equal(model.intercept[list(OTHER)], base.intercept[list(OTHER)])
    assert model.economy_head is base.economy_head
    vectors = np.asarray([row.menu.candidate_vector(0, feature_version=9) for row in rows])
    before, after = base.raw_predictions(vectors), model.raw_predictions(vectors)
    np.testing.assert_array_equal(after[:, OTHER], before[:, OTHER])
    for row in rows:
        for candidate in row.menu.candidates:
            a = np.asarray(base.predict_candidate(row.menu.context, candidate).vector())
            b = np.asarray(model.predict_candidate(row.menu.context, candidate).vector())
            np.testing.assert_array_equal(b[list(OTHER)], a[list(OTHER)])
    truth = np.asarray([r.outcome.party_cost for r in rows])
    assert np.mean((np.clip(after[:3, PARTY], 0, 1)-truth[:3])**2) < np.mean((np.clip(before[:3, PARTY], 0, 1)-truth[:3])**2)
    assert after[0, PARTY] < after[-1, PARTY]
    assert result.report.party_cost_weighted_mse_after < result.report.party_cost_weighted_mse_before
    assert base.to_dict() == old
    assert [r.public_dict() for r in (*rows, *curriculum)] == evidence
    assert result.model.train_dataset_sha256 == m.living_dex_option_train_dataset_sha256(rows, curriculum_examples=curriculum)
    doc = result.report.public_dict()
    assert doc['fitted_outcome_names'] == ['party_cost'] and doc['frozen_parent_model_sha256'] == base.model_sha256
    assert doc['normalization_retained'] and doc['economy_head_retained']
    assert not doc['outcome_balance_required'] and doc['counterfactual_targets'] == 0
    assert doc['party_cost_weighted_mse_after'] < doc['party_cost_weighted_mse_before']
    assert doc['total_examples'] == doc['settled_examples'] == 9
    assert model.objective == m.LIVING_DEX_PARTY_COST_RESIDUAL_OBJECTIVE
    restored = m.LivingDexOptionValueModel.from_dict(model.to_dict())
    assert restored.model_sha256 == model.model_sha256


def test_other_labels_cannot_change_party_fit():
    rows, curriculum = samples()
    def changed(r):
        return replace(r, outcome=replace(r.outcome, verified_success=False,
            completion_gain=.9, dependency_unlock_gain=.8, action_cost=.9, frame_cost=.8,
            resource_cost=.7, storage_cost=.6, irreversible_loss=.4))
    one = fit(rows=rows, curriculum=curriculum).model
    two = fit(rows=tuple(map(changed, rows)), curriculum=tuple(map(changed, curriculum))).model
    np.testing.assert_array_equal(one.coefficients, two.coefficients)
    np.testing.assert_array_equal(one.intercept, two.intercept)
    assert one.train_dataset_sha256 != two.train_dataset_sha256


def test_zero_party_cost_is_valid_and_does_not_require_artificial_success_balance():
    rows, curriculum = samples()
    one = fit(rows=tuple(replace(r, outcome=replace(r.outcome, party_cost=0.)) for r in rows),
        curriculum=tuple(replace(r, outcome=replace(r.outcome, party_cost=0.)) for r in curriculum))
    assert one.report.successful_examples == 9
    assert one.report.party_cost_weighted_mse_after < one.report.party_cost_weighted_mse_before


def test_censored_attempts_keep_counts_and_identity_without_a_false_target():
    rows, curriculum = samples()
    censored = replace(curriculum[0], decision_sha256='f'*64,
        outcome=m.LivingDexObservedOutcome(m.LivingDexOutcomeStatus.CENSORED,
            censor_reason=m.LivingDexCensorReason.EXTERNAL_INTERRUPTION))
    one=fit(rows=rows,curriculum=curriculum);two=fit(rows=rows,curriculum=(*curriculum,censored))
    np.testing.assert_array_equal(one.model.coefficients,two.model.coefficients)
    np.testing.assert_array_equal(one.model.intercept,two.model.intercept)
    assert two.report.total_examples==10 and two.report.settled_examples==9 and two.report.censored_examples==1
    assert one.model.train_dataset_sha256!=two.model.train_dataset_sha256


def test_row_order_is_deterministic_and_inherited_economy_count_is_separate():
    initial=base_model(); economy=replace(initial.economy_head,qualified_examples=13)
    base=replace(initial,economy_head=economy,settled_examples=20)
    rows, curriculum=samples()
    one=fit(base,rows,curriculum);two=fit(base,tuple(reversed(rows)),tuple(reversed(curriculum)))
    assert one.model.model_sha256==two.model.model_sha256
    assert one.report.public_dict()==two.report.public_dict()
    assert one.model.settled_examples==9 and one.model.economy_head is economy
    assert m.LivingDexOptionValueModel.from_dict(one.model.to_dict()).economy_head.to_dict()==economy.to_dict()
    doc=one.model.to_dict();doc['objective']=m.LIVING_DEX_OPTION_OBJECTIVE
    with pytest.raises(m.LivingDexOptionValueError):m.LivingDexOptionValueModel.from_dict(doc)


def test_zero_extension_retains_objective_and_outputs_without_opening_new_fit_version():
    model=fit().model; extended=m.upgrade_option_value_model_for_move_change(model)
    assert extended.feature_version==10 and extended.objective==model.objective
    assert m.LivingDexOptionValueModel.from_dict(extended.to_dict()).model_sha256==extended.model_sha256
    rows,_=samples()
    for row in rows:
        candidate=row.menu.candidates[0]
        np.testing.assert_allclose(model.predict_candidate(row.menu.context,candidate).vector(),
            extended.predict_candidate(row.menu.context,candidate).vector(),rtol=0,atol=1e-12)
    with pytest.raises(m.LivingDexOptionValueError):
        m.fit_living_dex_option_value(rows,feature_version=10,frozen_party_cost_base=extended)


@pytest.mark.parametrize('fault',['wrong_base','old_base','new_version','bool_version','success','workload','complete_paid'])
def test_modes_and_versions_fail_before_optimizer(monkeypatch,fault):
    rows,_=samples();base=base_model();kwargs=dict(feature_version=9,frozen_party_cost_base=base)
    if fault=='wrong_base':kwargs['frozen_party_cost_base']=object()
    elif fault=='old_base':
        from test_living_dex_goal_policy import _model
        kwargs['frozen_party_cost_base']=_model()
    elif fault=='new_version':kwargs['feature_version']=10
    elif fault=='bool_version':kwargs['feature_version']=True
    elif fault=='success':kwargs['frozen_success_base']=base
    elif fault=='workload':kwargs['frozen_level_workload_base']=base
    else:kwargs['complete_paid_success_basis']=m.CompletePaidSuccessBasis.CONSTANT
    monkeypatch.setattr(np.linalg,'solve',lambda *a,**k:pytest.fail('optimizer ran'))
    with pytest.raises(m.LivingDexOptionValueError):m.fit_living_dex_option_value(rows,**kwargs)


@pytest.mark.parametrize('fault',['development','duplicate','duplicate_curriculum','cross_duplicate','untyped','untyped_curriculum','later_features','too_few'])
def test_typed_train_data_refuses_before_optimizer(monkeypatch,fault):
    rows,curriculum=samples()
    if fault=='development':rows=(replace(rows[0],partition='development'),*rows[1:])
    elif fault=='duplicate':rows=(*rows,rows[0])
    elif fault=='duplicate_curriculum':curriculum=(*curriculum,curriculum[0])
    elif fault=='cross_duplicate':curriculum=(replace(curriculum[0],decision_sha256=rows[0].decision_sha256),)
    elif fault=='untyped':rows=(rows[0].public_dict(),)
    elif fault=='untyped_curriculum':curriculum=(curriculum[0].public_dict(),)
    elif fault=='later_features':curriculum=(replace(curriculum[0],feature_version=10,
        features=(*curriculum[0].features,*((0.,)*(len(m.option_feature_names(10))-len(m.option_feature_names(9)))))),)
    else:rows=rows[:1];curriculum=()
    monkeypatch.setattr(np.linalg,'solve',lambda *a,**k:pytest.fail('optimizer ran'))
    with pytest.raises((m.LivingDexOptionValueError,TypeError)):fit(rows=rows,curriculum=curriculum)
