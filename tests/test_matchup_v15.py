"""V15 observations and legacy arithmetic, using synthetic ROM-free inputs only."""
from dataclasses import replace
import copy
import numpy as np
import pytest
import pokemon_red_completion.living_dex_option_value as m
from pokemon_red_completion.player_option_matchup import OptionMatchup, MATCHUP_NAMES, matchup_vector
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.living_dex_policy_codec import (
    living_dex_private_menu_dict, restore_living_dex_private_menu, restore_living_dex_policy_menu)
from pokemon_red_completion.player_option_capture_invocation import OptionCaptureInvocation
from test_living_dex_option_value import _context, _features, _settled
from test_capture_invocation_v12 import candidate as capture
from test_complete_paid_capture_residual_v13 import parent
from test_story_success_output_retention import evidence

def facts():
    # Observed descriptor with no available groups; distinct from legacy absence.
    return OptionMatchup((0.,)*27)

def story(descriptor=None):
    return m.LivingDexOptionCandidate("private-original",
        _features(m.LivingDexOptionKind.UNLOCK_ACCESS,completion=0,unlock=.5,effort=.2),
        m.LivingDexOptionAvailability.AVAILABLE,
        challenge=OptionChallenge.from_levels(combat_levels=(18,20), opponent_levels=(20,22)),matchup=descriptor)

def ordinary14():
    model=m.upgrade_option_value_model_for_complete_paid_density(parent())
    c=model.coefficients.copy()
    c[-4:]=np.arange(36,dtype=float).reshape(4,9)*.013-.2
    return replace(model,coefficients=c)

def test_v15_appends_exact28_and_legacy_none_stays_unknown():
    arm=story(facts());old=replace(arm,matchup=None).vector(_context(),feature_version=14)
    assert arm.vector(_context(),feature_version=15)==(*old,*matchup_vector(facts()))
    assert len(m.option_feature_names(15))==506
    assert m.option_feature_names(15)[:-28]==m.option_feature_names(14)
    assert replace(arm,matchup=None).vector(_context(),feature_version=15)[-28:]==(0.,)*28
    assert arm.vector(_context(),feature_version=15)[-28]==1.
    assert replace(arm,binding_ref="private-other").vector(_context(),feature_version=15)==arm.vector(_context(),feature_version=15)

@pytest.mark.parametrize("version",range(1,15))
def test_legacy_scoring_cannot_silently_drop_matchup(version):
    with pytest.raises(ValueError,match="ignore matchup"):story(facts()).vector(_context(),feature_version=version)

@pytest.mark.parametrize("kind",[k for k in m.LivingDexOptionKind if k is not m.LivingDexOptionKind.UNLOCK_ACCESS])
def test_only_story_combat_can_carry_matchup(kind):
    a=story()
    with pytest.raises(ValueError,match="current combat"):
        replace(a,features=replace(a.features,kind=kind),matchup=facts())

@pytest.mark.parametrize("challenge",[None,OptionChallenge(False,False,0.,0.,0.)])
def test_current_combat_challenge_required(challenge):
    with pytest.raises(ValueError,match="current combat"):replace(story(),challenge=challenge,matchup=facts())

def test_policy_and_private_roundtrip_preserve_legacy_omission():
    old=m.LivingDexOptionMenu(_context(),(story(),replace(story(),binding_ref="peer")))
    olddoc=copy.deepcopy(old.policy_dict());assert "matchup"not in olddoc["candidates"][0]
    new=replace(old,candidates=(story(facts()),old.candidates[1]))
    assert new.feature_version==15 and new.policy_dict()["schema"].endswith(".v15")
    assert restore_living_dex_policy_menu(new.policy_dict()).policy_dict()==new.policy_dict()
    private=living_dex_private_menu_dict(new)
    assert living_dex_private_menu_dict(restore_living_dex_private_menu(private))==private
    assert old.policy_dict()==olddoc and old.feature_version==6
    for key,val in [("schema","bogus"),("future_success",True),("values",[0.]*26)]:
        d=copy.deepcopy(new.policy_dict());d["candidates"][0]["matchup"][key]=val
        with pytest.raises(ValueError):restore_living_dex_policy_menu(d)
    d=copy.deepcopy(new.policy_dict());d["candidates"][0]["matchup"]=None
    with pytest.raises(ValueError):restore_living_dex_policy_menu(d)
    d=copy.deepcopy(new.policy_dict());d["schema"]="pokemon.core.living-dex-option-menu.v12"
    with pytest.raises(ValueError):restore_living_dex_policy_menu(d)

