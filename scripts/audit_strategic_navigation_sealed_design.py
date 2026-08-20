#!/usr/bin/env python3
"""Audit the public sealed-scenario design without opening private evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.strategic_navigation_scenarios import (
    load_strategic_navigation_scenario_registry,
)
from pokemon_red_completion.strategic_navigation_test_design import (
    audit_strategic_sealed_test_design,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    audit = audit_strategic_sealed_test_design(registry, COMPLETION_QUEST)
    payload = {
        **audit.public_dict(),
        "inputs": {
            "committed_registry_only": True,
            "private_captures_accessed": False,
            "private_episodes_accessed": False,
            "live_route_costs_accessed": False,
            "model_predictions_accessed": False,
        },
        "interpretation": {
            "current_sealed_design_status": "blocked",
            "reason": (
                "No test challenge hypotheses were preregistered; structural "
                "eligibility cannot substitute for a measured disagreement."
            ),
            "safe_next_step": (
                "Preregister a replacement sealed-test design with at least six "
                "eligible challenge hypotheses before opening private test evidence."
            ),
        },
    }
    _atomic_json(args.out, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
