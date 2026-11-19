from types import SimpleNamespace as N
from copy import deepcopy
import pytest
from pokemon_red_completion.red_player_forced_motion import _loan_poison_boundary

@pytest.mark.parametrize("fault",[None,"custody","actor","poison","active","pp_gain","moves","species","healed","later_heal","unknown_control","frame","no_move"])
def test_retained_loan_poison_witness_preserves_actual_hp_and_rejects_unproved_changes(fault):
    raw=N(party_count=2,party_species_ids=(1,2),party_levels=(10,11),party_max_hp=(30,30),party_moves=((1,2),(1,2)),party_pp=((10,9),(10,10)),party_hp=(20,0),party_status=(0,0))
    observed=dict(party_species_ids=(1,2),party_levels=(10,11),party_max_hp=(30,30),party_moves=((1,2),(1,2)),party_pp=((10,10),(10,10)),party_hp=(21,10),party_status=(0,8),battle_state=1,active_party_index=0)
    payload=dict(source="native_level_evolution",actor="rule_based_support",selection_validated=True,execution_confirmed=False,observed=observed)
    events=[dict(kind="wild_training_move",frame=10,payload=payload)]+[dict(kind="wild_training_control",frame=11+i,payload=dict(action=c))for i,c in enumerate(("seek","fight","flee","heal"))]
    proof=dict(schema="pokemon.red.retained-loan-poison.v1",named_loan_verified=True,events=events,native_frames=20)
    if fault=="custody":proof["named_loan_verified"]=False
    if fault=="actor":payload["actor"]="unknown"
    if fault=="poison":observed["party_status"]=(0,0)
    if fault=="active":observed["active_party_index"]=1
    if fault=="pp_gain":raw.party_pp=((10,11),(10,10))
    if fault=="moves":raw.party_moves=((1,3),(1,2))
    if fault=="species":raw.party_species_ids=(1,3)
    if fault=="healed":raw.party_hp=(22,0)
    if fault=="later_heal":events[1]["payload"]["action"]="heal"
    if fault=="unknown_control":events[1]["payload"]["action"]="trade"
    if fault=="frame":proof["native_frames"]=9
    if fault=="no_move":events.pop(0)
    before=deepcopy((raw,proof));answer=_loan_poison_boundary(raw,proof)
    assert vars(raw)==vars(before[0]) and proof==before[1]
    assert answer==(((20,10),(0,8))if fault is None else None)
