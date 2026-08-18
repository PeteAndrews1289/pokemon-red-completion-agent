# ruff: noqa: E402 -- the script module is deliberately outside the package bundle.

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import public_execution_manifest as public_manifest
from public_execution_manifest import (
    PUBLIC_EXECUTION_MANIFEST_DIRECTORY,
    PublicExecutionManifestError,
    authenticate_public_execution_manifest,
    canonical_manifest_line,
    freeze_public_execution_manifest,
    public_execution_invocation,
    read_public_manifest,
)


def _bindings() -> dict[str, str]:
    return {
        "source_commit": "a" * 40,
        "source_bundle_sha256": "1" * 64,
        "runner_sha256": "2" * 64,
        "multiroot_runner_sha256": "3" * 64,
        "paired_runner_sha256": "4" * 64,
        "development_runner_sha256": "5" * 64,
        "runtime_sha256": "6" * 64,
        "numpy_runtime_sha256": "7" * 64,
        "skill_manifest_sha256": "8" * 64,
        "manifest_freezer_sha256": "9" * 64,
    }


def _invocation() -> dict[str, object]:
    return public_execution_invocation(
        lane_id="causal-lane-v2",
        operation="freeze",
        expected_campaign_sha256=None,
        expected_freeze_execution_manifest_sha256=None,
        expected_context_plan_sha256="b" * 64,
        expected_fit_result_receipt_sha256="c" * 64,
        expected_prior_campaign_sha256=("d" * 64, "e" * 64),
        public_bindings=_bindings(),
        private_input_roles=("context_plan", "rom"),
    )


def _payload() -> bytes:
    return canonical_manifest_line(freeze_public_execution_manifest(invocation=_invocation()))


def test_authenticates_exact_canonical_invocation_and_current_public_code() -> None:
    payload = _payload()

    result = authenticate_public_execution_manifest(
        payload,
        expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
        invocation=_invocation(),
        current_public_bindings=_bindings(),
    )

    assert result["private_path_fields"] == 0
    assert result["private_input_roles"] == ["context_plan", "rom"]


@pytest.mark.parametrize(
    ("binding", "replacement"),
    (
        ("runner_sha256", "0" * 64),
        ("multiroot_runner_sha256", "0" * 64),
        ("development_runner_sha256", "0" * 64),
        ("source_bundle_sha256", "0" * 64),
        ("runtime_sha256", "0" * 64),
    ),
)
def test_rejects_stale_or_swapped_actual_invocation_binding(
    binding: str,
    replacement: str,
) -> None:
    payload = _payload()
    invocation = deepcopy(_invocation())
    public = invocation["public_bindings"]
    assert isinstance(public, dict)
    public[binding] = replacement

    with pytest.raises(PublicExecutionManifestError, match="invocation differs"):
        authenticate_public_execution_manifest(
            payload,
            expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
            invocation=invocation,
            current_public_bindings=_bindings(),
        )


def test_rejects_manifest_whose_stale_hashes_are_internally_rehashed() -> None:
    invocation = deepcopy(_invocation())
    public = invocation["public_bindings"]
    assert isinstance(public, dict)
    public["runner_sha256"] = "0" * 64
    payload = canonical_manifest_line(freeze_public_execution_manifest(invocation=invocation))

    with pytest.raises(PublicExecutionManifestError, match="invocation differs"):
        authenticate_public_execution_manifest(
            payload,
            expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
            invocation=invocation,
            current_public_bindings=_bindings(),
        )


def test_rejects_campaign_or_prior_order_drift() -> None:
    payload = _payload()
    invocation = deepcopy(_invocation())
    prior = invocation["expected_prior_campaign_sha256"]
    assert isinstance(prior, list)
    prior.reverse()

    with pytest.raises(PublicExecutionManifestError, match="invocation differs"):
        authenticate_public_execution_manifest(
            payload,
            expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
            invocation=invocation,
            current_public_bindings=_bindings(),
        )


def test_rejects_private_path_injection_and_unsorted_roles() -> None:
    with pytest.raises(PublicExecutionManifestError, match="private input role"):
        public_execution_invocation(
            lane_id="causal-lane-v2",
            operation="freeze",
            expected_campaign_sha256=None,
            expected_freeze_execution_manifest_sha256=None,
            expected_context_plan_sha256="b" * 64,
            expected_fit_result_receipt_sha256="c" * 64,
            expected_prior_campaign_sha256=("d" * 64,),
            public_bindings=_bindings(),
            private_input_roles=("rom", "/private/secret"),
        )
    with pytest.raises(PublicExecutionManifestError, match="unique and sorted"):
        public_execution_invocation(
            lane_id="causal-lane-v2",
            operation="freeze",
            expected_campaign_sha256=None,
            expected_freeze_execution_manifest_sha256=None,
            expected_context_plan_sha256="b" * 64,
            expected_fit_result_receipt_sha256="c" * 64,
            expected_prior_campaign_sha256=("d" * 64,),
            public_bindings=_bindings(),
            private_input_roles=("rom", "context_plan"),
        )


def test_rejects_duplicate_keys_and_noncanonical_bytes() -> None:
    payload = _payload()
    duplicate = payload[:-2] + b',"schema":"pokemon.core.public-execution-manifest.v1"}\n'
    pretty = json.dumps(json.loads(payload), indent=2, sort_keys=True).encode() + b"\n"

    for mutated in (duplicate, pretty):
        with pytest.raises(PublicExecutionManifestError):
            authenticate_public_execution_manifest(
                mutated,
                expected_manifest_sha256=hashlib.sha256(mutated).hexdigest(),
                invocation=_invocation(),
                current_public_bindings=_bindings(),
            )


