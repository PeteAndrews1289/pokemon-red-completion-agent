from __future__ import annotations

import runpy

import pytest

from pokemon_red_completion.progress_dashboard import ProgressDashboardError

SCRIPT = runpy.run_path("scripts/run_repeatable_battle_scenario_dashboard.py")


def _progress(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "pokemon.red.battle.repeatable-materialization-progress.v1",
        "partition": "train",
        "plan_sha256": "a" * 64,
        "source_catalog_sha256": "d" * 64,
        "materializer_source_commit": "b" * 40,
        "rom_sha256": "c" * 64,
        "total": 48,
        "completed": 12,
        "pending": 36,
        "started": 0,
        "succeeded": 11,
        "failed": 1,
        "completion_fraction": 0.25,
        "outcomes": 0,
        "model_fits": 0,
        "model_predictions": 0,
        "teacher_queries": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }
    value.update(changes)
    return value


def test_dashboard_explains_materialization_without_calling_it_training() -> None:
    snapshot = SCRIPT["repeatable_battle_materialization_snapshot"](_progress())

    assert snapshot.run_status == "running"
    assert snapshot.stage_progress == 0.25
    assert snapshot.experiment.zero_shot_completed == 11
    assert snapshot.experiment.adaptation_completed == 12
    assert snapshot.experiment.sealed_completed == 0
    assert snapshot.model.decisions == 0
    assert snapshot.model.teacher_queries == 0
    assert any("fits 0" in event and "outcomes 0" in event for event in snapshot.events)
    assert any("Crystal remain downstream" in event for event in snapshot.events)


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"total": 47}, "counts differ"),
        ({"completed": 11}, "completion count differs"),
        ({"plan_sha256": "short"}, "plan_sha256"),
        ({"source_catalog_sha256": "short"}, "source_catalog_sha256"),
        ({"partition": "sealed"}, "partition"),
    ),
)
def test_dashboard_rejects_incoherent_or_unbound_progress(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ProgressDashboardError, match=message):
        SCRIPT["repeatable_battle_materialization_snapshot"](_progress(**changes))


def test_dashboard_marks_interrupted_terminal_as_paused() -> None:
    snapshot = SCRIPT["repeatable_battle_materialization_snapshot"](
        _progress(
            completed=48,
            pending=0,
            started=1,
            succeeded=47,
            failed=0,
            completion_fraction=1.0,
        )
    )

    assert snapshot.run_status == "paused"
    assert "power-loss" in snapshot.message
