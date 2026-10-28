"""ROM-free density residual contract; synthetic rows only, never native evidence."""
import copy
from dataclasses import replace
import numpy as np
import pytest
import pokemon_red_completion.living_dex_option_value as m
from pokemon_red_completion.player_option_capture_invocation import OptionCaptureInvocation, complete_paid_density_vector
from test_capture_invocation_v12 import candidate
from test_complete_paid_capture_residual_v13 import parent, fit as fit13
from test_living_dex_option_value import _context, _settled


def arm(cap=6, u=.9, complete=True, known=True):
    a = candidate(OptionCaptureInvocation(cap, complete) if known else None)
    return replace(a, features=replace(a.features, uncertainty=u))


def row(i, cap=6, u=.9, success=False, version=12, known=True):
    a=arm(cap,u,known=known)
    return m.LivingDexCurriculumOutcomeExample(f"{i:064x}", "train", version,
        a.vector(_context(),feature_version=version), _settled(success=success,completion=.1,unlock=.2,action_cost=.3))


def samples():
    return tuple(row(i+1,c,u,bool(i%2)) for i,(c,u) in enumerate(
        [(6,.9),(500,.9),(6,0.),(500,0.),(6,.9),(500,.9),(6,0.),(500,0.)]))


def fit(rows=None, basis=m.CompletePaidSuccessBasis.DENSITY, base=None, **kw):
    return m.fit_living_dex_option_value((), curriculum_examples=samples() if rows is None else rows,
        feature_version=14, frozen_success_base=parent() if base is None else base, complete_paid_success_basis=basis, **kw)


@pytest.mark.parametrize("cap",[6,500])
@pytest.mark.parametrize("u",[0.,.2,1.])
def test_v14_only_appends_two_input_products(cap,u):
    a=arm(cap,u); x=a.vector(_context(),feature_version=14); old=a.vector(_context(),feature_version=13)
    assert len(x)==478 and x[:-2]==old
    assert m.option_feature_names(14)[:-2]==m.option_feature_names(13)
    assert x[-4:]==(1.,cap/(cap+100),u,cap/(cap+100)*u)
    assert replace(a,binding_ref="unrelated-private-id").vector(_context(),feature_version=14)==x
    menu=m.LivingDexOptionMenu(_context(),(a,replace(a,binding_ref="second"))); assert menu.feature_version==12


@pytest.mark.parametrize("u",[-.1,1.1,True,None,float("nan"),float("inf")])
def test_density_requires_finite_unit_input_even_for_gate_zero(u):
    with pytest.raises(ValueError): complete_paid_density_vector((0.,0.),uncertainty=u)


@pytest.mark.parametrize("known,complete",[(False,True),(True,False)])
def test_gate_zero_blocks_every_local_weight_exactly(known,complete):
    base=parent(); model=m.upgrade_option_value_model_for_complete_paid_density(base)
    c=model.coefficients.copy();c[-4:,0]=[1e9,-2e9,3e9,-4e9];model=replace(model,coefficients=c)
    a=arm(500,.8,complete,known);x=a.vector(_context(),feature_version=14)
    assert x[-4:]==(0.,)*4
    np.testing.assert_array_equal(model.raw_predictions(x),base.raw_predictions(a.vector(_context(),feature_version=12)))


@pytest.mark.parametrize("basis",[m.CompletePaidSuccessBasis.CONSTANT,m.CompletePaidSuccessBasis.HORIZON])
def test_fitted_v13_zero_extension_retains_codec_parameters_and_numerics(basis):
    old=fit13(basis=basis).model; before=copy.deepcopy(old.to_dict())
    new=m.upgrade_option_value_model_for_complete_paid_density(old)
    np.testing.assert_array_equal(new.coefficients[:-2],old.coefficients)
    assert new.objective==old.objective and new.economy_head is old.economy_head
    xs=[arm(c,u)for c in (6,500)for u in (0.,.9)]
    np.testing.assert_array_equal(new.raw_predictions([a.vector(_context(),feature_version=14)for a in xs]),
                                  old.raw_predictions([a.vector(_context(),feature_version=13)for a in xs]))
    for a in xs:
        np.testing.assert_array_equal(new.raw_predictions(a.vector(_context(),feature_version=14)),old.raw_predictions(a.vector(_context(),feature_version=13)))
    assert old.to_dict()==before
    assert m.LivingDexOptionValueModel.from_dict(new.to_dict()).to_dict()==new.to_dict()


