#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_red_completion.artifacts import (  # noqa: E402
    inspect_public_tree,
    inspect_tracked_tree,
)


def main() -> int:
    violations = tuple(
        dict.fromkeys(
            (*inspect_public_tree(PROJECT_ROOT), *inspect_tracked_tree(PROJECT_ROOT))
        )
    )
    if violations:
        for violation in violations:
            print(f"{violation.path}: {violation.reason}")
        return 1
    print("Public-artifact check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
