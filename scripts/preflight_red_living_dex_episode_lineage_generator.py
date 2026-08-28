#!/usr/bin/env python3
"""Qualify one fresh Red train-root plan without opening an emulator.

The command authenticates a clean published source, the exact path-free
capacity result, and a canonical 6/6/1 train-first episode plan.  It has no ROM
argument, emulator, controller, teacher, claim writer, outcome collector,
scorer, or fitter.  Passing this preflight permits only a later bounded
generation decision; it does not itself generate or authorize a root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
    RedLivingDexEpisodeLineageError,
    compose_red_living_dex_fresh_episode_generator_execution_sha256,
    compose_red_living_dex_fresh_episode_teacher_execution_sha256,
    parse_red_living_dex_fresh_episode_plan,
    preflight_red_living_dex_fresh_episode_plan,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupEffectMeter,
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
_MAXIMUM_PLAN_BYTES = 512 * 1024
_MAXIMUM_EVIDENCE_BYTES = 512 * 1024


class FreshEpisodeGeneratorPreflightError(RuntimeError):
    """The plan, published source, or zero-effect boundary differs."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--expected-plan-sha256", required=True)
    return parser


def _read_bounded(path: Path, maximum_bytes: int) -> bytes:
    try:
        metadata = path.stat()
        if (
            not path.is_file()
            or path.is_symlink()
            or not 0 < metadata.st_size <= maximum_bytes
        ):
            raise FreshEpisodeGeneratorPreflightError("artifact_authentication")
        payload = path.read_bytes()
    except OSError:
        raise FreshEpisodeGeneratorPreflightError(
            "artifact_authentication"
        ) from None
    if len(payload) != metadata.st_size:
        raise FreshEpisodeGeneratorPreflightError("artifact_authentication")
    return payload


def _generator_execution_sha256(source_bundle_sha256: str) -> str:
    return compose_red_living_dex_fresh_episode_generator_execution_sha256(
        source_bundle_sha256=source_bundle_sha256,
        generator_runner_sha256=hashlib.sha256(
            GENERATOR_RUNNER_PATH.read_bytes()
        ).hexdigest(),
        conditioner_runner_sha256=hashlib.sha256(
            CONDITIONER_RUNNER_PATH.read_bytes()
        ).hexdigest(),
    )


def _run(args: argparse.Namespace) -> dict[str, object]:
    if (
        not isinstance(args.expected_plan_sha256, str)
        or _SHA256.fullmatch(args.expected_plan_sha256) is None
    ):
        raise FreshEpisodeGeneratorPreflightError("plan_authentication")
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    plan_payload = _read_bounded(args.plan.resolve(), _MAXIMUM_PLAN_BYTES)
    if hashlib.sha256(plan_payload).hexdigest() != args.expected_plan_sha256:
        raise FreshEpisodeGeneratorPreflightError("plan_authentication")
    plan = parse_red_living_dex_fresh_episode_plan(plan_payload)
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    generator_execution = _generator_execution_sha256(source_bundle)
    if (
        source.git_commit != plan.source_commit
        or source_bundle != plan.source_bundle_sha256
        or generator_execution != plan.generator_execution_sha256
        or plan.teacher_execution_sha256
        != compose_red_living_dex_fresh_episode_teacher_execution_sha256(
            source_bundle_sha256=source_bundle,
            generator_execution_sha256=generator_execution,
        )
    ):
        raise FreshEpisodeGeneratorPreflightError("source_authentication")
    capacity_payload = _read_bounded(
        CAPACITY_EVIDENCE_PATH,
        _MAXIMUM_EVIDENCE_BYTES,
    )
    if hashlib.sha256(capacity_payload).hexdigest() != (
        plan.capacity_evidence_sha256
    ):
        raise FreshEpisodeGeneratorPreflightError("capacity_authentication")
    meter = RedLivingDexSetupEffectMeter()
    before = meter.checkpoint()
    preflight = preflight_red_living_dex_fresh_episode_plan(
        plan,
        effects_before=before,
        effects_after=meter.checkpoint(),
    )
    return {
        **preflight.public_dict(),
        "capacity_evidence_bound": True,
        "clean_published_source_bound": True,
        "generator_execution_sha256": generator_execution,
        "plan_file_sha256": args.expected_plan_sha256,
        "source_commit": source.git_commit,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = _run(args)
    except (
        EvaluationIdentityError,
        FreshEpisodeGeneratorPreflightError,
        RedLivingDexEpisodeLineageError,
        OSError,
    ):
        parser.error(
            "Fresh-episode generator preflight failed closed; private paths were withheld."
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
