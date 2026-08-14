from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalogEntry,
    GoalManagerContextCatalogError,
    build_goal_manager_context_catalog_payload,
    goal_manager_catalog_episode_metadata,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (
    GOAL_MANAGER_REGISTRY_RELATIVE_PATH,
    parse_goal_manager_registry,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _registry():  # type: ignore[no-untyped-def]
    registry = parse_goal_manager_registry(
        (PROJECT_ROOT / GOAL_MANAGER_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    return replace(
        registry,
        execution=replace(registry.execution, source_commit="a" * 40),
    )


def _entries(registry):  # type: ignore[no-untyped-def]
    entries = []
    for ordinal, slot in enumerate(registry.slots, start=1):
        assignment = registry.assignment(slot.slot_id)
        kinds = {slot.focus_kind}
        for kind in GoalKind:
            kinds.add(kind)
            if len(kinds) == 3:
                break
        entries.append(
            GoalManagerContextCatalogEntry.build(
                assignment=assignment,
                capture_id=f"capture-{ordinal:03d}",
                state_sha256=_digest(f"state-{ordinal}"),
                envelope_sha256=_digest(f"envelope-{ordinal}"),
                question_sha256=_digest(f"question-{ordinal}"),
                binding_manifest_sha256=_digest(f"bindings-{ordinal}"),
                focus_pressure=0.50 + ordinal / 1_000,
                selected_kind=slot.focus_kind,
                available_goal_kinds=tuple(kinds),
            )
        )
    return tuple(entries)


def test_context_catalog_freezes_all_slots_without_private_paths() -> None:
    registry = _registry()
    entries = _entries(registry)

    payload = build_goal_manager_context_catalog_payload(registry, entries)
    catalog = parse_goal_manager_context_catalog(payload, registry)

    assert len(catalog.entries) == 81
    assert catalog.public_dict()["unique_state_count"] == 81
    assert catalog.public_dict()["unique_question_count"] == 81
    assert catalog.catalog_sha256 == hashlib.sha256(payload).hexdigest()
    encoded = payload.decode("ascii")
    assert "/" not in encoded
    assert "Users" not in encoded
    assignment = registry.assignment(registry.slots[0].slot_id)
    metadata = goal_manager_catalog_episode_metadata(assignment, catalog)
    goal = metadata["goal_manager"]
    assert isinstance(goal, dict)
    assert goal["context_catalog_sha256"] == catalog.catalog_sha256
    assert goal["context_id"] == entries[0].context_id


def test_context_catalog_rejects_duplicate_states_and_slot_reordering() -> None:
    registry = _registry()
    entries = list(_entries(registry))
    original = entries[1]
    duplicate = GoalManagerContextCatalogEntry.build(
        assignment=registry.assignment(original.slot_id),
        capture_id=original.capture_id,
        state_sha256=entries[0].state_sha256,
        envelope_sha256=original.envelope_sha256,
        question_sha256=original.question_sha256,
        binding_manifest_sha256=original.binding_manifest_sha256,
        focus_pressure=original.focus_pressure,
        selected_kind=original.selected_kind,
        available_goal_kinds=original.available_goal_kinds,
    )
    entries[1] = duplicate
    with pytest.raises(GoalManagerContextCatalogError, match="captured state"):
        build_goal_manager_context_catalog_payload(registry, tuple(entries))

    reordered = list(_entries(registry))
    reordered[0], reordered[1] = reordered[1], reordered[0]
    with pytest.raises(GoalManagerContextCatalogError, match="exact order"):
        build_goal_manager_context_catalog_payload(registry, tuple(reordered))


def test_context_catalog_parser_rejects_noncanonical_or_source_drift() -> None:
    registry = _registry()
    payload = build_goal_manager_context_catalog_payload(registry, _entries(registry))
    document = json.loads(payload)

    with pytest.raises(GoalManagerContextCatalogError, match="canonical ASCII"):
        parse_goal_manager_context_catalog(
            json.dumps(document, indent=2).encode("ascii"),
            registry,
        )

    document["source_commit"] = "b" * 40
    drifted = (
        json.dumps(document, separators=(",", ":"), sort_keys=True).encode("ascii")
        + b"\n"
    )
    with pytest.raises(GoalManagerContextCatalogError, match="source identity"):
        parse_goal_manager_context_catalog(drifted, registry)
