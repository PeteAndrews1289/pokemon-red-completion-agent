"""ROM-free checks of optional mechanical accounting; no native labels or fits."""
from dataclasses import replace
import numpy as np
import pytest
from test_machine_consequence_runtime_v10 import machine_options, v10_head
from test_red_branch_recovery import parent_choice
from test_red_consequence_choice import provisional_args
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalCashOutcome, GoalManagerRuntimeError
from pokemon_red_completion.living_dex_option_value import option_feature_names, upgrade_option_value_model_for_move_change
from pokemon_red_completion.player_challenge_consequence import ChallengeConsequenceHead
from pokemon_red_completion.red_live_option_menu import RedLiveOptionSelectionMode
import pokemon_red_completion.red_consequence_choice as chooser

MODE='certified_single_trainer_v1'

def constant_head(attempted=1.,completed=.25,version=10,mode=MODE):
    width=len(option_feature_names(version));intercept=np.array([attempted,completed,.1,.2,5.,.7,0.,0.,.5])
    return ChallengeConsequenceHead(np.zeros((width,9)),intercept,np.zeros(width),np.ones(width),
        'a'*64,2,1.,'synthetic',feedback_version=2,feature_version=version,cash_prediction=mode)

@pytest.mark.parametrize('attempted,completed,exposure,expected',[
    (1.,0.,407,407),(1.,1.,407,0),(.8,.3,3506,1753),(0.,0.,407,0),
    (.4,.9,407,0),(1.,0.,0,0),(1.,0.,500000,500000)])
def test_only_attempted_failed_battle_pays_certified_loss(attempted,completed,exposure,expected):
    head=constant_head(attempted,completed);features=(0.,)*len(option_feature_names(10))
    predicted=head.predict(features,single_battle_loss_debit=exposure)
    assert predicted[4]*1500==pytest.approx(expected)
    assert predicted[5]==.7 # Credits are not netted or mechanically inferred.
    assert head.predict(features)[4]==5. # Unknown scope keeps measured-target prediction.

@pytest.mark.parametrize('bad',[True,1.2,'407',-1,500001,float('nan')])
def test_invalid_exposure_never_silently_coerced(bad):
    with pytest.raises(ValueError):constant_head().predict((0.,)*len(option_feature_names(10)),single_battle_loss_debit=bad)

@pytest.mark.parametrize('version',[7,9,10,11])
def test_new_mode_changes_identity_and_round_trips_without_reinterpreting_old_models(version):
    legacy=constant_head(version=version,mode='independent');current=replace(legacy,cash_prediction=MODE)
    assert 'cash_prediction' not in legacy.document()
    assert current.document()['cash_prediction']==MODE and current.model_sha256!=legacy.model_sha256
    for head in (legacy,current):
        restored=ChallengeConsequenceHead.from_document(head.document(),expected_sha256=head.model_sha256)
        assert restored.model_sha256==head.model_sha256
        assert restored.predict((0.,)*len(option_feature_names(version)))==head.predict((0.,)*len(option_feature_names(version)))
    with pytest.raises(ValueError):legacy.predict((0.,)*len(option_feature_names(version)),single_battle_loss_debit=407)

def certified_options(tmp_path,monkeypatch):
    options,story,machine,rt,inputs=machine_options(tmp_path,monkeypatch)
    source=options.binding(machine).cash_outcome.source_sha256
    direct=replace(options.binding(story),maximum_cash_debit=407,
        cash_outcome=GoalCashOutcome(source,'single_trainer',407))
    indices=(story,machine,machine+1)
    subset=replace(options,bindings=(direct,options.binding(machine),options.binding(machine+1)),
        menu=replace(options.menu,candidates=tuple(options.menu.candidates[i]for i in indices)),
        ordinary_binding_refs=options.ordinary_binding_refs & {options.binding(i).binding_ref for i in indices})
    return subset,rt,inputs

def test_native_choice_uses_future_battle_exposure_for_owned_tm_not_zero(tmp_path,monkeypatch):
    options,rt,inputs=certified_options(tmp_path,monkeypatch)
    assert [b.maximum_cash_debit for b in options.bindings]==[407,0,0]
    refs=('private-combat-goal',)*3
    assert chooser.consequence_cash_exposures(options,challenge_refs=refs)==(407,407,407)
    selected,receipt=chooser.choose_consequence_binding(options,replace(v10_head(),cash_prediction=MODE),challenge_refs=refs)
    assert selected is options.binding(1)
    assert receipt['single_battle_loss_debits']==[407,407,407] and not receipt['executed']
    assert receipt['cash_certificates'][1]['kind']=='preserves_cash_approach'
    assert not inputs and rt.emulator.state==b'source'

