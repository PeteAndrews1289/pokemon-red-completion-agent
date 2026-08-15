#!/usr/bin/env python3
"""Compose the private Route 11 venue-prior registry from public receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_published_source,
)
from pokemon_red_completion.red_party_development_venue_priors import (  # noqa: E402
    attest_red_route_11_source_compatibility,
    compose_red_route_11_venue_prior,
)

DEFAULT_PLAN_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-party-development-outcome-plan-v2-2026-08-14.json"
)
DEFAULT_RESULT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-party-development-outcome-result-v2-2026-08-14.json"
)
_MAX_RECEIPT_BYTES = 1024 * 1024


class RedVenuePriorCompositionRunError(RuntimeError):
    """Raised before private venue evidence can be written ambiguously."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT_PATH)
    parser.add_argument("--out-registry", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    return parser


def _load_receipt(path: Path) -> tuple[dict[str, object], str]:
    payload = path.read_bytes()
    if not payload or len(payload) > _MAX_RECEIPT_BYTES:
        raise RedVenuePriorCompositionRunError("public venue receipt size is invalid")
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RedVenuePriorCompositionRunError(
            "public venue receipt is invalid"
        ) from error
    if not isinstance(value, dict):
        raise RedVenuePriorCompositionRunError(
            "public venue receipt must be an object"
        )
    return value, hashlib.sha256(payload).hexdigest()


def _canonical_payload(document: dict[str, object]) -> bytes:
    return (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")


def _write_exclusive(path: Path, payload: bytes) -> str:
    if not isinstance(payload, bytes):
        raise TypeError("venue-prior payload must be bytes")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(payload).hexdigest()


def _run(args: argparse.Namespace) -> dict[str, object]:
    registry_path = args.out_registry.resolve()
    summary_path = args.out_summary.resolve()
    if registry_path == summary_path:
        raise RedVenuePriorCompositionRunError(
            "private registry and public summary need distinct outputs"
        )
    try:
        registry_path.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise RedVenuePriorCompositionRunError(
            "private venue-prior registry must remain outside the repository"
        )
    if registry_path.exists() or summary_path.exists():
        raise FileExistsError("venue-prior output already exists")

    identity = detect_source_identity(PROJECT_ROOT)
    require_published_source(PROJECT_ROOT, identity)
    if identity.git_commit is None:  # pragma: no cover - publication guard owns this
        raise AssertionError("published source lost its commit")
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)
    source_compatibility = attest_red_route_11_source_compatibility(
        PROJECT_ROOT,
        current_commit=identity.git_commit,
        current_source_bundle_sha256=source_bundle_sha256,
    )
    plan, plan_sha256 = _load_receipt(args.plan)
    result, result_sha256 = _load_receipt(args.result)
    composition = compose_red_route_11_venue_prior(
        plan=plan,
        result=result,
        public_plan_sha256=plan_sha256,
        public_result_sha256=result_sha256,
        registry_source_commit=identity.git_commit,
        registry_source_bundle_sha256=source_bundle_sha256,
        source_compatibility=source_compatibility,
    )
    registry_payload = _canonical_payload(composition.registry.private_dict())
    registry_file_sha256 = hashlib.sha256(registry_payload).hexdigest()
    summary = {
        **composition.public_dict(),
        "private_registry_file_sha256": registry_file_sha256,
    }
    summary_payload = _canonical_payload(summary)
    _write_exclusive(registry_path, registry_payload)
    try:
        summary_file_sha256 = _write_exclusive(summary_path, summary_payload)
    except BaseException:
        registry_path.unlink(missing_ok=True)
        raise
    return {
        **summary,
        "public_summary_file_sha256": summary_file_sha256,
    }


def main(argv: list[str] | None = None) -> int:
    summary = _run(_parser().parse_args(argv))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
