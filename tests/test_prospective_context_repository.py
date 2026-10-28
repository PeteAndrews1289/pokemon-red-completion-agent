"""Synthetic dispatch/codec fixtures; zero fitting or native execution evidence."""
from pathlib import Path
from dataclasses import replace
import copy,json,hashlib
import numpy as np
import pytest
from pokemon_red_completion.player_consequence_projection import (PROSPECTIVE_CONTEXT,PROSPECTIVE_READINESS_NAMES,SHARED_CONTEXT,consequence_feature_names,project_consequence_features,consequence_normalization_scale)
from pokemon_red_completion.living_dex_option_value import option_feature_names,LivingDexOptionValueModel,LivingDexOptionKind
from pokemon_red_completion.player_challenge_consequence import ChallengeConsequenceHead,PROGRESS_TARGET_NAMES
from pokemon_red_completion.provenance import canonical_sha256
RAW=option_feature_names(15)
def head(prefer='kind.develop'):
    names=consequence_feature_names(15,PROSPECTIVE_CONTEXT);w=np.zeros((len(names),9));w[names.index(prefer),:2]=1.
    return ChallengeConsequenceHead(w,np.zeros(9),np.zeros(len(names)),np.ones(len(names)),'a'*64,2,1.,'native_train',feedback_version=2,feature_version=15,context_projection=PROSPECTIVE_CONTEXT)
def test_named_v15_projection_keeps_exact_declared_current_facts():
    names=consequence_feature_names(15,PROSPECTIVE_CONTEXT)
    assert len(RAW)==506 and len(names)==317 and len(set(names))==317
    assert all(not any(x in n for x in ('recent.','budget.','current.median_combat_level_gap','current.lowest_combat_level_gap')) for n in names)
    for suffix in PROSPECTIVE_READINESS_NAMES:assert 'readiness.unlock_access_x_'+suffix in names
    for prefix in ('challenge.','matchup.','preparation.','level_workload.','kind.','economy_'):
        assert tuple(n for n in names if n.startswith(prefix))==tuple(n for n in RAW if n.startswith(prefix))
    raw=tuple(float(i) for i in range(506));projected=project_consequence_features(raw,feature_version=15,context_projection=PROSPECTIVE_CONTEXT)
    assert projected==tuple(raw[RAW.index(n)] for n in names)
@pytest.mark.parametrize('version',[7,9,10,11,14,16])
def test_prospective_rejects_every_other_raw_version(version):
    with pytest.raises(ValueError):consequence_feature_names(version,PROSPECTIVE_CONTEXT)
@pytest.mark.parametrize('width',[317,468,540,505,507])
def test_predict_requires_full_raw_v15_input_not_projected_or_shortened(width):
    with pytest.raises(ValueError):head().predict((0.,)*width)
def test_history_gaps_and_administrative_budget_cannot_change_prediction():
    h=head();before=[0.]*506;before[RAW.index('kind.develop')]=1.
    after=before.copy();kept=set(consequence_feature_names(15,PROSPECTIVE_CONTEXT))
    excluded=[i for i,n in enumerate(RAW) if n not in kept]
    assert len(excluded)==189
    for i in excluded:after[i]=.75
    assert project_consequence_features(before,feature_version=15,context_projection=PROSPECTIVE_CONTEXT)==project_consequence_features(after,feature_version=15,context_projection=PROSPECTIVE_CONTEXT)
    assert h.predict(before)==h.predict(after)
@pytest.mark.parametrize('field',['challenge.unlock_access_x_opposition_known','readiness.unlock_access_x_current.hp_fraction','readiness.unlock_access_x_current.pp_fraction','readiness.unlock_access_x_current.combat_level_spread','matchup.own.attack.mean','preparation.remaining_xp','level_workload.remaining_xp'])
def test_retained_observations_remain_effective_inputs(field):
    names=consequence_feature_names(15,PROSPECTIVE_CONTEXT);assert field in names
    w=np.zeros((len(names),9));w[names.index(field),:2]=1.
    h=ChallengeConsequenceHead(w,np.zeros(9),np.zeros(len(names)),np.ones(len(names)),'a'*64,2,1.,'synthetic',feedback_version=2,feature_version=15,context_projection=PROSPECTIVE_CONTEXT)
    a=[0.]*506;b=a.copy();b[RAW.index(field)]=.4
    assert h.predict(a)!=h.predict(b)
