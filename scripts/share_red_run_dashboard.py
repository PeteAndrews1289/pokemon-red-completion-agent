#!/usr/bin/env python3
"""Share an existing spectator on a private interface without touching the player."""

import argparse
import json
import os
import secrets
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pokemon_red_completion.phone_dashboard import PhoneDashboard  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Specific private IPv4 address")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--upstream-port", type=int, default=8768)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--access-file", type=Path, required=True)
    parser.add_argument("--deadline-utc", required=True)
    args = parser.parse_args(argv)
    deadline = datetime.fromisoformat(args.deadline_utc)
    now = datetime.now(UTC)
    if deadline.tzinfo is None or not 0 < (deadline - now).total_seconds() <= 86400:
        parser.error("deadline must be timezone-aware and within the next 24 hours")
    if not args.access_file.parent.is_dir() or args.access_file.exists():
        parser.error("use an existing private directory and a new access file")
    token = secrets.token_urlsafe(32)
    with PhoneDashboard(host=args.host, port=args.port, upstream_port=args.upstream_port,
                        token=token, run_id=args.run_id) as viewer:
        # Verify that the requested read-only run is available before advertising.
        viewer._status()
        record = dict(schema="pokemon.phone-spectator-access.v1", pid=os.getpid(),
            created_at_utc=now.isoformat(), deadline_utc=deadline.isoformat(),
            run_id=args.run_id, private_url=viewer.private_url, view_only=True,
            controller_endpoints=0, upstream_port=args.upstream_port)
        fd = os.open(args.access_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(record, stream, sort_keys=True, indent=2)
            stream.write("\n")
        print(json.dumps(dict(ready=True, pid=os.getpid(), private_link_saved=True,
                              deadline_utc=deadline.isoformat())), flush=True)
        try:
            while datetime.now(UTC) < deadline:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
