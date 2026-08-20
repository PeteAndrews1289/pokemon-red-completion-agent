from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
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
    all_kinds = tuple(GoalKind)
    for ordinal, slot in enumerate(registry.slots, start=1):
        assignment = registry.assignment(slot.slot_id)
        focus_index = all_kinds.index(slot.focus_kind)
        group_start = (focus_index // 3) * 3
        available = frozenset(all_kinds[group_start : group_start + 3])
        shift = ordinal % len(all_kinds)
        candidate_order = all_kinds[shift:] + all_kinds[:shift]
        question = GoalManagerQuestion(
            GoalSituation(
                *(0.50 + (ordinal + index) / 10_000 for index in range(len(all_kinds)))
            ),
            tuple(
                GoalOpportunity(
                    binding_ref=f"test:{ordinal}:{kind.value}",
                    kind=kind,
                    availability=(
                        GoalAvailability.AVAILABLE
                        if kind in available
                        else GoalAvailability.UNAVAILABLE
                    ),
                    estimated_effort=0.1 if kind in available else None,
                    estimated_risk=0.1 if kind in available else None,
                    unavailable_reason=(
                        None
                        if kind in available
                        else GoalUnavailableReason.MISSING_CAPABILITY
                    ),
                )
                for kind in candidate_order
            ),
        )
        entries.append(
            GoalManagerContextCatalogEntry.build(
                assignment=assignment,
                capture_id=f"capture-{ordinal:03d}",
                state_sha256=_digest(f"state-{ordinal}"),
                envelope_sha256=_digest(f"envelope-{ordinal}"),
                question_sha256=question.ordered_policy_input_sha256,
                policy_context_sha256=question.policy_context_sha256,
                available_menu_sha256=question.available_menu_sha256,
                selected_candidate_index=candidate_order.index(slot.focus_kind),
                candidate_goal_kinds=candidate_order,
                binding_manifest_sha256=_digest(f"bindings-{ordinal}"),
                focus_pressure=0.50 + ordinal / 1_000,
                selected_kind=slot.focus_kind,
                available_goal_kinds=tuple(
                    kind for kind in GoalKind if kind in available
                ),
            )
        )
    return tuple(entries)


def _menu_digest(available: tuple[GoalKind, ...]) -> str:
    available_set = frozenset(available)
    question = GoalManagerQuestion(
        GoalSituation(*(0.5 for _kind in GoalKind)),
        tuple(
            GoalOpportunity(
                binding_ref=f"menu:{kind.value}",
                kind=kind,
                availability=(
                    GoalAvailability.AVAILABLE
                    if kind in available_set
                    else GoalAvailability.UNAVAILABLE
                ),
                estimated_effort=0.1 if kind in available_set else None,
                estimated_risk=0.1 if kind in available_set else None,
                unavailable_reason=(
                    None
                    if kind in available_set
                    else GoalUnavailableReason.MISSING_CAPABILITY
                ),
            )
            for kind in GoalKind
        ),
    )
    return question.available_menu_sha256


def _rebuild_entry(
    registry,  # type: ignore[no-untyped-def]
    entry: GoalManagerContextCatalogEntry,
    *,
    available_goal_kinds: tuple[GoalKind, ...] | None = None,
    policy_context_sha256: str | None = None,
    candidate_goal_kinds: tuple[GoalKind, ...] | None = None,
) -> GoalManagerContextCatalogEntry:
    available = available_goal_kinds or entry.available_goal_kinds
    candidates = candidate_goal_kinds or entry.candidate_goal_kinds
    return GoalManagerContextCatalogEntry.build(
        assignment=registry.assignment(entry.slot_id),
        capture_id=entry.capture_id,
        state_sha256=entry.state_sha256,
        envelope_sha256=entry.envelope_sha256,
        question_sha256=entry.question_sha256,
        policy_context_sha256=policy_context_sha256 or entry.policy_context_sha256,
        available_menu_sha256=_menu_digest(available),
        selected_candidate_index=candidates.index(entry.selected_kind),
        candidate_goal_kinds=candidates,
        binding_manifest_sha256=entry.binding_manifest_sha256,
        focus_pressure=entry.focus_pressure,
        selected_kind=entry.selected_kind,
        available_goal_kinds=available,
    )


def test_context_catalog_freezes_all_slots_without_private_paths() -> None:
    registry = _registry()
    entries = _entries(registry)

    payload = build_goal_manager_context_catalog_payload(registry, entries)
    catalog = parse_goal_manager_context_catalog(payload, registry)

    assert len(catalog.entries) == 81
    assert catalog.public_dict()["unique_state_count"] == 81
    assert catalog.public_dict()["unique_question_count"] == 81
    assert catalog.public_dict()["unique_policy_context_count"] == 81
    assert catalog.public_dict()["multiway_train_contexts"] == 54
    assert catalog.public_dict()["context_dependent_train_menus"] == 3
    assert catalog.catalog_sha256 == hashlib.sha256(payload).hexdigest()
    encoded = payload.decode("ascii")
    assert "/" not in encoded
    assert "Users" not in encoded
    assignment = registry.assignment(registry.slots[0].slot_id)
    assert catalog.entries[0].root_lineage_id == assignment.root_lineage_id
    assert catalog.entries[0].root_lineage_id != catalog.entries[0].slot_id
    assert (
        catalog.entries[0].authenticated_root_lineage_id(
            slot_id=catalog.entries[0].slot_id,
            capture_id=catalog.entries[0].capture_id,
            state_sha256=catalog.entries[0].state_sha256,
            envelope_sha256=catalog.entries[0].envelope_sha256,
        )
        == assignment.root_lineage_id
    )
    with pytest.raises(GoalManagerContextCatalogError, match="capture identity"):
        catalog.entries[0].authenticated_root_lineage_id(
            slot_id=catalog.entries[0].slot_id,
            capture_id=catalog.entries[0].capture_id,
            state_sha256="0" * 64,
            envelope_sha256=catalog.entries[0].envelope_sha256,
        )
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
        policy_context_sha256=original.policy_context_sha256,
        available_menu_sha256=original.available_menu_sha256,
        selected_candidate_index=original.selected_candidate_index,
        candidate_goal_kinds=original.candidate_goal_kinds,
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


def test_context_catalog_rejects_curriculum_defects_before_collection() -> None:
    registry = _registry()
    entries = list(_entries(registry))

    for index, entry in enumerate(entries):
        assignment = registry.assignment(entry.slot_id)
        if assignment.partition != "train":
            continue
        available = (entry.selected_kind,)
        entries[index] = GoalManagerContextCatalogEntry.build(
            assignment=assignment,
            capture_id=entry.capture_id,
            state_sha256=entry.state_sha256,
            envelope_sha256=entry.envelope_sha256,
            question_sha256=entry.question_sha256,
            policy_context_sha256=entry.policy_context_sha256,
            available_menu_sha256=GoalManagerQuestion(
                GoalSituation(*(0.5 for _ in GoalKind)),
                tuple(
                    GoalOpportunity(
                        binding_ref=f"singleton:{index}:{kind.value}",
                        kind=kind,
                        availability=(
                            GoalAvailability.AVAILABLE
                            if kind in available
                            else GoalAvailability.UNAVAILABLE
                        ),
                        estimated_effort=0.1 if kind in available else None,
                        estimated_risk=0.1 if kind in available else None,
                        unavailable_reason=(
                            None
                            if kind in available
                            else GoalUnavailableReason.MISSING_CAPABILITY
                        ),
                    )
                    for kind in entry.candidate_goal_kinds
                ),
            ).available_menu_sha256,
            selected_candidate_index=entry.selected_candidate_index,
            candidate_goal_kinds=entry.candidate_goal_kinds,
            binding_manifest_sha256=entry.binding_manifest_sha256,
            focus_pressure=entry.focus_pressure,
            selected_kind=entry.selected_kind,
            available_goal_kinds=available,
        )

    with pytest.raises(GoalManagerContextCatalogError, match="multiway"):
        build_goal_manager_context_catalog_payload(registry, tuple(entries))

    entries = list(_entries(registry))
    all_kinds = tuple(GoalKind)
    for index, entry in enumerate(entries):
        if registry.assignment(entry.slot_id).partition == "train":
            entries[index] = _rebuild_entry(
                registry,
                entry,
                available_goal_kinds=all_kinds,
            )
    with pytest.raises(GoalManagerContextCatalogError, match="context-dependent"):
        build_goal_manager_context_catalog_payload(registry, tuple(entries))

    entries = list(_entries(registry))
    for index, entry in enumerate(entries):
        if registry.assignment(entry.slot_id).partition != "train":
            continue
        candidates = (entry.selected_kind,) + tuple(
            kind for kind in GoalKind if kind is not entry.selected_kind
        )
        entries[index] = _rebuild_entry(
            registry,
            entry,
            candidate_goal_kinds=candidates,
        )
    with pytest.raises(GoalManagerContextCatalogError, match="position diversity"):
        build_goal_manager_context_catalog_payload(registry, tuple(entries))

    entries = list(_entries(registry))
    entries[1] = _rebuild_entry(
        registry,
        entries[1],
        policy_context_sha256=entries[0].policy_context_sha256,
    )
    with pytest.raises(GoalManagerContextCatalogError, match="policy context"):
        build_goal_manager_context_catalog_payload(registry, tuple(entries))


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
