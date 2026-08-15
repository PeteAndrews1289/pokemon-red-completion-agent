#!/usr/bin/env python3
"""Show the honest Red completion-aware party-learning readiness gate."""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.party_development_readiness_dashboard import (  # noqa: E402
    party_development_readiness_dashboard_snapshot,
)
from pokemon_red_completion.progress_dashboard import (  # noqa: E402
    DASHBOARD_DEFAULT_PORT,
    DashboardState,
    ProgressDashboardError,
    ProgressDashboardServer,
)

EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "party-development-v2-readiness-2026-08-15.json"
)
DEFAULT_READINESS_PORT = DASHBOARD_DEFAULT_PORT + 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_READINESS_PORT)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    return parser


def _load_evidence() -> dict[str, object]:
    value = json.loads(EVIDENCE_PATH.read_text(encoding="ascii"))
    if not isinstance(value, dict):
        raise ProgressDashboardError(
            "party-development readiness evidence must be a JSON object"
        )
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.duration_seconds < 0:
        raise ProgressDashboardError("dashboard duration must be non-negative")
    evidence = _load_evidence()
    state = DashboardState(
        party_development_readiness_dashboard_snapshot(evidence)
    )
    with ProgressDashboardServer(state, port=args.port) as dashboard:
        print(
            json.dumps(
                {
                    "schema": "pokemon-party-development-v2-readiness-dashboard-v1",
                    "url": dashboard.url,
                    "view_only": True,
                    "outcome_collection_progress": "0/14",
                    "model_fit": False,
                    "teacher_queries": 0,
                    "controller_actions": 0,
                    "sealed_red_cases_opened": 0,
                    "crystal_cases_opened": 0,
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
