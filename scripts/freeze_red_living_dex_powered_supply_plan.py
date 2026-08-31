#!/usr/bin/env python3
"""Freeze the sole bounded Red powered-lineage yield qualification plan.

This command is action-free.  It binds exact published source, the failed
powered-capacity census, the shared generator/conditioner bytes, and the
canonical 3-train / 8-development / 1-contingency schedule.  It cannot open a
ROM, generate a root, issue a claim, select behavior, observe an outcome, fit
a model, or authorize population scale.
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
CAPACITY_RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-clustered-powered-v2-capacity-result-v1-2026-08-31.json"
)

from pokemon_red_completion.collection_protocol import (
    working_source_bundle_sha256,
)
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_living_dex_powered_lineage_supply import (
    RED_LIVING_DEX_POWERED_SUPPLY_CAPACITY_RESULT_SHA256,
    RED_LIVING_DEX_POWERED_SUPPLY_DESIGN_SHA256,
    RedLivingDexPoweredSupplyError,
    build_red_living_dex_powered_supply_plan,
    compose_red_living_dex_powered_supply_generator_sha256,
    compose_red_living_dex_powered_supply_teacher_sha256,
    encode_red_living_dex_powered_supply_plan,
    preflight_red_living_dex_powered_supply_plan,
)
from pokemon_red_completion.runtime_identity import (
    RuntimeIdentityError,
    build_runtime_identity,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_MAXIMUM_EVIDENCE_BYTES = 512 * 1024


class PoweredSupplyFreezeError(RuntimeError):
    """One zero-effect source, evidence, or publication binding failed."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise PoweredSupplyFreezeError("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--expected-generator-execution-sha256", required=True)
    parser.add_argument("--expected-runtime-identity-sha256", required=True)
    parser.add_argument("--expected-capacity-result-sha256", required=True)
    parser.add_argument("--expected-powered-design-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


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
        raise PoweredSupplyFreezeError("source_authentication") from None
    return hashlib.sha256(payload).hexdigest()


def _read_capacity_result() -> bytes:
    try:
        metadata = CAPACITY_RESULT_PATH.lstat()
        if (
            CAPACITY_RESULT_PATH.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or not 0 < metadata.st_size <= _MAXIMUM_EVIDENCE_BYTES
        ):
            raise OSError("unsafe evidence")
        payload = CAPACITY_RESULT_PATH.read_bytes()
    except OSError:
        raise PoweredSupplyFreezeError("capacity_authentication") from None
    if len(payload) != metadata.st_size:
        raise PoweredSupplyFreezeError("capacity_authentication")
    return payload


def _generator_execution(source_bundle_sha256: str) -> str:
    return _generator_execution_binding(source_bundle_sha256)[0]


def _generator_execution_binding(
    source_bundle_sha256: str,
) -> tuple[str, str, str]:
    generator_runner_sha256 = _sha256_file(GENERATOR_PATH)
    conditioner_runner_sha256 = _sha256_file(CONDITIONER_PATH)
    return (
        compose_red_living_dex_powered_supply_generator_sha256(
            source_bundle_sha256=source_bundle_sha256,
            generator_runner_sha256=generator_runner_sha256,
            conditioner_runner_sha256=conditioner_runner_sha256,
        ),
        generator_runner_sha256,
        conditioner_runner_sha256,
    )


def _write_exclusive(path: Path, payload: bytes) -> None:
    destination = path.resolve()
    parent = destination.parent
    descriptor = -1
    directory_descriptor = -1
    try:
        parent_metadata = parent.lstat()
        if (
            parent.is_symlink()
            or not stat.S_ISDIR(parent_metadata.st_mode)
            or parent_metadata.st_uid != os.getuid()
            or stat.S_IMODE(parent_metadata.st_mode) & 0o022
        ):
            raise OSError("unsafe output parent")
        directory_descriptor = os.open(
            parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        descriptor = os.open(
            destination.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=directory_descriptor,
        )
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("plan write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.fsync(directory_descriptor)
    except OSError:
        raise PoweredSupplyFreezeError("exclusive_plan_publication") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def _require_sha256(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PoweredSupplyFreezeError("arguments")
    return value


def _run(args: argparse.Namespace) -> dict[str, object]:
    if (
        not isinstance(args.expected_source_commit, str)
        or _GIT_OID.fullmatch(args.expected_source_commit) is None
    ):
        raise PoweredSupplyFreezeError("arguments")
    expected_bundle = _require_sha256(args.expected_source_bundle_sha256)
    expected_generator = _require_sha256(
        args.expected_generator_execution_sha256
    )
    expected_runtime = _require_sha256(args.expected_runtime_identity_sha256)
    expected_capacity = _require_sha256(
        args.expected_capacity_result_sha256
    )
    expected_design = _require_sha256(args.expected_powered_design_sha256)
    if (
        expected_capacity
        != RED_LIVING_DEX_POWERED_SUPPLY_CAPACITY_RESULT_SHA256
        or expected_design != RED_LIVING_DEX_POWERED_SUPPLY_DESIGN_SHA256
    ):
        raise PoweredSupplyFreezeError("capacity_authentication")

    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    (
        generator_execution,
        generator_runner_sha256,
        conditioner_runner_sha256,
    ) = _generator_execution_binding(source_bundle)
    capacity_payload = _read_capacity_result()
    capacity_sha256 = hashlib.sha256(capacity_payload).hexdigest()
    runtime_identity_sha256 = build_runtime_identity().sha256
    if (
        source.git_commit != args.expected_source_commit
        or source_bundle != expected_bundle
        or generator_execution != expected_generator
    ):
        raise PoweredSupplyFreezeError("source_authentication")
    if capacity_sha256 != expected_capacity:
        raise PoweredSupplyFreezeError("capacity_authentication")
    if runtime_identity_sha256 != expected_runtime:
        raise PoweredSupplyFreezeError("runtime_authentication")
    teacher_execution = compose_red_living_dex_powered_supply_teacher_sha256(
        source_bundle_sha256=source_bundle,
        generator_execution_sha256=generator_execution,
    )
    plan = build_red_living_dex_powered_supply_plan(
        source_commit=source.git_commit,
        source_bundle_sha256=source_bundle,
        teacher_execution_sha256=teacher_execution,
        generator_execution_sha256=generator_execution,
        generator_runner_sha256=generator_runner_sha256,
        conditioner_runner_sha256=conditioner_runner_sha256,
        runtime_identity_sha256=runtime_identity_sha256,
    )
    preflight = preflight_red_living_dex_powered_supply_plan(plan)
    payload = encode_red_living_dex_powered_supply_plan(plan)
    _write_exclusive(args.out, payload)
    return {
        **preflight.public_dict(),
        "capacity_result_sha256": capacity_sha256,
        "conditioner_runner_sha256": conditioner_runner_sha256,
        "generator_execution_sha256": generator_execution,
        "generator_runner_sha256": generator_runner_sha256,
        "plan_file_sha256": hashlib.sha256(payload).hexdigest(),
        "powered_design_sha256": plan.powered_design_sha256,
        "runtime_identity_sha256": runtime_identity_sha256,
        "source_commit": source.git_commit,
        "source_bundle_sha256": source_bundle,
        "status": "bounded_powered_lineage_supply_plan_frozen_without_execution",
        "teacher_execution_sha256": teacher_execution,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _run(parser.parse_args(argv))
    except (
        EvaluationIdentityError,
        PoweredSupplyFreezeError,
        RedLivingDexPoweredSupplyError,
        RuntimeIdentityError,
        OSError,
    ):
        parser.error(
            "Powered supply freeze failed closed; private paths were withheld."
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
