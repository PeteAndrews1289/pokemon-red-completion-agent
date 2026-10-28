from copy import deepcopy
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel
from pokemon_red_completion.red_trainer_practice_features import MOVE_SCHEMA_ID, MOVE_FEATURE_NAMES
from pokemon_red_completion.red_trainer_opening_preview import (
    OpeningPreviewUnavailable, preview_fresh_trainer_moves,
)


def facts():
    return dict(state_sha256='a'*64, actions=0, frames=0,
        lesson=dict(in_battle=False,party=[dict(specimen_ref='observed-lead',species_id=28,
            level=50,hp=156,max_hp=156,status='healthy',moves=[[44,25],[39,30],[58,10],[57,15]])]),
        machine_boundary=dict(party_stats=[[112,124,104,118]]))


def head():
    # Fixed untrained parameters: tests never fit a model.
    w=np.zeros((len(MOVE_FEATURE_NAMES),2));w[MOVE_FEATURE_NAMES.index('move.power_fraction'),0]=1
    return TrainerHeadModel(MOVE_SCHEMA_ID,MOVE_FEATURE_NAMES,w,np.zeros(2),np.array([1.,0.]),0)


def arguments():
    h=head()
    return dict(opponent_species_id=33,opponent_level=42,
        opponent_base_stats=dict(attack=70,defense=45,speed=60,special=50),
        opponent_quote_sha256='b'*64,head=h,expected_head_sha256=canonical_sha256(h.to_dict()),
        fresh_trainer=True,approach_preserves_party=True)


def lesson(slot=1):
    return dict(lesson=dict(party_slot=1,species_id=28,before_moves=[44,39,58,57],replace_slot=slot,move_id=59),
        move_change=dict(proposed_current_pp=5))


def test_preview_is_pure_conditional_and_reuses_frozen_head():
    before=facts();original=deepcopy(before);args=arguments();identity=canonical_sha256(args['head'].to_dict())
    result=preview_fresh_trainer_moves(before,**args)
    assert before==original and canonical_sha256(args['head'].to_dict())==identity
    assert result.candidate_slots==(1,3,4) and sum(result.probabilities)==pytest.approx(1)
    assert result.preferred_slot in result.candidate_slots
    assert 'conditional on attack; control/switch unpredicted' in result.assumptions
    assert 'not a win probability' in result.assumptions[-1]
    assert result.public_dict()['schema']=='pokemon.red.conditional-opening-preview.v1'
    with pytest.raises(FrozenInstanceError):result.preferred_slot=4
    before['lesson']['party'][0]['moves'][0][0]=59
    assert result.input_sha256==preview_fresh_trainer_moves(original,**args).input_sha256


def test_replacement_changes_only_proposed_vector_and_preserves_retained_moves():
    before=facts();args=arguments();direct=preview_fresh_trainer_moves(before,**args)
    changed=preview_fresh_trainer_moves(before,**args,machine_lesson=lesson())
    assert direct.source_sha256==changed.source_sha256 and direct.head_sha256==changed.head_sha256
    assert direct.input_sha256!=changed.input_sha256
    assert direct.candidate_vectors[1:]==changed.candidate_vectors[1:]
    assert direct.candidate_vectors[0]!=changed.candidate_vectors[0]


def test_exact_source_party_peer_supplies_only_missing_stats():
    peer=facts();before=deepcopy(peer);before.pop('machine_boundary')
    expected=preview_fresh_trainer_moves(peer,**arguments())
    assert preview_fresh_trainer_moves(before,stats_peer=peer,**arguments())==expected


@pytest.mark.parametrize('change',[
    lambda b:b.update(state_sha256='c'*64),lambda b:b.update(actions=1),
    lambda b:b.update(frames=False),lambda b:b['lesson'].update(in_battle=True),
    lambda b:b['lesson']['party'][0].update(specimen_ref='other'),
    lambda b:b['lesson']['party'][0]['moves'][0].__setitem__(1,24),
])
def test_stats_join_rejects_related_but_different_sources(change):
    peer=facts();before=deepcopy(peer);before.pop('machine_boundary');change(peer)
    with pytest.raises(OpeningPreviewUnavailable):preview_fresh_trainer_moves(before,stats_peer=peer,**arguments())


