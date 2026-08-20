"""Canonical public invocation manifests for the rootless dependency pipeline."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence

from public_execution_manifest import canonical_manifest_line

from pokemon_red_completion.provenance import canonical_sha256

ROOTLESS_EXECUTION_MANIFEST_SCHEMA = "pokemon.core.rootless-execution-manifest.v1"
ROOTLESS_EXECUTION_INVOCATION_SCHEMA = "pokemon.core.rootless-execution-invocation.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,127}\Z")


class RootlessExecutionManifestError(RuntimeError):
    """The public rootless invocation manifest is invalid or stale."""


def rootless_execution_invocation(
    *,
    lane_id: str,
    operation: str,
    semantic_bindings: Mapping[str, str],
    public_bindings: Mapping[str, str],
    private_input_roles: Sequence[str],
) -> dict[str, object]:
    roles = tuple(_token(value, "private input role") for value in private_input_roles)
    if not roles or roles != tuple(sorted(roles)) or len(set(roles)) != len(roles):
        raise RootlessExecutionManifestError("private input roles differ")
    return {
        "schema": ROOTLESS_EXECUTION_INVOCATION_SCHEMA,
        "lane_id": _token(lane_id, "lane"),
        "operation": _token(operation, "operation"),
        "semantic_bindings": _digest_bindings(semantic_bindings, subject="semantic"),
        "public_bindings": _public_bindings(public_bindings),
        "private_input_roles": list(roles),
        "private_path_fields": 0,
    }


def freeze_rootless_execution_manifest(
    invocation: Mapping[str, object],
) -> dict[str, object]:
    normalized = _invocation(invocation)
    return {
        "schema": ROOTLESS_EXECUTION_MANIFEST_SCHEMA,
        "lane_id": normalized["lane_id"],
        "operation": normalized["operation"],
        "invocation": normalized,
        "invocation_sha256": canonical_sha256(normalized),
        "public_bindings": normalized["public_bindings"],
        "semantic_bindings": normalized["semantic_bindings"],
        "private_input_roles": normalized["private_input_roles"],
        "private_path_fields": 0,
    }


def authenticate_rootless_execution_manifest(
    payload: bytes,
    *,
    expected_manifest_sha256: str,
    invocation: Mapping[str, object],
    current_public_bindings: Mapping[str, str],
) -> dict[str, object]:
    expected = _sha(expected_manifest_sha256, "execution manifest")
    if hashlib.sha256(payload).hexdigest() != expected:
        raise RootlessExecutionManifestError("execution manifest digest differs")
    try:
        import json

        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RootlessExecutionManifestError("execution manifest document differs") from None
    if (
        not isinstance(document, dict)
        or canonical_manifest_line(document) != payload
        or set(document)
        != {
            "invocation",
            "invocation_sha256",
            "lane_id",
            "operation",
            "private_input_roles",
            "private_path_fields",
            "public_bindings",
            "schema",
            "semantic_bindings",
        }
        or document.get("schema") != ROOTLESS_EXECUTION_MANIFEST_SCHEMA
    ):
        raise RootlessExecutionManifestError("execution manifest document differs")
    frozen = _invocation(_mapping(document.get("invocation"), "invocation"))
    actual = _invocation(invocation)
    public = _public_bindings(current_public_bindings)
    if (
        frozen != actual
        or frozen["public_bindings"] != public
        or document.get("lane_id") != frozen["lane_id"]
        or document.get("operation") != frozen["operation"]
        or document.get("public_bindings") != public
        or document.get("semantic_bindings") != frozen["semantic_bindings"]
        or document.get("private_input_roles") != frozen["private_input_roles"]
        or document.get("private_path_fields") != 0
        or document.get("invocation_sha256") != canonical_sha256(frozen)
    ):
        raise RootlessExecutionManifestError("execution manifest invocation differs")
    return document


def _invocation(value: Mapping[str, object]) -> dict[str, object]:
    if (
        set(value)
        != {
            "lane_id",
            "operation",
            "private_input_roles",
            "private_path_fields",
            "public_bindings",
            "schema",
            "semantic_bindings",
        }
        or value.get("schema") != ROOTLESS_EXECUTION_INVOCATION_SCHEMA
    ):
        raise RootlessExecutionManifestError("execution invocation fields differ")
    roles = value.get("private_input_roles")
    if (
        not isinstance(roles, list)
        or any(not isinstance(item, str) for item in roles)
        or roles != sorted(roles)
        or len(set(roles)) != len(roles)
        or not roles
        or value.get("private_path_fields") != 0
    ):
        raise RootlessExecutionManifestError("execution invocation roles differ")
    normalized_roles = tuple(_token(item, "private input role") for item in roles)
    semantic_bindings = _digest_bindings(
        _mapping(value.get("semantic_bindings"), "semantic bindings"),
        subject="semantic",
    )
    public_bindings = _public_bindings(_mapping(value.get("public_bindings"), "public bindings"))
    return rootless_execution_invocation(
        lane_id=_token(value.get("lane_id"), "lane"),
        operation=_token(value.get("operation"), "operation"),
        semantic_bindings=semantic_bindings,
        public_bindings=public_bindings,
        private_input_roles=normalized_roles,
    )


def _public_bindings(value: Mapping[str, object]) -> dict[str, str]:
    if "source_commit" not in value or "source_bundle_sha256" not in value:
        raise RootlessExecutionManifestError("public bindings differ")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or _TOKEN.fullmatch(key) is None:
            raise RootlessExecutionManifestError("public binding name differs")
        result[key] = _commit(item, key) if key == "source_commit" else _sha(item, key)
    if not 3 <= len(result) <= 32:
        raise RootlessExecutionManifestError("public binding cardinality differs")
    return dict(sorted(result.items()))


def _digest_bindings(value: Mapping[str, object], *, subject: str) -> dict[str, str]:
    if not value or len(value) > 32:
        raise RootlessExecutionManifestError(f"{subject} binding cardinality differs")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or _TOKEN.fullmatch(key) is None or not key.endswith("_sha256"):
            raise RootlessExecutionManifestError(f"{subject} binding name differs")
        result[key] = _sha(item, key)
    return dict(sorted(result.items()))


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RootlessExecutionManifestError(f"{subject} differ")
    return value


def _token(value: object, subject: str) -> str:
    if not isinstance(value, str) or _TOKEN.fullmatch(value) is None:
        raise RootlessExecutionManifestError(f"{subject} differs")
    return value


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RootlessExecutionManifestError(f"{subject} differs")
    return value


def _commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
        raise RootlessExecutionManifestError(f"{subject} differs")
    return value