@pytest.mark.parametrize("version",[7,9,10,11,12,13,14])
def test_original_curriculum_keeps_unknown_and_original_digest(version):
    a=capture(OptionCaptureInvocation(6,True)if version>=12 else None)
    row=m.LivingDexCurriculumOutcomeExample("b"*64,"train",version,a.vector(_context(),feature_version=version),
        _settled(success=False,completion=0,unlock=0,action_cost=.3))
    original=copy.deepcopy(row.public_dict())
    v=m.curriculum_features(row,15)
    assert v[:-28]==m.curriculum_features(row,14) and v[-28:]==(0.,)*28
    assert row.public_dict()==original

@pytest.mark.parametrize("oldversion",[13,14])
def test_nonzero_paid_prefix_arithmetic_retained_bit_exact(oldversion):
    base=ordinary14()
    if oldversion==13:
        base=replace(base,feature_version=13,coefficients=base.coefficients[:-2],
                     feature_mean=base.feature_mean[:-2],feature_scale=base.feature_scale[:-2])
    document=copy.deepcopy(base.to_dict());new=m.upgrade_option_value_model_for_matchup(base)
    arms=[capture(OptionCaptureInvocation(cap,complete))for cap in (6,500)for complete in (False,True)]
    for a in arms:
        np.testing.assert_array_equal(new.raw_predictions(a.vector(_context(),feature_version=15)),
                                      base.raw_predictions(a.vector(_context(),feature_version=oldversion)))
    np.testing.assert_array_equal(new.raw_predictions([a.vector(_context(),feature_version=15)for a in arms]),
                                  base.raw_predictions([a.vector(_context(),feature_version=oldversion)for a in arms]))
    assert base.to_dict()==document and new.economy_head is base.economy_head
    assert new.settled_examples==base.settled_examples and new.train_dataset_sha256==base.train_dataset_sha256
    assert m.upgrade_option_value_model_for_matchup(new)is new
    assert m.LivingDexOptionValueModel.from_dict(new.to_dict()).to_dict()==new.to_dict()

def test_v15_tail_is_separate_after_exact_paid_density_reductions():
    base=ordinary14();model=m.upgrade_option_value_model_for_matchup(base)
    c=model.coefficients.copy();c[-28:,0]=np.linspace(.1,.9,28)
    model=replace(model,coefficients=c)
    a=story(facts());v=np.array(a.vector(_context(),feature_version=15));old=v[:-28]
    expected=base.raw_predictions(old).copy();delta=v[-28:]@c[-28:]
    np.add(expected,delta,out=expected,where=delta!=0.)
    np.testing.assert_array_equal(model.raw_predictions(v),expected)
    unknown=replace(a,matchup=None).vector(_context(),feature_version=15)
    np.testing.assert_array_equal(model.raw_predictions(unknown),base.raw_predictions(old))

@pytest.mark.parametrize("fault",["paid","density","presence","unknown_nonzero","wrong_kind","not_combat","mask"])
def test_raw_gateway_and_curriculum_reject_forged_v15(fault):
    model=m.upgrade_option_value_model_for_matchup(ordinary14())
    v=list(story(facts()).vector(_context(),feature_version=15));names=m.option_feature_names(15)
    if fault=="paid":v[len(m.option_feature_names(12))]=.1
    elif fault=="density":v[len(m.option_feature_names(13))]=.1
    elif fault=="presence":v[-28]=.5
    elif fault=="unknown_nonzero":v[-28]=0.;v[-27]=1.
    elif fault=="wrong_kind":v[names.index("kind.unlock_access")]=0.;v[names.index("kind.develop")]=1.
    elif fault=="not_combat":v[names.index("challenge.unlock_access_x_combat_required")]=0.
    elif fault=="mask":v[-27]=.5
    with pytest.raises(ValueError):model.raw_predictions(v)
    row=m.LivingDexCurriculumOutcomeExample("c"*64,"train",15,tuple(v),
        _settled(success=False,completion=0,unlock=0,action_cost=.1))
    with pytest.raises(ValueError):m.curriculum_features(row,15)

