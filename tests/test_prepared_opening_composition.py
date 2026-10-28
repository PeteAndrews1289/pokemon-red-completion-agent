from copy import deepcopy
from dataclasses import asdict,replace
import numpy as np
import pytest
from test_red_trainer_opening_control import facts,args,lesson
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.gen1_trainer_parties import TrainerPartyMember,TrainerPartyQuote
from pokemon_red_completion.red_trainer_opening_control import preview_fresh_trainer_control,preview_machine_control,_control_view
from pokemon_red_completion.red_trainer_opening_preview import OpeningPreviewUnavailable
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import RED_BATTLE_CATALOG
from pokemon_red_completion.red_battle_scenario import PreparedRedBattleScenario
from pokemon_red_completion.red_trainer_practice_outcome_policy import RedTrainerPracticeOutcomePolicy


def prepared_args(quote=None):
    a=args()
    quote=quote or TrainerPartyQuote(244,1,(TrainerPartyMember(33,33,42),),99,4158)
    a.update(trainer_quote=quote,expected_trainer_quote_sha256=canonical_sha256(asdict(quote)),
        preparation_configuration=dict(minimum_hp_ratio=0.,allow_fainted_reserves=True,maximum_level_deficit=5,allow_status=False))
    return a


@pytest.mark.parametrize('reserve',[False,True])
def test_identity_preparation_preserves_existing_vectors_and_probability(reserve):
    before=facts(reserve)
    old=preview_fresh_trainer_control(before,**args())
    got=preview_fresh_trainer_control(before,**prepared_args())
    assert got.candidate_vectors==old.candidate_vectors and got.probabilities==old.probabilities
    assert got.move_slots==old.move_slots and got.supported_mask==old.supported_mask
    assert got.preparation['permutation']==([1,2] if reserve else [1]) and not got.preparation['observed_after']


def swap_facts():
    before=facts();lead=before['lesson']['party'][0]
    reserve=deepcopy(lead);reserve.update(specimen_ref='other-same-species',level=65,hp=170,max_hp=180)
    reserve['moves']=[[85,12],[44,9],[57,7],[58,5]]
    before['lesson']['party'][1]=reserve;before['machine_boundary']['party_stats'][1]=[137,153,125,146]
    return before


def test_lesson_stays_with_original_specimen_during_exact_lead_swap():
    before=swap_facts();original=deepcopy(before);a=prepared_args();proposal=lesson()
    view=_control_view(before,machine_lesson=proposal,stats_peer=None,**{k:a[k]for k in ['opponent_species_id','opponent_level','opponent_base_stats','trainer_quote','expected_trainer_quote_sha256','preparation_configuration']})
    p=view['features']['party'];proof=view['conditional_preparation']
    assert proof['permutation']==[2,1] and proof['derived_specimen_order']==['other-same-species','lead']
    assert p['active_index']==0 and p['lead']==p['members'][0]
    assert p['members'][0]['stats']['attack']==137 and p['members'][1]['stats']['attack']==112
    assert p['members'][0]['moves'][0]['move_ref'].endswith(':085')
    assert p['members'][1]['moves'][0]['move_ref'].endswith(':059')
    assert p['members'][1]['moves'][0]['pp']==5 and p['members'][0]['moves'][0]['pp']==12
    assert [m['party_index']for m in p['members']]==[0,1] and before==original
    assert proof['observed_snapshot_sha256']==canonical_sha256(original)


def test_prepared_preview_matches_policy_from_independent_postpreparation_view():
    before=swap_facts();a=prepared_args();proposal=lesson()
    got=preview_fresh_trainer_control(before,**a,machine_lesson=proposal)
    # Independent explicit expected fixture: original observed snapshot remains intact.
    expected=deepcopy(before);party=expected['lesson']['party'];party[0]['moves'][0]=[59,5]
    party[0],party[1]=party[1],party[0]
    stats=expected['machine_boundary']['party_stats'];stats[0],stats[1]=stats[1],stats[0]
    view=_control_view(expected,machine_lesson=None,stats_peer=None,**{k:a[k]for k in ['opponent_species_id','opponent_level','opponent_base_stats']})
    base=BattleFeatureProjector(RED_BATTLE_CATALOG,mask_counter_without_prior_damage=True).project(view)
    prepared=PreparedRedBattleScenario(canonical_sha256(view),base)
    policy=RedTrainerPracticeOutcomePolicy('composition-fixture','fresh',a['model'])
    policy.choose_main(view,prepared);diag=policy.last_decision_diagnostics
    assert got.probabilities==pytest.approx(diag['control_probabilities'])
    assert np.asarray(got.candidate_vectors)==pytest.approx(np.asarray(diag['control_candidate_vectors']))
    assert got.proposed_move_slot==diag['proposed_move_slot'] and got.proposed_switch_slot==diag['proposed_switch_slot']
    assert got.selected_control==diag['control_choice']


def test_baseline_and_lesson_recompute_their_own_plans():
    before=facts();p=before['lesson']['party']
    p[0].update(level=63,hp=199,max_hp=199,moves=[[66,25],[70,15],[58,10],[57,15]])
    p[1].update(species_id=104,level=55,hp=160,max_hp=160,moves=[[85,15],[28,15],[42,20],[98,30]])
    a=prepared_args(TrainerPartyQuote(244,1,(TrainerPartyMember(120,87,54),),99,5346))
    a.update(opponent_species_id=120,opponent_level=54,opponent_base_stats=dict(hp=90,attack=70,defense=80,speed=70,special=95))
    proposal=dict(lesson=dict(party_slot=1,species_id=28,before_moves=[66,70,58,57],replace_slot=1,move_id=59),move_change=dict(proposed_current_pp=5))
    got=preview_machine_control(before,**a,machine_lesson=proposal)
    assert got.before.preparation['permutation']==[1,2]
    assert got.after.preparation['permutation']==[2,1]
    assert got.before.source_sha256==got.after.source_sha256==before['state_sha256']


@pytest.mark.parametrize('change',[
    lambda a:a.update(expected_trainer_quote_sha256='f'*64),
    lambda a:a.update(opponent_species_id=34),
    lambda a:a.update(opponent_level=43),
    lambda a:a['preparation_configuration'].update(maximum_level_deficit=100),
    lambda a:a.update(trainer_quote=None),
    lambda a:a.update(expected_trainer_quote_sha256=None),
])
def test_stale_quote_or_unqualified_preparation_fails_unavailable(change):
    a=prepared_args();change(a)
    with pytest.raises(OpeningPreviewUnavailable):preview_fresh_trainer_control(facts(),**a)


def test_preparation_does_not_bypass_missing_stats_or_contradictory_source():
    before=facts();peer=deepcopy(before);before.pop('machine_boundary');peer['state_sha256']='c'*64
    with pytest.raises(OpeningPreviewUnavailable):preview_machine_control(before,stats_peer=peer,**prepared_args())


