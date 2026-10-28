from copy import deepcopy
from dataclasses import replace
import numpy as np
import pytest

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import RED_BATTLE_CATALOG
from pokemon_red_completion.red_battle_scenario import PreparedRedBattleScenario
from pokemon_red_completion.red_trainer_opening_control import (
    ORDINARY_FRESH_POLICY_CONFIGURATION, preview_machine_control,
    preview_fresh_trainer_control, _control_view,
)
from pokemon_red_completion.red_trainer_opening_preview import OpeningPreviewUnavailable
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel
from pokemon_red_completion.red_trainer_practice_features import MOVE_SCHEMA_ID,MOVE_FEATURE_NAMES,SWITCH_SCHEMA_ID,SWITCH_FEATURE_NAMES_V2
from pokemon_red_completion.red_trainer_proposed_control import PROPOSED_CONTROL_SCHEMA,PROPOSED_CONTROL_NAMES
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_outcome_policy import RedTrainerPracticeOutcomePolicy


def facts(reserve=True):
    party=[dict(specimen_ref='lead',species_id=28,level=50,hp=156,max_hp=156,status='healthy',moves=[[44,25],[39,30],[58,10],[57,15]])]
    stats=[[112,124,104,118]]
    if reserve:
        party.append(dict(specimen_ref='reserve',species_id=64,level=45,hp=100,max_hp=120,status='healthy',moves=[[163,20],[28,15],[15,30],[19,15]]))
        stats.append([110,80,95,89])
    return dict(state_sha256='a'*64,actions=0,frames=0,cash=1000,
        lesson=dict(in_battle=False,party=party),machine_boundary=dict(party_stats=stats,badges=127),
        economy=dict(schema='pokemon.core.resource-economy-snapshot.v1',cash=1000,inventory=[['red-item-001',1],['red-item-020',3],['red-item-214',1]]))


def model():
    rng=np.random.default_rng(41)
    def head(schema,names):
        return TrainerHeadModel(schema,names,rng.normal(0,.1,(len(names),2)),np.zeros(2),np.array([1.,0.]),0)
    return TrainerPracticeThreeHeadModel(head(MOVE_SCHEMA_ID,MOVE_FEATURE_NAMES),head(PROPOSED_CONTROL_SCHEMA,PROPOSED_CONTROL_NAMES),head(SWITCH_SCHEMA_ID,SWITCH_FEATURE_NAMES_V2),('fixed-test-capture',),('fixed-test-root',),'fitted_components')


def args():
    m=model();policy=deepcopy(ORDINARY_FRESH_POLICY_CONFIGURATION)
    return dict(model=m,expected_model_sha256=canonical_sha256(m.to_dict()),policy_configuration=policy,
        expected_policy_sha256=canonical_sha256(policy),opponent_species_id=33,opponent_level=42,
        opponent_base_stats=dict(hp=65,attack=70,defense=45,speed=60,special=50),opponent_quote_sha256='b'*64,
        fresh_trainer=True,approach_preserves_party=True,approach_preserves_resources=True)


def lesson():
    return dict(lesson=dict(party_slot=1,species_id=28,before_moves=[44,39,58,57],replace_slot=1,move_id=59),move_change=dict(proposed_current_pp=5))


@pytest.mark.parametrize('reserve',[True,False])
@pytest.mark.parametrize('changed',[True,False])
def test_preview_matches_fresh_production_policy_and_is_pure(reserve,changed):
    before=facts(reserve);a=args();proposal=lesson() if changed else None;original=deepcopy(before)
    got=preview_fresh_trainer_control(before,**a,machine_lesson=proposal)
    view=_control_view(before,machine_lesson=proposal,stats_peer=None,**{k:a[k]for k in ['opponent_species_id','opponent_level','opponent_base_stats']})
    base=BattleFeatureProjector(RED_BATTLE_CATALOG,mask_counter_without_prior_damage=True).project(view)
    prepared=PreparedRedBattleScenario(canonical_sha256(view),replace(base,legal_mask=(True,False,True,True)))
    policy=RedTrainerPracticeOutcomePolicy('fixed-test','fresh-test',a['model'])
    action=policy.choose_main(view,prepared);diag=policy.last_decision_diagnostics
    assert got.supported_mask==prepared.supported_candidate_mask
    assert got.probabilities==pytest.approx(diag['control_probabilities'])
    assert np.asarray(got.candidate_vectors)==pytest.approx(np.asarray(diag['control_candidate_vectors']))
    assert got.selected_control==diag['control_choice']
    assert before==original and canonical_sha256(a['model'].to_dict())==a['expected_model_sha256']
    assert got.forced_attack is (not reserve)
    if not reserve:assert got.probabilities==(1.,0.) and got.proposed_switch_slot is None


