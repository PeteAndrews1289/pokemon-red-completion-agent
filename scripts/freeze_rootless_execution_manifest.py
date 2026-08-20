#!/usr/bin/env python3
"""Freeze or validate one exact public invocation of the rootless dependency pipeline."""

# ruff: noqa: E402 -- script-local modules must precede the package import path.

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
    PUBLIC_EXECUTION_MANIFEST_DIRECTORY,
    canonical_manifest_line,
    read_public_manifest,
)
from rootless_execution_manifest import (
    RootlessExecutionManifestError,
    authenticate_rootless_execution_manifest,
    freeze_rootless_execution_manifest,
    rootless_execution_invocation,
)

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.provenance import (
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.runtime_identity import build_runtime_identity

PUBLIC_MANIFEST_ROOT = PROJECT_ROOT / PUBLIC_EXECUTION_MANIFEST_DIRECTORY
_ROLE_PATH = re.compile(
    r"([a-z0-9][a-z0-9_]*)=((?:scripts|src/pokemon_red_completion)/[A-Za-z0-9_.-]+\.py)\Z"
)
_DIGEST_BINDING = re.compile(r"([a-z0-9][a-z0-9_]*)=([0-9a-f]{64})\Z")
_LANE = re.compile(r"[a-z0-9][a-z0-9-]{0,95}\Z")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RootlessExecutionManifestError("manifest arguments differ")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--action", choices=("freeze", "validate"), required=True)
    parser.add_argument("--lane-id", required=True)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--runner", required=True)
    parser.add_argument("--dependency", action="append", default=[])
    parser.add_argument("--semantic-binding", action="append", required=True)
    parser.add_argument("--private-input-role", action="append", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if (args.action == "freeze") != (args.expected_manifest_sha256 is None):
            raise RootlessExecutionManifestError("manifest action differs")
        semantic = _bindings(args.semantic_binding)
        public = _current_public_bindings(
            lane_id=args.lane_id,
            runner=args.runner,
            dependencies=args.dependency,
        )
        invocation = rootless_execution_invocation(
            lane_id=args.lane_id,
            operation=args.operation,
            semantic_bindings=semantic,
            public_bindings=public,
            private_input_roles=tuple(sorted(args.private_input_role)),
        )
        if args.action == "freeze":
            payload = canonical_manifest_line(freeze_rootless_execution_manifest(invocation))
            _write_manifest(args.manifest, payload)
            status = "rootless_public_invocation_frozen"
        else:
            payload = read_public_manifest(
                args.manifest,
                repository_root=PROJECT_ROOT,
            )
            authenticate_rootless_execution_manifest(
                payload,
                expected_manifest_sha256=args.expected_manifest_sha256,
                invocation=invocation,
                current_public_bindings=public,
            )
            status = "rootless_public_invocation_validated"
        print(
            json.dumps(
                {
                    "schema": "pokemon.core.rootless-execution-manifest-qualification.v1",
                    "status": status,
                    "operation": args.operation,
                    "execution_manifest_sha256": hashlib.sha256(payload).hexdigest(),
                    "public_binding_count": len(public),
                    "semantic_binding_count": len(semantic),
                    "private_input_role_count": len(set(args.private_input_role)),
                    "private_inputs_opened": 0,
                    "rom_accesses": 0,
                    "claim_registry_accesses": 0,
                    "predictions": 0,
                    "synthetic_transitions": 0,
                    "private_path_fields": 0,
                },
                allow_nan=False,
                sort_keys=True,
            )
        )
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "schema": "pokemon.core.rootless-execution-manifest-failure.v1",
                    "status": "failed_closed",
                    "failure_stage": "public_manifest_authentication",
                    "private_inputs_opened": 0,
                    "rom_accesses": 0,
                    "claim_registry_accesses": 0,
                    "predictions": 0,
                    "synthetic_transitions": 0,
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1


def _current_public_bindings(
    *, lane_id: str, runner: str, dependencies: list[str]
) -> dict[str, str]:
    if _LANE.fullmatch(lane_id) is None:
        raise RootlessExecutionManifestError("rootless lane identity differs")
    runner_path = _public_file(runner)
    bound: dict[str, Path] = {}
    for item in dependencies:
        match = _ROLE_PATH.fullmatch(item)
        if match is None:
            raise RootlessExecutionManifestError("dependency binding differs")
        role, relative = match.groups()
        key = f"{role}_sha256"
        if key in bound or relative == runner:
            raise RootlessExecutionManifestError("dependency binding differs")
        bound[key] = _public_file(relative)
    if not bound:
        raise RootlessExecutionManifestError("dependency binding differs")
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:
        raise RootlessExecutionManifestError("source identity differs")
    return {
        "source_commit": source.git_commit,
        "source_bundle_sha256": working_source_bundle_sha256(PROJECT_ROOT),
        "runner_sha256": _file_sha256(runner_path),
        **{key: _file_sha256(path) for key, path in sorted(bound.items())},
        "manifest_freezer_sha256": _file_sha256(Path(__file__).resolve()),
        "runtime_sha256": build_runtime_identity().sha256,
    }


def _bindings(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        match = _DIGEST_BINDING.fullmatch(value)
        if match is None or not match.group(1).endswith("_sha256"):
            raise RootlessExecutionManifestError("semantic binding differs")
        key, digest = match.groups()
        if key in result:
            raise RootlessExecutionManifestError("semantic binding differs")
        result[key] = digest
    return result


def _public_file(relative: str) -> Path:
    match = _ROLE_PATH.fullmatch(f"runner={relative}")
    if match is None:
        raise RootlessExecutionManifestError("public file binding differs")
    path = PROJECT_ROOT / relative
    try:
        named = path.lstat()
        resolved = path.resolve(strict=True)
        root = PROJECT_ROOT.resolve(strict=True)
    except OSError:
        raise RootlessExecutionManifestError("public file is unavailable") from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(named.st_mode)
        or named.st_nlink != 1
        or root not in resolved.parents
    ):
        raise RootlessExecutionManifestError("public file binding differs")
    return resolved


def _write_manifest(path: Path, payload: bytes) -> None:
    try:
        PUBLIC_MANIFEST_ROOT.mkdir(mode=0o700, exist_ok=True)
        root = PUBLIC_MANIFEST_ROOT.resolve(strict=True)
        named = PUBLIC_MANIFEST_ROOT.lstat()
        parent = path.parent.resolve(strict=True)
    except OSError:
        raise RootlessExecutionManifestError("manifest destination differs") from None
    if (
        PUBLIC_MANIFEST_ROOT.is_symlink()
        or not stat.S_ISDIR(named.st_mode)
        or parent != root
        or path.suffix != ".json"
    ):
        raise RootlessExecutionManifestError("manifest destination differs")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    directory = -1
    try:
        descriptor = os.open(path, flags, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("manifest write made no progress")
            offset += written
        os.fsync(descriptor)
        directory = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        os.fsync(directory)
    except OSError:
        raise RootlessExecutionManifestError("manifest publication failed") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if directory >= 0:
            os.close(directory)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
