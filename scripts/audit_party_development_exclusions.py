#!/usr/bin/env python3
"""Audit prior-exclusion effectiveness without exposing private identities."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.goal_manager_context_catalog import (  # noqa: E402
    GoalManagerContextCatalog,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.party_development_exclusion_audit import (  # noqa: E402
    audit_party_development_exclusions,
)
from pokemon_red_completion.party_development_inventory import (  # noqa: E402
    PartyDevelopmentCheckpointInventory,
)
from pokemon_red_completion.party_development_question_reservations import (  # noqa: E402
    PartyDevelopmentQuestionReservationPlan,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)


class PartyDevelopmentExclusionAuditRunError(RuntimeError):
    """Raised before a private exclusion audit can be misidentified."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--inventory-file-sha256", required=True)
    parser.add_argument("--reservation-plan", type=Path, required=True)
    parser.add_argument("--reservation-plan-file-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--context-catalog-file-sha256", required=True)
    return parser


def _load_private_json(
    path: Path,
    *,
    expected_sha256: str,
    subject: str,
) -> Mapping[str, object]:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise PartyDevelopmentExclusionAuditRunError(
            f"private {subject} must remain outside the repository"
        )
    payload = resolved.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise PartyDevelopmentExclusionAuditRunError(
            f"private {subject} file digest differs"
        )
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PartyDevelopmentExclusionAuditRunError(
            f"private {subject} is invalid"
        ) from error
    if not isinstance(value, Mapping):
        raise PartyDevelopmentExclusionAuditRunError(
            f"private {subject} is not an object"
        )
    return value


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    inventory = PartyDevelopmentCheckpointInventory.from_private_dict(
        _load_private_json(
            args.inventory,
            expected_sha256=args.inventory_file_sha256,
            subject="inventory",
        )
    )
    plan = PartyDevelopmentQuestionReservationPlan.from_private_dict(
        _load_private_json(
            args.reservation_plan,
            expected_sha256=args.reservation_plan_file_sha256,
            subject="reservation plan",
        )
    )
    catalog_document = _load_private_json(
        args.context_catalog,
        expected_sha256=args.context_catalog_file_sha256,
        subject="historical context catalog",
    )
    catalog_source_commit = catalog_document.get("source_commit")
    if not isinstance(catalog_source_commit, str):
        raise PartyDevelopmentExclusionAuditRunError(
            "historical context catalog source is invalid"
        )
    historical_registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        catalog_source_commit,
    )
    catalog: GoalManagerContextCatalog = parse_goal_manager_context_catalog(
        args.context_catalog.read_bytes(),
        historical_registry,
    )
    root_lineage_by_checkpoint_id = {}
    for inventory_entry in inventory.entries:
        catalog_entry = catalog.entry(inventory_entry.checkpoint_id)
        root_lineage_by_checkpoint_id[inventory_entry.checkpoint_id] = (
            catalog_entry.authenticated_root_lineage_id(
                slot_id=inventory_entry.checkpoint_id,
                capture_id=inventory_entry.checkpoint_id,
                state_sha256=inventory_entry.state_sha256,
                envelope_sha256=inventory_entry.envelope_sha256,
            )
        )
    audit = audit_party_development_exclusions(
        inventory,
        plan,
        root_lineage_by_checkpoint_id=root_lineage_by_checkpoint_id,
    )
    return {
        **audit.public_dict(),
        "source_commit": source.git_commit,
        "historical_context_catalog_sha256": catalog.catalog_sha256,
        "historical_goal_manager_registry_sha256": catalog.registry_sha256,
        "historical_goal_manager_source_commit": catalog.source_commit,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _run(parser.parse_args(argv))
    except (OSError, RuntimeError, TypeError, ValueError):
        parser.error(
            "Party exclusion audit failed closed; private paths were withheld."
        )
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
