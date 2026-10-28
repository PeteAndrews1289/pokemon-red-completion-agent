"""Real recorder/consumer composition on a fake port; no fits or ROM inputs."""
import copy
from dataclasses import replace
import pytest
from test_native_challenge_consequence import harness,session
from test_consequence_v15_vertical import upgrade_args,dispatch_head
from test_red_post_battle_strategy import episode
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel
from pokemon_red_completion.provenance import canonical_sha256
import pokemon_red_completion.red_challenge_consequence as recording
import pokemon_red_completion.red_consequence_choice as consumer


def prepared(tmp_path,monkeypatch,*,fault=None):
    args,state=harness(tmp_path,monkeypatch,fault=fault)
    upgrade_args(args)
    args['consequence_spec']=replace(args['consequence_spec'],feedback_version=2)
    enumeration=args['enumerate_bindings']; challenges=args['observe_challenges']
    def bindings(*a):
        bs=enumeration(*a);items=[]
        for b in bs.bindings:
            if b.kind is GoalKind.ADVANCE_STORY:
                execute=b.execute
                def challenge(execute=execute):
                    report=execute()
                    return replace(report,evidence={'battle':{'outcome':'lost','episode':episode()}})
                b=replace(b,execute=challenge,story_objective_ref='private-combat-goal')
            items.append(b)
        return replace(bs,bindings=tuple(items))
    def previews(*a,**kw):
        result=dict(challenges(*a,**kw));result.pop('train',None);return result
    args.update(enumerate_bindings=bindings,observe_challenges=previews)
    s=session(args);options=s.observe(0)
    dose=next(b for b in options.bindings if b.kind is GoalKind.DEVELOP_TEAM)
    parent=next(b for b in options.bindings if b.kind is GoalKind.ADVANCE_STORY)
    return args,state,s,options,dose,parent


def finish_prefix(s,dose):
    dose.verify(dose.execute())
    result=s.consequence.finish()
    assert result['error'] is None
    return result


def test_real_recorder_loader_vector_equals_actual_consumer_child(tmp_path,monkeypatch):
    args,state,s,options,dose,parent=prepared(tmp_path,monkeypatch)
    raw=copy.deepcopy(options.menu.policy_dict())
    monkeypatch.setattr(LivingDexOptionValueModel,'scores',lambda *a:pytest.fail('support parent is not queried'))
    choice=consumer.select_branch_recovery_live_option(args['model'],options,dispatch_head(),
        objective_ref='private-combat-goal',seed=args['seed'],greedy_selection=True,
        defer_unbound_preparation=True,allow_singleton_parent_support=True)
    child=choice.branch_recovery.child
    child_at=next(i for i,b in enumerate(child.options.bindings) if b is dose)
    expected=child.options.menu.candidate_vector(child_at,feature_version=15)
    witness=s.consequence.declare_preparation_parent(options,dose,parent)
    assert witness['authority']=='teacher_supplied_observed_parent' and witness['model_queries']==0
    pre=s.consequence.begin(options,dose,preflight_only=True)
    assert pre['schema']=='pokemon.red.challenge-consequence-plan.v9'
    assert pre['menu']==raw and options.menu.policy_dict()==raw
    assert options.menu.candidates[options.bindings.index(dose)].challenge is None
    dose.verify(dose.execute())
    after=s.observe(1);battle=next(b for b in after.bindings if b.kind is GoalKind.ADVANCE_STORY)
    battle.verify(battle.execute())
    result=s.consequence.finish()
    row=recording.load_challenge_consequence(args['store'],declaration_sha256=result['declaration_sha256'],result_sha256=canonical_sha256(result))
    assert row.features==expected and row.features!=options.menu.candidate_vector(options.bindings.index(dose),feature_version=15)
    assert row.outcome.attempted and not row.outcome.completed
    assert row.outcome.actions==3 and row.outcome.frames==6 and row.outcome.restorations==1
    assert s.consequence.plan['menu']==raw
    assert child.options.menu.candidates[child_at].matchup is None
    assert not args['emulator'].pressed_buttons