@pytest.mark.parametrize("basis",[m.CompletePaidSuccessBasis.DENSITY,m.CompletePaidSuccessBasis.HORIZON_DENSITY])
def test_exact_raw_normal_equation_and_unchanged_parent(basis):
    rows=samples();base=parent();before=copy.deepcopy(base.to_dict()); result=fit(rows,basis=basis,base=base)
    model=result.model; cols=m.complete_paid_success_columns(basis);p=len(m.option_feature_names(12))
    X=np.array([m.curriculum_features(r,14)[p:]for r in rows])[:,cols]
    y=np.array([float(r.outcome.verified_success)for r in rows])
    raw=base.raw_predictions(np.array([r.features for r in rows]))[:,0]
    expected=np.linalg.solve(X.T@X+.25*np.eye(len(cols)),X.T@(y-raw))
    np.testing.assert_array_equal(model.coefficients[np.array(cols)+p,0],expected)
    np.testing.assert_array_equal(model.coefficients[:p],base.coefficients)
    np.testing.assert_array_equal(model.coefficients[p:,1:],np.zeros((4,8)))
    np.testing.assert_array_equal(model.intercept,base.intercept)
    np.testing.assert_array_equal(model.feature_mean[:p],base.feature_mean)
    np.testing.assert_array_equal(model.feature_scale[:p],base.feature_scale)
    assert model.economy_head is base.economy_head and base.to_dict()==before
    report=result.report.public_dict()
    assert report['complete_paid_settled_examples']==8 and report['complete_paid_distinct_horizons']==2
    assert report['complete_paid_distinct_uncertainties']==2 and report['complete_paid_design_rank']==len(cols)
    assert m.LivingDexOptionValueModel.from_dict(model.to_dict()).to_dict()==model.to_dict()
    assert fit(tuple(reversed(rows)),basis=basis).model.to_dict()==model.to_dict()
    if basis is m.CompletePaidSuccessBasis.DENSITY:
        np.testing.assert_array_equal(model.coefficients[p+np.array([1,3])],np.zeros((2,9)))


@pytest.mark.parametrize("version",[7,9,10,11,12,13,14])
def test_original_curriculum_identity_and_projection(version):
    source=row(21,version=version,known=version>=12); before=copy.deepcopy(source.public_dict())
    x=m.curriculum_features(source,14)
    assert x[-4:]==((1.,6/106,.9,6/106*.9)if version>=12 else(0.,)*4)
    assert source.public_dict()==before


@pytest.mark.parametrize("fault",['constant_density','missing_cell','forged','legacy_basis','wrong_version','nontrain','duplicate'])
def test_invalid_contract_is_refused_before_optimizer(monkeypatch,fault):
    monkeypatch.setattr(np.linalg,'solve',lambda*a,**k:pytest.fail('optimizer ran'))
    with pytest.raises(m.LivingDexOptionValueError):
        if fault=='constant_density':fit(tuple(row(i+1,6 if i%2 else 500,.9,bool(i%2))for i in range(4)))
        elif fault=='missing_cell':fit((row(1,6,.9),row(2,500,.9,True),row(3,500,0.,True)),basis=m.CompletePaidSuccessBasis.HORIZON_DENSITY)
        elif fault=='forged':
            r=row(99,version=14);fit((*samples(),replace(r,features=(*r.features[:-1],.77))))
        elif fault=='legacy_basis':fit(basis=m.CompletePaidSuccessBasis.HORIZON)
        elif fault=='wrong_version':m.fit_living_dex_option_value((),curriculum_examples=samples(),feature_version=13,frozen_success_base=parent(),complete_paid_success_basis=m.CompletePaidSuccessBasis.DENSITY)
        elif fault=='nontrain':fit((replace(samples()[0],partition='development'),*samples()[1:]))
        else:fit((*samples(),samples()[0]))


def test_suffix_codec_refuses_unused_density_terms_or_other_heads():
    doc=fit().model.to_dict()
    for index,column in [(-3,0),(-1,0),(-2,1)]:
        bad=copy.deepcopy(doc);bad['coefficients'][index][column]=.1
        with pytest.raises(m.LivingDexOptionValueError):m.LivingDexOptionValueModel.from_dict(bad)
    for field,value in [('feature_mean',.1),('feature_scale',2.)]:
        bad=copy.deepcopy(doc);bad[field][-1]=value
        with pytest.raises(m.LivingDexOptionValueError):m.LivingDexOptionValueModel.from_dict(bad)


def test_density_fit_is_horizon_invariant_only_in_its_correction():
    model=fit().model;base=parent();deltas=[]
    for cap in (6,500):
        a=arm(cap,.4)
        deltas.append(model.raw_predictions(a.vector(_context(),feature_version=14))[0]-base.raw_predictions(a.vector(_context(),feature_version=12))[0])
    assert deltas[0]==pytest.approx(deltas[1],abs=2e-15)
    p=len(m.option_feature_names(12))
    assert model.coefficients[p+1,0]==model.coefficients[p+3,0]==0.
