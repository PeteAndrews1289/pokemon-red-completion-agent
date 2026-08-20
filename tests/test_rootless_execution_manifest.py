# ruff: noqa: E402 -- the manifest helper is deliberately script-local.

from __future__ import annotations

import hashlib
import sys
from copy import deepcopy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

from public_execution_manifest import canonical_manifest_line
from rootless_execution_manifest import (
    RootlessExecutionManifestError,
    authenticate_rootless_execution_manifest,
    freeze_rootless_execution_manifest,
    rootless_execution_invocation,
)


def _public() -> dict[str, str]:
    return {
        "source_commit": "a" * 40,
        "source_bundle_sha256": "1" * 64,
        "runner_sha256": "2" * 64,
        "core_sha256": "3" * 64,
        "runtime_sha256": "4" * 64,
    }


def _invocation() -> dict[str, object]:
    return rootless_execution_invocation(
        lane_id="rootless-living-dex-dependency-curriculum-v1",
        operation="preflight",
        semantic_bindings={
            "development_roster_sha256": "5" * 64,
            "design_qualification_sha256": "6" * 64,
        },
        public_bindings=_public(),
        private_input_roles=("claim_registry", "development_opening_records", "private_root"),
    )


def test_authenticates_exact_generic_rootless_invocation() -> None:
    payload = canonical_manifest_line(freeze_rootless_execution_manifest(_invocation()))

    result = authenticate_rootless_execution_manifest(
        payload,
        expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
        invocation=_invocation(),
        current_public_bindings=_public(),
    )

    assert result["private_path_fields"] == 0
    assert result["semantic_bindings"]["development_roster_sha256"] == "5" * 64


@pytest.mark.parametrize("mutation", ("operation", "semantic", "runner", "roles", "bytes"))
def test_rootless_manifest_mutations_fail_closed(mutation: str) -> None:
    invocation = _invocation()
    payload = canonical_manifest_line(freeze_rootless_execution_manifest(invocation))
    actual = deepcopy(invocation)
    public = _public()
    expected = hashlib.sha256(payload).hexdigest()
    if mutation == "operation":
        actual["operation"] = "execute"
    elif mutation == "semantic":
        actual["semantic_bindings"]["development_roster_sha256"] = "0" * 64
    elif mutation == "runner":
        public["runner_sha256"] = "0" * 64
    elif mutation == "roles":
        actual["private_input_roles"] = ["private_root"]
    else:
        payload = payload + b" "

    with pytest.raises(RootlessExecutionManifestError):
        authenticate_rootless_execution_manifest(
            payload,
            expected_manifest_sha256=expected,
            invocation=actual,
            current_public_bindings=public,
        )


def test_rejects_unsorted_private_roles_and_nondigest_semantic_names() -> None:
    with pytest.raises(RootlessExecutionManifestError):
        rootless_execution_invocation(
            lane_id="rootless-v1",
            operation="freeze",
            semantic_bindings={"roster": "1" * 64},
            public_bindings=_public(),
            private_input_roles=("private_root", "claim_registry"),
        )
