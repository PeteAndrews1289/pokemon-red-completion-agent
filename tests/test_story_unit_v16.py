"""ROM-free interface checks; no fitted weights or native evidence."""
from dataclasses import replace
import copy
import pytest
from pokemon_red_completion.player_option_story_unit import (
    OptionStoryUnit, story_unit_vector, story_unit_from_vector, STORY_UNIT_FEATURE_NAMES,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionCandidate, LivingDexOptionFeatures, LivingDexOptionContext,
    LivingDexOptionKind, LivingDexOptionAvailability, LivingDexOptionMenu,
    option_feature_names, curriculum_features,
)
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification, GoalManagerRuntimeError
from pokemon_red_completion.red_native_curriculum import (
    SCOPED_STORY_UNIT_CONTRACT, SCOPED_STORY_UNIT_PLAN_SCHEMA, SCOPED_STORY_UNIT_OUTCOME_SCHEMA,
    curriculum_projection, reconstruct_native_curriculum,
)
from pokemon_red_completion.provenance import canonical_sha256

def candidate():
    return LivingDexOptionCandidate("private-id", LivingDexOptionFeatures(
        LivingDexOptionKind.UNLOCK_ACCESS,0.,.5,0.,.02,0.,0.,.15,0.,0.),
        LivingDexOptionAvailability.AVAILABLE)

def context():
    return LivingDexOptionContext(.1,.2,.3,.4,.5,.6,.7)

@pytest.mark.parametrize("mode", ["movement","interaction"])
@pytest.mark.parametrize("further", [False,True])
def test_scope_roundtrip_and_append_only(mode,further):
    unit=OptionStoryUnit(mode,further)
    assert OptionStoryUnit.from_public(unit.public_dict())==unit
    assert story_unit_from_vector(story_unit_vector(unit))==unit
    old=candidate();new=replace(old,story_unit=unit)
    assert new.vector(context(),feature_version=16)[:-4]==old.vector(context(),feature_version=15)
    assert option_feature_names(16)==(*option_feature_names(15),*STORY_UNIT_FEATURE_NAMES)
    with pytest.raises(ValueError):
        new.vector(context(),feature_version=15)
    menu=LivingDexOptionMenu(context(),(new,replace(old,binding_ref="comparison")))
    doc=menu.policy_dict()
    assert restore_living_dex_policy_menu(doc,binding_refs=("private-id","comparison")).policy_dict()==doc
    assert "private-id" not in str(doc)

def test_unknown_is_not_terminal_or_movement():
    assert story_unit_vector(None)==(0.,0.,0.,0.)
    assert candidate().vector(context(),feature_version=16)[-4:]==(0.,0.,0.,0.)
    assert story_unit_vector(OptionStoryUnit("movement",False))==(1.,1.,0.,0.)
    old=LivingDexOptionMenu(context(),(candidate(),replace(candidate(),binding_ref="comparison")))
    assert "story_unit" not in str(old.policy_dict())
    assert restore_living_dex_policy_menu(old.policy_dict()).policy_dict()==old.policy_dict()

@pytest.mark.parametrize("mode,further", [("secret-key",True),(17,True),("movement",1),("movement",None)])
def test_bad_descriptor_refused(mode,further):
    with pytest.raises(ValueError):OptionStoryUnit(mode,further)

@pytest.mark.parametrize("vector", [(1.,0.,0.,1.),(1.,1.,1.,0.),(0.,1.,0.,0.),(1.,1.,0.,.5)])
def test_bad_vector_refused(vector):
    with pytest.raises(ValueError):story_unit_from_vector(vector)

def test_scope_must_match_private_execution_and_story_kind():
    args=("private",GoalKind.ADVANCE_STORY,.1,.1,lambda:GoalExecutionReport(1,1,{}),
          lambda _:GoalVerification.succeeded())
    good=ExecutableGoalBinding(*args,story_objective_ref="hidden",story_approach_only=True,
                               story_unit=OptionStoryUnit("movement",True))
    assert good.story_unit.requires_further_selected_unit
    with pytest.raises(GoalManagerRuntimeError):replace(good,story_approach_only=False)
    with pytest.raises(GoalManagerRuntimeError):replace(good,kind=GoalKind.RESTORE_TEAM)
    with pytest.raises(GoalManagerRuntimeError):replace(good,story_objective_ref=None)
    with pytest.raises(ValueError):replace(candidate(),features=replace(candidate().features,kind=LivingDexOptionKind.ACQUIRE),story_unit=good.story_unit)

@pytest.mark.parametrize("mode",["movement","interaction"])
def test_v11_true_unit_scope_exact_projection_and_no_fake_completion(tmp_path,mode):
    from test_red_story_approach_curriculum import approach_records
    plan,result=approach_records(tmp_path)
    oldrow=reconstruct_native_curriculum(plan,result)
    assert oldrow.feature_version==6
    assert curriculum_features(oldrow,16)[-4:]==(0.,0.,0.,0.)
    plan.update(schema=SCOPED_STORY_UNIT_PLAN_SCHEMA,contract=SCOPED_STORY_UNIT_CONTRACT,
                story_unit_scope=OptionStoryUnit(mode,True).public_dict())
    result.update(schema=SCOPED_STORY_UNIT_OUTCOME_SCHEMA,declaration_sha256=canonical_sha256(plan))
    row=reconstruct_native_curriculum(plan,result)
    assert row.feature_version==16
    assert row.features[:-4]==curriculum_features(oldrow,15)
    assert row.features[-4:]==story_unit_vector(OptionStoryUnit(mode,True))
    assert row.outcome==oldrow.outcome
    assert row.outcome.completion_gain==row.outcome.dependency_unlock_gain==0
    assert curriculum_projection(plan)[1].story_unit==OptionStoryUnit(mode,True)
    bad=copy.deepcopy(plan);bad["story_approach_only"]=False
    with pytest.raises(ValueError):curriculum_projection(bad)

