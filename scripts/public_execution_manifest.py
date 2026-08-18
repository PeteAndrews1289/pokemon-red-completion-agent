"""Canonical public-source manifests for path-free future-lane invocations."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from pokemon_red_completion.provenance import canonical_sha256

PUBLIC_EXECUTION_MANIFEST_SCHEMA = "pokemon.core.public-execution-manifest.v1"
PUBLIC_EXECUTION_INVOCATION_SCHEMA = "pokemon.core.public-execution-invocation.v1"
PUBLIC_EXECUTION_MANIFEST_DIRECTORY = ".public-execution-manifests"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,127}\Z")
_MAX_DOCUMENT_BYTES = 1024 * 1024


class PublicExecutionManifestError(RuntimeError):
    """Raised when a public manifest or its invocation binding is invalid."""


def public_execution_invocation(
    *,
    lane_id: str,
    operation: str,
    expected_campaign_sha256: str | None,
    expected_context_plan_sha256: str,
    expected_fit_result_receipt_sha256: str,
    expected_prior_campaign_sha256: Sequence[str],
    public_bindings: Mapping[str, str],
    private_input_roles: Sequence[str],
) -> dict[str, object]:
    """Build the path-free semantic invocation that a live runner must match."""

    lane = _token(lane_id, "lane")
    mode = _token(operation, "operation")
    roles = tuple(_token(role, "private input role") for role in private_input_roles)
    if not roles or len(set(roles)) != len(roles) or tuple(sorted(roles)) != roles:
        raise PublicExecutionManifestError("private input roles must be unique and sorted")
    prior = tuple(_sha(value, "prior campaign") for value in expected_prior_campaign_sha256)
    if not prior or len(set(prior)) != len(prior):
        raise PublicExecutionManifestError("prior campaign bindings must be unique")
    expected_campaign = (
        None if expected_campaign_sha256 is None else _sha(expected_campaign_sha256, "campaign")
    )
    if (mode == "freeze") != (expected_campaign is None):
        raise PublicExecutionManifestError("campaign binding differs from operation")
    bindings = _public_bindings(public_bindings)
    return {
        "schema": PUBLIC_EXECUTION_INVOCATION_SCHEMA,
        "lane_id": lane,
        "operation": mode,
        "expected_campaign_sha256": expected_campaign,
        "expected_context_plan_sha256": _sha(
            expected_context_plan_sha256,
            "context plan",
        ),
        "expected_fit_result_receipt_sha256": _sha(
            expected_fit_result_receipt_sha256,
            "fit result receipt",
        ),
        "expected_prior_campaign_sha256": list(prior),
        "public_bindings": bindings,
        "private_input_roles": list(roles),
        "private_path_fields": 0,
    }


def freeze_public_execution_manifest(
    *,
    invocation: Mapping[str, object],
) -> dict[str, object]:
    """Freeze one canonical invocation together with its public executable bindings."""

    normalized = _invocation(invocation)
    bindings = cast(Mapping[str, str], normalized["public_bindings"])
    return {
        "schema": PUBLIC_EXECUTION_MANIFEST_SCHEMA,
        "lane_id": normalized["lane_id"],
        "invocation": normalized,
        "invocation_sha256": canonical_sha256(normalized),
        "public_bindings": dict(bindings),
        "private_input_roles": list(cast(Sequence[str], normalized["private_input_roles"])),
        "private_path_fields": 0,
    }


def authenticate_public_execution_manifest(
    payload: bytes,
    *,
    expected_manifest_sha256: str,
    invocation: Mapping[str, object],
    current_public_bindings: Mapping[str, str],
) -> dict[str, object]:
    """Authenticate canonical bytes, current public code, and the exact invocation."""

    expected_digest = _sha(expected_manifest_sha256, "execution manifest")
    if hashlib.sha256(payload).hexdigest() != expected_digest:
        raise PublicExecutionManifestError("execution manifest digest differs")
    document = _canonical_document(payload)
    if (
        set(document)
        != {
            "invocation",
            "invocation_sha256",
            "lane_id",
            "private_input_roles",
            "private_path_fields",
            "public_bindings",
            "schema",
        }
        or document.get("schema") != PUBLIC_EXECUTION_MANIFEST_SCHEMA
    ):
        raise PublicExecutionManifestError("execution manifest schema differs")
    frozen_invocation = _invocation(_mapping(document.get("invocation"), "invocation"))
    actual_invocation = _invocation(invocation)
    frozen_bindings = _public_bindings(_mapping(document.get("public_bindings"), "public bindings"))
    current_bindings = _public_bindings(current_public_bindings)
    if (
        document.get("lane_id") != frozen_invocation["lane_id"]
        or document.get("private_path_fields") != 0
        or document.get("private_input_roles") != frozen_invocation["private_input_roles"]
        or frozen_bindings != frozen_invocation["public_bindings"]
        or document.get("invocation_sha256") != canonical_sha256(frozen_invocation)
        or frozen_invocation != actual_invocation
        or frozen_bindings != current_bindings
    ):
        raise PublicExecutionManifestError("execution manifest invocation differs")
    return document


def canonical_manifest_line(document: Mapping[str, object]) -> bytes:
    """Encode one public manifest in the only accepted byte representation."""

    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def read_public_manifest(
    path: Path,
    *,
    repository_root: Path,
    forbidden_aliases: Sequence[Path] = (),
) -> bytes:
    """Read one repo-local public manifest through a no-follow stable descriptor."""

    try:
        root = repository_root.resolve(strict=True)
        public_root_path = root / PUBLIC_EXECUTION_MANIFEST_DIRECTORY
        public_root = public_root_path.resolve(strict=True)
        public_root_stat = public_root_path.lstat()
        parent = path.parent.resolve(strict=True)
        expected = path.lstat()
    except OSError:
        raise PublicExecutionManifestError("execution manifest is unavailable") from None
    if (
        public_root_path.is_symlink()
        or not stat.S_ISDIR(public_root_stat.st_mode)
        or public_root.parent != root
        or parent != public_root
        or path.name in {"", ".", ".."}
        or not path.name.endswith(".json")
        or stat.S_ISLNK(expected.st_mode)
        or not stat.S_ISREG(expected.st_mode)
        or expected.st_nlink != 1
    ):
        raise PublicExecutionManifestError("execution manifest is not public regular input")
    if not 0 < expected.st_size <= _MAX_DOCUMENT_BYTES:
        raise PublicExecutionManifestError("execution manifest size is invalid")
    for forbidden in forbidden_aliases:
        try:
            forbidden_stat = forbidden.lstat()
        except OSError:
            continue
        if forbidden_stat.st_dev == expected.st_dev and forbidden_stat.st_ino == expected.st_ino:
            raise PublicExecutionManifestError("execution manifest aliases protected input")

    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    directory_descriptor = -1
    descriptor = -1
    try:
        directory_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        if hasattr(os, "O_CLOEXEC"):
            directory_flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            directory_flags |= os.O_NOFOLLOW
        directory_descriptor = os.open(public_root_path, directory_flags)
        opened_root = os.fstat(directory_descriptor)
        if (
            not stat.S_ISDIR(opened_root.st_mode)
            or opened_root.st_dev != public_root_stat.st_dev
            or opened_root.st_ino != public_root_stat.st_ino
        ):
            raise PublicExecutionManifestError("public manifest directory changed")
        descriptor = os.open(path.name, flags, dir_fd=directory_descriptor)
        opened = os.fstat(descriptor)
        if not _same_regular_file(expected, opened):
            raise PublicExecutionManifestError("execution manifest changed while opening")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(
                descriptor,
                min(64 * 1024, _MAX_DOCUMENT_BYTES - total + 1),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > _MAX_DOCUMENT_BYTES:
                raise PublicExecutionManifestError("execution manifest size is invalid")
        finished = os.fstat(descriptor)
        if not _same_regular_file(opened, finished) or total != opened.st_size:
            raise PublicExecutionManifestError("execution manifest changed while reading")
        return b"".join(chunks)
    except PublicExecutionManifestError:
        raise
    except OSError:
        raise PublicExecutionManifestError("execution manifest is unavailable") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def _same_regular_file(first: os.stat_result, second: os.stat_result) -> bool:
    return bool(
        stat.S_ISREG(first.st_mode)
        and stat.S_ISREG(second.st_mode)
        and first.st_nlink == second.st_nlink == 1
        and first.st_dev == second.st_dev
        and first.st_ino == second.st_ino
        and first.st_size == second.st_size
        and first.st_mtime_ns == second.st_mtime_ns
        and first.st_ctime_ns == second.st_ctime_ns
    )


def _invocation(value: Mapping[str, object]) -> dict[str, object]:
    if (
        set(value)
        != {
            "expected_campaign_sha256",
            "expected_context_plan_sha256",
            "expected_fit_result_receipt_sha256",
            "expected_prior_campaign_sha256",
            "lane_id",
            "operation",
            "private_input_roles",
            "private_path_fields",
            "public_bindings",
            "schema",
        }
        or value.get("schema") != PUBLIC_EXECUTION_INVOCATION_SCHEMA
    ):
        raise PublicExecutionManifestError("execution invocation schema differs")
    expected_campaign = value.get("expected_campaign_sha256")
    campaign = None if expected_campaign is None else _sha(expected_campaign, "campaign")
    operation = _token(value.get("operation"), "operation")
    if (operation == "freeze") != (campaign is None):
        raise PublicExecutionManifestError("campaign binding differs from operation")
    prior_raw = value.get("expected_prior_campaign_sha256")
    roles_raw = value.get("private_input_roles")
    if not isinstance(prior_raw, list) or not isinstance(roles_raw, list):
        raise PublicExecutionManifestError("execution invocation lists differ")
    prior = [_sha(item, "prior campaign") for item in prior_raw]
    roles = [_token(item, "private input role") for item in roles_raw]
    if (
        not prior
        or len(set(prior)) != len(prior)
        or not roles
        or len(set(roles)) != len(roles)
        or roles != sorted(roles)
        or value.get("private_path_fields") != 0
    ):
        raise PublicExecutionManifestError("execution invocation cardinality differs")
    return {
        "schema": PUBLIC_EXECUTION_INVOCATION_SCHEMA,
        "lane_id": _token(value.get("lane_id"), "lane"),
        "operation": operation,
        "expected_campaign_sha256": campaign,
        "expected_context_plan_sha256": _sha(
            value.get("expected_context_plan_sha256"),
            "context plan",
        ),
        "expected_fit_result_receipt_sha256": _sha(
            value.get("expected_fit_result_receipt_sha256"),
            "fit result receipt",
        ),
        "expected_prior_campaign_sha256": prior,
        "public_bindings": _public_bindings(
            _mapping(value.get("public_bindings"), "public bindings")
        ),
        "private_input_roles": roles,
        "private_path_fields": 0,
    }


def _public_bindings(value: Mapping[str, object]) -> dict[str, str]:
    required = {"runner_sha256", "source_bundle_sha256", "source_commit"}
    if (
        not required.issubset(value)
        or not 3 <= len(value) <= 32
        or any(_TOKEN.fullmatch(key) is None for key in value)
        or any(key != "source_commit" and not key.endswith("_sha256") for key in value)
    ):
        raise PublicExecutionManifestError("public binding names differ")
    result = {
        key: (_commit(item, key) if key == "source_commit" else _sha(item, key))
        for key, item in value.items()
    }
    return dict(sorted(result.items()))


def _canonical_document(payload: bytes) -> dict[str, object]:
    if not isinstance(payload, bytes) or not 0 < len(payload) <= _MAX_DOCUMENT_BYTES:
        raise PublicExecutionManifestError("execution manifest document is invalid")
    try:
        document = json.loads(payload, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise PublicExecutionManifestError("execution manifest document is invalid") from None
    if not isinstance(document, dict) or canonical_manifest_line(document) != payload:
        raise PublicExecutionManifestError("execution manifest is not canonical")
    return cast(dict[str, object], document)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PublicExecutionManifestError(f"{subject} differs")
    return value


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PublicExecutionManifestError(f"{subject} digest differs")
    return value


def _commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise PublicExecutionManifestError(f"{subject} differs")
    return value


def _token(value: object, subject: str) -> str:
    if not isinstance(value, str) or _TOKEN.fullmatch(value) is None:
        raise PublicExecutionManifestError(f"{subject} differs")
    return value
