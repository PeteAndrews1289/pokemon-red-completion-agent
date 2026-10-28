"""ROM-free prospective capture facts and zero-influence compatibility."""
from dataclasses import replace
import copy
import numpy as np
import pytest
from test_living_dex_option_value import _context, _features, _settled
from test_move_change_v10 import model
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionCandidate, LivingDexOptionKind, LivingDexOptionAvailability,
    LivingDexOptionMenu, LivingDexOptionValueModel, LivingDexCurriculumOutcomeExample,
    option_feature_names, curriculum_features, upgrade_option_value_model_for_capture_invocation,
)
from pokemon_red_completion.living_dex_policy_codec import (
    living_dex_private_menu_dict, restore_living_dex_private_menu, restore_living_dex_policy_menu,
)
from pokemon_red_completion.player_option_capture_invocation import (
    OptionCaptureInvocation, capture_invocation_feature_names, capture_invocation_vector,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.resource_economy_observation import EconomySnapshot, EconomyOffer, EconomyMode


def candidate(facts=None,binding="private-original-source-and-target"):
    return LivingDexOptionCandidate(binding,
        _features(LivingDexOptionKind.ACQUIRE,completion=.3,unlock=0,effort=.5),
        LivingDexOptionAvailability.AVAILABLE,capture_invocation=facts)


def test_horizon_and_lifecycle_are_separate_prospective_facts_with_exact_legacy_prefix():
    context=_context();short=candidate(OptionCaptureInvocation(6,True));long=candidate(OptionCaptureInvocation(500,True))
    legacy=candidate().vector(context,feature_version=11)
    assert short.vector(context,feature_version=12)[:-4]==long.vector(context,feature_version=12)[:-4]==legacy
    assert option_feature_names(12)[:-4]==option_feature_names(11)
    assert len(legacy)==470 and len(option_feature_names(12))==474
    assert short.capture_invocation.vector()==(1.,1.,6/106,1.)
    assert long.capture_invocation.vector()==(1.,1.,500/600,1.)
    assert OptionCaptureInvocation(6,False).vector()==(1.,1.,6/106,0.)
    assert capture_invocation_vector(None)==(0.,0.,0.,0.)
    assert not any(any(x in n for x in ("species","map","source","slot","result")) for n in capture_invocation_feature_names())


@pytest.mark.parametrize("kwargs",[
    {"maximum_encounters":True},{"maximum_encounters":0},{"maximum_encounters":-1},
    {"maximum_encounters":6.0},{"maximum_encounters":None},{"maximum_encounters":float("nan")},
    {"complete_paid_session":1},{"complete_paid_session":None},
    {"mechanism":"safari"},{"mechanism":True},
])
def test_invalid_invocation_is_rejected(kwargs):
    values=dict(maximum_encounters=6,complete_paid_session=True);values.update(kwargs)
    with pytest.raises(ValueError):OptionCaptureInvocation(**values)


@pytest.mark.parametrize("version",range(1,12))
def test_legacy_scorer_must_not_silently_ignore_capture_facts(version):
    with pytest.raises(ValueError,match="ignore capture"):
        candidate(OptionCaptureInvocation(6,True)).vector(_context(),feature_version=version)


def test_descriptor_only_binds_acquisition_and_never_injects_a_private_id():
    with pytest.raises(ValueError,match="acquisition"):
        replace(candidate(OptionCaptureInvocation(6,True)),features=_features(LivingDexOptionKind.DEVELOP,completion=0,unlock=0,effort=.1))
    with pytest.raises(ValueError):candidate({"maximum_encounters":6})
    a=candidate(OptionCaptureInvocation(6,True),"private-a")
    b=replace(a,binding_ref="private-b")
    assert a.policy_dict(_context())==b.policy_dict(_context())


def test_policy_private_codec_roundtrip_and_strict_descriptor_fields():
    menu=LivingDexOptionMenu(_context(),(candidate(OptionCaptureInvocation(6,True)),candidate(binding="other")))
    assert menu.feature_version==12
    doc=menu.policy_dict()
    assert restore_living_dex_policy_menu(doc).policy_dict()==doc
    private=living_dex_private_menu_dict(menu)
    assert living_dex_private_menu_dict(restore_living_dex_private_menu(private))==private
    for field,value in [("schema","unknown"),("maximum_encounters",True),("result",False)]:
        bad=copy.deepcopy(doc);bad["candidates"][0]["capture_invocation"][field]=value
        with pytest.raises(ValueError):restore_living_dex_policy_menu(bad)
    bad=copy.deepcopy(doc);bad["schema"]="pokemon.core.living-dex-option-menu.v10"
    with pytest.raises(ValueError):restore_living_dex_policy_menu(bad)


@pytest.mark.parametrize("economy",[False,True])
def test_zero_extension_retains_original_predictions_counts_identity_and_economy(economy):
    old=model(economy);before=old.to_dict();new=upgrade_option_value_model_for_capture_invocation(old)
    assert old.to_dict()==before and new.feature_version==12
    assert new.train_dataset_sha256==old.train_dataset_sha256
    assert (new.settled_examples,new.censored_examples)==(old.settled_examples,old.censored_examples)
    assert np.array_equal(new.coefficients[:370],old.coefficients) and not new.coefficients[370:].any()
    assert upgrade_option_value_model_for_capture_invocation(new) is new
    assert LivingDexOptionValueModel.from_dict(new.to_dict()).to_dict()==new.to_dict()
    context=replace(_context(),economy_snapshot=EconomySnapshot(1000,()),target_cash=500)
    plain=replace(candidate(),economy_offer=EconomyOffer(EconomyMode.OTHER,planned_spend=500))
    for facts in (None,OptionCaptureInvocation(6,False),OptionCaptureInvocation(6,True),OptionCaptureInvocation(500,True)):
        enriched=replace(plain,capture_invocation=facts)
        np.testing.assert_allclose(new.predict_candidate(context,enriched).vector(),old.predict_candidate(context,plain).vector(),rtol=0,atol=1e-14)
        assert new.predict_economy_candidate(context,enriched)==old.predict_economy_candidate(context,plain)


@pytest.mark.parametrize("version",[7,9,10,11])
def test_historical_curriculum_projects_unknown_without_relabeling_originals(version):
    row=LivingDexCurriculumOutcomeExample("f"*64,"train",version,candidate().vector(_context(),feature_version=version),
        _settled(success=False,completion=0,unlock=0,action_cost=.1))
    before=copy.deepcopy(row.public_dict());digest=canonical_sha256(before)
    projected=curriculum_features(row,12)
    assert projected[:-4]==curriculum_features(row,11) and projected[-4:]==(0.,)*4
    assert row.public_dict()==before and canonical_sha256(row.public_dict())==digest


def test_nontrivial_normalizers_and_economy_diagnostics_retain_all_predictions():
    from pokemon_red_completion.living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY
    old=model(True);rng=np.random.default_rng(913)
    old=replace(old,feature_mean=rng.uniform(.1,.9,len(old.feature_mean)),
                feature_scale=rng.uniform(.2,1.2,len(old.feature_scale)),
                economy_head=replace(old.economy_head,
                    coefficients=rng.normal(0,.01,old.economy_head.coefficients.shape),
                    feature_mean=rng.uniform(.1,.9,len(old.economy_head.feature_mean)),
                    feature_scale=rng.uniform(.2,1.2,len(old.economy_head.feature_scale))))
    new=upgrade_option_value_model_for_capture_invocation(old)
    ctx=replace(_context(),economy_snapshot=EconomySnapshot(1000,()),target_cash=500)
    plain=candidate();enriched=replace(plain,capture_invocation=OptionCaptureInvocation(500,True))
    menu=LivingDexOptionMenu(ctx,(enriched,replace(plain,binding_ref="other")))
    np.testing.assert_allclose(new.predict_candidate(ctx,enriched).vector(),old.predict_candidate(ctx,plain).vector(),rtol=0,atol=1e-14)
    assert new.predict_economy_candidate(ctx,enriched)==old.predict_economy_candidate(ctx,plain)
    diagnostic=new.diagnose_menu(menu,DEFAULT_LIVING_DEX_GOAL_UTILITY,selected_index=0)
    assert diagnostic is not None


@pytest.mark.parametrize("field,value",[("schema","pokemon.core.living-dex-option-value-model.v11"),
                                      ("normalization","pokemon.core.living-dex-option-normalization.v11")])
def test_v12_model_codec_rejects_old_schema_claim(field,value):
    doc=upgrade_option_value_model_for_capture_invocation(model()).to_dict();doc[field]=value
    with pytest.raises(ValueError):LivingDexOptionValueModel.from_dict(doc)


def test_v12_model_codec_rejects_changed_feature_names():
    doc=upgrade_option_value_model_for_capture_invocation(model()).to_dict();doc["feature_names"][-1]="observed_success"
    with pytest.raises(ValueError):LivingDexOptionValueModel.from_dict(doc)
