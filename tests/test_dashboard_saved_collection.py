from __future__ import annotations

import json
import runpy
import time
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.dashboard_relay import DashboardRelayState, snapshot_from_public_status
from pokemon_red_completion.progress_dashboard import (
    _DASHBOARD_HTML,
    DashboardSavedCollection,
    DashboardSnapshot,
    DashboardState,
    ProgressDashboardError,
)

ROOT = Path(__file__).resolve().parents[1]
OVERVIEW = runpy.run_path(str(ROOT / "scripts/run_product_focus_dashboard.py"))


def saved() -> DashboardSavedCollection:
    return DashboardSavedCollection(
        "2026-09-07 10:11 UTC", "Route 24", 26, 21, 23, 4, 109, "a" * 64
    )


def test_saved_state_does_not_claim_live_observation() -> None:
    snapshot = DashboardSnapshot(
        "Red",
        "waiting",
        "Review",
        "Saved results",
        collection_observed=False,
        saved_collection=saved(),
    )
    status = json.loads(DashboardState(snapshot).status_bytes()[0])
    assert status["collection"]["observed"] is False
    assert status["saved_collection"]["live"] is False
    assert status["saved_collection"]["living_species"] == 21
    assert status["saved_collection"]["specimens"] == 23
    assert status["dashboard"]["frame_age_seconds"] is None
    assert snapshot_from_public_status(status).saved_collection == saved()
    status["saved_collection"]["live"] = True
    with pytest.raises(ProgressDashboardError, match="cannot claim live"):
        snapshot_from_public_status(status)


@pytest.mark.parametrize(
    "change",
    [
        {"living_species": 27},
        {"specimens": 20},
        {"specimens": 247},
        {"capture_items": True},
        {"money": -1},
        {"checkpoint_sha256": "invalid"},
    ],
)
def test_saved_state_rejects_inconsistent_or_untyped_counts(change: dict) -> None:
    with pytest.raises(ProgressDashboardError):
        replace(saved(), **change)


def test_committed_saved_state_is_loaded_by_exact_hash(tmp_path: Path) -> None:
    actual = OVERVIEW["_load_saved_collection"]()
    assert (actual.living_species, actual.specimens, actual.capture_items, actual.money) == (
        21,
        23,
        4,
        109,
    )
    reference = json.loads((ROOT / "configs/dashboard-saved-state.json").read_text())
    reference["sha256"] = "0" * 64
    changed = tmp_path / "reference.json"
    changed.write_text(json.dumps(reference))
    with pytest.raises(ProgressDashboardError, match="unavailable or changed"):
        OVERVIEW["_load_saved_collection"](changed)
    assert OVERVIEW["_load_saved_collection"](tmp_path / "absent.json") is None


def test_saved_counts_stay_separate_when_live_feed_arrives() -> None:
    overview = DashboardSnapshot(
        "Red",
        "waiting",
        "Review",
        "Saved results",
        collection_observed=False,
        saved_collection=saved(),
    )
    live = DashboardSnapshot(
        "Red",
        "running",
        "Capture",
        "Playing",
        registered_species=28,
        living_species=22,
        collection_target=151,
    )
    relay = DashboardRelayState(overview, live_port=18769)
    metadata = json.loads(DashboardState(live).status_bytes()[0])["dashboard"]
    relay._remote = (live, metadata, time.monotonic())
    status = json.loads(relay.status_bytes()[0])
    assert status["collection"]["living"] == 22
    assert status["saved_collection"]["living_species"] == 21
    assert status["saved_collection"]["live"] is False
    assert b"LAST VERIFIED SAVE" in _DASHBOARD_HTML
    assert b"Not live gameplay" in _DASHBOARD_HTML
    assert b"const savedOnly = !observed && savedCollection" in _DASHBOARD_HTML