def test_reader_rejects_symlink(tmp_path: Path) -> None:
    public_root = tmp_path / PUBLIC_EXECUTION_MANIFEST_DIRECTORY
    public_root.mkdir()
    target = public_root / "manifest.json"
    target.write_bytes(_payload())
    link = public_root / "linked.json"
    link.symlink_to(target)

    with pytest.raises(PublicExecutionManifestError, match="public regular"):
        read_public_manifest(link, repository_root=tmp_path)


def test_reader_rejects_arbitrary_path_outside_public_repo_location(
    tmp_path: Path,
) -> None:
    (tmp_path / PUBLIC_EXECUTION_MANIFEST_DIRECTORY).mkdir()
    outside = tmp_path / "private-manifest.json"
    outside.write_bytes(_payload())

    with pytest.raises(PublicExecutionManifestError, match="public regular"):
        read_public_manifest(outside, repository_root=tmp_path)


@pytest.mark.parametrize("protected_role", ("rom", "private_root", "claim_registry"))
def test_reader_rejects_hardlink_aliases_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    protected_role: str,
) -> None:
    public_root = tmp_path / PUBLIC_EXECUTION_MANIFEST_DIRECTORY
    public_root.mkdir()
    protected = tmp_path / protected_role
    protected.write_bytes(_payload())
    alias = public_root / "manifest.json"
    alias.hardlink_to(protected)
    monkeypatch.setattr(
        public_manifest.os,
        "open",
        lambda *args, **kwargs: pytest.fail("aliased input was opened"),
    )

    with pytest.raises(PublicExecutionManifestError, match="public regular"):
        read_public_manifest(
            alias,
            repository_root=tmp_path,
            forbidden_aliases=(protected,),
        )


def test_reader_rejects_inode_swap_between_lstat_and_descriptor_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_root = tmp_path / PUBLIC_EXECUTION_MANIFEST_DIRECTORY
    public_root.mkdir()
    manifest = public_root / "manifest.json"
    payload = _payload()
    manifest.write_bytes(payload)
    replacement = public_root / "replacement.json"
    replacement.write_bytes(b"x" * len(payload))
    real_open = public_manifest.os.open

    def swapping_open(path, flags, *, dir_fd=None):  # type: ignore[no-untyped-def]
        if dir_fd is not None:
            manifest.unlink()
            replacement.rename(manifest)
            return real_open(path, flags, dir_fd=dir_fd)
        return real_open(path, flags)

    monkeypatch.setattr(public_manifest.os, "open", swapping_open)

    with pytest.raises(PublicExecutionManifestError, match="changed while opening"):
        read_public_manifest(manifest, repository_root=tmp_path)


def test_reader_rejects_public_directory_swap_before_file_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_root = tmp_path / PUBLIC_EXECUTION_MANIFEST_DIRECTORY
    public_root.mkdir()
    manifest = public_root / "manifest.json"
    manifest.write_bytes(_payload())
    moved = tmp_path / "moved-public-root"
    real_open = public_manifest.os.open
    swapped = False

    def swapping_open(path, flags, *, dir_fd=None):  # type: ignore[no-untyped-def]
        nonlocal swapped
        if not swapped and dir_fd is None:
            swapped = True
            public_root.rename(moved)
            public_root.mkdir()
        if dir_fd is None:
            return real_open(path, flags)
        return real_open(path, flags, dir_fd=dir_fd)

    monkeypatch.setattr(public_manifest.os, "open", swapping_open)

    with pytest.raises(PublicExecutionManifestError, match="directory changed"):
        read_public_manifest(manifest, repository_root=tmp_path)


def test_nonfreeze_requires_exact_campaign_binding() -> None:
    with pytest.raises(PublicExecutionManifestError, match="campaign binding"):
        public_execution_invocation(
            lane_id="causal-lane-v2",
            operation="execute",
            expected_campaign_sha256=None,
            expected_freeze_execution_manifest_sha256="f" * 64,
            expected_context_plan_sha256="b" * 64,
            expected_fit_result_receipt_sha256="c" * 64,
            expected_prior_campaign_sha256=("d" * 64,),
            public_bindings=_bindings(),
            private_input_roles=("rom",),
        )


def test_nonfreeze_invocation_authenticates_exact_freeze_manifest_binding() -> None:
    invocation = public_execution_invocation(
        lane_id="causal-lane-v2",
        operation="execute",
        expected_campaign_sha256="a" * 64,
        expected_freeze_execution_manifest_sha256="f" * 64,
        expected_context_plan_sha256="b" * 64,
        expected_fit_result_receipt_sha256="c" * 64,
        expected_prior_campaign_sha256=("d" * 64,),
        public_bindings=_bindings(),
        private_input_roles=("rom",),
    )
    payload = canonical_manifest_line(freeze_public_execution_manifest(invocation=invocation))
    changed = deepcopy(invocation)
    changed["expected_freeze_execution_manifest_sha256"] = "0" * 64

    with pytest.raises(PublicExecutionManifestError, match="invocation differs"):
        authenticate_public_execution_manifest(
            payload,
            expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
            invocation=changed,
            current_public_bindings=_bindings(),
        )
