"""A late observed KO gets text settlement, never a second selected attack."""
from dataclasses import replace
import pytest
from pokemon_red_completion import battle_runtime as br
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import BattleMenuPhase,BattleMenuState
from test_battle_runtime import MeasuredTurnRuntime,_raw

def runtime_case(*,battle_state=1,roster=None,ko_at=2,settle_at=4,change=None):
 original=replace(_raw(),battle_state=battle_state)
 runtime=MeasuredTurnRuntime(raw=replace(original,first_party_pp=(34,30,30,11)),menu=BattleMenuState(BattleMenuPhase.UNKNOWN))
 runtime.read_enemy_party_roster_hp=lambda:roster
 pulses=[]
 def advance(action):
  if action.kind not in {MacroActionKind.CONFIRM,MacroActionKind.CANCEL}:return
  pulses.append(action.kind);n=len(pulses)
  assert action.kind is (MacroActionKind.CANCEL if n<=ko_at else MacroActionKind.CONFIRM)
  if n==ko_at:runtime.raw=replace(runtime.raw,enemy_hp=0)
  if n==3 and change=='selected_pp':runtime.raw=replace(runtime.raw,first_party_pp=(35,30,30,11))
  if n==3 and change=='other_pp':runtime.raw=replace(runtime.raw,first_party_pp=(34,29,30,11))
  if n==3 and change=='living_foe':runtime.raw=replace(runtime.raw,enemy_hp=3)
  if n==settle_at:runtime.raw=replace(runtime.raw,battle_state=0)
 runtime.on_action=advance
 return original,runtime,pulses

def settle(original,runtime,*,battle_state=1):
 token=br._ACTIVE_BATTLE_STATE.set(battle_state)
 try:
  return br._await_next_battle_decision(runtime,runtime,expected_map=original.map_id,expected_battle_state=battle_state,initial_raw=original,slot=1,move_executed=True,timing=replace(br.BattleRuntimeTiming(),max_post_attack_transition_pulses=2),label='late KO test')
 finally:br._ACTIVE_BATTLE_STATE.reset(token)

@pytest.mark.parametrize('battle_state,roster',[(1,None),(2,(0,)),(2,(0,0))])
def test_late_proved_final_knockout_gets_one_finite_text_allowance(battle_state,roster):
 original,runtime,pulses=runtime_case(battle_state=battle_state,roster=roster)
 assert settle(original,runtime,battle_state=battle_state)
 assert runtime.raw.battle_state==0 and len(pulses)==4
 assert runtime.raw.first_party_pp==(34,30,30,11)
 assert all(a.kind in {MacroActionKind.CONFIRM,MacroActionKind.CANCEL,MacroActionKind.WAIT}for a in runtime.actions)

@pytest.mark.parametrize('roster',[None,(),(0,11),(False,),(0,None)])
def test_active_trainer_ko_without_defeated_roster_gets_no_reserve(roster):
 original,runtime,pulses=runtime_case(battle_state=2,roster=roster)
 with pytest.raises(br.BattleRuntimeError,match='next decision boundary'):settle(original,runtime,battle_state=2)
 assert len(pulses)==2

@pytest.mark.parametrize('knocked_out',[False,True])
def test_no_progress_or_stuck_terminal_remains_finitely_bounded(knocked_out):
 original,runtime,pulses=runtime_case(ko_at=2 if knocked_out else 99,settle_at=99)
 with pytest.raises(br.BattleRuntimeError,match='next decision boundary'):settle(original,runtime)
 assert len(pulses)==(4 if knocked_out else 2)

@pytest.mark.parametrize('change',['selected_pp','other_pp','living_foe'])
def test_terminal_reserve_keeps_PP_and_terminal_evidence_guards(change):
 original,runtime,pulses=runtime_case(change=change)
 with pytest.raises(br.BattleRuntimeError):settle(original,runtime)
 assert len(pulses)==3