@pytest.mark.parametrize('fault',['source','menu','parent_index','parent_ref','dose_ref','dose_index','target','authority','queries','missing','noncombat'])
def test_projector_rejects_changed_private_parent_witness(tmp_path,monkeypatch,fault):
    args,state,s,options,dose,parent=prepared(tmp_path,monkeypatch)
    s.consequence.declare_preparation_parent(options,dose,parent)
    result=finish_prefix(s,dose)
    plan=copy.deepcopy(s.consequence.plan);w=plan['preparation_parent_witness']
    if fault=='source':w['source_state_sha256']='f'*64
    elif fault=='menu':w['menu_sha256']='f'*64
    elif fault=='parent_index':w['parent_index']=w['selected_dose_index']
    elif fault=='parent_ref':w['parent_binding_ref']='foreign-parent'
    elif fault=='dose_ref':w['selected_dose_ref']='foreign-dose'
    elif fault=='dose_index':w['selected_dose_index']=w['parent_index']
    elif fault=='target':w['preparation_target']['level']+=1
    elif fault=='authority':w['authority']='model_selected'
    elif fault=='queries':w['model_queries']=False
    elif fault=='missing':plan['preparation_parent_witness']=None
    else:
        at=w['parent_index'];plan['menu']['candidates'][at]['challenge']['combat_required']=False
        w['menu_sha256']=canonical_sha256(plan['menu'])
    with pytest.raises(ValueError):recording.project_consequence(plan,result['phases'])


@pytest.mark.parametrize('foreign',['dose','parent'])
def test_declaration_requires_exact_observed_objects_before_inputs(tmp_path,monkeypatch,foreign):
    args,state,s,options,dose,parent=prepared(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='exact observed'):
        s.consequence.declare_preparation_parent(options,replace(dose) if foreign=='dose' else dose,
            replace(parent) if foreign=='parent' else parent)
    assert not s.recorder.trace and args['emulator'].frame_count==0


def test_unwitnessed_rows_keep_original_missing_features_and_prefix_censor(tmp_path,monkeypatch):
    args,state,s,options,dose,parent=prepared(tmp_path,monkeypatch)
    expected=options.menu.candidate_vector(options.bindings.index(dose),feature_version=15)
    result=finish_prefix(s,dose)
    row=recording.load_challenge_consequence(args['store'],declaration_sha256=result['declaration_sha256'],result_sha256=canonical_sha256(result))
    assert s.consequence.plan['schema']=='pokemon.red.challenge-consequence-plan.v8'
    assert 'preparation_parent_witness' not in s.consequence.plan
    assert row.features==expected and row.outcome is None
    assert row.censor_reason=='challenge_not_reached_before_stop'

@pytest.mark.parametrize('fault',['dose_failed','exception'])
def test_witness_preserves_charged_failed_and_censored_dose(tmp_path,monkeypatch,fault):
    args,state,s,options,dose,parent=prepared(tmp_path,monkeypatch,fault=fault)
    s.consequence.declare_preparation_parent(options,dose,parent)
    if fault=='exception':
        with pytest.raises(RuntimeError,match='interrupted'):dose.execute()
    else:
        dose.verify(dose.execute())
    result=s.consequence.finish()
    row=recording.load_challenge_consequence(args['store'],declaration_sha256=result['declaration_sha256'],result_sha256=canonical_sha256(result))
    if fault=='exception':
        assert row.outcome is None and row.censor_reason=='execution_or_verification_incomplete'
    else:
        assert row.outcome.initial_goal_failed and not row.outcome.attempted
        assert row.outcome.actions==2 and row.outcome.frames==4 and row.outcome.restorations==1
    assert result['phases'][0]['after']['actions']==2
    assert result['phases'][0]['after']['frames']==4
    assert result['phases'][0]['after']['heals']==1
    assert not args['emulator'].pressed_buttons


def test_changed_pending_binding_inventory_is_rejected_before_execution(tmp_path,monkeypatch):
    args,state,s,options,dose,parent=prepared(tmp_path,monkeypatch)
    s.consequence.declare_preparation_parent(options,dose,parent)
    witness=s.consequence.preparation_parent_witness
    witness['bindings'][witness['parent_index']]['story_objective_ref']='foreign-target'
    with pytest.raises(ValueError,match='inventory changed'):
        s.consequence.begin(options,dose,preflight_only=True)
    assert not s.recorder.trace and args['emulator'].frame_count==0
