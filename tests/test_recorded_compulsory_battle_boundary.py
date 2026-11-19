from types import SimpleNamespace as N
import pytest
from pokemon_red_completion.red_integrated_play import observable_player_boundary,settled_player_boundary

def snapshot(battle,permission=True,**changes):
 facts=dict(battle_state=battle,compulsory_battle_control=permission,buttons_released=True,input_ready=True,owned_species=['a'],completed_objectives=['x'],specimen_counts={'a':1});facts.update(changes);return N(safe=True,facts=facts)

@pytest.mark.parametrize('battle',[1,2])
def test_explicit_compulsory_battle_is_observable_but_never_settled(battle):
 s=snapshot(battle);assert observable_player_boundary(s) and not settled_player_boundary(s)

@pytest.mark.parametrize('permission',[None,False,1,'true'])
@pytest.mark.parametrize('battle',[1,2])
def test_no_coerced_or_undeclared_battle_authority(permission,battle):
 assert not observable_player_boundary(snapshot(battle,permission))

@pytest.mark.parametrize('changes',[{'buttons_released':False},{'specimen_counts':{}},{'owned_species':['a','a']}])
def test_compulsory_marker_cannot_bypass_existing_state_proofs(changes):
 assert not observable_player_boundary(snapshot(2,**changes))

def test_other_battle_state_and_unsafe_source_are_not_admitted():
 assert not observable_player_boundary(snapshot(3));s=snapshot(2);s.safe=False;assert not observable_player_boundary(s)
