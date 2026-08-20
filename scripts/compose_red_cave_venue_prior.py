#!/usr/bin/env python3
"""Compose exactly one Cave prior beside the frozen Route 11 prior."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.party_development_venue_priors import (  # noqa: E402
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_cave_venue_measurement import (  # noqa: E402
    RED_CAVE_VENUE_PRIOR_REGISTRY_FILE_SHA256,
)
from pokemon_red_completion.red_cave_venue_prior import (  # noqa: E402
    attest_red_cave_source_compatibility,
    compose_red_cave_venue_prior,
)

DEFAULT_PLAN_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-cave-venue-measurement-plan-v2-2026-08-15.json"
)
DEFAULT_RESULT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-cave-venue-measurement-result-v2-2026-08-16.json"
)
_MAX_JSON_BYTES = 1024 * 1024


class RedCaveVenuePriorRunError(RuntimeError):
    """Raised before a Cave prior can be written ambiguously."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT_PATH)
    parser.add_argument("--existing-registry", type=Path, required=True)
    parser.add_argument("--existing-registry-file-sha256", required=True)
    parser.add_argument("--out-registry", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    return parser


def _load_json(path: Path, *, expected_sha256: str | None = None) -> tuple[dict[str, object], str]:
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if (
        not payload
        or len(payload) > _MAX_JSON_BYTES
        or (expected_sha256 is not None and digest != expected_sha256)
    ):
        raise RedCaveVenuePriorRunError("Cave prior input bytes are invalid")
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RedCaveVenuePriorRunError("Cave prior input is invalid") from error
    if not isinstance(value, dict):
        raise RedCaveVenuePriorRunError("Cave prior input must be an object")
    return value, digest


def _canonical_payload(document: Mapping[str, object]) -> bytes:
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
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(payload).hexdigest()


def _require_external(path: Path, *, subject: str) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise RedCaveVenuePriorRunError(f"{subject} must remain outside the repository")
    return resolved


def _run(args: argparse.Namespace) -> dict[str, object]:
    if (
        args.existing_registry_file_sha256
        != RED_CAVE_VENUE_PRIOR_REGISTRY_FILE_SHA256
    ):
        raise RedCaveVenuePriorRunError(
            "existing registry argument differs from the prospective plan"
        )
    existing_path = _require_external(
        args.existing_registry,
        subject="existing private registry",
    )
    registry_path = _require_external(
        args.out_registry,
        subject="composed private registry",
    )
    summary_path = _require_external(
        args.out_summary,
        subject="composition summary",
    )
    if len({existing_path, registry_path, summary_path}) != 3:
        raise RedCaveVenuePriorRunError("Cave prior paths must be distinct")
    if registry_path.exists() or summary_path.exists():
        raise FileExistsError("Cave prior output already exists")

    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - source guards own this
        raise AssertionError("published Cave prior source lost its commit")
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)
    source_compatibility = attest_red_cave_source_compatibility(
        PROJECT_ROOT,
        current_commit=source.git_commit,
        current_source_bundle_sha256=source_bundle_sha256,
    )

    existing_document, _existing_sha256 = _load_json(
        existing_path,
        expected_sha256=args.existing_registry_file_sha256,
    )
    existing_registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(
        existing_document
    )
    plan, plan_sha256 = _load_json(args.plan)
    result, result_sha256 = _load_json(args.result)
    composition = compose_red_cave_venue_prior(
        existing_registry=existing_registry,
        plan=plan,
        result=result,
        public_plan_sha256=plan_sha256,
        public_result_sha256=result_sha256,
        registry_source_commit=source.git_commit,
        registry_source_bundle_sha256=source_bundle_sha256,
        source_compatibility=source_compatibility,
        repository_root=PROJECT_ROOT,
    )
    registry_payload = _canonical_payload(composition.registry.private_dict())
    registry_file_sha256 = hashlib.sha256(registry_payload).hexdigest()
    summary: dict[str, object] = {
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
    result = _run(_parser().parse_args(argv))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
