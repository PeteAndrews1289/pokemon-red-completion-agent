#!/usr/bin/env python3
"""Audit private capture coverage without publishing paths or capture identity."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.captured_progress import (  # noqa: E402
    CapturedProgressError,
    load_captured_progress,
)
from pokemon_red_completion.strategic_frontier_inventory import (  # noqa: E402
    strategic_frontier_inventory,
)
from pokemon_red_completion.strategic_navigation_scenarios import (  # noqa: E402
    load_strategic_navigation_scenario_registry,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    return parser


def _run(private_root: Path) -> dict[str, object]:
    resolved = private_root.resolve()
    if not resolved.is_dir() or resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise CapturedProgressError("inventory root must be a private directory")

    captures = []
    invalid_envelopes = 0
    for envelope_path in sorted(resolved.rglob("*.state.json")):
        state_path = Path(str(envelope_path)[: -len(".json")])
        try:
            captures.append(
                load_captured_progress(envelope_path, state_path=state_path)
            )
        except CapturedProgressError:
            invalid_envelopes += 1

    payload = strategic_frontier_inventory(
        captures,
        load_strategic_navigation_scenario_registry(PROJECT_ROOT),
    )
    return {
        **payload,
        "invalid_capture_envelopes_excluded": invalid_envelopes,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = _run(args.private_root)
    except (CapturedProgressError, OSError):
        _parser().error("Strategic frontier inventory failed; private paths were withheld.")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
