"""Authenticate and admit collected goal-manager episodes for model fitting."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from pokemon_red_completion.goal_manager import (
    GoalCurriculumAudit,
    GoalCurriculumRequirements,
    GoalManagerExample,
    audit_goal_curriculum,
)
from pokemon_red_completion.goal_manager_context_catalog import GoalManagerContextCatalog
from pokemon_red_completion.goal_manager_protocol import (
    GOAL_MANAGER_ACTOR,
    GOAL_MANAGER_GAME_ID,
    GOAL_MANAGER_POLICY_ID,
    GoalManagerAssignment,
    GoalManagerCollectionRegistry,
)
from pokemon_red_completion.goal_manager_trajectory import (
    CollectedGoalManagerDataset,
    GoalEpisodeReader,
    load_goal_manager_episode,
)


class GoalManagerDatasetError(RuntimeError):
    """Raised when private episodes cannot form the preregistered corpus."""


@dataclass(frozen=True, slots=True)
class GoalManagerCollectionStatus:
    declared_slots: int
    collected_slots: int
    successful_teacher_slots: int
    multiway_slots: int
    missing_slot_ids: tuple[str, ...]
    invalid_slot_ids: tuple[str, ...]
    duplicate_manifest_count: int
    ready_for_training: bool
    reasons: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-red-goal-manager-collection-status-v1",
            "declared_slots": self.declared_slots,
            "collected_slots": self.collected_slots,
            "successful_teacher_slots": self.successful_teacher_slots,
            "multiway_slots": self.multiway_slots,
            "missing_slot_count": len(self.missing_slot_ids),
            "invalid_slot_count": len(self.invalid_slot_ids),
            "duplicate_manifest_count": self.duplicate_manifest_count,
            "ready_for_training": self.ready_for_training,
            "reasons": list(self.reasons),
            "private_path_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class GoalManagerTrainingCorpus:
    train_examples: tuple[GoalManagerExample, ...]
    validation_examples: tuple[GoalManagerExample, ...]
    curriculum_audit: GoalCurriculumAudit
    collection_status: GoalManagerCollectionStatus
    context_catalog_sha256: str
    episode_manifest_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.curriculum_audit.ready_for_training:
            raise GoalManagerDatasetError("goal-manager curriculum audit did not pass")
        if not self.collection_status.ready_for_training:
            raise GoalManagerDatasetError("goal-manager collection status did not pass")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-red-goal-manager-training-corpus-v1",
            "train_examples": len(self.train_examples),
            "validation_examples": len(self.validation_examples),
            "episode_manifests": len(self.episode_manifest_sha256s),
            "context_catalog_sha256": self.context_catalog_sha256,
            "curriculum_audit": self.curriculum_audit.public_dict(),
            "collection_status": self.collection_status.public_dict(),
            "private_path_fields": 0,
        }


def load_assigned_goal_manager_episode(
    reader: GoalEpisodeReader,
    assignment: GoalManagerAssignment,
    *,
    context_catalog: GoalManagerContextCatalog,
) -> CollectedGoalManagerDataset:
    """Strictly load one episode and bind it to one committed public slot."""

    if not isinstance(assignment, GoalManagerAssignment):
        raise TypeError("assignment must be a GoalManagerAssignment")
    if assignment.source_commit is None:
        raise GoalManagerDatasetError("goal-manager collection requires committed source")
    _require_catalog_identity(context_catalog, assignment=assignment)
    context = context_catalog.entry(assignment.slot_id)
    dataset = load_goal_manager_episode(reader)
    expected = (
        assignment.episode_id,
        assignment.root_lineage_id,
        assignment.partition,
        GOAL_MANAGER_GAME_ID,
        GOAL_MANAGER_ACTOR,
        GOAL_MANAGER_POLICY_ID,
        assignment.collection_id,
        assignment.assignment_id,
        assignment.source_commit,
    )
    observed = (
        dataset.episode_id,
        dataset.root_lineage_id,
        dataset.partition,
        dataset.environment_id,
        dataset.actor,
        dataset.policy_id,
        dataset.collection_id,
        dataset.assignment_id,
        dataset.source_commit,
    )
    if observed != expected:
        raise GoalManagerDatasetError("goal-manager episode differs from its assignment")
    if (
        dataset.context_catalog_sha256 != context_catalog.catalog_sha256
        or dataset.context_id != context.context_id
        or dataset.binding_manifest_sha256 != context.binding_manifest_sha256
        or dataset.capture_state_sha256 != context.state_sha256
        or dataset.capture_envelope_sha256 != context.envelope_sha256
    ):
        raise GoalManagerDatasetError("goal-manager episode differs from its frozen context")
    if len(dataset.examples) != 1:
        raise GoalManagerDatasetError("a short goal-manager slot must contain one decision")
    return dataset


def audit_goal_manager_collection(
    registry: GoalManagerCollectionRegistry,
    context_catalog: GoalManagerContextCatalog,
    datasets_by_slot: Mapping[str, CollectedGoalManagerDataset],
    *,
    active_pressure_threshold: float = 0.5,
) -> GoalManagerCollectionStatus:
    """Report partial progress without weakening final admission requirements."""

    if not isinstance(registry, GoalManagerCollectionRegistry):
        raise TypeError("registry must be a GoalManagerCollectionRegistry")
    _require_catalog_identity(context_catalog, registry=registry)
    if not isinstance(datasets_by_slot, Mapping):
        raise TypeError("datasets_by_slot must be a mapping")
    if not 0.0 <= active_pressure_threshold <= 1.0:
        raise ValueError("active_pressure_threshold must be between zero and one")
    declared = {slot.slot_id: slot for slot in registry.slots}
    reasons: list[str] = []
    unknown = sorted(set(datasets_by_slot).difference(declared))
    if unknown:
        reasons.append("unknown_collection_slot")
    missing = tuple(slot.slot_id for slot in registry.slots if slot.slot_id not in datasets_by_slot)
    if missing:
        reasons.append("missing_collection_slot")
    invalid: list[str] = []
    successful = 0
    multiway = 0
    manifests: list[str] = []
    for slot_id, dataset in datasets_by_slot.items():
        if slot_id not in declared:
            invalid.append(slot_id)
            continue
        slot = declared[slot_id]
        assignment = registry.assignment(slot_id)
        context = context_catalog.entry(slot_id)
        valid = True
        if len(dataset.examples) != 1:
            valid = False
        else:
            example = dataset.examples[0]
            if (
                dataset.episode_id != assignment.episode_id
                or dataset.root_lineage_id != assignment.root_lineage_id
                or dataset.partition != assignment.partition
                or dataset.environment_id != GOAL_MANAGER_GAME_ID
                or dataset.actor != GOAL_MANAGER_ACTOR
                or dataset.policy_id != GOAL_MANAGER_POLICY_ID
                or dataset.collection_id != assignment.collection_id
                or dataset.assignment_id != assignment.assignment_id
                or dataset.source_commit != assignment.source_commit
                or dataset.context_catalog_sha256 != context_catalog.catalog_sha256
                or dataset.context_id != context.context_id
                or dataset.binding_manifest_sha256 != context.binding_manifest_sha256
                or dataset.capture_state_sha256 != context.state_sha256
                or dataset.capture_envelope_sha256 != context.envelope_sha256
            ):
                valid = False
            if example.question.situation.pressure(slot.focus_need) < active_pressure_threshold:
                valid = False
            if example.teacher_choice_target is not None:
                successful += 1
            if len(example.question.available_indices) >= 3:
                multiway += 1
        if not valid:
            invalid.append(slot_id)
        manifests.append(dataset.manifest_sha256)
    if invalid:
        reasons.append("invalid_collection_slot")
    duplicate_manifests = len(manifests) - len(set(manifests))
    if duplicate_manifests:
        reasons.append("duplicate_episode_manifest")
    if successful < len(registry.slots):
        reasons.append("unsuccessful_or_non_teacher_slot")
    return GoalManagerCollectionStatus(
        declared_slots=len(registry.slots),
        collected_slots=len(datasets_by_slot),
        successful_teacher_slots=successful,
        multiway_slots=multiway,
        missing_slot_ids=missing,
        invalid_slot_ids=tuple(sorted(set(invalid))),
        duplicate_manifest_count=duplicate_manifests,
        ready_for_training=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def admit_goal_manager_collection(
    registry: GoalManagerCollectionRegistry,
    context_catalog: GoalManagerContextCatalog,
    datasets_by_slot: Mapping[str, CollectedGoalManagerDataset],
    *,
    requirements: GoalCurriculumRequirements | None = None,
) -> GoalManagerTrainingCorpus:
    """Require all prospective slots and the portable leakage/coverage gates."""

    if registry.execution.source_commit is None:
        raise GoalManagerDatasetError("goal-manager admission requires committed source")
    rules = requirements or GoalCurriculumRequirements()
    status = audit_goal_manager_collection(
        registry,
        context_catalog,
        datasets_by_slot,
        active_pressure_threshold=rules.active_pressure_threshold,
    )
    if not status.ready_for_training:
        raise GoalManagerDatasetError(
            "goal-manager collection is not ready: " + ", ".join(status.reasons)
        )
    examples = tuple(
        datasets_by_slot[slot.slot_id].examples[0] for slot in registry.slots
    )
    audit = audit_goal_curriculum(examples, requirements=rules)
    if not audit.ready_for_training:
        raise GoalManagerDatasetError(
            "goal-manager curriculum is not ready: " + ", ".join(audit.reasons)
        )
    train = tuple(item for item in examples if item.partition == "train")
    validation = tuple(item for item in examples if item.partition == "validation")
    manifests = tuple(
        datasets_by_slot[slot.slot_id].manifest_sha256 for slot in registry.slots
    )
    return GoalManagerTrainingCorpus(
        train,
        validation,
        audit,
        status,
        context_catalog.catalog_sha256,
        manifests,
    )


def goal_manager_selected_kind_counts(
    examples: Iterable[GoalManagerExample],
) -> dict[str, int]:
    """Small public audit helper used by collection progress reports."""

    return dict(Counter(item.selected_kind.value for item in examples))


def _require_catalog_identity(
    catalog: GoalManagerContextCatalog,
    *,
    registry: GoalManagerCollectionRegistry | None = None,
    assignment: GoalManagerAssignment | None = None,
) -> None:
    if not isinstance(catalog, GoalManagerContextCatalog):
        raise TypeError("context_catalog must be a GoalManagerContextCatalog")
    expected_registry_sha256 = (
        registry.registry_sha256
        if registry is not None
        else assignment.registry_sha256
        if assignment is not None
        else None
    )
    expected_source = (
        registry.execution.source_bundle_sha256
        if registry is not None
        else assignment.source_bundle_sha256
        if assignment is not None
        else None
    )
    expected_commit = (
        registry.execution.source_commit
        if registry is not None
        else assignment.source_commit
        if assignment is not None
        else None
    )
    if (
        expected_registry_sha256 is None
        or catalog.registry_sha256 != expected_registry_sha256
        or catalog.source_bundle_sha256 != expected_source
        or catalog.source_commit != expected_commit
    ):
        raise GoalManagerDatasetError("goal-manager context catalog identity differs")
