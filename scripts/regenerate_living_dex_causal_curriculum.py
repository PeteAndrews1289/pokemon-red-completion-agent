#!/usr/bin/env python3
"""Regenerate the public powered living-Dex causal curriculum design."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pokemon_red_completion.living_dex_causal_curriculum import (  # noqa: E402
    canonical_living_dex_causal_curriculum_bytes,
)

OUTPUT = PROJECT_ROOT / "configs" / "living-dex-causal-curriculum-v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = canonical_living_dex_causal_curriculum_bytes()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != payload:
            print(f"stale: {OUTPUT.relative_to(PROJECT_ROOT)}", file=sys.stderr)
            return 1
        print(f"current: {OUTPUT.relative_to(PROJECT_ROOT)}")
        return 0
    OUTPUT.write_bytes(payload)
    print(f"wrote: {OUTPUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
