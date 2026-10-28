"""ROM-free V11 projection/runtime regressions; no native learning evidence."""
from dataclasses import replace
import copy
import numpy as np
import pytest
from test_move_change_v10 import change, candidate, model, _context, _settled
from test_machine_consequence_runtime_v10 import machine_options, v10_head
from test_red_consequence_choice import provisional_args
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCurriculumOutcomeExample, LivingDexOptionValueModel,
    curriculum_features, option_feature_names, project_move_context_features,
    upgrade_option_value_model_for_move_change, upgrade_option_value_model_for_move_context,
)
from pokemon_red_completion.player_option_move_change import (
    move_change_vector, move_context_from_v10, move_context_feature_names,
)
from pokemon_red_completion.player_challenge_consequence import (
    ChallengeConsequence, ChallengeConsequenceHead, ConsequenceExample,
    fit_challenge_consequence,
)
from pokemon_red_completion.provenance import canonical_sha256


def context_head():
    old=v10_head()
    return replace(old,feature_version=11,
        coefficients=np.vstack((old.coefficients,np.zeros((2,len(old.intercept))))),
        feature_mean=np.append(old.feature_mean,[0.,0.]),
        feature_scale=np.append(old.feature_scale,[1.,1.]))


@pytest.mark.parametrize('old',[0,39,44,55])
def test_recorded_projection_matches_runtime_and_preserves_v10_prefix(old):
    facts=change(old,recipient_attack=70,recipient_special_attack=90)
    item=candidate(facts)
    v10=item.vector(_context(),feature_version=10)
    v11=item.vector(_context(),feature_version=11)
    assert len(v10)==468 and len(v11)==470
    assert v11==project_move_context_features(v10)
    assert v11[:468]==v10
    assert option_feature_names(11)[:468]==option_feature_names(10)
    assert all('id' not in n and 'slot' not in n for n in move_context_feature_names())
    expected=(facts.proposed.power/255*facts.proposed.accuracy/1.5*90/190)
    assert v11[-1]==pytest.approx(expected)
    if old in (0,39):assert v11[-2]==0
    elif old==55:assert v11[-2]==pytest.approx(40/255*90/190)
    else:assert v11[-2]==pytest.approx(60/255/1.5*70/170)


def test_unknown_and_absent_mechanics_are_masked_without_inventing_recipient_stats():
    assert move_context_from_v10(move_change_vector(None))==(0.,0.)
    assert move_context_from_v10(change().vector())==(0.,0.)
    with pytest.raises(ValueError):project_move_context_features((0.,)*467)


@pytest.mark.parametrize('economy',[False,True])
def test_v11_zero_extension_retains_parent_scores_counts_evidence_and_economy(economy):
    from pokemon_red_completion.resource_economy_observation import EconomySnapshot
    old=upgrade_option_value_model_for_move_change(model(economy));before=old.to_dict()
    new=upgrade_option_value_model_for_move_context(old)
    assert old.to_dict()==before and new.feature_version==11
    assert new.train_dataset_sha256==old.train_dataset_sha256
    assert (new.settled_examples,new.censored_examples)==(old.settled_examples,old.censored_examples)
    assert np.array_equal(new.coefficients[:468],old.coefficients)
    assert not new.coefficients[468:].any()
    assert upgrade_option_value_model_for_move_context(new) is new
    assert LivingDexOptionValueModel.from_dict(new.to_dict()).to_dict()==new.to_dict()
    context=replace(_context(),economy_snapshot=EconomySnapshot(100,()),target_cash=500)
    for item in [candidate(),candidate(change(55,recipient_attack=100,recipient_special_attack=120)),candidate(change(39))]:
        np.testing.assert_allclose(new.predict_candidate(context,item).vector(),old.predict_candidate(context,item).vector(),rtol=0,atol=1e-14)
        assert new.predict_economy_candidate(context,item)==old.predict_economy_candidate(context,item)


@pytest.mark.parametrize('version',[9,10])
def test_curriculum_projection_preserves_original_record_identity(version):
    item=candidate(change(55,recipient_attack=100,recipient_special_attack=120)) if version==10 else candidate()
    row=LivingDexCurriculumOutcomeExample('f'*64,'train',version,item.vector(_context(),feature_version=version),_settled(success=True,completion=0,unlock=0,action_cost=.1))
    before=copy.deepcopy(row.public_dict());digest=canonical_sha256(before)
    projected=curriculum_features(row,11)
    assert projected==project_move_context_features(curriculum_features(row,10))
    assert row.public_dict()==before and canonical_sha256(row.public_dict())==digest
    assert (projected[-1]>0)==(version==10)


