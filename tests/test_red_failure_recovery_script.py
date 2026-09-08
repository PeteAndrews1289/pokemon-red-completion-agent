"""Exercise recovery's actual serialized proposal interface, without a ROM."""
import json
import runpy
from pathlib import Path

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)


def test_recovery_restores_canonical_existing_proposal_without_resampling():
    module = runpy.run_path(str(
        Path(__file__).resolve().parents[1] / "scripts/recover_red_player_failure.py"
    ))
    payload = build_red_goal_context_profile_payload(
        profile_id="recovery-test",
        providers=(
            (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
            (GoalKind.DEVELOP_TEAM, RedGoalMechanic.BALANCED_TEAM, {}),
            (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
        ),
    )
    original = parse_red_goal_context_profile(payload)
    document = {"profile": json.loads(payload), "profile_sha256": original.profile_sha256}
    assert module["restored_proposal_profile"](document) == original
    assert document["profile"] == json.loads(payload)
    with pytest.raises(ValueError, match="identity differs"):
        module["restored_proposal_profile"]({**document, "profile_sha256": "f" * 64})
