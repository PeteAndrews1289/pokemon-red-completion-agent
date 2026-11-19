from test_battle_runtime import MeasuredTurnRuntime
from pokemon_red_completion.battle_runtime import advance_battle_to_policy_boundary
from pokemon_red_completion.observation import BattleMenuState,BattleMenuPhase,MapId
from pokemon_red_completion.actions import MacroActionKind
import pytest

@pytest.mark.parametrize('arrives',[False,True])
def test_visible_prompt_is_yielded_without_confirming_a_party_choice(arrives):
 p=MeasuredTurnRuntime(menu=BattleMenuState(BattleMenuPhase.UNKNOWN));visible=[not arrives];p.trainer_switch_prompt_visible=lambda raw:visible[0]
 def action(a):
  if a.kind is MacroActionKind.CONFIRM:
   assert not visible[0];visible[0]=True
 p.on_action=action
 b=advance_battle_to_policy_boundary(p,p,expected_map=MapId.CERULEAN_CITY,expected_battle_state=2)
 assert b.actions_executed==(2 if arrives else 0)
 assert sum(a.kind is MacroActionKind.CONFIRM for a in p.actions)==int(arrives)