def test_mask_removes_depleted_and_status_moves_before_control_aggregation():
    before=facts();before['lesson']['party'][0]['moves'][2][1]=0
    got=preview_fresh_trainer_control(before,**args())
    assert got.supported_mask==(True,False,False,True) and got.move_slots==(1,4)
    name='attack_or_decline.moves.usable_count'
    assert got.candidate_vectors[0][got.feature_names.index(name)]==.5


def test_before_after_share_model_source_and_pinned_declared_lesson():
    before=facts();a=args();m=lesson();result=preview_machine_control(before,**a,machine_lesson=m)
    assert result.before.source_sha256==result.after.source_sha256==before['state_sha256']
    assert result.before.model_sha256==result.after.model_sha256==a['expected_model_sha256']
    assert result.before.policy_sha256==result.after.policy_sha256
    assert result.before.input_sha256!=result.after.input_sha256
    assert result.lesson_sha256==canonical_sha256(m) and result.snapshot_sha256==canonical_sha256(before)
    # Replacing an unselected move may leave the concrete child proposals unchanged.
    assert len(result.before.candidate_vectors)==len(result.after.candidate_vectors)==2
    assert 'not subsequent turns, damage or victory' in result.after.assumptions[-1]
    direct=preview_machine_control(before,**a)
    assert direct.before is direct.after and direct.lesson_sha256 is None


@pytest.mark.parametrize('change',[
    lambda b:b.pop('economy'),lambda b:b['economy'].pop('inventory'),lambda b:b['economy'].update(cash=2),
    lambda b:b['economy'].update(inventory=[['red-item-020',True]]),lambda b:b['economy'].update(inventory=[['red-item-020',1],['red-item-020',2]]),
    lambda b:b['machine_boundary'].pop('badges'),lambda b:b['machine_boundary'].update(badges=True),
    lambda b:b['lesson']['party'][1].update(hp=0),lambda b:b.update(actions=1),lambda b:b.update(state_sha256='bad'),
])
def test_unknown_resource_status_or_source_facts_fail_unavailable(change):
    before=facts();change(before)
    with pytest.raises(OpeningPreviewUnavailable):preview_fresh_trainer_control(before,**args())


@pytest.mark.parametrize('key,value',[
    ('expected_model_sha256','f'*64),('expected_policy_sha256','c'*64),('fresh_trainer',False),
    ('approach_preserves_resources',False),('approach_preserves_party',False),
    ('opponent_base_stats',dict(attack=70,defense=45,speed=60,special=50)),
])
def test_exact_model_policy_and_opening_scope_required(key,value):
    a=args();a[key]=value
    with pytest.raises(OpeningPreviewUnavailable):preview_fresh_trainer_control(facts(),**a)


def test_policy_change_rejected_even_with_matching_new_hash():
    a=args();a['policy_configuration']['mechanics_aware_choices']=True
    a['expected_policy_sha256']=canonical_sha256(a['policy_configuration'])
    with pytest.raises(OpeningPreviewUnavailable):preview_fresh_trainer_control(facts(),**a)


def test_exact_peer_joins_missing_stats_but_not_other_source():
    peer=facts();before=deepcopy(peer);before.pop('machine_boundary')
    got=preview_machine_control(before,stats_peer=peer,**args())
    assert got.before==preview_machine_control(peer,**args()).before
    assert got.stats_peer_sha256==canonical_sha256(peer)
    peer['state_sha256']='d'*64
    with pytest.raises(OpeningPreviewUnavailable):preview_machine_control(before,stats_peer=peer,**args())


def test_no_supported_attack_remains_unavailable_even_with_reserve():
    before=facts()
    for pair in before['lesson']['party'][0]['moves']:pair[1]=0
    with pytest.raises(OpeningPreviewUnavailable,match='no ordinary supported attack'):
        preview_fresh_trainer_control(before,**args())


def test_matching_preinput_peer_supplies_missing_resource_inventory():
    peer=facts();before=deepcopy(peer);before.pop('economy');before.pop('machine_boundary')
    result=preview_machine_control(before,stats_peer=peer,**args())
    assert result.before==preview_machine_control(peer,**args()).before
    assert result.stats_peer_sha256==canonical_sha256(peer)


@pytest.mark.parametrize('change',[
    lambda b:b.update(cash=123),lambda b:b['economy'].update(inventory=[]),
    lambda b:b.update(state_sha256='f'*64),lambda b:b.update(actions=1),
])
def test_control_peer_cannot_splice_contradictory_resource_or_source_facts(change):
    peer=facts();before=deepcopy(peer);before.pop('machine_boundary');change(peer)
    with pytest.raises(OpeningPreviewUnavailable):preview_machine_control(before,stats_peer=peer,**args())


def test_mutating_exported_configuration_cannot_widen_qualified_policy(monkeypatch):
    monkeypatch.setitem(ORDINARY_FRESH_POLICY_CONFIGURATION,'mechanics_aware_choices',True)
    a=args()
    with pytest.raises(OpeningPreviewUnavailable):preview_machine_control(facts(),**a)
