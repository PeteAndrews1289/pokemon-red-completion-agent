"""ROM-free selected-objective custody and real helper-to-battler spy checks.

No emulator, model forecast, fit or native gameplay occurs in these tests.
"""
from dataclasses import replace
from types import SimpleNamespace as NS
import json
import pytest
from pokemon_red_completion.party_preparation import PreparationPurpose
from pokemon_red_completion.player_preparation_party_context import PreparationPartyWitness
from pokemon_red_completion.wild_training_objective import WildTrainingObjective
from pokemon_red_completion.red_learned_trainer import FrozenTrainerBattler
from pokemon_red_completion.red_trainer_practice_outcome_policy import RedTrainerPracticeOutcomePolicy
from pokemon_red_completion import red_wild_preparation as w
from test_red_party_preparation import setup
import test_red_wild_preparation as baseline

def context():
    members,_=setup()
    a,b,c=members
    rebound=(replace(b,observation=replace(b.observation,slot=1)),
             replace(a,observation=replace(a.observation,slot=2)),c)
    return WildTrainingObjective.from_members(source_state_sha256='b'*64,
        trainee_ref='2',target_level=34,members=rebound)

def actor(tmp_path):
    return FrozenTrainerBattler(None,None,tmp_path,'a'*40,'synthetic-unit-only','b'*64,{})

def test_semantic_binding_follows_selected_identity_after_party_swap():
    obj=context()
    assert obj.trainee_ref=='2'and obj.trainee_slot==1 and obj.slot_refs==('2','1','3')
    assert obj.current_level==22 and obj.current_experience==1000 and obj.target_level==34
    assert obj.party_witness.source_state_sha256=='b'*64
    assert dict(obj.party_witness.roles)['2']=='combat'
    doc=json.loads(json.dumps(obj.document()))
    assert WildTrainingObjective.from_document(doc)==obj
    assert obj.diagnostics()['current_heads_consume_context']is False
    assert 'trainee_ref'not in obj.diagnostics()and 'slot_refs'not in obj.diagnostics()

@pytest.mark.parametrize('fault',['unknown_ref','duplicate_slot_ref','missing_slot','wrong_role','bool_target','met_target','unknown_xp','bool_xp','wrong_source'])
def test_objective_rejects_unbound_or_unobserved_facts(fault):
    obj=context();kw={}
    if fault=='unknown_ref':kw['trainee_ref']='absent'
    if fault=='duplicate_slot_ref':kw['slot_refs']=('2','2','3')
    if fault=='missing_slot':kw['slot_refs']=('2','1')
    if fault=='wrong_role':kw['party_witness']=PreparationPartyWitness('b'*64,(('2','undecided'),('1','combat'),('3','combat')))
    if fault=='bool_target':kw['target_level']=True
    if fault=='met_target':kw['target_level']=22
    if fault=='unknown_xp':kw['current_experience']=None
    if fault=='bool_xp':kw['current_experience']=True
    if fault=='wrong_source':kw['party_witness']='b'*64
    with pytest.raises(ValueError):replace(obj,**kw)

@pytest.mark.parametrize('fault',['schema','extra','tuple_slots','bad_count'])
def test_objective_codec_refuses_incomplete_or_widened_context(fault):
    d=context().document()
    if fault=='schema':d['schema']='unversioned'
    if fault=='extra':d['action']='switch'
    if fault=='tuple_slots':d['slot_refs']=tuple(d['slot_refs'])
    if fault=='bad_count':d['party_witness']['counts']['total']=1
    with pytest.raises(ValueError):WildTrainingObjective.from_document(d)

def test_live_semantic_member_sequence_must_be_complete_and_slot_ordered():
    members,_=setup()
    with pytest.raises(ValueError):WildTrainingObjective.from_members(source_state_sha256='b'*64,trainee_ref='2',target_level=34,members=list(members))
    with pytest.raises(ValueError):WildTrainingObjective.from_members(source_state_sha256='b'*64,trainee_ref='2',target_level=34,members=(members[1],members[0],members[2]))
    bad=replace(members[1],observation=replace(members[1].observation,experience=None))
    with pytest.raises(ValueError):WildTrainingObjective.from_members(source_state_sha256='b'*64,trainee_ref='2',target_level=34,members=(members[0],bad,members[2]))

@pytest.mark.parametrize('supplied',[False,True])
def test_actual_frozen_entry_forwards_exact_context_and_keeps_generic_kwargs(tmp_path,supplied):
    obj=context();a=actor(tmp_path);seen=[]
    a.wild_authority=lambda expected_map:'synthetic-authority'
    a._play=lambda *args,**kwargs:seen.append((args,kwargs))or'synthetic-episode'
    reader=NS(read=lambda:NS(battle_state=1,map_id=15));executor=object();timing=object();guard=object()
    result=a.run_wild_training(reader,executor,expected_map=15,timing=timing,decision_guard=guard,
        **({'training_objective':obj}if supplied else{}))
    assert result=='synthetic-episode'and len(seen)==1
    args,kw=seen[0];assert args==(reader,executor)
    expected=dict(expected_map=15,timing=timing,label='learned wild training',decision_guard=guard,
        resume=False,require_win=False,maximum_decisions=80,authority='synthetic-authority',wild_training=True)
    if supplied:expected['training_objective']=obj
    assert kw==expected

