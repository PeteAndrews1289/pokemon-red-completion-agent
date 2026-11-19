"""V16 players can serialize a valid lower-feature V12 menu for replay."""
import pytest
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_goal_policy import living_dex_option_kind_for_goal,LivingDexGoalPolicyError
from pokemon_red_completion.living_dex_option_value import option_feature_names

@pytest.mark.parametrize("kind",list(GoalKind))
def test_existing_v12_uses_the_same_semantic_kind_mapping(kind):
 assert len(option_feature_names(12))>0
 assert living_dex_option_kind_for_goal(kind,feature_version=12)is living_dex_option_kind_for_goal(kind,feature_version=13)

@pytest.mark.parametrize("bad",[0,17,True,"12",None])
def test_unknown_or_implicit_version_stays_rejected(bad):
 with pytest.raises(LivingDexGoalPolicyError):living_dex_option_kind_for_goal(GoalKind.DEVELOP_TEAM,feature_version=bad)
