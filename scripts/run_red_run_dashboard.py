#!/usr/bin/env python3
"""Open a Mac-local spectator for one run. This never launches or resumes Red."""

import argparse
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--live-port", type=int, default=8769)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--duration-seconds", type=int, default=0)
    args = parser.parse_args(argv)
    if args.port == args.live_port or args.duration_seconds < 0:
        parser.error("viewer/feed ports must differ and duration must be nonnegative")
    state = RunViewerState(RedRunReader(args.run_dir), live_port=args.live_port)
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
