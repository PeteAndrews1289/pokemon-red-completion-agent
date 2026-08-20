#!/usr/bin/env python3
"""Freeze or validate a public manifest for a future causal-lane invocation."""

# ruff: noqa: E402 -- script-local imports require the scripts directory on sys.path.

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
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

from public_execution_manifest import (
    PublicExecutionManifestError,
    authenticate_public_execution_manifest,
    canonical_manifest_line,
    freeze_public_execution_manifest,
    public_execution_invocation,
    read_public_manifest,
)

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.goal_manager_composition_qualification import (
    composition_skill_manifest,
)
from pokemon_red_completion.goal_manager_development import (
    goal_manager_development_numpy_runtime_sha256,
)
from pokemon_red_completion.provenance import (
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.runtime_identity import build_runtime_identity

PUBLIC_MANIFEST_ROOT = PROJECT_ROOT / ".public-execution-manifests"
RETIRED_RUNNER = "scripts/run_single_root_causal_goal_outcome.py"
_ROLE_PATH = re.compile(r"([a-z0-9][a-z0-9_]*)=(scripts/[A-Za-z0-9_.-]+\.py)\Z")
_LANE = re.compile(r"[a-z0-9][a-z0-9-]{0,95}\Z")

PRIVATE_INPUT_ROLES = tuple(
    sorted(
        (
            "base_fit_summary",
            "base_model",
            "campaign_plan",
            "candidate_fit_summary",
            "candidate_model",
            "context_catalog",
            "context_plan",
            "fit_result_receipt",
            "prior_campaign",
            "private_root",
            "rom",
        )
    )
)


class _SanitizedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise PublicExecutionManifestError("manifest arguments differ")


def _parser() -> argparse.ArgumentParser:
    parser = _SanitizedArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("freeze", "validate"), required=True)
    parser.add_argument("--lane-id", required=True)
    parser.add_argument("--runner", required=True)
    parser.add_argument("--dependency", action="append", default=[])
    parser.add_argument(
        "--operation",
        choices=("freeze", "preflight", "execute", "admit"),
        required=True,
    )
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--expected-fit-result-receipt-sha256", required=True)
    parser.add_argument(
        "--expected-prior-campaign-sha256",
        action="append",
        required=True,
    )
    parser.add_argument("--expected-campaign-sha256")
    parser.add_argument("--expected-freeze-execution-manifest-sha256")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if (args.operation == "freeze") != (args.expected_campaign_sha256 is None) or (
            args.action == "freeze"
        ) != (args.expected_manifest_sha256 is None):
            raise PublicExecutionManifestError("manifest mode arguments differ")
        if (args.operation == "freeze") != (args.expected_freeze_execution_manifest_sha256 is None):
            raise PublicExecutionManifestError("manifest mode arguments differ")
        public_bindings = _current_public_bindings(
            lane_id=args.lane_id,
            runner=args.runner,
            dependencies=args.dependency,
        )
        invocation = public_execution_invocation(
            lane_id=args.lane_id,
            operation=args.operation,
            expected_campaign_sha256=args.expected_campaign_sha256,
            expected_freeze_execution_manifest_sha256=(
                args.expected_freeze_execution_manifest_sha256
            ),
            expected_context_plan_sha256=args.expected_context_plan_sha256,
            expected_fit_result_receipt_sha256=(args.expected_fit_result_receipt_sha256),
            expected_prior_campaign_sha256=args.expected_prior_campaign_sha256,
            public_bindings=public_bindings,
            private_input_roles=PRIVATE_INPUT_ROLES,
        )
        if args.action == "freeze":
            manifest = freeze_public_execution_manifest(invocation=invocation)
            payload = canonical_manifest_line(manifest)
            _write_public_manifest(args.manifest, payload)
            status = "future_lane_public_invocation_manifest_frozen"
            manifest_sha256 = hashlib.sha256(payload).hexdigest()
        else:
            payload = read_public_manifest(
                args.manifest,
                repository_root=PROJECT_ROOT,
            )
            authenticate_public_execution_manifest(
                payload,
                expected_manifest_sha256=args.expected_manifest_sha256,
                invocation=invocation,
                current_public_bindings=public_bindings,
            )
            status = "future_lane_public_invocation_manifest_validated"
            manifest_sha256 = hashlib.sha256(payload).hexdigest()
        print(
            json.dumps(
                {
                    "schema": "pokemon.core.causal-execution-manifest-qualification.v1",
                    "status": status,
                    "execution_manifest_sha256": manifest_sha256,
                    "operation": args.operation,
                    "public_binding_count": len(public_bindings),
                    "private_input_role_count": len(PRIVATE_INPUT_ROLES),
                    "private_inputs_opened": 0,
                    "rom_accesses": 0,
                    "claim_registry_accesses": 0,
                    "model_predictions": 0,
                    "controller_actions": 0,
                    "private_path_fields": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "schema": "pokemon.core.causal-execution-manifest-qualification-failure.v1",
                    "status": "failed_closed",
                    "failure_stage": "public_manifest_qualification",
                    "private_inputs_opened": 0,
                    "rom_accesses": 0,
                    "claim_registry_accesses": 0,
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1


def _current_public_bindings(
    *,
    lane_id: str,
    runner: str,
    dependencies: list[str],
) -> dict[str, str]:
    if _LANE.fullmatch(lane_id) is None or lane_id == "first-causal-goal-outcome-v1":
        raise PublicExecutionManifestError("future causal lane identity differs")
    if runner == RETIRED_RUNNER:
        raise PublicExecutionManifestError("retired causal runner is forbidden")
    runner_path = _public_script(runner)
    dependency_paths: dict[str, Path] = {}
    for value in dependencies:
        match = _ROLE_PATH.fullmatch(value)
        if match is None:
            raise PublicExecutionManifestError("dependency binding differs")
        role, relative = match.groups()
        key = f"{role}_sha256"
        if key in dependency_paths or relative in {runner, RETIRED_RUNNER}:
            raise PublicExecutionManifestError("dependency binding differs")
        dependency_paths[key] = _public_script(relative)
    if not dependency_paths:
        raise PublicExecutionManifestError("dependency binding differs")
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:
        raise PublicExecutionManifestError("public source identity differs")
    skill_sha = composition_skill_manifest(PROJECT_ROOT).get("manifest_sha256")
    if not isinstance(skill_sha, str):
        raise PublicExecutionManifestError("skill manifest identity differs")
    return {
        "source_commit": source.git_commit,
        "source_bundle_sha256": working_source_bundle_sha256(PROJECT_ROOT),
        "runner_sha256": _file_sha256(runner_path),
        **{key: _file_sha256(path) for key, path in sorted(dependency_paths.items())},
        "manifest_freezer_sha256": _file_sha256(Path(__file__).resolve()),
        "runtime_sha256": build_runtime_identity().sha256,
        "numpy_runtime_sha256": goal_manager_development_numpy_runtime_sha256(),
        "skill_manifest_sha256": skill_sha,
    }


def _public_script(relative: str) -> Path:
    match = _ROLE_PATH.fullmatch(f"runner={relative}")
    if match is None or relative == RETIRED_RUNNER:
        raise PublicExecutionManifestError("public runner binding differs")
    path = PROJECT_ROOT / relative
    try:
        expected = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        raise PublicExecutionManifestError("public runner is unavailable") from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(expected.st_mode)
        or expected.st_nlink != 1
        or resolved.parent != SCRIPTS_ROOT.resolve(strict=True)
    ):
        raise PublicExecutionManifestError("public runner binding differs")
    return resolved


def _write_public_manifest(path: Path, payload: bytes) -> None:
    try:
        PUBLIC_MANIFEST_ROOT.mkdir(mode=0o700, exist_ok=True)
        public_root = PUBLIC_MANIFEST_ROOT.resolve(strict=True)
        root_stat = PUBLIC_MANIFEST_ROOT.lstat()
        parent = path.parent.resolve(strict=True)
    except OSError:
        raise PublicExecutionManifestError("public manifest location differs") from None
    if (
        PUBLIC_MANIFEST_ROOT.is_symlink()
        or not stat.S_ISDIR(root_stat.st_mode)
        or parent != public_root
        or path.name in {"", ".", ".."}
        or not path.name.endswith(".json")
    ):
        raise PublicExecutionManifestError("public manifest location differs")
    destination = public_root / path.name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(destination, flags, 0o600)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise PublicExecutionManifestError("public manifest destination differs")
        view = memoryview(payload)
        total = 0
        while total < len(payload):
            total += os.write(descriptor, view[total:])
        os.fsync(descriptor)
    except PublicExecutionManifestError:
        raise
    except OSError:
        raise PublicExecutionManifestError("public manifest destination differs") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
