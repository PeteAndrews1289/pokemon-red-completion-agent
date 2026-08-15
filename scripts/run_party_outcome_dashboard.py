#!/usr/bin/env python3
"""Show the first real Red party-development result in the view-only dashboard."""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.progress_dashboard import (  # noqa: E402
    DASHBOARD_DEFAULT_PORT,
    DashboardFrameObserver,
    DashboardState,
    ProgressDashboardError,
    ProgressDashboardServer,
)
from pokemon_red_completion.provenance import file_sha256  # noqa: E402
from pokemon_red_completion.red_party_development_dashboard import (  # noqa: E402
    party_development_dashboard_snapshot,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402

EVIDENCE_PATH = (
    PROJECT_ROOT / "docs" / "evidence" / "red-party-development-outcome-result-2026-08-14.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DASHBOARD_DEFAULT_PORT)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument(
        "--state",
        type=Path,
        default=None,
        help="optional authenticated source frame; sends no controller input",
    )
    return parser


def _load_evidence() -> dict[str, object]:
    value = json.loads(EVIDENCE_PATH.read_text(encoding="ascii"))
    if not isinstance(value, dict):
        raise ProgressDashboardError("party-development evidence must be a JSON object")
    return value


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ProgressDashboardError(f"party-development {key.replace('_', ' ')} is invalid")
    return value


def _publish_authenticated_source_frame(
    state: DashboardState,
    evidence: Mapping[str, object],
    *,
    rom: Path | None,
    source_state: Path | None,
) -> bool:
    if source_state is None:
        return False
    root = _mapping(evidence, "authenticated_root")
    expected_state = root.get("state_sha256")
    expected_rom = root.get("rom_sha256")
    if file_sha256(source_state) != expected_state:
        raise ProgressDashboardError("dashboard state is outside the published party result")
    rom_path = resolve_rom_path(rom)
    if verify_rom(rom_path).sha256 != expected_rom:
        raise ProgressDashboardError("dashboard ROM is outside the published party result")

    observer = DashboardFrameObserver(state, maximum_fps=30)
    with PyBoyAdapter(rom_path, frame_observer=observer) as emulator:
        emulator.load_state(source_state)
        emulator.tick(1)
    return True


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.duration_seconds < 0:
        raise ProgressDashboardError("dashboard duration must be non-negative")
    evidence = _load_evidence()
    state = DashboardState(party_development_dashboard_snapshot(evidence))
    frame_ready = _publish_authenticated_source_frame(
        state,
        evidence,
        rom=args.rom,
        source_state=args.state,
    )
    with ProgressDashboardServer(state, port=args.port) as dashboard:
        print(
            json.dumps(
                {
                    "schema": "pokemon-red-party-development-dashboard-v1",
                    "url": dashboard.url,
                    "view_only": True,
                    "authenticated_source_frame": frame_ready,
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
            while args.duration_seconds == 0 or time.monotonic() - started < args.duration_seconds:
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
