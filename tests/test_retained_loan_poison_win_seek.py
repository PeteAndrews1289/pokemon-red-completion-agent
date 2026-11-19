from types import SimpleNamespace as N
from copy import deepcopy
import pytest
from pokemon_red_completion.red_player_forced_motion import _loan_poison_boundary

@pytest.mark.parametrize("fault",[None,"no_xp","zero_xp","delta","xp_actor","xp_source","recipient","late_xp","no_seek","fight","heal","unknown_event","custody","active","poison","hp_gain","pp_gain","frame"])
def test_win_then_seek_poison_witness_is_narrow_and_read_only(fault):
    raw=N(party_count=2,party_species_ids=(1,2),party_levels=(10,11),party_max_hp=(30,30),party_moves=((1,2),(1,2)),party_pp=((10,9),(10,10)),party_hp=(20,0),party_status=(0,0))
    old=dict(party_species_ids=(1,2),party_levels=(10,11),party_max_hp=(30,30),party_moves=((1,2),(1,2)),party_pp=((10,10),(10,10)),party_hp=(21,1),party_status=(0,8),battle_state=1,active_party_index=0)
    move=dict(kind="wild_training_move",frame=10,payload=dict(source="native_level_evolution",actor="rule_based_support",selection_validated=True,execution_confirmed=False,observed=old))
    xp=dict(kind="wild_training_experience",frame=12,payload=dict(source="native_level_evolution",actor="rule_based_support",experience_before=100,experience_after=150,experience_gained=50,recipient_species_id_before=1,recipient_species_id_after=1))
    events=[move,xp,dict(kind="wild_training_control",frame=14,payload=dict(action="seek")),dict(kind="wild_training_control",frame=16,payload=dict(action="seek"))]
    proof=dict(schema="pokemon.red.retained-loan-poison.v1",named_loan_verified=True,events=events,native_frames=20)
    if fault=="no_xp":events.remove(xp)
    if fault=="zero_xp":xp["payload"].update(experience_after=100,experience_gained=0)
    if fault=="delta":xp["payload"]["experience_gained"]=49
    if fault=="xp_actor":xp["payload"]["actor"]="unknown"
    if fault=="xp_source":xp["payload"]["source"]="unrelated"
    if fault=="recipient":xp["payload"].update(recipient_species_id_before=3,recipient_species_id_after=3)
    if fault=="late_xp":xp["frame"]=18
    if fault=="no_seek":events[:]=[move,xp]
    if fault in ("fight","heal"):events[-1]["payload"]["action"]=fault
    if fault=="unknown_event":events.append(dict(kind="trade",frame=18,payload={}))
    if fault=="custody":proof["named_loan_verified"]=False
    if fault=="active":old["active_party_index"]=1
    if fault=="poison":old["party_status"]=(0,0)
    if fault=="hp_gain":raw.party_hp=(22,0)
    if fault=="pp_gain":raw.party_pp=((10,11),(10,10))
    if fault=="frame":proof["native_frames"]=15
    before=deepcopy((raw,proof));answer=_loan_poison_boundary(raw,proof)
    assert vars(raw)==vars(before[0]) and proof==before[1]
    assert answer==(((20,1),(0,8))if fault is None else None)
