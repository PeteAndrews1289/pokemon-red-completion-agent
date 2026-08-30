#!/usr/bin/env python3
"""Audit the complete authentic causal corpus before the first plumbing fit.

The command opens only the immutable causal journal under the validated private
artifact root.  It has no ROM, emulator, controller, claim writer, teacher,
development-plan, scorer, prediction, fit, retry, or public-private-record
publication surface.  Output is a path-free aggregate readiness result.
"""

# ruff: noqa: E402 -- pin the project source root before package imports.

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
while str(SRC_ROOT) in sys.path:
    sys.path.remove(str(SRC_ROOT))
sys.path.insert(0, str(SRC_ROOT))

from pokemon_red_completion.living_dex_causal_integration_readiness import (
    audit_living_dex_causal_integration_readiness,
)
from pokemon_red_completion.living_dex_causal_journal import (
    load_living_dex_authenticated_causal_examples,
)
from pokemon_red_completion.private_artifacts import open_private_root

RESULT_SCHEMA = "pokemon.red.living-dex-causal-integration-readiness-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-causal-integration-readiness-failure.v1"


class IntegrationReadinessCommandError(RuntimeError):
    """The aggregate audit failed at one sanitized action-free stage."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise IntegrationReadinessCommandError("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        stage = "private_root_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        stage = "complete_causal_denominator_authentication"
        examples = load_living_dex_authenticated_causal_examples(store)
        stage = "train_only_integration_readiness"
        audit = audit_living_dex_causal_integration_readiness(examples)
        result = {
            **audit.public_dict(),
            "schema": RESULT_SCHEMA,
            "status": (
                "authenticated_train_only_integration_ready"
                if audit.ready
                else "authenticated_train_only_integration_not_ready"
            ),
        }
        print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
    except IntegrationReadinessCommandError as error:
        stage = error.stage
    except BaseException:
        pass
    failure = {
        "controller_actions": 0,
        "counterfactual_targets": 0,
        "development_schedule_reads": 0,
        "emulator_frames": 0,
        "fit_executions": 0,
        "model_predictions": 0,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "root_claims": 0,
        "schema": FAILURE_SCHEMA,
        "stage": stage,
        "status": "failed_closed",
        "teacher_queries": 0,
        "unselected_action_targets": 0,
    }
    print(json.dumps(failure, allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 1


if __name__ == "__main__":  # pragma: no cover - script boundary
    raise SystemExit(main())