def rows_for_projection():
    rows=[]
    for i,stats in enumerate([(50,60),(100,120)]):
        features=candidate(change(55,recipient_attack=stats[0],recipient_special_attack=stats[1])).vector(_context(),feature_version=10)
        outcome=ChallengeConsequence(True,bool(i),100+i,200+i,0,0,0,feedback_version=2,initial_goal_failed=False,challenge_progress=float(i))
        rows.append(ConsequenceExample(str(i+1)*64,'f'*64,features,outcome,None,feedback_version=2,feature_version=10))
    return rows


def test_fit_derives_nonzero_observed_products_and_keeps_evidence_identity():
    rows=rows_for_projection();before=[r.document() for r in rows]
    head=fit_challenge_consequence(rows,feature_version=11,feedback_version=2)
    expected=np.asarray([project_move_context_features(r.features) for r in rows])
    np.testing.assert_array_equal(head.feature_mean,expected.mean(axis=0))
    assert np.all(head.feature_mean[-2:]>0) and np.any(head.coefficients[-2:])
    assert head.evidence_sha256==canonical_sha256(before)
    assert [r.document() for r in rows]==before
    assert all(r.feature_version==10 for r in rows)


def test_raw_v11_consequence_rows_are_rejected_instead_of_misserialized():
    row=rows_for_projection()[0]
    with pytest.raises(ValueError,match='raw V11 rows'):
        replace(row,feature_version=11,features=project_move_context_features(row.features))


def test_two_products_can_represent_a_context_dependent_pair_order_without_identity_features():
    # Constructed coefficients test representational capacity, not a fitted claim.
    small=[candidate(change(move,recipient_attack=50,recipient_special_attack=60)).vector(_context(),feature_version=11) for move in (55,39)]
    large=[candidate(change(move,recipient_attack=100,recipient_special_attack=120)).vector(_context(),feature_version=11) for move in (55,39)]
    names=option_feature_names(11);coef=np.zeros(len(names))
    threshold=(small[0][-2]+large[0][-2])/2
    coef[names.index('move_change.removed.category.special')]=threshold
    coef[-2]=-1
    assert np.dot(coef,np.subtract(small[0],small[1]))>0
    assert np.dot(coef,np.subtract(large[0],large[1]))<0


def test_head_codec_retains_legacy_and_strictly_authenticates_v11_names_schema():
    legacy=v10_head();before=legacy.document();digest=legacy.model_sha256
    assert ChallengeConsequenceHead.from_document(before,expected_sha256=digest).document()==before
    head=context_head();doc=head.document()
    assert doc['schema']=='pokemon.player.challenge-consequence-head.v6'
    assert ChallengeConsequenceHead.from_document(doc,expected_sha256=head.model_sha256).document()==doc
    for field,value in [('schema','pokemon.player.challenge-consequence-head.v5'),('feature_names',doc['feature_names'][:-1])]:
        bad=copy.deepcopy(doc);bad[field]=value
        with pytest.raises(ValueError):ChallengeConsequenceHead.from_document(bad,expected_sha256=canonical_sha256(bad))
    assert legacy.model_sha256==digest and legacy.document()==before


@pytest.mark.parametrize('mode',['ordinary','direct','branch'])
def test_v11_parent_head_reaches_continuous_adapters_with_v10_or_older_menu(tmp_path,monkeypatch,mode):
    import pokemon_red_completion.red_native_player as native
    from test_red_branch_recovery import greedy_native_args
    args,state=(greedy_native_args if mode=='branch' else provisional_args)(tmp_path,monkeypatch)
    args['model']=upgrade_option_value_model_for_move_context(args['model'])
    args['consequence_head']=context_head()
    if mode=='ordinary':
        args.pop('consequence_head');args.pop('consequence_challenge_ref');args['greedy_selection']=True
    monkeypatch.setattr(LivingDexOptionValueModel,'scores',lambda self,observed,utility:tuple(float(c.features.kind.value=='unlock_access') for c in observed.candidates))
    # Prefer challenge in the consequence child as well.
    h=args.get('consequence_head')
    if h is not None:
        coefficients=np.zeros_like(h.coefficients);coefficients[option_feature_names(11).index('kind.unlock_access'),:2]=1
        args['consequence_head']=replace(h,coefficients=coefficients)
    result=native.run_native_continuous_player(**args)
    assert result['executed_decisions']==result['model_decisions']==1
    assert state['challenge'] and not state['trained'] and not args['emulator'].pressed_buttons
    if mode=='branch':assert result['strategic_policy_queries']==2


