from __future__ import annotations

import json

from pokemon_red_completion.play import QualifiedPlayProgress
from pokemon_red_completion.progress_dashboard import DashboardState
from pokemon_red_completion.red_training_runtime import RedTrainingDashboardTracker


def _status(state: DashboardState) -> dict[str, object]:
    payload, _version = state.status_bytes()
    document = json.loads(payload)
    assert isinstance(document, dict)
    return document


def test_red_training_tracker_projects_live_route_and_policy_updates() -> None:
    now = [100.0]
    state = DashboardState()
    tracker = RedTrainingDashboardTracker(state, clock=lambda: now[0])
    tracker.start()
    now[0] = 102.0
    tracker.on_progress(
        QualifiedPlayProgress(
            checkpoint_id="brock_defeated",
            label="Defeated Brock",
            completed=20,
            total=100,
            frames_executed=7200,
        )
    )
    tracker.on_battle_policy(
        {
            "decisions": 2,
            "model_decisions": 1,
            "teacher_queries": 2,
            "teacher_fallbacks": 1,
            "correction_records": 1,
            "fallback_reasons": {"teacher_disagreement": 1},
        }
    )
    tracker.on_team_policy({"decisions": 3, "agreements": 2})

    document = _status(state)
    assert document["run_status"] == "running"
    assert document["stage"] == "Defeated Brock"
    assert document["frame_count"] == 7200
    assert document["stage_progress"] == 0.2
    assert document["model"]["decisions"] == 2  # type: ignore[index]
    assert document["live_evaluation"]["teacher_agreement_rate"] == 0.5  # type: ignore[index]
    assert document["live_evaluation"]["team_accuracy"] == 2 / 3  # type: ignore[index]
    assert document["controller_endpoints"] == 0


def test_red_training_frame_observer_publishes_pixels_and_heartbeat() -> None:
    state = DashboardState()
    tracker = RedTrainingDashboardTracker(state)
    observer = tracker.frame_observer

    assert observer.wants_frame(60)
    observer.publish_frame(1, 1, bytes((4, 5, 6)), 60)

    document = _status(state)
    assert document["frame_count"] == 60
    assert document["dashboard"]["frame_ready"] is True  # type: ignore[index]


def test_red_training_failure_status_never_includes_private_exception_text() -> None:
    state = DashboardState()
    tracker = RedTrainingDashboardTracker(state)

    tracker.fail_run(exception_type="QualifiedPlayError")

    encoded = json.dumps(_status(state), sort_keys=True)
    assert "QualifiedPlayError" in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_red_training_diagnostic_snapshot_retains_latest_semantic_counters() -> None:
    state = DashboardState()
    tracker = RedTrainingDashboardTracker(state)
    tracker.start()
    tracker.on_progress(
        QualifiedPlayProgress(
            checkpoint_id="saffron_arrival",
            label="Reached Saffron",
            completed=41,
            total=100,
            frames_executed=12345,
        )
    )
    tracker.on_battle_policy({"decisions": 12, "agreements": 9})
    tracker.on_team_policy({"decisions": 7, "agreements": 6})

    snapshot = tracker.diagnostic_snapshot()

    assert snapshot["stage"] == "Reached Saffron"
    assert snapshot["frame_count"] == 12345
    assert snapshot["verified_checkpoints"] == 1
    assert snapshot["battle_policy"] == {"decisions": 12, "agreements": 9}
    assert snapshot["team_policy"] == {"decisions": 7, "agreements": 6}
