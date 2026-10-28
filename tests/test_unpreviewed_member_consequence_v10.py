"""Explicit V10 raw-None collector coverage; ROM-free and no fitting."""
from dataclasses import replace
import pytest
from test_unpreviewed_member_consequence import unpreviewed_documents
from test_native_challenge_consequence import harness,session
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import (
    option_feature_names,upgrade_option_value_model_for_level_workload,
    upgrade_option_value_model_for_move_change,
)
from pokemon_red_completion.provenance import canonical_sha256
import pokemon_red_completion.red_challenge_consequence as consequence


def test_v10_projection_keeps_exact_raw_none_features(tmp_path,monkeypatch):
    plan,phases,menu=unpreviewed_documents(tmp_path,monkeypatch)
    plan.update(schema='pokemon.red.challenge-consequence-plan.v7',feature_version=10)
    original=canonical_sha256(plan['menu'])
    row=consequence.project_consequence(plan,phases)
    assert row.feature_version==10 and len(row.features)==len(option_feature_names(10))
    assert row.features==menu.candidate_vector(0,feature_version=10)
    assert canonical_sha256(plan['menu'])==original and menu.candidates[0].challenge is None
    assert row.outcome.actions==120 and row.outcome.frames==7000


@pytest.mark.parametrize('fault',[None,'win'])
def test_v10_real_recorder_and_sealed_loader_keep_raw_none(tmp_path,monkeypatch,fault):
    args,state=harness(tmp_path,monkeypatch,fault=fault)
    args['model']=upgrade_option_value_model_for_move_change(
        upgrade_option_value_model_for_level_workload(args['model']))
    original=args['observe_challenges']
    args['observe_challenges']=lambda rt,bindings,*rest:{
        key:value for key,value in original(rt,bindings,*rest).items()if key!='train'}
    s=session(args);options=s.observe(0)
    train=next(b for b in options.bindings if b.kind is GoalKind.DEVELOP_TEAM)
    index=options.bindings.index(train);raw=options.menu.policy_dict();vector=options.menu.candidate_vector(index,feature_version=10)
    pre=s.consequence.begin(options,train,preflight_only=True)
    assert pre['schema']=='pokemon.red.challenge-consequence-plan.v7' and pre['feature_version']==10
    assert pre['menu']==raw and options.menu.candidates[index].challenge is None
    assert args['emulator'].frame_count==0 and not s.recorder.trace
    train.verify(train.execute())
    later=s.observe(1);story=next(b for b in later.bindings if b.kind is GoalKind.ADVANCE_STORY)
    story.verify(story.execute())
    result=s.consequence.finish()
    row=consequence.load_challenge_consequence(args['store'],
        declaration_sha256=result['declaration_sha256'],result_sha256=canonical_sha256(result))
    assert row.feature_version==10 and row.features==vector and s.consequence.plan['menu']==raw
    assert row.outcome.completed is (fault=='win') and row.outcome.actions==3 and row.outcome.frames==6
    assert not args['emulator'].pressed_buttons