@pytest.mark.parametrize('fault',['missing_direct','wrong_objective','stale_machine','zero_bound_only','no_move_change','approach_only','ambiguous'])
def test_no_borrowed_proof_from_numeric_bound_or_ambiguous_or_stale_scope(tmp_path,monkeypatch,fault):
    options,rt,inputs=certified_options(tmp_path,monkeypatch);bindings=list(options.bindings);candidates=list(options.menu.candidates)
    expected=(407,407,407)
    if fault=='missing_direct':bindings[0]=replace(bindings[0],cash_outcome=None);expected=(None,None,None)
    elif fault=='wrong_objective':bindings[0]=replace(bindings[0],story_objective_ref='other');expected=(None,None,None)
    elif fault=='stale_machine':bindings[1]=replace(bindings[1],cash_outcome=GoalCashOutcome('b'*64,'preserves_cash_approach'));expected=(407,None,407)
    elif fault=='zero_bound_only':bindings[1]=replace(bindings[1],cash_outcome=None);expected=(407,None,407)
    elif fault=='no_move_change':candidates[1]=replace(candidates[1],move_change=None);expected=(407,None,407)
    elif fault=='approach_only':bindings[0]=replace(bindings[0],cash_outcome=None,story_approach_only=True);expected=(None,None,None)
    elif fault=='ambiguous':
        bindings.append(replace(bindings[0],binding_ref=bindings[0].binding_ref+'-other'));candidates.append(replace(candidates[0],binding_ref=bindings[-1].binding_ref));expected=(None,)*4
    options=replace(options,bindings=tuple(bindings),menu=replace(options.menu,candidates=tuple(candidates)))
    assert chooser.consequence_cash_exposures(options,challenge_refs=('private-combat-goal',)*len(bindings))==expected
    assert not inputs

def test_uncertified_restoration_stays_present_and_keeps_independent_prediction(tmp_path,monkeypatch):
    options,story,machine,rt,inputs=machine_options(tmp_path,monkeypatch)
    bindings=list(options.bindings);source=bindings[machine].cash_outcome.source_sha256
    bindings[story]=replace(bindings[story],maximum_cash_debit=407,cash_outcome=GoalCashOutcome(source,'single_trainer',407))
    options=replace(options,bindings=tuple(bindings))
    # Subset exactly as branch refinement does; travel is a different challenge.
    indices=tuple(i for i,b in enumerate(bindings)if b is bindings[story]or b.kind in {GoalKind.RESTORE_TEAM,GoalKind.DEVELOP_TEAM})
    options=replace(options,bindings=tuple(bindings[i]for i in indices),
        menu=replace(options.menu,candidates=tuple(replace(options.menu.candidates[i],challenge=options.menu.candidates[story].challenge)for i in indices)),
        ordinary_binding_refs=options.ordinary_binding_refs & {bindings[i].binding_ref for i in indices})
    exposures=chooser.consequence_cash_exposures(options,challenge_refs=('private-combat-goal',)*len(indices))
    assert any(b.kind is GoalKind.RESTORE_TEAM for b in options.bindings)
    for b,e in zip(options.bindings,exposures):
        if b.kind is GoalKind.RESTORE_TEAM:assert e is None
    assert not inputs

@pytest.mark.parametrize('fault',['wrong_bound','approach','wrong_kind'])
def test_invalid_executable_certificate_rejected(tmp_path,monkeypatch,fault):
    options,_,_=certified_options(tmp_path,monkeypatch)
    changes={'wrong_bound':dict(maximum_cash_debit=0),'approach':dict(story_approach_only=True),'wrong_kind':dict(kind=GoalKind.RESTORE_TEAM,story_objective_ref=None)}[fault]
    with pytest.raises(GoalManagerRuntimeError):replace(options.binding(0),**changes)