@pytest.mark.parametrize('change',[
    lambda b:b.pop('machine_boundary'),lambda b:b['machine_boundary'].update(party_stats=[]),
    lambda b:b['machine_boundary']['party_stats'][0].__setitem__(2,None),
    lambda b:b.update(actions=False),lambda b:b.update(frames=1),lambda b:b.update(state_sha256='bad'),
    lambda b:b['lesson'].update(in_battle=True),lambda b:b['lesson']['party'][0].update(status=None),
    lambda b:b['lesson']['party'][0].update(status='paralysis'),lambda b:b['lesson']['party'][0].update(hp=0),
    lambda b:b['lesson']['party'][0].update(hp=157),lambda b:b['lesson']['party'][0].update(level=True),
    lambda b:b['lesson']['party'][0].pop('specimen_ref'),
    lambda b:b['lesson']['party'][0]['moves'][0].__setitem__(1,-1),
    lambda b:b['lesson']['party'][0]['moves'].__setitem__(0,[0,1]),
])
def test_unknown_or_unsupported_observations_remain_unavailable(change):
    before=facts();change(before)
    with pytest.raises(OpeningPreviewUnavailable):preview_fresh_trainer_moves(before,**arguments())


@pytest.mark.parametrize('key,value',[
    ('fresh_trainer',False),('fresh_trainer',1),('approach_preserves_party',False),
    ('expected_head_sha256','f'*64),('opponent_quote_sha256',None),('opponent_level',True),
    ('opponent_base_stats',dict(attack=70,defense=None,speed=60,special=50)),
])
def test_preview_requires_explicit_scope_and_pinned_head(key,value):
    args=arguments();args[key]=value
    with pytest.raises(OpeningPreviewUnavailable):preview_fresh_trainer_moves(facts(),**args)


@pytest.mark.parametrize('change',[
    lambda m:m['lesson'].update(party_slot=2),lambda m:m['lesson'].update(party_slot=True),
    lambda m:m['lesson'].update(species_id=1),lambda m:m['lesson'].update(before_moves=[44,39,0,57]),
    lambda m:m['lesson'].update(replace_slot=0),lambda m:m['move_change'].update(proposed_current_pp=4),
])
def test_proposal_must_match_original_lead_and_native_new_move_charges(change):
    proposal=lesson();change(proposal)
    with pytest.raises(OpeningPreviewUnavailable):preview_fresh_trainer_moves(facts(),machine_lesson=proposal,**arguments())


def test_no_supported_attack_is_unavailable_not_a_struggle_or_status_choice():
    before=facts();before['lesson']['party'][0]['moves']=[[44,0],[39,30],[58,0],[57,0]]
    with pytest.raises(OpeningPreviewUnavailable,match='no ordinary supported attack'):
        preview_fresh_trainer_moves(before,**arguments())


def test_empty_slot_replacement_preserves_actual_slot_indices():
    before=facts();before['lesson']['party'][0]['moves'][2]=[0,0]
    proposal=lesson(3);proposal['lesson']['before_moves'][2]=0
    result=preview_fresh_trainer_moves(before,**arguments(),machine_lesson=proposal)
    assert result.candidate_slots==(1,3,4)


def test_same_width_but_different_feature_contract_is_unavailable():
    from dataclasses import replace
    args=arguments();h=args['head']
    args['head']=replace(h,feature_names=('wrong.name',*h.feature_names[1:]))
    args['expected_head_sha256']=canonical_sha256(args['head'].to_dict())
    with pytest.raises(OpeningPreviewUnavailable,match='ordinary stat move head'):
        preview_fresh_trainer_moves(facts(),**args)


from pokemon_red_completion.red_trainer_opening_preview import (
    OPENING_PREFERENCE_FEATURE_NAMES, preview_machine_preference,
)


def test_direct_preference_requires_a_real_qualified_baseline():
    result=preview_machine_preference(facts(),**arguments())
    assert result.feature_names==OPENING_PREFERENCE_FEATURE_NAMES
    assert result.values==(1.,0.,0.) and result.before is result.after
    assert result.lesson_sha256 is None and result.replaced_slot is None
    missing=facts();missing.pop('machine_boundary')
    with pytest.raises(OpeningPreviewUnavailable):preview_machine_preference(missing,**arguments())