def test_real_recorder_selects_v11_from_actual_binding(tmp_path,monkeypatch):
    from test_red_story_approach_curriculum import recorder_fixture
    from pokemon_red_completion.red_player_lesson_runtime import record_native_player_lesson
    store,emulator,kwargs=recorder_fixture(tmp_path,monkeypatch)
    prior=kwargs["enumerate_bindings"]
    def enumerate_bindings(*args):
        bindings=prior(*args)
        return replace(bindings,bindings=tuple(
            replace(b,story_objective_ref="private-test",story_unit=OptionStoryUnit("interaction",True))
            for b in bindings.bindings))
    kwargs["enumerate_bindings"]=enumerate_bindings
    # The recorder uses the actual selected binding; this synthetic mock fixture opens no backend.
    preflight=record_native_player_lesson(store,**kwargs,preflight_only=True)
    assert preflight["declaration"]["schema"]==SCOPED_STORY_UNIT_PLAN_SCHEMA
    result=record_native_player_lesson(store,**kwargs)
    assert result["admitted"] and result["succeeded"]


def test_zero_extension_changes_no_existing_parameters_or_record():
    import numpy as np
    from pokemon_red_completion.living_dex_option_value import (
        LivingDexOptionValueModel, upgrade_option_value_model_for_story_unit,
    )
    width=len(option_feature_names(15))
    baseline=LivingDexOptionValueModel(
        coefficients=np.zeros((width,9)),intercept=np.arange(9,dtype=float)/10,
        feature_mean=np.zeros(width),feature_scale=np.ones(width),
        train_dataset_sha256="a"*64,settled_examples=2,censored_examples=0,
        ridge=.25,maximum_importance_weight=1.,feature_version=15,
    )
    old=baseline.to_dict();candidate_model=upgrade_option_value_model_for_story_unit(baseline)
    assert candidate_model.feature_version==16 and baseline.to_dict()==old
    assert np.array_equal(candidate_model.coefficients[:width],baseline.coefficients)
    assert not candidate_model.coefficients[width:].any()
    assert not candidate_model.feature_mean[width:].any()
    assert (candidate_model.feature_scale[width:]==1).all()
    assert candidate_model.to_dict()==LivingDexOptionValueModel.from_dict(candidate_model.to_dict()).to_dict()
    assert upgrade_option_value_model_for_story_unit(candidate_model) is candidate_model

def test_scope_live_menu_and_native_recorder_projection_match(tmp_path):
    from test_red_story_approach_curriculum import approach_records
    from pokemon_red_completion.goal_manager import GoalManagerQuestion
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
    from pokemon_red_completion.player_option_challenge import OptionChallenge
    from pokemon_red_completion.player_readiness import PlayerReadiness
    from pokemon_red_completion.red_live_option_menu import build_red_live_option_set,supplemental_live_option
    from pokemon_red_completion.red_player_economy import restore_snapshot
    plan,result=approach_records(tmp_path)
    unit=OptionStoryUnit("movement",True)
    plan.update(schema=SCOPED_STORY_UNIT_PLAN_SCHEMA,contract=SCOPED_STORY_UNIT_CONTRACT,
                story_unit_scope=unit.public_dict())
    question=GoalManagerQuestion.from_policy_input(plan["question"])
    old=question.opportunities[plan["selected_index"]]
    binding=ExecutableGoalBinding(old.binding_ref,old.kind,old.estimated_effort,old.estimated_risk,
        lambda:GoalExecutionReport(0,0,{}),lambda _:GoalVerification.succeeded(),
        story_objective_ref="private-objective",story_approach_only=True,story_unit=unit)
    other=replace(binding,binding_ref="private-other",story_unit=OptionStoryUnit("interaction",True))
    readiness=PlayerReadiness.from_public(plan["readiness"])
    extra=project_living_dex_goal_candidate(question,plan["selected_index"],feature_version=16,
        binding_ref=other.binding_ref,readiness=readiness)
    challenge=OptionChallenge.from_public(plan["challenge"])
    options=build_red_live_option_set(situation=question.situation,
        binding_set=GoalBindingSet(question.opportunities,(binding,)),
        supplements=(supplemental_live_option(other,extra),),readiness=readiness,
        challenges={binding.binding_ref:challenge,other.binding_ref:challenge},
        model_feature_version=16,ordering_seed_sha256="f"*64,
        economy_snapshot=restore_snapshot(plan["economy_before"]),target_cash=plan["target_cash"])
    context_,projected=curriculum_projection(plan)
    ix=next(i for i,b in enumerate(options.bindings) if b.binding_ref==binding.binding_ref)
    assert options.menu.candidate_vector(ix,feature_version=16)==projected.vector(context_,feature_version=16)
    assert options.menu.feature_version==16