def test_prospective_uses_existing_std_normalization_without_shared_geometry():
    x=np.array([[0.]*317,[.4]*317]);scale=consequence_normalization_scale(x,feature_version=15,context_projection=PROSPECTIVE_CONTEXT)
    assert np.allclose(scale,x.std(axis=0))
    assert np.array_equal(consequence_normalization_scale(np.zeros((2,317)),feature_version=15,context_projection=PROSPECTIVE_CONTEXT),np.ones(317))
def test_explicit_projection_metadata_and_inference_roundtrip():
    h=head();d=h.document();assert d['schema']=='pokemon.player.challenge-consequence-head.v8'
    assert d['context_projection']==PROSPECTIVE_CONTEXT
    assert d['context_projection_parameters']['raw_feature_width']==506
    assert d['context_projection_parameters']['selected_indices']==[RAW.index(n) for n in d['feature_names']]
    restored=ChallengeConsequenceHead.from_document(d,expected_sha256=h.model_sha256)
    x=[0.]*506;x[RAW.index('kind.develop')]=1.
    assert restored.predict(x)==h.predict(x)
@pytest.mark.parametrize('fault',['indices','readiness_names','raw_version','normalization','feature_names','identity_mode','shared_mode','unknown_mode'])
def test_rehashed_projection_metadata_or_identity_tampering_is_rejected(fault):
    d=copy.deepcopy(head().document());p=d['context_projection_parameters']
    if fault=='indices':p['selected_indices'][0]=505
    elif fault=='readiness_names':p['retained_readiness_names'].append('recent.won')
    elif fault=='raw_version':p['raw_feature_version']=10
    elif fault=='normalization':p['normalization']='shared_geometry'
    elif fault=='feature_names':d['feature_names'][0]='future.stats'
    elif fault=='identity_mode':d['context_projection']='identity'
    elif fault=='shared_mode':d['context_projection']=SHARED_CONTEXT
    else:d['context_projection']='visible_preparation_spine_v2'
    with pytest.raises(ValueError):ChallengeConsequenceHead.from_document(d,expected_sha256=canonical_sha256(d))
def test_actual_existing_native_parent_child_consumer_uses_projected_head(tmp_path,monkeypatch):
    from test_consequence_v15_vertical import unbound_hierarchy_args
    import pokemon_red_completion.red_consequence_choice as composition
    import pokemon_red_completion.red_native_player as native
    from pokemon_red_completion.goal_manager import GoalKind
    args,state=unbound_hierarchy_args(tmp_path,monkeypatch);args['consequence_head']=head()
    monkeypatch.setattr(LivingDexOptionValueModel,'scores',lambda self,menu,utility:tuple(float(c.challenge is not None and c.challenge.combat_required) if i in menu.available_indices else None for i,c in enumerate(menu.candidates)))
    choices=[];select=composition.select_branch_recovery_live_option
    def capture(*a,**kw):
        c=select(*a,**kw);choices.append(c);return c
    monkeypatch.setattr(composition,'select_branch_recovery_live_option',capture)
    result=native.run_native_continuous_player(**args)
    assert result['executed_decisions']==1 and result['strategic_policy_queries']==2 and state['trained'] and not state['challenge']
    c=choices[0];assert c.branch_recovery.child is not None
    assert c.branch_recovery.parent.selected_binding.kind is GoalKind.ADVANCE_STORY
    assert c.selected_binding.kind is GoalKind.DEVELOP_TEAM
    rawdose=c.options.menu.candidates[c.selected_candidate_index];assert rawdose.challenge is None
    assert len(c.options.menu.candidate_vector(c.selected_candidate_index,feature_version=15))==506
    plan=json.loads((args['output']/'native-plan.json').read_bytes());assert plan['consequence_feature_version']==15
    assert not args['emulator'].pressed_buttons

