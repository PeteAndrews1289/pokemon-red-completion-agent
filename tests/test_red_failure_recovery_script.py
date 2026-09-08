"""Exercise recovery's actual serialized proposal interface, without a ROM."""
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)


def test_switch_history_comes_from_actual_battle_transitions_and_retains_ancestry():
    module = runpy.run_path(str(
        Path(__file__).resolve().parents[1] / "scripts/recover_red_player_failure.py"
    ))
    def snapshot(key, active, kind="trainer"):
        return {"snapshot_sha256": key, "snapshot": {"features": {
            "party": {"active_index": active}, "battle": {"kind": kind},
        }}}
    def episode(prior=None):
        metadata = {"schema": "pokemon.red.forced-recovery-header.v1",
                    "recovery": {"failure_episode_id": prior}} if prior else {}
        streams = {
            "snapshots": [snapshot("a", 0, "field"), snapshot("b", 1, "field"),
                          snapshot("c", 1), snapshot("d", 3), snapshot("e", 0)],
            "executions": [{"before_sha256": "a", "after_sha256": "b"},
                           {"before_sha256": "c", "after_sha256": "d"},
                           {"before_sha256": "d", "after_sha256": "d"},
                           {"before_sha256": "d", "after_sha256": "e"}],
        }
        return SimpleNamespace(read_header=lambda: {"metadata": metadata},
                               iter_stream=lambda name: iter(streams[name]))
    store = SimpleNamespace(
        open_failed_episode=lambda key: episode("parent" if key == "child" else None),
    )
    assert module["observed_failed_trainer_switches"](store, "parent") == (4, 1)
    assert module["observed_failed_trainer_switches"](store, "child") == (4, 1, 4, 1)


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
