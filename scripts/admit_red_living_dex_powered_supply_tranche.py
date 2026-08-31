#!/usr/bin/env python3
"""Admit one complete Red powered-lineage supply qualification tranche.

This action-free command authenticates the exact published V2 plan, runner and
conditioner bytes, reconciles any interrupted one-shot private namespaces,
validates every successful root and terminal failure, and seals one private
admission record.  It cannot open a ROM, restore a root into an emulator,
collect an outcome, score or fit a model, or authorize population scale.
"""

# ruff: noqa: E402 -- establish reviewed script roots before project imports.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
for root in (SCRIPTS_ROOT, SRC_ROOT):
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

GENERATOR_PATH = SCRIPTS_ROOT / "generate_red_living_dex_fresh_episode_root.py"
CONDITIONER_PATH = SCRIPTS_ROOT / "materialize_goal_manager_context.py"
_MAXIMUM_PLAN_BYTES = 512 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")

from pokemon_red_completion.collection_protocol import (
    working_source_bundle_sha256,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    open_private_root,
)
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_living_dex_powered_lineage_supply import (
    RedLivingDexPoweredSupplyError,
    compose_red_living_dex_powered_supply_generator_sha256,
    parse_red_living_dex_powered_supply_plan,
)
from pokemon_red_completion.red_living_dex_powered_supply_admission import (
    RED_LIVING_DEX_POWERED_SUPPLY_ADMISSION_RECORD_KIND,
    RedLivingDexPoweredSupplyAdmissionError,
    authenticate_red_living_dex_powered_supply_private_tranche,
)


class PoweredSupplyAdmissionCommandError(RuntimeError):
    """One sanitized source, plan, or private disposition check failed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise PoweredSupplyAdmissionCommandError("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--expected-generator-execution-sha256", required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    return parser


def _read_bounded(path: Path, maximum_bytes: int) -> bytes:
    try:
        metadata = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or not 0 < metadata.st_size <= maximum_bytes
        ):
            raise OSError("unsafe input")
        payload = path.read_bytes()
    except OSError:
        raise PoweredSupplyAdmissionCommandError("plan_authentication") from None
    if len(payload) != metadata.st_size:
        raise PoweredSupplyAdmissionCommandError("plan_authentication")
    return payload


def _sha256_file(path: Path) -> str:
    try:
        metadata = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise OSError("unsafe source")
        payload = path.read_bytes()
    except OSError:
        raise PoweredSupplyAdmissionCommandError("source_authentication") from None
    return hashlib.sha256(payload).hexdigest()


def _require_sha256(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PoweredSupplyAdmissionCommandError("arguments")
    return value


def _run(args: argparse.Namespace) -> dict[str, object]:
    if (
        not isinstance(args.expected_source_commit, str)
        or _GIT_OID.fullmatch(args.expected_source_commit) is None
    ):
        raise PoweredSupplyAdmissionCommandError("arguments")
    expected_plan = _require_sha256(args.expected_plan_sha256)
    expected_bundle = _require_sha256(args.expected_source_bundle_sha256)
    expected_generator = _require_sha256(
        args.expected_generator_execution_sha256
    )

    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if (
        source.git_commit != args.expected_source_commit
        or source_bundle != expected_bundle
    ):
        raise PoweredSupplyAdmissionCommandError("source_authentication")

    plan_payload = _read_bounded(args.plan.resolve(), _MAXIMUM_PLAN_BYTES)
    if hashlib.sha256(plan_payload).hexdigest() != expected_plan:
        raise PoweredSupplyAdmissionCommandError("plan_authentication")
    plan = parse_red_living_dex_powered_supply_plan(plan_payload)
    runner_sha256 = _sha256_file(GENERATOR_PATH)
    conditioner_sha256 = _sha256_file(CONDITIONER_PATH)
    generator_execution = compose_red_living_dex_powered_supply_generator_sha256(
        source_bundle_sha256=source_bundle,
        generator_runner_sha256=runner_sha256,
        conditioner_runner_sha256=conditioner_sha256,
    )
    if (
        plan.source_commit != source.git_commit
        or plan.source_bundle_sha256 != source_bundle
        or plan.generator_execution_sha256 != generator_execution
        or plan.generator_runner_sha256 != runner_sha256
        or plan.conditioner_runner_sha256 != conditioner_sha256
        or expected_generator != generator_execution
    ):
        raise PoweredSupplyAdmissionCommandError("plan_authentication")

    store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    claim_registry = open_fixed_account_claim_registry()
    bundle = authenticate_red_living_dex_powered_supply_private_tranche(
        plan,
        private_store=store,
        claim_registry=claim_registry,
        recover_interrupted=True,
    )
    record = store.publish_sealed_record(
        bundle.record_id,
        kind=RED_LIVING_DEX_POWERED_SUPPLY_ADMISSION_RECORD_KIND,
        record=bundle.private_dict(),
    )
    return {
        **bundle.public_dict(),
        "admission_manifest_sha256": record.summary.manifest_sha256,
        "admission_record_sha256": record.summary.record_sha256,
    }


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    try:
        result = _run(_parser().parse_args(argv))
        print(
            json.dumps(
                result,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    except PoweredSupplyAdmissionCommandError as error:
        stage = error.stage
    except (
        EvaluationIdentityError,
        PrivateArtifactError,
        RedLivingDexPoweredSupplyAdmissionError,
        RedLivingDexPoweredSupplyError,
    ):
        stage = "private_tranche_authentication"
    except BaseException:
        stage = "unclassified_failure"
    print(
        json.dumps(
            {
                "controller_actions": 0,
                "emulator_frames": 0,
                "model_fits": 0,
                "model_predictions": 0,
                "outcomes": 0,
                "population_scale_authorized": False,
                "private_identity_fields": 0,
                "private_path_fields": 0,
                "root_claims": 0,
                "root_state_restores": 0,
                "stage": stage,
                "status": "failed_closed",
            },
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
