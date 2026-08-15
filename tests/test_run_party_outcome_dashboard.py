from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from pokemon_red_completion.progress_dashboard import DashboardState, ProgressDashboardError
from pokemon_red_completion.red_party_development_dashboard import (
    party_development_dashboard_snapshot,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(str(PROJECT_ROOT / "scripts" / "run_party_outcome_dashboard.py"))


def test_party_dashboard_source_frame_is_optional() -> None:
    evidence = SCRIPT["_load_evidence"]()
    state = DashboardState(party_development_dashboard_snapshot(evidence))

    assert (
        SCRIPT["_publish_authenticated_source_frame"](
            state,
            evidence,
            rom=None,
            source_state=None,
        )
        is False
    )


def test_party_dashboard_rejects_an_unbound_state_before_opening_a_rom(
    tmp_path: Path,
) -> None:
    evidence = SCRIPT["_load_evidence"]()
    state = DashboardState(party_development_dashboard_snapshot(evidence))
    source_state = tmp_path / "wrong.state"
    source_state.write_bytes(b"not the authenticated state")

    with pytest.raises(ProgressDashboardError, match="outside the published party result"):
        SCRIPT["_publish_authenticated_source_frame"](
            state,
            evidence,
            rom=None,
            source_state=source_state,
        )
