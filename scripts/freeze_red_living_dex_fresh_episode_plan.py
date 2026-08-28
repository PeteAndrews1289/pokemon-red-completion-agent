#!/usr/bin/env python3
"""Freeze the canonical Red fresh-root plan without opening a cartridge.

Run this only from the clean, published implementation commit that will later
execute the plan.  The output is a new external, path-free plan file.  This
command has no ROM, emulator, controller, teacher, learner, claim, outcome, or
model surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from pokemon_red_completion.collection_protocol import (
    working_source_bundle_sha256,
)
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_living_dex_episode_lineage import (
    RED_LIVING_DEX_FRESH_EPISODE_FIRST_HARNESS_SEED,
    RedLivingDexEpisodeLineageError,
    build_red_living_dex_fresh_episode_plan,
    compose_red_living_dex_fresh_episode_generator_execution_sha256,
    compose_red_living_dex_fresh_episode_teacher_execution_sha256,
    encode_red_living_dex_fresh_episode_plan,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPACITY_EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-causal-capacity-census-v1-2026-08-28.json"
)
GENERATOR_RUNNER_PATH = (
    PROJECT_ROOT / "scripts/generate_red_living_dex_fresh_episode_root.py"
)
CONDITIONER_RUNNER_PATH = (
    PROJECT_ROOT / "scripts/materialize_goal_manager_context.py"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_MAXIMUM_EVIDENCE_BYTES = 512 * 1024


class FreshEpisodePlanFreezeError(RuntimeError):
    """The published source, evidence, execution, or output differs."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--expected-generator-execution-sha256", required=True)
    parser.add_argument("--expected-capacity-evidence-sha256", required=True)
    return parser


def _require_sha256(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise FreshEpisodePlanFreezeError("arguments")
    return value


def _read_evidence() -> tuple[bytes, str]:
    try:
        metadata = CAPACITY_EVIDENCE_PATH.lstat()
        if (
            CAPACITY_EVIDENCE_PATH.is_symlink()
            or not CAPACITY_EVIDENCE_PATH.is_file()
            or not 0 < metadata.st_size <= _MAXIMUM_EVIDENCE_BYTES
        ):
            raise OSError("unsafe evidence")
        payload = CAPACITY_EVIDENCE_PATH.read_bytes()
    except OSError:
        raise FreshEpisodePlanFreezeError("capacity_authentication") from None
    if len(payload) != metadata.st_size:
        raise FreshEpisodePlanFreezeError("capacity_authentication")
    return payload, hashlib.sha256(payload).hexdigest()


def _generator_execution(source_bundle_sha256: str) -> str:
    return compose_red_living_dex_fresh_episode_generator_execution_sha256(
        source_bundle_sha256=source_bundle_sha256,
        generator_runner_sha256=hashlib.sha256(
            GENERATOR_RUNNER_PATH.read_bytes()
        ).hexdigest(),
        conditioner_runner_sha256=hashlib.sha256(
            CONDITIONER_RUNNER_PATH.read_bytes()
        ).hexdigest(),
    )


def _write_exclusive(path: Path, payload: bytes) -> None:
    resolved = path.resolve()
    if (
        resolved.is_relative_to(PROJECT_ROOT.resolve())
        or not resolved.parent.is_dir()
        or path.is_symlink()
        or path.exists()
    ):
        raise FreshEpisodePlanFreezeError("output_authentication")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    directory_descriptor = -1
    try:
        descriptor = os.open(resolved, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("plan write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        directory_descriptor = os.open(
            resolved.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        os.fsync(directory_descriptor)
    except OSError:
        raise FreshEpisodePlanFreezeError("output_authentication") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def _run(args: argparse.Namespace) -> dict[str, object]:
    if (
        not isinstance(args.expected_source_commit, str)
        or _GIT_OID.fullmatch(args.expected_source_commit) is None
    ):
        raise FreshEpisodePlanFreezeError("arguments")
    expected_bundle = _require_sha256(args.expected_source_bundle_sha256)
    expected_generator = _require_sha256(
        args.expected_generator_execution_sha256
    )
    expected_capacity = _require_sha256(
        args.expected_capacity_evidence_sha256
    )
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    generator_execution = _generator_execution(source_bundle)
    evidence_payload, capacity_sha256 = _read_evidence()
    del evidence_payload
    if (
        source.git_commit != args.expected_source_commit
        or source_bundle != expected_bundle
        or generator_execution != expected_generator
        or capacity_sha256 != expected_capacity
    ):
        raise FreshEpisodePlanFreezeError("source_authentication")
    teacher_execution = (
        compose_red_living_dex_fresh_episode_teacher_execution_sha256(
            source_bundle_sha256=source_bundle,
            generator_execution_sha256=generator_execution,
        )
    )
    plan = build_red_living_dex_fresh_episode_plan(
        source_commit=source.git_commit,
        source_bundle_sha256=source_bundle,
        teacher_execution_sha256=teacher_execution,
        generator_execution_sha256=generator_execution,
        capacity_evidence_sha256=capacity_sha256,
    )
    payload = encode_red_living_dex_fresh_episode_plan(plan)
    _write_exclusive(args.out, payload)
    return {
        "assignments": len(plan.assignments),
        "controller_actions": 0,
        "emulator_frames": 0,
        "first_harness_seed": (
            RED_LIVING_DEX_FRESH_EPISODE_FIRST_HARNESS_SEED
        ),
        "generator_execution_sha256": generator_execution,
        "learner_outcomes": 0,
        "model_fits": 0,
        "model_predictions": 0,
        "plan_file_sha256": hashlib.sha256(payload).hexdigest(),
        "plan_sha256": plan.plan_sha256,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "root_generation_executions": 0,
        "schema": "pokemon.red.living-dex-fresh-episode-plan-freeze.v1",
        "source_commit": source.git_commit,
        "status": "fresh_episode_plan_frozen_without_execution",
        "teacher_queries": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = _run(args)
    except (
        EvaluationIdentityError,
        FreshEpisodePlanFreezeError,
        RedLivingDexEpisodeLineageError,
        OSError,
    ):
        parser.error(
            "Fresh-episode plan freeze failed closed; private paths were withheld."
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
