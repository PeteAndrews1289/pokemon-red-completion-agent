#!/usr/bin/env python3
"""Show the first real Red outcome-learning result in the view-only dashboard."""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    open_battle_scenario_capture,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.progress_dashboard import (  # noqa: E402
    DASHBOARD_DEFAULT_PORT,
    DashboardFrameObserver,
    DashboardState,
    ProgressDashboardError,
    ProgressDashboardServer,
)
from pokemon_red_completion.red_battle_outcome_dashboard import (  # noqa: E402
    battle_outcome_dashboard_snapshot,
)
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402

EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-battle-outcome-learning-cycle-2026-08-14.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DASHBOARD_DEFAULT_PORT)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--capture-state", type=Path, default=None)
    parser.add_argument("--capture-manifest", type=Path, default=None)
    return parser


def _load_evidence() -> dict[str, object]:
    value = json.loads(EVIDENCE_PATH.read_text(encoding="ascii"))
    if not isinstance(value, dict):
        raise ProgressDashboardError("battle outcome evidence must be a JSON object")
    return value


def _publish_authenticated_frame(
    state: DashboardState,
    evidence: dict[str, object],
    *,
    rom: Path | None,
    capture_state: Path | None,
    capture_manifest: Path | None,
) -> bool:
    if (capture_state is None) != (capture_manifest is None):
        raise ProgressDashboardError(
            "capture state and manifest must be supplied together"
        )
    if capture_state is None or capture_manifest is None:
        return False
    capture = open_battle_scenario_capture(capture_state, capture_manifest)
    rows = evidence.get("captures")
    if not isinstance(rows, list):
        raise ProgressDashboardError("battle outcome capture catalog is invalid")
    expected_manifests = {
        row.get("manifest_sha256")
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("manifest_sha256"), str)
    }
    if capture.manifest_sha256 not in expected_manifests:
        raise ProgressDashboardError("dashboard capture is outside the published result")

    observer = DashboardFrameObserver(state, maximum_fps=30)
    with PyBoyAdapter(resolve_rom_path(rom), frame_observer=observer) as emulator:
        emulator.load_state_bytes(capture.state_bytes)
        emulator.tick(1)
    return True


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.duration_seconds < 0:
        raise ProgressDashboardError("dashboard duration must be non-negative")
    evidence = _load_evidence()
    state = DashboardState(battle_outcome_dashboard_snapshot(evidence))
    frame_ready = _publish_authenticated_frame(
        state,
        evidence,
        rom=args.rom,
        capture_state=args.capture_state,
        capture_manifest=args.capture_manifest,
    )
    with ProgressDashboardServer(state, port=args.port) as dashboard:
        print(
            json.dumps(
                {
                    "schema": "pokemon-red-battle-outcome-dashboard-v1",
                    "url": dashboard.url,
                    "view_only": True,
                    "authenticated_frame": frame_ready,
                    "teacher_queries": 0,
                    "authority_promoted": False,
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        if not args.no_browser:
            webbrowser.open(dashboard.url)
        started = time.monotonic()
        try:
            while (
                args.duration_seconds == 0
                or time.monotonic() - started < args.duration_seconds
            ):
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
