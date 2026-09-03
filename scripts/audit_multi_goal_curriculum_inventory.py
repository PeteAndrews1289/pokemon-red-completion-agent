#!/usr/bin/env python3
"""Authenticate Red multi-goal curriculum supply without running game or model."""

# ruff: noqa: E402 -- make the repository source authoritative for direct invocation

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
while str(SRC_ROOT) in sys.path:
    sys.path.remove(str(SRC_ROOT))
sys.path.insert(0, str(SRC_ROOT))

from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    root_claim_is_available,
    root_consumption_sha256,
)
from pokemon_red_completion.goal_manager_protocol import (
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.multi_goal_curriculum_inventory import (
    MultiGoalCurriculumInventoryError,
    audit_multi_goal_curriculum_inventory,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--profile-lineage", type=Path, required=True)
    parser.add_argument("--expected-profile-lineage-sha256", required=True)
    parser.add_argument("--lineage-manifest", type=Path)
    parser.add_argument("--expected-lineage-manifest-sha256")
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    plan_payload = _read_bound(
        args.plan, args.expected_plan_sha256, subject="context plan"
    )
    profile_lineage_payload = _read_bound(
        args.profile_lineage,
        args.expected_profile_lineage_sha256,
        subject="profile lineage",
    )
    try:
        plan = json.loads(plan_payload.decode("ascii"))
        source_commit = plan["source_commit"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        raise MultiGoalCurriculumInventoryError("context plan binding differs") from None
    if not isinstance(source_commit, str):
        raise MultiGoalCurriculumInventoryError("context plan binding differs")
    registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT, source_commit
    )
    lineage_payload = None
    if args.lineage_manifest is not None:
        if args.expected_lineage_manifest_sha256 is None:
            raise MultiGoalCurriculumInventoryError(
                "verified lineage manifest digest is required"
            )
        lineage_payload = _read_bound(
            args.lineage_manifest,
            args.expected_lineage_manifest_sha256,
            subject="verified lineage manifest",
        )
    elif args.expected_lineage_manifest_sha256 is not None:
        raise MultiGoalCurriculumInventoryError(
            "verified lineage manifest location is required"
        )
    claim_registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(claim_registry, exclusive=False):
        result = audit_multi_goal_curriculum_inventory(
            plan_payload=plan_payload,
            profile_lineage_payload=profile_lineage_payload,
            registry=registry,
            read_file=_read_external,
            lineage_manifest_payload=lineage_payload,
            root_is_available=lambda state_sha256, envelope_sha256: (
                root_claim_is_available(
                    claim_registry,
                    root_consumption_sha256(
                        state_sha256=state_sha256,
                        envelope_sha256=envelope_sha256,
                    ),
                )
            ),
        )
    return result.public_dict()


def _read_bound(path: Path, expected_sha256: object, *, subject: str) -> bytes:
    payload = _read_regular(path, subject=subject)
    if (
        not isinstance(expected_sha256, str)
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise MultiGoalCurriculumInventoryError(f"{subject} digest differs")
    return payload


def _read_external(location: str) -> bytes:
    return _read_regular(Path(location), subject="private context input")


def _read_regular(path: Path, *, subject: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError:
        raise MultiGoalCurriculumInventoryError(f"{subject} is unavailable") from None
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise MultiGoalCurriculumInventoryError(f"{subject} is not a regular file")
    try:
        return path.read_bytes()
    except OSError:
        raise MultiGoalCurriculumInventoryError(f"{subject} is unavailable") from None


def main() -> int:
    try:
        result = _run(_parser().parse_args())
    except (MultiGoalCurriculumInventoryError, OSError) as error:
        print(json.dumps({"status": "failed", "reason": type(error).__name__}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