def test_new_curriculum_roundtrip_and_no_downcast():
    a=story(facts());row=m.LivingDexCurriculumOutcomeExample("a"*64,"train",15,
        a.vector(_context(),feature_version=15),_settled(success=True,completion=.1,unlock=.2,action_cost=.3))
    assert m.curriculum_features(row,15)==row.features
    with pytest.raises(ValueError):m.curriculum_features(row,14)

@pytest.mark.parametrize("version",[9,10])
def test_bounded_head_never_silently_zero_extended(version):
    base,rows,ids=evidence()
    head=m.LivingDexBoundedStorySuccessHead(np.zeros(370),.2,base.model_sha256)
    model=replace(base,objective=m.LIVING_DEX_BOUNDED_STORY_SUCCESS_OBJECTIVE,bounded_story_success_head=head)
    if version==10:model=m.upgrade_option_value_model_for_move_change(model)
    before=copy.deepcopy(model.to_dict())
    with pytest.raises(ValueError,match="no V15 compatibility"):m.upgrade_option_value_model_for_matchup(model)
    assert model.to_dict()==before

def test_affine_paid_residual_upgrade_retains_allowed_terms_and_rejects_new_terms():
    base=ordinary14();c=base.coefficients.copy();p=len(m.option_feature_names(12))
    c[p:]=0.;c[p,0]=.3;c[p+1,0]=-.2
    old=replace(base,objective=m._COMPLETE_PAID_SUCCESS_OBJECTIVES[m.CompletePaidSuccessBasis.HORIZON],coefficients=c)
    new=m.upgrade_option_value_model_for_matchup(old)
    a=capture(OptionCaptureInvocation(500,True))
    np.testing.assert_array_equal(new.raw_predictions(a.vector(_context(),feature_version=15)),old.raw_predictions(a.vector(_context(),feature_version=14)))
    bad=new.to_dict();bad["coefficients"][-1][0]=.1
    with pytest.raises(ValueError):m.LivingDexOptionValueModel.from_dict(bad)


def test_goal_projection_v15_preserves_every_existing_kind():
    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.living_dex_goal_policy import living_dex_option_kind_for_goal
    for kind in GoalKind:
        assert living_dex_option_kind_for_goal(kind,feature_version=15)==living_dex_option_kind_for_goal(kind,feature_version=14)


@pytest.mark.parametrize("challenge",[OptionChallenge(True,False,0.,0.,0.),OptionChallenge.from_levels(combat_levels=(18,),opponent_levels=(20,))])
def test_known_matchup_roster_must_equal_current_challenge(challenge):
    descriptor=OptionMatchup((1.,0.,1.,1.,.5,.5,2/6,*((0.,)*20)))
    with pytest.raises(ValueError,match="roster differs"):
        replace(story(),challenge=challenge,matchup=descriptor)
    v=list(story().vector(_context(),feature_version=14))
    n=m.option_feature_names(14)
    v[n.index("challenge.unlock_access_x_opponent_fraction")]=1/6
    with pytest.raises(ValueError,match="roster differs"):
        m.project_matchup_features(v,descriptor)


def test_truthful_known_opposition_with_zero_combat_keeps_legacy_deficits_unknown():
    descriptor=OptionMatchup((1.,1.,1.,1.,0.,0.,2/6,*((0.,)*20)))
    arm=replace(story(),challenge=OptionChallenge(True,False,0.,0.,0.),matchup=descriptor)
    v=arm.vector(_context(),feature_version=15);n=m.option_feature_names(15)
    assert v[n.index("challenge.unlock_access_x_opposition_known")]==0.
    assert v[n.index("matchup.opposition_roster_known")]==1.
    assert v[n.index("matchup.opponent_fraction")]==2/6
    assert v[n.index("matchup.living_combat_fraction")]==0.
    model=m.upgrade_option_value_model_for_matchup(ordinary14())
    assert np.all(np.isfinite(model.raw_predictions(v)))
    menu=m.LivingDexOptionMenu(_context(),(arm,story()))
    assert restore_living_dex_policy_menu(menu.policy_dict()).policy_dict()==menu.policy_dict()
