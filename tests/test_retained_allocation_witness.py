from dataclasses import replace
import pytest
from test_red_battle_move_learning import automatic_learning_states
from test_battle_runtime import MeasuredTurnRuntime
from pokemon_red_completion import battle_runtime as runtime
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import BattleMenuState,BattleMenuPhase

def states():
 a,w=automatic_learning_states();a=replace(a,enemy_party_position=2,enemy_hp=12)
 w=replace(w,enemy_party_position=1,enemy_hp=0)
 b=replace(w,enemy_party_position=2,enemy_hp=12)
 return a,w,b

def test_exact_observed_allocation_survives_next_foe_matching_initial_identity():
 a,w,b=states()
 with pytest.raises(runtime.BattleRuntimeError):runtime._verify_selected_turn_pp(a,b,slot=1,label='no witness')
 runtime._verify_selected_turn_pp(a,b,slot=1,label='retained',automatic_allocation_witness=w)

@pytest.mark.parametrize('fault',['no_faint','no_level','wrong_species','wrong_slot','PP','double_spend','other_spend','lost_move','changed_active'])
def test_unverified_or_changed_allocation_never_excuses_resource_errors(fault):
 a,w,b=states()
 if fault=='no_faint':w=replace(w,enemy_hp=12,enemy_party_position=2)
 elif fault=='no_level':w=replace(w,active_party_level=16)
 elif fault=='wrong_species':w=replace(w,active_party_species_id=1)
 elif fault=='wrong_slot':w=replace(w,first_party_moves=(72,15,78,0),first_party_pp=(7,30,30,0))
 elif fault=='PP':b=replace(b,first_party_pp=(7,30,20,29))
 elif fault=='double_spend':b=replace(b,first_party_pp=(6,30,20,30))
 elif fault=='other_spend':b=replace(b,first_party_pp=(7,29,20,30))
 elif fault=='lost_move':b=replace(b,first_party_moves=(72,15,71,0))
 else:b=replace(b,active_party_index=1)
 with pytest.raises(runtime.BattleRuntimeError):runtime._verify_selected_turn_pp(a,b,slot=1,label='strict',automatic_allocation_witness=w)

class LearningSendout(MeasuredTurnRuntime):
 def __init__(self):
  self.initial,w,self.final=states();super().__init__(raw=w,menu=BattleMenuState(BattleMenuPhase.UNKNOWN))
 def execute(self,action):
  assert action.kind is not MacroActionKind.CONFIRM
  if action.kind is MacroActionKind.WAIT:self.raw=self.final;self.menu=BattleMenuState(BattleMenuPhase.MAIN,selected_main_command=0)
  return super().execute(action)

def test_bounded_settlement_itself_latches_observed_allocation_without_another_attack():
 p=LearningSendout();token=runtime._ACTIVE_BATTLE_STATE.set(2)
 try:
  assert runtime._await_next_battle_decision(p,p,expected_map=p.initial.map_id,expected_battle_state=2,initial_raw=p.initial,slot=1,move_executed=True,timing=runtime.BattleRuntimeTiming(max_post_attack_transition_pulses=6),label='learning sendout') is True
 finally:runtime._ACTIVE_BATTLE_STATE.reset(token)
