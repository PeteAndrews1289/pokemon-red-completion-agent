#!/usr/bin/env python3
"""Freeze all 81 passed goal-manager preflights before any counted action."""

from __future__ import annotations

import argparse
import json
import os
from contextlib import suppress
from pathlib import Path

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalogError,
    build_goal_manager_context_catalog_payload,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_preflight import (
    GoalManagerPreflightError,
    context_entry_from_preflight,
    parse_goal_manager_preflight,
)
from pokemon_red_completion.goal_manager_protocol import (
    GoalManagerProtocolError,
    load_committed_goal_manager_registry,
)
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class GoalManagerCatalogFreezeError(RuntimeError):
    """Raised when the prospective context set is incomplete or unsafe."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-root", type=Path, required=True)
    parser.add_argument("--out-catalog", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = _freeze(args.preflight_root, args.out_catalog)
    except (
        EvaluationIdentityError,
        GoalManagerCatalogFreezeError,
        GoalManagerContextCatalogError,
        GoalManagerPreflightError,
        GoalManagerProtocolError,
        OSError,
    ):
        parser.error(
            "Goal-manager context freeze failed closed; private paths were withheld."
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _freeze(preflight_root: Path, out_catalog: Path) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    registry = load_committed_goal_manager_registry(PROJECT_ROOT)
    if (
        source.git_commit != registry.execution.source_commit
        or working_source_bundle_sha256(PROJECT_ROOT)
        != registry.execution.source_bundle_sha256
    ):
        raise GoalManagerCatalogFreezeError(
            "working source differs from the committed goal-manager registry"
        )

    root = preflight_root.resolve()
    destination = out_catalog.resolve()
    repository = PROJECT_ROOT.resolve()
    if (
        not root.is_dir()
        or root.is_relative_to(repository)
        or destination.is_relative_to(repository)
        or not destination.parent.is_dir()
        or destination.exists()
    ):
        raise GoalManagerCatalogFreezeError(
            "goal-manager context artifacts must use new private external paths"
        )
    expected_names = {f"{slot.slot_id}.json" for slot in registry.slots}
    observed_names = {path.name for path in root.glob("*.json") if path.is_file()}
    if observed_names != expected_names:
        raise GoalManagerCatalogFreezeError(
            "goal-manager preflight file coverage differs from the registry"
        )

    entries = []
    for slot in registry.slots:
        assignment = registry.assignment(slot.slot_id)
        payload = (root / f"{slot.slot_id}.json").read_bytes()
        preflight = parse_goal_manager_preflight(payload, assignment)
        entries.append(context_entry_from_preflight(assignment, preflight))
    catalog_payload = build_goal_manager_context_catalog_payload(
        registry,
        tuple(entries),
    )
    catalog = parse_goal_manager_context_catalog(catalog_payload, registry)
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(catalog_payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        with suppress(OSError):
            destination.unlink()
        raise
    return {
        **catalog.public_dict(),
        "status": "frozen",
        "counted_actions_executed": 0,
        "episodes_created": 0,
    }


if __name__ == "__main__":
    raise SystemExit(main())