def test_wrong_objective_type_rejects_before_live_reader_or_authority(tmp_path):
    a=actor(tmp_path)
    a.wild_authority=lambda *_:pytest.fail('authority must not be reached')
    reader=NS(read=lambda:pytest.fail('reader must not be reached'))
    with pytest.raises(ValueError,match='typed selected'):
        a.run_wild_training(reader,object(),expected_map=15,timing=None,decision_guard=None,training_objective={})

@pytest.mark.parametrize('wrong_mode',[False,True])
def test_actual_play_rejects_unbound_source_or_nonwild_context_before_native(tmp_path,wrong_mode):
    a=actor(tmp_path);obj=context()
    if not wrong_mode:obj=replace(obj,party_witness=PreparationPartyWitness('c'*64,obj.party_witness.roles))
    with pytest.raises(ValueError,match='admitted source or mode'):
        a._play(None,None,expected_map=15,timing=None,label='unit',decision_guard=None,
                resume=False,require_win=False,wild_training=not wrong_mode,training_objective=obj)

class ModelMustNotBeConsulted:
    def __getattribute__(self,name):
        raise AssertionError('observability check must not consult a learned model')

@pytest.mark.parametrize('supplied',[False,True])
def test_policy_records_metadata_without_claiming_model_consumption(supplied):
    obj=context()if supplied else None
    p=RedTrainerPracticeOutcomePolicy('synthetic','unit',ModelMustNotBeConsulted(),training_objective=obj)
    assert p.training_objective is obj
    p._record_pp_screen(())
    assert p.last_decision_diagnostics==({'wild_training_objective':obj.diagnostics()}if supplied else{})
    if supplied:assert p.last_decision_diagnostics['wild_training_objective']['current_heads_consume_context']is False

def test_policy_rejects_untyped_context_before_any_model_use():
    with pytest.raises(ValueError,match='typed selected'):
        RedTrainerPracticeOutcomePolicy('synthetic','unit',ModelMustNotBeConsulted(),training_objective={})

def test_policy_preserves_every_preexisting_positional_init_slot():
    catalog=object();history=object()
    p=RedTrainerPracticeOutcomePolicy('synthetic','unit',ModelMustNotBeConsulted(),catalog,history,True)
    assert p.catalog is catalog and p.history is history and p.allow_immune_switch_recovery is True
    assert p.training_objective is None

@pytest.mark.parametrize('capability',[None,1])
def test_real_preparation_helper_binds_after_lead_and_preserves_legacy_call(tmp_path,monkeypatch,capability):
    original=w.execute_wild_preparation;seen=[]
    def observed(**kwargs):
        battler=kwargs['battler'];battler.wild_training_objective_version=capability
        fake_battle=battler.run_wild_training
        def spy(reader,executor,**battle_kwargs):
            seen.append(battle_kwargs)
            return fake_battle(reader,executor,**battle_kwargs)
        battler.run_wild_training=spy
        return original(**kwargs)
    monkeypatch.setattr(w,'execute_wild_preparation',observed)
    monkeypatch.setattr(baseline,'w',w)
    baseline.test_wild_excursion_tracks_xp_and_retains_failures(tmp_path,monkeypatch,None,3,False,False)
    assert len(seen)==3
    for i,kw in enumerate(seen):
        assert set(kw)==({'expected_map','timing','decision_guard'}|({'training_objective'}if capability==1 else set()))
        if capability==1:
            obj=kw['training_objective'];assert type(obj)is WildTrainingObjective
            assert obj.trainee_ref=='2'and obj.trainee_slot==1 and obj.current_level==22
            assert obj.current_experience==1000+200*i
            assert obj.party_witness.source_state_sha256=='b'*64

@pytest.mark.parametrize('capability',[True,False,2,'1'])
def test_real_helper_refuses_unknown_capability_without_calling_battle(tmp_path,monkeypatch,capability):
    original=w.execute_wild_preparation;seen=[]
    def observed(**kwargs):
        battler=kwargs['battler'];battler.wild_training_objective_version=capability
        battler.run_wild_training=lambda *a,**kw:seen.append(kw)or pytest.fail('battle must not run')
        return original(**kwargs)
    monkeypatch.setattr(w,'execute_wild_preparation',observed);monkeypatch.setattr(baseline,'w',w)
    with pytest.raises(ValueError,match='objective capability'):
        baseline.test_wild_excursion_tracks_xp_and_retains_failures(tmp_path,monkeypatch,None,1,False,False)
    assert seen==[]