def test_branch_refinement_reuses_same_accounting_and_exact_binding(tmp_path,monkeypatch):
    options,rt,inputs=certified_options(tmp_path,monkeypatch)
    args,_=provisional_args(tmp_path/'model',monkeypatch);model=upgrade_option_value_model_for_move_change(args['model'])
    monkeypatch.setattr(chooser,'select_red_live_option',lambda m,o,**kw:parent_choice(o,0,m,seed=kw['seed'],mode=RedLiveOptionSelectionMode.MODEL_GREEDY))
    head=replace(v10_head(),cash_prediction=MODE)
    selected=chooser.select_branch_recovery_live_option(model,options,head,objective_ref='private-combat-goal',seed=3,greedy_selection=True)
    assert selected.selected_binding is options.binding(1)
    direct_receipt=chooser.choose_consequence_binding(options,head,challenge_refs=('private-combat-goal',)*3)[1]
    assert tuple(selected.branch_recovery.child.scores)==tuple(direct_receipt['scores'])
    assert not inputs and rt.emulator.state==b'source'


@pytest.mark.parametrize('mode',['direct','branch'])
def test_native_decision_retains_private_cash_proof_before_execution(tmp_path,monkeypatch,mode):
    import json
    import pokemon_red_completion.red_native_player as native
    from test_red_branch_recovery import greedy_native_args
    from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel
    from pokemon_red_completion.provenance import canonical_sha256
    args,state=(greedy_native_args if mode=='branch' else provisional_args)(tmp_path,monkeypatch)
    args['model']=upgrade_option_value_model_for_move_change(args['model'])
    args['consequence_head']=replace(v10_head('kind.unlock_access'),cash_prediction=MODE)
    monkeypatch.setattr(LivingDexOptionValueModel,'scores',lambda self,observed,utility:
        tuple(float(c.features.kind.value=='unlock_access') for c in observed.candidates))
    result=native.run_native_continuous_player(**args)
    assert result['executed_decisions']==result['model_decisions']==1
    step=args['output']/'episode/step-000'
    receipt=json.loads((step/'consequence-cash-private.json').read_text())
    decision=json.loads((step/'decision.json').read_text())
    public=decision['consequence'] if mode=='direct' else decision['branch_recovery']['recovery']['consequence']
    assert public['cash_accounting_receipt_sha256']==receipt['choice_sha256']
    assert canonical_sha256({k:v for k,v in receipt.items()if k!='choice_sha256'})==receipt['choice_sha256']
    assert receipt['cash_prediction']==MODE
    assert 'cash_certificates' not in str(decision) and 'binding_refs' not in str(decision)
    assert not args['emulator'].pressed_buttons


def test_private_cash_receipt_cannot_be_mutated_or_rebound(tmp_path,monkeypatch):
    import json
    options,rt,inputs=certified_options(tmp_path,monkeypatch)
    choice=chooser.select_consequence_live_option(options,replace(v10_head(),cash_prediction=MODE),challenge_ref='private-combat-goal',seed=3)
    receipt=choice.private_consequence_receipt();receipt['single_battle_loss_debits'][1]=0
    assert choice.private_consequence_receipt()['single_battle_loss_debits'][1]==407
    with pytest.raises(ValueError):replace(choice,consequence_receipt_json=json.dumps(receipt))
    assert not inputs


@pytest.mark.parametrize('cash,expected',[(None,None),(0,0),(813,407),(814,407),(999999,500000)])
def test_story_certificate_factory_preserves_unknown_money_and_odd_rounding(monkeypatch,cash,expected):
    from test_red_player_story_battle import setup
    from pokemon_red_completion import red_player_story_battle as story
    rt,actions,route,raw,lesson,inputs,calls,contract,_=setup(monkeypatch)
    raw.player_money=cash
    monkeypatch.setattr(story,'certified_cash_safe_transition',lambda *args:object())
    binding=story.story_battle_binding(rt,actions,contract=contract,route=route,battler=object())
    assert binding.maximum_cash_debit==expected
    if expected is None:assert binding.cash_outcome is None
    else:assert binding.cash_outcome.loss_debit==expected
    assert not inputs and not calls


@pytest.mark.parametrize('field',['menu','binding_ref','kind'])
def test_rehashed_private_cash_receipt_cannot_misrepresent_live_payload(tmp_path,monkeypatch,field):
    import json
    from pokemon_red_completion.provenance import canonical_sha256
    options,rt,inputs=certified_options(tmp_path,monkeypatch)
    choice=chooser.select_consequence_live_option(options,replace(v10_head(),cash_prediction=MODE),challenge_ref='private-combat-goal',seed=3)
    receipt=choice.private_consequence_receipt()
    receipt[field]={'fabricated':True} if field=='menu' else 'fabricated'
    receipt['choice_sha256']=canonical_sha256({k:v for k,v in receipt.items()if k!='choice_sha256'})
    with pytest.raises(ValueError):replace(choice,consequence_receipt_json=json.dumps(receipt))
    assert not inputs
