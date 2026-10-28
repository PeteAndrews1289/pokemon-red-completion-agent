"""ROM-free collector compatibility; no fit, emulator, or native evidence."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import pytest
from test_consequence_workload_v9 import workload_documents,upgraded_head
from test_native_challenge_consequence import harness,session
from test_red_consequence_choice import progress_head
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import upgrade_option_value_model_for_level_workload
from pokemon_red_completion.provenance import canonical_sha256
import pokemon_red_completion.red_challenge_consequence as consequence


def unpreviewed_documents(tmp_path,monkeypatch):
    plan,phases,menu,old=workload_documents(tmp_path,monkeypatch)
    raw=replace(menu,candidates=(replace(menu.candidates[0],challenge=None),*menu.candidates[1:]))
    plan['menu']=raw.policy_dict()
    return plan,phases,raw


def test_raw_none_collects_without_changing_any_input_or_vector(tmp_path,monkeypatch):
    plan,phases,raw=unpreviewed_documents(tmp_path,monkeypatch)
    saved=deepcopy(plan);digest=canonical_sha256(plan['menu'])
    row=consequence.project_consequence(plan,phases)
    assert row.features==raw.candidate_vector(0,feature_version=9)
    assert plan==saved and canonical_sha256(plan['menu'])==digest
    assert raw.candidates[0].challenge is None and 'challenge'not in plan['menu']['candidates'][0]
    from pokemon_red_completion.living_dex_option_value import option_feature_names
    names=option_feature_names(9)
    assert all(row.features[i]==0 for i,name in enumerate(names)if name.startswith('challenge.'))
    assert row.outcome.actions==120 and row.outcome.frames==7000


@pytest.mark.parametrize('fault',['member','target_level','missing_target','workload','preparation','source_partition','leading_input'])
def test_missing_preview_does_not_relax_native_dose_or_source_guards(tmp_path,monkeypatch,fault):
    plan,phases,raw=unpreviewed_documents(tmp_path,monkeypatch)
    if fault=='member':plan['spec']['preparation_target']['specimen_ref']='absent-member'
    elif fault=='target_level':plan['spec']['preparation_target']['level']+=1
    elif fault=='missing_target':plan['spec']['preparation_target']=None
    elif fault=='workload':
        first=raw.candidates[0]
        raw=replace(raw,candidates=(replace(first,level_workload=replace(first.level_workload,remaining_xp=first.level_workload.remaining_xp+1)),*raw.candidates[1:]))
        plan['menu']=raw.policy_dict()
    elif fault=='preparation':
        raw=replace(raw,candidates=(replace(raw.candidates[0],preparation=None),*raw.candidates[1:]))
        plan['menu']=raw.policy_dict()
    elif fault=='source_partition':plan['source']['partition']='development'
    elif fault=='leading_input':plan['before']['actions']=1
    with pytest.raises(ValueError):consequence.project_consequence(plan,phases)


@pytest.mark.parametrize('kind',[GoalKind.ADVANCE_STORY,GoalKind.RESTORE_TEAM])
def test_other_action_families_keep_missing_preview_refusal(tmp_path,monkeypatch,kind):
    plan,phases,raw=unpreviewed_documents(tmp_path,monkeypatch)
    spec=consequence.ChallengeConsequenceSpec(kind,dict(kind='events',map_id=0,events=[1]))
    assert not consequence._has_challenge_or_member_preparation_target(spec,raw.candidates[0],feature_version=9)


def test_legacy_feature_contract_still_requires_preview(tmp_path,monkeypatch):
    from test_challenge_consequence import documents
    plan,phases,menu=documents(tmp_path,monkeypatch)
    menu=replace(menu,candidates=(replace(menu.candidates[0],challenge=None),*menu.candidates[1:]))
    plan['menu']=menu.policy_dict()
    with pytest.raises(ValueError):consequence.project_consequence(plan,phases)


def test_machine_and_hybrid_descriptors_do_not_borrow_member_gate(tmp_path,monkeypatch):
    plan,_,raw=unpreviewed_documents(tmp_path,monkeypatch)
    spec=consequence.ChallengeConsequenceSpec.from_document(plan['spec'])
    fake=SimpleNamespace(challenge=None,features=raw.candidates[0].features,
        preparation=raw.candidates[0].preparation,level_workload=raw.candidates[0].level_workload,
        move_change=object())
    assert not consequence._has_challenge_or_member_preparation_target(spec,fake,feature_version=9)
    changed=SimpleNamespace(initial_kind=GoalKind.DEVELOP_TEAM,preparation_target=None,machine_lesson={})
    assert not consequence._has_challenge_or_member_preparation_target(changed,raw.candidates[0],feature_version=9)


@pytest.mark.parametrize('fault',[None,'win','dose_failed','exception'])
def test_real_recorder_begin_and_sealed_readback_keep_raw_none(tmp_path,monkeypatch,fault):
    args,state=harness(tmp_path,monkeypatch,fault=fault)
    args['model']=upgrade_option_value_model_for_level_workload(args['model'])
    old=args['observe_challenges']
    args['observe_challenges']=lambda rt,bindings,*rest:{k:v for k,v in old(rt,bindings,*rest).items()if k!='train'}
    s=session(args);options=s.observe(0)
    train=next(b for b in options.bindings if b.kind is GoalKind.DEVELOP_TEAM)
    index=options.bindings.index(train);raw=options.menu.policy_dict();vector=options.menu.candidate_vector(index,feature_version=9)
    pre=s.consequence.begin(options,train,preflight_only=True)
    assert pre['menu']==raw and options.menu.candidates[index].challenge is None
    assert args['emulator'].frame_count==0 and not s.recorder.trace
    if fault=='exception':
        with pytest.raises(RuntimeError):train.execute()
    else:
        train.verify(train.execute())
        if fault!='dose_failed':
            next_options=s.observe(1);story=next(b for b in next_options.bindings if b.kind is GoalKind.ADVANCE_STORY)
            story.verify(story.execute())
    result=s.consequence.finish()
    row=consequence.load_challenge_consequence(args['store'],declaration_sha256=result['declaration_sha256'],result_sha256=canonical_sha256(result))
    assert s.consequence.plan['menu']==raw and row.features==vector
    assert not args['emulator'].pressed_buttons
    if fault=='exception':assert row.outcome is None and row.censor_reason
    else:assert row.outcome.completed is (fault=='win') and row.outcome.actions==(2 if fault=='dose_failed' else 3)


def test_existing_inference_head_is_deliberately_not_extended(tmp_path,monkeypatch):
    _,_,raw=unpreviewed_documents(tmp_path,monkeypatch)
    head=upgraded_head(progress_head())
    with pytest.raises(ValueError):head.scores(raw,challenge_refs=('same',)*len(raw.candidates))
