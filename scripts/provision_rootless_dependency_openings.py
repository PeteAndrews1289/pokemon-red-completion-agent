#!/usr/bin/env python3
"""Provision four sealed synthetic development openings and a public commitment roster."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.goal_manager import GoalKind  # noqa: E402
from pokemon_red_completion.living_dex_dependency_curriculum import (  # noqa: E402
    DEVELOPMENT_OPENING_SCHEMA,
    DependencyMultiplicity,
)
from pokemon_red_completion.private_artifacts import (  # noqa: E402
    PrivateArtifactError,
    open_private_root,
)

PROVISION_SCHEMA = "pokemon.private.rootless-dependency-development-provision.v1"
PUBLIC_ROSTER_SCHEMA = "pokemon.core.rootless-dependency-development-roster.v1"
PROVISION_RECORD_ID = "rootless-dependency-development-provision-v1"
PROVISION_KIND = "rootless-dependency-development-provision"
OPENING_KIND = "rootless-dependency-development-opening"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--public-roster", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        provision = store.find_sealed_record(
            PROVISION_RECORD_ID,
            expected_kind=PROVISION_KIND,
        )
        if provision is None:
            provision_document = _new_provision()
            provision = store.publish_sealed_record(
                PROVISION_RECORD_ID,
                kind=PROVISION_KIND,
                record=provision_document,
            )
        else:
            provision_document = provision.read()
            _validate_provision(provision_document)
        openings = provision_document.get("openings")
        if not isinstance(openings, list):
            raise ValueError("development provision differs")
        rows: list[dict[str, str]] = []
        for raw in openings:
            if not isinstance(raw, dict):
                raise ValueError("opening differs")
            record_id = raw["scenario_id"]
            if not isinstance(record_id, str):
                raise ValueError("opening identity differs")
            opening = store.publish_sealed_record(
                record_id,
                kind=OPENING_KIND,
                record=raw,
            )
            rows.append(
                {
                    "scenario_id": record_id,
                    "opening_sha256": opening.summary.record_sha256,
                    "record_manifest_sha256": opening.summary.manifest_sha256,
                }
            )
        roster = {
            "schema": PUBLIC_ROSTER_SCHEMA,
            "row_count": 4,
            "rows": rows,
            "provision_record_sha256": provision.summary.record_sha256,
            "private_path_fields": 0,
        }
        payload = _line(roster)
        _publish_public_roster(args.public_roster, payload)
        print(
            json.dumps(
                {
                    "schema": "pokemon.core.rootless-dependency-provision-result.v1",
                    "status": "development_openings_provisioned",
                    "development_commitments": 4,
                    "development_openings_decoded_for_training": 0,
                    "public_roster_sha256": hashlib.sha256(payload).hexdigest(),
                    "provision_record_sha256": provision.summary.record_sha256,
                    "rom_accesses": 0,
                    "controller_actions": 0,
                    "model_predictions": 0,
                    "model_fits": 0,
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, PrivateArtifactError, TypeError, ValueError):
        print(
            json.dumps(
                {
                    "schema": "pokemon.core.rootless-dependency-provision-failure.v1",
                    "status": "failed_closed",
                    "failure_stage": "development_opening_provision",
                    "rom_accesses": 0,
                    "controller_actions": 0,
                    "model_predictions": 0,
                    "model_fits": 0,
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1


def _new_provision() -> dict[str, object]:
    structures: list[tuple[int, int]] = []
    while len(structures) < 2:
        candidate = (3 + secrets.randbelow(13), 3 + secrets.randbelow(13))
        if candidate not in structures:
            structures.append(candidate)
    openings: list[dict[str, object]] = []
    for family_index, (precursor, evolved) in enumerate(structures):
        family_id = f"development-family-{secrets.token_hex(8)}"
        for multiplicity in DependencyMultiplicity:
            scarce = multiplicity is DependencyMultiplicity.SCARCE
            action = (
                GoalKind.ACQUIRE_SPECIES
                if scarce == (family_index % 2 == 0)
                else GoalKind.EVOLVE_SPECIES
            )
            openings.append(
                {
                    "schema": DEVELOPMENT_OPENING_SCHEMA,
                    "scenario_id": f"rootless-development-{secrets.token_hex(8)}",
                    "family_id": family_id,
                    "nonce": secrets.token_hex(32),
                    "partition": "development",
                    "multiplicity": multiplicity.value,
                    "structure": {
                        "required_precursor_count": precursor,
                        "required_evolved_count": evolved,
                    },
                    "before": {
                        "precursor_count": (precursor if scarce else precursor + evolved),
                        "evolved_count": 0,
                    },
                    "assigned_action": action.value,
                }
            )
    document = {
        "schema": PROVISION_SCHEMA,
        "opening_count": 4,
        "openings": openings,
        "entropy": "os-csprng",
    }
    _validate_provision(document)
    return document


def _validate_provision(document: dict[str, object]) -> None:
    if set(document) != {"entropy", "opening_count", "openings", "schema"} or (
        document.get("schema") != PROVISION_SCHEMA
        or document.get("opening_count") != 4
        or document.get("entropy") != "os-csprng"
    ):
        raise ValueError("development provision differs")
    openings = document.get("openings")
    if not isinstance(openings, list) or len(openings) != 4:
        raise ValueError("development provision differs")
    ids: set[str] = set()
    nonces: set[str] = set()
    for opening in openings:
        if not isinstance(opening, dict):
            raise ValueError("development provision differs")
        scenario_id = opening.get("scenario_id")
        nonce = opening.get("nonce")
        if not isinstance(scenario_id, str) or not isinstance(nonce, str):
            raise ValueError("development provision differs")
        ids.add(scenario_id)
        nonces.add(nonce)
    if len(ids) != 4 or len(nonces) != 4:
        raise ValueError("development provision differs")


def _publish_public_roster(path: Path, payload: bytes) -> None:
    expected = PROJECT_ROOT / "configs" / "rootless-dependency-development-roster-v1.json"
    if path.resolve(strict=False) != expected.resolve(strict=False):
        raise ValueError("public roster destination differs")
    path = expected
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("public roster already differs")
        return
    descriptor = -1
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("roster write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _line(document: dict[str, object]) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        + b"\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
