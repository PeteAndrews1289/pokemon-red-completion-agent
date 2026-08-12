#!/usr/bin/env python3
"""Audit learning frontiers against the currently qualified teacher order."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.strategic_curriculum_order import (  # noqa: E402
    audit_qualified_skill_order,
)
from pokemon_red_completion.strategic_navigation_scenarios import (  # noqa: E402
    load_strategic_navigation_scenario_registry,
)


def main() -> int:
    payload = audit_qualified_skill_order(
        load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
