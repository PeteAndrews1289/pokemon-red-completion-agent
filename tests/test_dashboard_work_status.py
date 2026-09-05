from __future__ import annotations

import json

import pytest

from pokemon_red_completion.dashboard_work_status import (
    DashboardWorkStatusError,
    load_dashboard_work_status,
    write_dashboard_work_status,
)
from pokemon_red_completion.progress_dashboard import DashboardWorkState


def test_work_status_round_trips_and_absent_file_is_idle(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "status" / "work.json"
    assert load_dashboard_work_status(path).status == "idle"
    expected = DashboardWorkState(
        status="testing",
        headline="Testing the dashboard",
        detail="Targeted observer checks are running.",
        current_step="Run view-only safety tests",
        next_step="Publish one coherent checkpoint",
        completed_units=3,
        total_units=5,
        updated_at_utc="2026-09-05T19:30:00Z",
    )

    write_dashboard_work_status(path, expected)

    assert load_dashboard_work_status(path) == expected
    document = json.loads(path.read_text(encoding="ascii"))
    assert document["schema"] == "pokemon.core.dashboard-work-status.v1"
    assert "progress" not in document


def test_work_status_fails_closed_on_unknown_fields(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "work.json"
    path.write_text('{"schema":"pokemon.core.dashboard-work-status.v1"}', encoding="ascii")

    with pytest.raises(DashboardWorkStatusError, match="authentication"):
        load_dashboard_work_status(path)
