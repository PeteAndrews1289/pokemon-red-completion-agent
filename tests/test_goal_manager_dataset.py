from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalKind,
    GoalManagerExample,
    GoalManagerQuestion,
    GoalNeed,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalogEntry,
    build_goal_manager_context_catalog_payload,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_dataset import (
    GoalManagerDatasetError,
    admit_goal_manager_collection,
    audit_goal_manager_collection,
)
from pokemon_red_completion.goal_manager_protocol import (
    GOAL_MANAGER_ACTOR,
    GOAL_MANAGER_GAME_ID,
    GOAL_MANAGER_POLICY_ID,
    GOAL_MANAGER_REGISTRY_RELATIVE_PATH,
    GoalManagerCollectionRegistry,
    parse_goal_manager_registry,
)
from pokemon_red_completion.goal_manager_trajectory import CollectedGoalManagerDataset


def _registry() -> GoalManagerCollectionRegistry:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    parsed = parse_goal_manager_registry(
        (root / GOAL_MANAGER_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    return replace(
        parsed,
        execution=replace(parsed.execution, source_commit="a" * 40),
    )


def _dataset(
    registry: GoalManagerCollectionRegistry,
    slot_index: int,
) -> tuple[CollectedGoalManagerDataset, GoalManagerContextCatalogEntry]:
    slot = registry.slots[slot_index]
    assignment = registry.assignment(slot.slot_id)
    local_ordinal = slot_index % 9
    pattern = local_ordinal % 3
    common = {
        0: set(GoalKind),
        1: {
            GoalKind.ADVANCE_STORY,
            GoalKind.ACQUIRE_SPECIES,
            GoalKind.RESTORE_TEAM,
            slot.focus_kind,
        },
        2: {
            GoalKind.DEVELOP_TEAM,
            GoalKind.EVOLVE_SPECIES,
            GoalKind.RESUPPLY,
            GoalKind.MANAGE_STORAGE,
            slot.focus_kind,
        },
    }[pattern]
    if len(common) < 3:
        raise AssertionError("test menu must remain multiway")
    opportunities = tuple(
        GoalOpportunity(
            binding_ref=f"private:{slot.slot_id}:{kind.value}",
            kind=kind,
            availability=(
                GoalAvailability.AVAILABLE
                if kind in common
                else GoalAvailability.UNAVAILABLE
            ),
            estimated_effort=(0.10 + slot_index / 1_000 if kind in common else None),
            estimated_risk=(0.05 + slot_index / 2_000 if kind in common else None),
            unavailable_reason=(
                None if kind in common else GoalUnavailableReason.TEMPORARILY_BLOCKED
            ),
        )
        for kind in GoalKind
    )
    pressures = {need: 0.20 + slot_index / 10_000 for need in GoalNeed}
    pressures[slot.focus_need] = 0.80 + slot_index / 10_000
    situation = GoalSituation(
        story_pressure=pressures[GoalNeed.STORY_PROGRESS],
        collection_pressure=pressures[GoalNeed.COLLECTION_PROGRESS],
        team_pressure=pressures[GoalNeed.TEAM_READINESS],
        evolution_pressure=pressures[GoalNeed.EVOLUTION_PROGRESS],
        safety_pressure=pressures[GoalNeed.SAFETY],
        resource_pressure=pressures[GoalNeed.RESOURCES],
        storage_pressure=pressures[GoalNeed.STORAGE_CAPACITY],
        recovery_pressure=pressures[GoalNeed.CONTROL_RECOVERY],
        exploration_pressure=pressures[GoalNeed.WORLD_KNOWLEDGE],
    )
    question = GoalManagerQuestion(situation, opportunities)
    selected = next(
        index
        for index, opportunity in enumerate(opportunities)
        if opportunity.kind is slot.focus_kind
    )
    example = GoalManagerExample(
        decision_id=f"{assignment.episode_id}:goal-manager:0",
        episode_id=assignment.episode_id,
        decision_index=0,
        root_lineage_id=assignment.root_lineage_id,
        partition=assignment.partition,
        environment_id=GOAL_MANAGER_GAME_ID,
        actor=GOAL_MANAGER_ACTOR,
        policy_id=GOAL_MANAGER_POLICY_ID,
        question=question,
        selected_candidate_index=selected,
        outcome_status=GoalDecisionOutcome.SUCCEEDED,
    )
    state_sha256 = hashlib.sha256(f"state:{slot.slot_id}".encode()).hexdigest()
    envelope_sha256 = hashlib.sha256(f"envelope:{slot.slot_id}".encode()).hexdigest()
    entry = GoalManagerContextCatalogEntry.build(
        assignment=assignment,
        capture_id=f"capture-{slot_index + 1:03d}",
        state_sha256=state_sha256,
        envelope_sha256=envelope_sha256,
        question_sha256=question.ordered_policy_input_sha256,
        policy_context_sha256=question.policy_context_sha256,
        available_menu_sha256=question.available_menu_sha256,
        selected_candidate_index=selected,
        candidate_goal_kinds=tuple(
            opportunity.kind for opportunity in question.opportunities
        ),
        binding_manifest_sha256=hashlib.sha256(
            f"bindings:{slot.slot_id}".encode()
        ).hexdigest(),
        focus_pressure=question.situation.pressure(slot.focus_need),
        selected_kind=slot.focus_kind,
        available_goal_kinds=tuple(
            opportunity.kind
            for opportunity in opportunities
            if opportunity.availability is GoalAvailability.AVAILABLE
        ),
    )
    dataset = CollectedGoalManagerDataset(
        episode_id=assignment.episode_id,
        manifest_sha256=hashlib.sha256(slot.slot_id.encode()).hexdigest(),
        root_lineage_id=assignment.root_lineage_id,
        partition=assignment.partition,
        environment_id=GOAL_MANAGER_GAME_ID,
        actor=GOAL_MANAGER_ACTOR,
        policy_id=GOAL_MANAGER_POLICY_ID,
        collection_id=assignment.collection_id,
        assignment_id=assignment.assignment_id,
        source_commit=assignment.source_commit or "",
        context_catalog_sha256="0" * 64,
        context_id=entry.context_id,
        binding_manifest_sha256=entry.binding_manifest_sha256,
        capture_state_sha256=entry.state_sha256,
        capture_envelope_sha256=entry.envelope_sha256,
        examples=(example,),
    )
    return dataset, entry


def _complete_fixture(
    registry: GoalManagerCollectionRegistry,
):  # type: ignore[no-untyped-def]
    pairs = tuple(_dataset(registry, index) for index, _slot in enumerate(registry.slots))
    catalog = parse_goal_manager_context_catalog(
        build_goal_manager_context_catalog_payload(
            registry,
            tuple(entry for _dataset_value, entry in pairs),
        ),
        registry,
    )
    datasets = {
        slot.slot_id: replace(dataset, context_catalog_sha256=catalog.catalog_sha256)
        for slot, (dataset, _entry) in zip(registry.slots, pairs, strict=True)
    }
    return catalog, datasets


def test_complete_prospective_collection_passes_every_training_gate() -> None:
    registry = _registry()
    catalog, datasets = _complete_fixture(registry)
    corpus = admit_goal_manager_collection(registry, catalog, datasets)

    assert len(corpus.train_examples) == 54
    assert len(corpus.validation_examples) == 27
    assert corpus.curriculum_audit.ready_for_training
    assert corpus.curriculum_audit.context_dependent_menu_count >= 3
    assert corpus.collection_status.ready_for_training
    assert corpus.public_dict()["private_path_fields"] == 0


def test_partial_collection_reports_exact_remaining_slots() -> None:
    registry = _registry()
    catalog, datasets = _complete_fixture(registry)
    removed = registry.slots[-1].slot_id
    del datasets[removed]

    status = audit_goal_manager_collection(registry, catalog, datasets)

    assert not status.ready_for_training
    assert status.missing_slot_ids == (removed,)
    assert status.public_dict()["missing_slot_count"] == 1
    with pytest.raises(GoalManagerDatasetError, match="not ready"):
        admit_goal_manager_collection(registry, catalog, datasets)


def test_reused_episode_manifest_cannot_fill_two_slots() -> None:
    registry = _registry()
    catalog, datasets = _complete_fixture(registry)
    first, second = registry.slots[:2]
    datasets[second.slot_id] = replace(
        datasets[second.slot_id],
        manifest_sha256=datasets[first.slot_id].manifest_sha256,
    )

    status = audit_goal_manager_collection(registry, catalog, datasets)

    assert status.duplicate_manifest_count == 1
    assert "duplicate_episode_manifest" in status.reasons


def test_focus_is_an_observed_pressure_requirement_not_a_hidden_label() -> None:
    registry = _registry()
    catalog, datasets = _complete_fixture(registry)
    first = registry.slots[0]
    dataset = datasets[first.slot_id]
    example = dataset.examples[0]
    low_story = replace(example.question.situation, story_pressure=0.49)
    datasets[first.slot_id] = replace(
        dataset,
        examples=(replace(example, question=replace(example.question, situation=low_story)),),
    )

    status = audit_goal_manager_collection(registry, catalog, datasets)

    assert first.focus_need is GoalNeed.STORY_PROGRESS
    assert first.focus_kind is GoalKind.ADVANCE_STORY
    assert first.slot_id in status.invalid_slot_ids
    assert not status.ready_for_training
