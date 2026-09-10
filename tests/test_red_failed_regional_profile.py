import json
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_failed_regional_profile import committed_failed_source_profile
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)


@pytest.mark.parametrize(
    "damage", [None, "hash", "absent", "episode", "negative", "bool", "range", "profile"]
)
def test_failed_selected_profile_uses_exact_record_without_resampling(damage):
    payload = build_red_goal_context_profile_payload(
        profile_id="failed-source",
        providers=(
            (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
            (GoalKind.DEVELOP_TEAM, RedGoalMechanic.BALANCED_TEAM, {}),
            (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
        ),
    )
    profile = parse_red_goal_context_profile(payload)
    doc = {
        "episode_id": "failed",
        "selection": {"selected_candidate_index": 1},
        "candidates": [
            {"profile": "must not parse the unselected candidate"},
            {"profile": json.loads(payload), "profile_sha256": profile.profile_sha256},
        ],
    }
    metadata = {"regional_choice_record_sha256": "a" * 64, "profile_sha256": profile.profile_sha256}
    record = SimpleNamespace(summary=SimpleNamespace(record_sha256="a" * 64), read=lambda: doc)
    if damage == "hash":
        record.summary.record_sha256 = "b" * 64
    elif damage == "absent":
        record = None
    elif damage == "episode":
        doc["episode_id"] = "different"
    elif damage in {"negative", "bool", "range"}:
        doc["selection"]["selected_candidate_index"] = {"negative": -1, "bool": True, "range": 2}[
            damage
        ]
    elif damage == "profile":
        metadata["profile_sha256"] = "f" * 64
    store = SimpleNamespace(
        open_failed_episode=lambda _: SimpleNamespace(read_header=lambda: {"metadata": metadata}),
        find_sealed_record=lambda *a, **kw: record,
    )
    if damage:
        with pytest.raises(ValueError, match="failed regional choice"):
            committed_failed_source_profile(store, "failed")
    else:
        assert committed_failed_source_profile(store, "failed") == profile


def test_nonregional_failure_does_not_require_a_choice_record():
    store = SimpleNamespace(
        open_failed_episode=lambda _: SimpleNamespace(read_header=lambda: {"metadata": {}})
    )
    assert committed_failed_source_profile(store, "failed") is None


@pytest.mark.parametrize("bad", ["sequence", "boolean", "ledger", "session", None])
def test_registered_recovery_requires_ledger_wiring_before_gameplay(bad):
    from recover_red_player_failure import require_registered_recovery_binding

    ready = SimpleNamespace(
        registration_policy=object(),
        registration_sequence=6,
        registration_ledger="ledger",
        registration_session_record_id="session",
    )
    if bad == "sequence":
        ready.registration_sequence = 0
    elif bad == "boolean":
        ready.registration_sequence = True
    elif bad == "ledger":
        ready.registration_ledger = None
    elif bad == "session":
        ready.registration_session_record_id = None
    if bad:
        with pytest.raises(ValueError, match="registered recovery requires"):
            require_registered_recovery_binding(ready)
    else:
        require_registered_recovery_binding(ready)
    require_registered_recovery_binding(SimpleNamespace())