@pytest.mark.parametrize('fault',[None,'train','synthetic','version','no_scope'])
def test_v11_admission_keeps_development_provenance_and_exact_parent_head_version(tmp_path,monkeypatch,fault):
    import pokemon_red_completion.red_consequence_choice as choice
    args,_=provisional_args(tmp_path,monkeypatch)
    parent=upgrade_option_value_model_for_move_context(args['model']);head=context_head()
    source={**args['source'],'experiment_sha256':'b'*64};scope='private-combat-goal'
    if fault=='train':source['partition']='train'
    elif fault=='synthetic':head=replace(head,provenance='synthetic')
    elif fault=='version':parent=upgrade_option_value_model_for_move_change(args['model'])
    elif fault=='no_scope':scope=''
    kwargs=dict(allow=True,greedy_selection=True,source=source,model=parent,head=head,objective_ref=scope,challenge_ref='same',refine_preparation=True)
    if fault is None:choice.validate_greedy_branch_recovery_scope(**kwargs)
    else:
        with pytest.raises(ValueError):choice.validate_greedy_branch_recovery_scope(**kwargs)
    assert args['emulator'].frame_count==0


def test_v11_scores_real_owned_machine_menu_without_changing_public_v10_identity(tmp_path,monkeypatch):
    import pokemon_red_completion.red_consequence_choice as choice
    options,story,machine,rt,inputs=machine_options(tmp_path,monkeypatch)
    indices=(story,machine,machine+1)
    subset=replace(options,bindings=tuple(options.binding(i) for i in indices),menu=replace(options.menu,candidates=tuple(options.menu.candidates[i] for i in indices)),ordinary_binding_refs=options.ordinary_binding_refs & {options.binding(i).binding_ref for i in indices})
    before=subset.menu.policy_dict();assert subset.menu.feature_version==10
    binding,receipt=choice.choose_consequence_binding(subset,context_head(),challenge_refs=('one',)*3)
    assert binding is options.binding(machine) and receipt['scores'][1]>receipt['scores'][0]
    assert subset.menu.policy_dict()==before and not inputs and rt.emulator.state==b'source'


@pytest.mark.parametrize('parent_version,head_version',[(11,11),(10,11),(11,10)])
def test_settlement_requires_exact_v11_parent_head_scope(tmp_path,monkeypatch,parent_version,head_version):
    import pokemon_red_completion.red_native_player as native
    args,_=provisional_args(tmp_path,monkeypatch)
    parent=(upgrade_option_value_model_for_move_context if parent_version==11 else upgrade_option_value_model_for_move_change)(args['model'])
    head=context_head() if head_version==11 else v10_head()
    kwargs=dict(allow=True,source=args['source'],model=parent,head=head,objective_ref='one',challenge_ref='one',settlement_requested=True,sequence_horizon=None,sequence_policy=None,consequence_spec=None)
    if parent_version==head_version:assert native.validate_settlement_refinement_scope(**kwargs)
    else:
        with pytest.raises(ValueError):native.validate_settlement_refinement_scope(**kwargs)
    assert args['emulator'].frame_count==0


def test_v11_native_train_recording_rejected_before_inputs(tmp_path,monkeypatch):
    from test_native_challenge_consequence import harness
    import pokemon_red_completion.red_native_player as native
    args,_=harness(tmp_path,monkeypatch)
    args['model']=upgrade_option_value_model_for_move_context(args['model'])
    with pytest.raises(ValueError,match='consequence recording requires'):
        native.run_native_continuous_player(**args)
    assert args['emulator'].frame_count==0 and not args['emulator'].pressed_buttons


def test_v11_configured_assembly_keeps_workload_and_move_fact_inventory(tmp_path):
    from types import SimpleNamespace
    from test_red_player_configuration import config
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    from pokemon_red_completion.red_player_configuration import assemble_configured_player
    from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory
    calls=[];menu=NativeStoryBranchInventory(lambda *_:GoalBindingSet((),()),lambda *_:())
    def assembly(*args,**kwargs):
        calls.append(kwargs);return b'unchanged',None,menu,{}, {'partition':'development'}
    rom=tmp_path/'synthetic.dat';rom.write_bytes(b'fixture')
    result=assemble_configured_player(SimpleNamespace(assembly=assembly,c=SimpleNamespace(ROM=rom)),config(),tmp_path,tmp_path,plan_path=tmp_path/'plan.json',model_feature_version=11)
    assert result[0]==b'unchanged' and calls[0]['include_level_workload']
    assert getattr(menu.enumerate_owned_machines,'move_change_inventory',False)



def test_real_machine_binding_runs_through_v11_native_wrapper(tmp_path,monkeypatch):
    import test_machine_consequence_runtime_v10 as fixture
    original=fixture.v10_head
    def upgraded_head(*args,**kwargs):
        h=original(*args,**kwargs)
        return replace(h,feature_version=11,coefficients=np.vstack((h.coefficients,np.zeros((2,len(h.intercept))))),feature_mean=np.append(h.feature_mean,[0.,0.]),feature_scale=np.append(h.feature_scale,[1.,1.]))
    monkeypatch.setattr(fixture,'v10_head',upgraded_head)
    monkeypatch.setattr(fixture,'upgrade_option_value_model_for_move_change',upgrade_option_value_model_for_move_context)
    fixture.test_real_machine_runs_through_native_branch_wrapper(tmp_path,monkeypatch)