def test_preference_reports_removed_and_proposed_mass_with_proof_not_ids_in_features():
    snapshot=facts();proposal=lesson();original=deepcopy((snapshot,proposal))
    result=preview_machine_preference(snapshot,**arguments(),machine_lesson=proposal)
    assert (snapshot,proposal)==original
    assert result.values==(1.,result.before.probabilities[0],result.after.probabilities[0])
    assert result.before.source_sha256==result.after.source_sha256==snapshot['state_sha256']
    assert result.before.head_sha256==result.after.head_sha256
    assert result.before.opponent_quote_sha256==result.after.opponent_quote_sha256
    assert result.before.assumptions==result.after.assumptions
    assert result.lesson_sha256==canonical_sha256(proposal)
    assert result.snapshot_sha256==canonical_sha256(snapshot)
    assert result.stats_peer_sha256 is None
    assert result.replaced_slot==1 and len(result.values)==3
    assert result.public_dict()['schema']=='pokemon.red.conditional-opening-preference.v1'
    with pytest.raises(FrozenInstanceError):result.values=(0.,0.,0.)


def test_replacing_an_unsupported_status_move_has_known_zero_removed_attack_mass():
    result=preview_machine_preference(facts(),**arguments(),machine_lesson=lesson(2))
    assert 2 not in result.before.candidate_slots and 2 in result.after.candidate_slots
    assert result.values[0:2]==(1.,0.) and result.values[2]>0
    assert result.removed_move==(39,30) and result.proposed_move==(59,5)
    assert result.public_dict()['removed_slot_legal'] is False
    assert result.public_dict()['proposed_slot_legal'] is True


def test_new_move_need_not_be_preferred_over_retained_attacks():
    snapshot=facts();proposal=lesson();proposal['lesson']['move_id']=33
    proposal['move_change']['proposed_current_pp']=35
    result=preview_machine_preference(snapshot,**arguments(),machine_lesson=proposal)
    assert result.after.preferred_slot in (3,4) and result.replaced_slot==1
    assert result.values[2]<result.after.probabilities[result.after.candidate_slots.index(result.after.preferred_slot)]


def test_stats_peer_proof_is_present_only_when_used():
    peer=facts();snapshot=deepcopy(peer);snapshot.pop('machine_boundary')
    result=preview_machine_preference(snapshot,stats_peer=peer,**arguments())
    assert result.stats_peer_sha256==canonical_sha256(peer)
    direct=preview_machine_preference(peer,stats_peer={'unrelated':'unused'},**arguments())
    assert direct.stats_peer_sha256 is None


def test_different_lesson_changes_proof_even_when_both_summaries_have_same_width():
    first=preview_machine_preference(facts(),**arguments(),machine_lesson=lesson(1))
    second=preview_machine_preference(facts(),**arguments(),machine_lesson=lesson(3))
    assert first.lesson_sha256!=second.lesson_sha256
    assert canonical_sha256(first.public_dict())!=canonical_sha256(second.public_dict())
    assert first.feature_names==second.feature_names



def test_proposed_status_move_is_zero_attack_mass_with_explicit_scope():
    proposal=lesson();proposal['lesson']['move_id']=92
    proposal['move_change']['proposed_current_pp']=10
    result=preview_machine_preference(facts(),**arguments(),machine_lesson=proposal)
    assert result.values[0]==1. and result.values[2]==0.
    assert result.proposed_move==(92,10)
    assert result.public_dict()['proposed_slot_legal'] is False
    assert result.after.candidate_slots==(3,4)


def test_removing_the_only_supported_attack_stays_unavailable():
    snapshot=facts();snapshot['lesson']['party'][0]['moves'][2][1]=0
    snapshot['lesson']['party'][0]['moves'][3][1]=0
    proposal=lesson();proposal['lesson']['move_id']=92
    proposal['move_change']['proposed_current_pp']=10
    with pytest.raises(OpeningPreviewUnavailable,match='no ordinary supported attack'):
        preview_machine_preference(snapshot,**arguments(),machine_lesson=proposal)