def test_actual_launcher_decoder_accepts_only_pinned_native_train_projected_head(tmp_path):
    import importlib.util
    file=(Path(__file__).resolve().parents[1] / 'scripts/run_configured_red_player.py')
    spec=importlib.util.spec_from_file_location('projectionlauncher',file);launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
    h=head();path=tmp_path/'head.json';path.write_text(json.dumps(h.document()))
    plan=dict(partition='development',objectives=['defeat_misty'],goal_selection=dict(mode='greedy',reason='synthetic codec dispatch gate'),readiness_refinement=dict(objective_ref='defeat_misty',head_path=str(path),head_sha256=h.model_sha256,content_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),reason='synthetic dispatch only',defer_unbound_preparation=True,allow_singleton_parent_support=True))
    result=launcher.declared_readiness_refinement(plan)
    assert result['consequence_head'].context_projection==PROSPECTIVE_CONTEXT
    bad=copy.deepcopy(plan);bad['readiness_refinement']['content_sha256']='f'*64
    with pytest.raises(ValueError):launcher.declared_readiness_refinement(bad)
    bad=copy.deepcopy(plan);bad['partition']='train'
    with pytest.raises(ValueError):launcher.declared_readiness_refinement(bad)

def test_identity_and_shared_names_projection_normalization_metadata_exact_against_baseline():
    import importlib.util
    path=(Path(__file__).resolve().parents[1] / 'src/pokemon_red_completion/player_consequence_projection.py')
    spec=importlib.util.spec_from_file_location('pokemon_red_completion._legacy_projection_baseline',path);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    for version in (7,9,10,11,15):
        for mode in ('identity',SHARED_CONTEXT):
            if mode==SHARED_CONTEXT and version not in (10,15):continue
            raw=tuple(float(i%7)/7 for i in range(len(option_feature_names(version))))
            assert consequence_feature_names(version,mode)==old.consequence_feature_names(version,mode)
            projected=project_consequence_features(raw,feature_version=version,context_projection=mode)
            assert projected==old.project_consequence_features(raw,feature_version=version,context_projection=mode)
            x=np.array([projected,tuple(v*.9 for v in projected),projected])
            assert np.array_equal(consequence_normalization_scale(x,feature_version=version,context_projection=mode),old.consequence_normalization_scale(x,feature_version=version,context_projection=mode))
            from pokemon_red_completion.player_consequence_projection import context_projection_metadata
            assert context_projection_metadata(mode)==old.context_projection_metadata(mode)

def test_all_actual_cash_and_economy_cost_columns_survive_exactly():
    names=consequence_feature_names(15,PROSPECTIVE_CONTEXT)
    cash=tuple(n for n in RAW if any(part in n for part in ('cash','afford','cost','workload')) and not n.startswith('readiness.'))
    assert cash and all(n in names for n in cash)

def test_actual_choice_receipt_invariant_to_typed_history_gap_and_budget_changes(tmp_path,monkeypatch):
    from test_native_challenge_consequence import harness,session
    from test_consequence_v15_vertical import upgrade_args
    from pokemon_red_completion.player_readiness import CONTEXT_NAMES,BUDGET_NAMES
    from pokemon_red_completion.red_consequence_choice import choose_consequence_binding
    args,_=harness(tmp_path,monkeypatch);upgrade_args(args);options=session(args).observe(0)
    h=head();before,before_receipt=choose_consequence_binding(options,h,challenge_refs=('same',)*len(options.bindings))
    candidates=[]
    for c in options.menu.candidates:
        r=c.readiness;assert r is not None
        facts=dict(zip((*CONTEXT_NAMES,*BUDGET_NAMES),r.values,strict=True))
        facts.update({'recent.won':1.,'recent.lost':0.,'recent.unresolved':0.,'current.median_combat_level_gap':.2,'current.lowest_combat_level_gap':.3})
        facts.update({n:.25 for n in BUDGET_NAMES})
        candidates.append(replace(c,readiness=replace(r,values=tuple(facts[n] for n in (*CONTEXT_NAMES,*BUDGET_NAMES)),history_observed=True)))
    changed=replace(options,menu=replace(options.menu,candidates=tuple(candidates)))
    after,after_receipt=choose_consequence_binding(changed,h,challenge_refs=('same',)*len(options.bindings))
    assert options.menu.policy_sha256!=changed.menu.policy_sha256
    assert before is after and before_receipt['scores']==after_receipt['scores']
    for i in options.menu.available_indices:
        a=options.menu.candidate_vector(i,feature_version=15);b=changed.menu.candidate_vector(i,feature_version=15)
        assert len(a)==len(b)==506 and a!=b
        assert project_consequence_features(a,feature_version=15,context_projection=PROSPECTIVE_CONTEXT)==project_consequence_features(b,feature_version=15,context_projection=PROSPECTIVE_CONTEXT)
    assert not args['emulator'].pressed_buttons and args['emulator'].frame_count==0
