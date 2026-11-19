#!/usr/bin/env python3
"""Open a Mac-local spectator for one run. This never launches or resumes Red."""

import argparse
import hashlib
import json
import sys
import time
import webbrowser
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pokemon_red_completion.progress_dashboard import ProgressDashboardServer  # noqa: E402
from pokemon_red_completion.red_run_spectator import RedRunReader, RunViewerState  # noqa: E402



class CampaignRunReader:
    """Follow one worker's receipt-backed versions without changing viewer ports."""

    def __init__(self, root: Path, roster_path: Path) -> None:
        self.root = root.resolve(strict=True)
        self.roster_path = roster_path.resolve(strict=True)
        self.reader = RedRunReader(self.root)
        self.identity = json.loads((self.root / "PLAN.json").read_bytes())["campaign_run_id"]

    def read(self):
        try:
            next_root = self._latest_ready_root()
        except (OSError, ValueError, KeyError, TypeError):
            next_root = self.reader.root
        if next_root is not None and next_root != self.reader.root:
            reader = RedRunReader(next_root)
            snapshot, data = reader.read()
            splits = data.get("milestone_splits") or {}
            if not data.get("milestone_split_error") and (
                splits.get("identity", {}).get("campaign_run_id") == self.identity
            ):
                self.reader = reader
                return snapshot, data
        return self.reader.read()

    def _latest_ready_root(self):
        roster = json.loads(self.roster_path.read_bytes())
        rows = [row for row in roster["runs"] if row.get("campaign_run_id") == self.identity]
        if len(rows) != 1 or Path(rows[0]["player_root"]).resolve() != self.root:
            return None
        for entry in reversed(rows[0].get("continuations", [])):
            if not entry.get("dispatch_receipt"):
                continue
            candidate = Path(entry["player_root"]).resolve(strict=True)
            if candidate.name != self.root.name or not candidate.is_relative_to(self.roster_path.parent):
                continue
            plan = candidate / "PLAN.json"
            live = entry["live_plan"]
            if plan != Path(live["path"]) or hashlib.sha256(plan.read_bytes()).hexdigest() != live["sha256"]:
                continue
            if json.loads(plan.read_bytes()).get("campaign_run_id") != self.identity:
                continue
            launch = candidate / "LAUNCH.json"
            dispatch = entry["dispatch_receipt"]
            if launch != Path(dispatch["path"]) or hashlib.sha256(launch.read_bytes()).hexdigest() != dispatch["sha256"]:
                continue
            return candidate
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--live-port", type=int, default=8769)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--baseline-run-dir", type=Path)
    parser.add_argument("--campaign-roster", type=Path)
    parser.add_argument("--duration-seconds", type=int, default=0)
    args = parser.parse_args(argv)
    if args.port == args.live_port or args.duration_seconds < 0:
        parser.error("viewer/feed ports must differ and duration must be nonnegative")
    def reader_for(root):
        if args.campaign_roster is not None:
            return CampaignRunReader(root, args.campaign_roster)
        return RedRunReader(root)

    baseline = reader_for(args.baseline_run_dir) if args.baseline_run_dir else None
    state = RunViewerState(reader_for(args.run_dir), live_port=args.live_port, baseline_reader=baseline)
    with ProgressDashboardServer(state, port=args.port) as server:
        url = server.url + "watch"
        print(
            json.dumps(
                dict(url=url, view_only=True, run=state.reader.root.name, controller_endpoints=0)
            ),
            flush=True,
        )
        if not args.no_browser:
            webbrowser.open(url)
        start = time.monotonic()
        try:
            while not args.duration_seconds or time.monotonic() - start < args.duration_seconds:
                with suppress(OSError, ValueError, KeyError, TypeError, IndexError):
                    state.refresh()
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
