#!/usr/bin/env python3
"""Independently reopen and validate the private Red clustered schedule plan."""

# ruff: noqa: E402 -- pin the reviewed package root before imports.

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

from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.red_living_dex_clustered_schedule_plan import (
    RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_ID,
    RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_KIND,
    RED_LIVING_DEX_CLUSTERED_SUCCESSOR_PLAN_RECORD_ID,
    RED_LIVING_DEX_CLUSTERED_SUCCESSOR_PLAN_RECORD_KIND,
    RedLivingDexClusteredScheduleBindings,
    validate_red_living_dex_clustered_private_plan,
)

RESULT_SCHEMA = "pokemon.red.living-dex-clustered-schedule-validation-result.v1"
SUCCESSOR_RESULT_SCHEMA = (
    "pokemon.red.living-dex-clustered-successor-validation-result.v1"
)
FAILURE_SCHEMA = "pokemon.red.living-dex-clustered-schedule-validation-failure.v1"
EXPECTED_SCHEDULE_SHA256 = "35c00f382b5cd0f52b5231f0114eee7f423beb49c9fe4235ffe840fcc51dc905"
EXPECTED_POLICY_SHA256 = "dc72fb9449f7279c12b673b266e0973d01b62577f99d22ec7fdb14fceb8589be"
SUCCESSOR_EXPECTED_SCHEDULE_SHA256 = (
    "94b1330d968b9fd4ac91cd046e177d5178262815dd667bd073db5cc2a44f6e2a"
)
SUCCESSOR_EXPECTED_POLICY_SHA256 = (
    "4594fce41976b29c56f672071650ff11df6e2cafed3710db742b796c9d791171"
)


class ClusteredScheduleValidationError(RuntimeError):
    """One sanitized read-only validation stage failed closed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise ClusteredScheduleValidationError("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--expected-private-plan-sha256", required=True)
    parser.add_argument("--expected-plan-manifest-sha256", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--expected-rom-sha256", required=True)
    parser.add_argument("--expected-goal-registry-sha256", required=True)
    parser.add_argument("--expected-route-registry-sha256", required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--expected-runtime-identity-sha256", required=True)
    parser.add_argument("--expected-census-receipt-sha256", required=True)
    parser.add_argument("--successor", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        stage = "expected_binding_authentication"
        bindings = RedLivingDexClusteredScheduleBindings(
            source_commit=args.expected_source_commit,
            source_bundle_sha256=args.expected_source_bundle_sha256,
            rom_sha256=args.expected_rom_sha256,
            goal_registry_sha256=args.expected_goal_registry_sha256,
            route_registry_sha256=args.expected_route_registry_sha256,
            context_catalog_sha256=args.expected_context_catalog_sha256,
            context_plan_sha256=args.expected_context_plan_sha256,
            runtime_identity_sha256=args.expected_runtime_identity_sha256,
            census_receipt_sha256=args.expected_census_receipt_sha256,
        )
        expected_plan = _sha(args.expected_private_plan_sha256)
        expected_manifest = _sha(args.expected_plan_manifest_sha256)
        record_id = (
            RED_LIVING_DEX_CLUSTERED_SUCCESSOR_PLAN_RECORD_ID
            if args.successor
            else RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_ID
        )
        record_kind = (
            RED_LIVING_DEX_CLUSTERED_SUCCESSOR_PLAN_RECORD_KIND
            if args.successor
            else RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_KIND
        )
        expected_schedule_sha256 = (
            SUCCESSOR_EXPECTED_SCHEDULE_SHA256
            if args.successor
            else EXPECTED_SCHEDULE_SHA256
        )
        expected_policy_sha256 = (
            SUCCESSOR_EXPECTED_POLICY_SHA256
            if args.successor
            else EXPECTED_POLICY_SHA256
        )
        stage = "private_namespace_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        stage = "private_plan_reopen"
        record = store.find_sealed_record(
            record_id,
            expected_kind=record_kind,
        )
        if record is None or record.summary.manifest_sha256 != expected_manifest:
            raise ClusteredScheduleValidationError("private_plan_reopen")
        document = record.read()
        if document.get("private_plan_sha256") != expected_plan:
            raise ClusteredScheduleValidationError("private_plan_reopen")
        stage = "private_plan_validation"
        schedule = validate_red_living_dex_clustered_private_plan(
            document,
            expected_bindings=bindings,
            expected_schedule_sha256=expected_schedule_sha256,
            expected_policy_sha256=expected_policy_sha256,
        )
        result = {
            **schedule.public_dict(),
            "collection_authorized": False,
            "plan_manifest_sha256": record.summary.manifest_sha256,
            "plan_record_sha256": record.summary.record_sha256,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "private_plan_sha256": expected_plan,
            "private_plan_reopened": True,
            "schema": (
                SUCCESSOR_RESULT_SCHEMA if args.successor else RESULT_SCHEMA
            ),
            "status": (
                "private_clustered_successor_independently_validated"
                if args.successor
                else "private_clustered_schedule_independently_validated"
            ),
        }
        print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
    except ClusteredScheduleValidationError as error:
        stage = error.stage
    except BaseException:
        pass
    print(
        json.dumps(
            {
                "collection_authorized": False,
                "controller_actions": 0,
                "development_outcomes_opened": 0,
                "emulator_frames": 0,
                "model_fits": 0,
                "model_predictions": 0,
                "outcomes_observed": 0,
                "private_identity_fields": 0,
                "private_path_fields": 0,
                "provider_executions": 0,
                "root_claims": 0,
                "schema": FAILURE_SCHEMA,
                "stage": _safe_stage(stage),
                "status": "failed_closed",
                "teacher_queries": 0,
            },
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


def _sha(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ClusteredScheduleValidationError("expected_binding_authentication")
    return value


def _safe_stage(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(
            not (character.islower() or character.isdigit() or character == "_")
            for character in value
        )
    ):
        return "unexpected_failure"
    return value


if __name__ == "__main__":  # pragma: no cover - script boundary
    raise SystemExit(main())
