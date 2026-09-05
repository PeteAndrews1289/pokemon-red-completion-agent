#!/usr/bin/env python3
"""Publish a path-free engineering update to the local project dashboard."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.dashboard_work_status import (  # noqa: E402
    write_dashboard_work_status,
)
from pokemon_red_completion.progress_dashboard import DashboardWorkState  # noqa: E402

DEFAULT_STATUS_PATH = PROJECT_ROOT / ".dashboard-status" / "product-focus.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status",
        choices=("idle", "working", "testing", "waiting", "blocked", "complete"),
        required=True,
    )
    parser.add_argument("--headline", required=True)
    parser.add_argument("--detail", required=True)
    parser.add_argument("--current-step", required=True)
    parser.add_argument("--next-step", required=True)
    parser.add_argument("--completed-units", type=int, default=0)
    parser.add_argument("--total-units", type=int, default=0)
    parser.add_argument("--status-file", type=Path, default=DEFAULT_STATUS_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    status = DashboardWorkState(
        status=args.status,
        headline=args.headline,
        detail=args.detail,
        current_step=args.current_step,
        next_step=args.next_step,
        completed_units=args.completed_units,
        total_units=args.total_units,
        updated_at_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    write_dashboard_work_status(args.status_file, status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
