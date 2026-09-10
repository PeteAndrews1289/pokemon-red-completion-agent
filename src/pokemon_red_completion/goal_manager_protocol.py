"""Prospective authenticated assignments for Red goal-manager collection.

The public registry fixes train/validation membership, curriculum coverage,
teacher identity and executable source before any private checkpoint is mapped
or any outcome is observed.  ``focus_need`` and ``focus_kind`` tell the capture
curator what semantic pressure a slot must exercise; neither field is passed to
the teacher or learned policy, and neither declares the eventual label.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from pokemon_red_completion.collection_protocol import (
    collection_document_sha256,
    committed_source_bundle_sha256,
)
from pokemon_red_completion.goal_manager import (
    GOAL_KIND_NEEDS,
    GoalAvailability,
    GoalCurriculumRequirements,
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalNeed,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_model import goal_manager_fit_configuration
from pokemon_red_completion.goal_manager_runtime import CompletionFirstGoalTeacher
from pokemon_red_completion.red_goal_context_profile import (
    red_goal_manager_contract_document,
)

GOAL_MANAGER_REGISTRY_RELATIVE_PATH = "configs/red-goal-manager-collection-v1.json"
GOAL_MANAGER_REGISTRY_DIGEST_RELATIVE_PATH = (
    "configs/red-goal-manager-collection-v1.digest.json"
)
GOAL_MANAGER_REGISTRY_SCHEMA = "pokemon-red-goal-manager-collection-v1"
GOAL_MANAGER_REGISTRY_DIGEST_SCHEMA = "pokemon-red-goal-manager-registry-digest-v1"
GOAL_MANAGER_EXECUTION_SCHEMA = "pokemon-red-goal-manager-teacher-execution-v1"
GOAL_MANAGER_ASSIGNMENT_SCHEMA = "pokemon-red-goal-manager-assignment-v1"
GOAL_MANAGER_CONTRACT_SCHEMA = "pokemon-core-goal-manager-contract-v1"

GOAL_MANAGER_COLLECTION_ID = "red-goal-manager-v1"
GOAL_MANAGER_GAME_ID = "pokemon.mainline:red:gb:us:rev0"
GOAL_MANAGER_ADAPTER_ID = "pokemon.red.gb.us.rev0.goal-manager.v1"
GOAL_MANAGER_ONTOLOGY_ID = "pokemon.core.v1"
GOAL_MANAGER_ACTOR = "deterministic_teacher"
GOAL_MANAGER_POLICY_ID = "completion-first-goal-teacher-v1"
GOAL_MANAGER_REGIME = "authenticated_short_context"
GOAL_MANAGER_EPISODE_PREFIX = "red-goal-"

GOAL_MANAGER_PRIMARY_NEED: Mapping[GoalKind, GoalNeed] = {
    GoalKind.ADVANCE_STORY: GoalNeed.STORY_PROGRESS,
    GoalKind.ACQUIRE_SPECIES: GoalNeed.COLLECTION_PROGRESS,
    GoalKind.DEVELOP_TEAM: GoalNeed.TEAM_READINESS,
    GoalKind.EVOLVE_SPECIES: GoalNeed.EVOLUTION_PROGRESS,
    GoalKind.RESTORE_TEAM: GoalNeed.SAFETY,
    GoalKind.RESUPPLY: GoalNeed.RESOURCES,
    GoalKind.MANAGE_STORAGE: GoalNeed.STORAGE_CAPACITY,
    GoalKind.RECOVER_CONTROL: GoalNeed.CONTROL_RECOVERY,
    GoalKind.EXPLORE: GoalNeed.WORLD_KNOWLEDGE,
}

_PARTITION_COUNTS_PER_KIND = {"train": 6, "validation": 3}
_PARTITION_COUNTS = {
    partition: count * len(GoalKind)
    for partition, count in _PARTITION_COUNTS_PER_KIND.items()
}
_SLOT_COUNT = sum(_PARTITION_COUNTS.values())
_MAX_REGISTRY_BYTES = 2 * 1024 * 1024
_MAX_DIGEST_BYTES = 4096
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class GoalManagerProtocolError(RuntimeError):
    """Raised when prospective collection identity or provenance drifts."""


@dataclass(frozen=True, slots=True)
class GoalManagerExecution:
    source_bundle_sha256: str
    decision_contract_sha256: str
    teacher_configuration_sha256: str
    teacher_execution_sha256: str
    source_commit: str | None = None


@dataclass(frozen=True, slots=True)
class GoalManagerCollectionSlot:
    slot_id: str
    partition: str
    harness_seed: int
    focus_need: GoalNeed
    focus_kind: GoalKind


@dataclass(frozen=True, slots=True)
class GoalManagerAssignment:
    collection_id: str
    registry_sha256: str
    slot_id: str
    partition: str
    harness_seed: int
    focus_need: GoalNeed
    focus_kind: GoalKind
    assignment_id: str
    root_lineage_id: str
    episode_id: str
    collection_slot_ordinal: int
    declared_collection_slots: int
    partition_slot_ordinal: int
    declared_partition_slots: int
    source_bundle_sha256: str
    teacher_execution_sha256: str
    source_commit: str | None = None

    def __post_init__(self) -> None:
        if self.collection_id != GOAL_MANAGER_COLLECTION_ID:
            raise GoalManagerProtocolError("goal-manager assignment collection differs")
        for value, subject in (
            (self.registry_sha256, "registry digest"),
            (self.assignment_id, "assignment digest"),
            (self.source_bundle_sha256, "source digest"),
            (self.teacher_execution_sha256, "teacher execution digest"),
        ):
            _digest(value, subject)
        _safe_id(self.slot_id, "slot identity")
        _seed(self.harness_seed)
        if self.partition not in _PARTITION_COUNTS:
            raise GoalManagerProtocolError("goal-manager assignment partition differs")
        if not isinstance(self.focus_need, GoalNeed) or not isinstance(
            self.focus_kind, GoalKind
        ):
            raise GoalManagerProtocolError("goal-manager assignment focus is invalid")
        if GOAL_MANAGER_PRIMARY_NEED[self.focus_kind] is not self.focus_need:
            raise GoalManagerProtocolError("goal-manager assignment focus mapping differs")
        if not 1 <= self.collection_slot_ordinal <= self.declared_collection_slots:
            raise GoalManagerProtocolError("goal-manager collection ordinal differs")
        if self.declared_collection_slots != _SLOT_COUNT:
            raise GoalManagerProtocolError("goal-manager collection total differs")
        if not 1 <= self.partition_slot_ordinal <= self.declared_partition_slots:
            raise GoalManagerProtocolError("goal-manager partition ordinal differs")
        if self.declared_partition_slots != _PARTITION_COUNTS[self.partition]:
            raise GoalManagerProtocolError("goal-manager partition total differs")
        expected = collection_document_sha256(
            {
                "collection_id": self.collection_id,
                "focus_kind": self.focus_kind.value,
                "focus_need": self.focus_need.value,
                "harness_seed": self.harness_seed,
                "partition": self.partition,
                "registry_sha256": self.registry_sha256,
                "schema": GOAL_MANAGER_ASSIGNMENT_SCHEMA,
                "slot_id": self.slot_id,
                "teacher_execution_sha256": self.teacher_execution_sha256,
            }
        )
        if self.assignment_id != expected:
            raise GoalManagerProtocolError("goal-manager assignment digest differs")
        if self.root_lineage_id != f"red-goal-root-{self.assignment_id}":
            raise GoalManagerProtocolError("goal-manager lineage differs")
        if self.episode_id != f"{GOAL_MANAGER_EPISODE_PREFIX}{self.assignment_id}":
            raise GoalManagerProtocolError("goal-manager episode differs")
        if self.source_commit is not None and _GIT_OID.fullmatch(self.source_commit) is None:
            raise GoalManagerProtocolError("goal-manager source commit differs")

    def metadata_dict(self) -> dict[str, object]:
        """Return path-free provenance; focus is explicitly curator-only."""

        return {
            "assignment_id": self.assignment_id,
            "attempt": {"attempts_per_slot": 1, "counted": True},
            "collection_id": self.collection_id,
            "collection_slot": {
                "collection_ordinal": self.collection_slot_ordinal,
                "collection_total": self.declared_collection_slots,
                "partition_ordinal": self.partition_slot_ordinal,
                "partition_total": self.declared_partition_slots,
            },
            "curation_focus": {
                "excluded_from_policy_input": True,
                "kind": self.focus_kind.value,
                "need": self.focus_need.value,
                "not_a_teacher_label": True,
            },
            "execution": {
                "source_bundle_sha256": self.source_bundle_sha256,
                "teacher_execution_sha256": self.teacher_execution_sha256,
            },
            "harness_seed": self.harness_seed,
            "registry_sha256": self.registry_sha256,
            "slot_id": self.slot_id,
            "split": {
                "partition": self.partition,
                "regime": GOAL_MANAGER_REGIME,
                "root_lineage_id": self.root_lineage_id,
            },
        }

    def episode_metadata(self) -> dict[str, object]:
        if self.source_commit is None:
            raise GoalManagerProtocolError(
                "goal-manager episode metadata requires a committed assignment"
            )
        return {
            "goal_manager": {
                "assignment_id": self.assignment_id,
                "collection_id": self.collection_id,
                "source_commit": self.source_commit,
            },
            "policy": {
                "actor": GOAL_MANAGER_ACTOR,
                "policy_id": GOAL_MANAGER_POLICY_ID,
            },
            "source": {"git_commit": self.source_commit},
            "source_bundle_sha256": self.source_bundle_sha256,
            "split": {
                "partition": self.partition,
                "regime": GOAL_MANAGER_REGIME,
                "root_lineage_id": self.root_lineage_id,
            },
        }


@dataclass(frozen=True, slots=True)
class GoalManagerCollectionRegistry:
    registry_sha256: str
    execution: GoalManagerExecution
    slots: tuple[GoalManagerCollectionSlot, ...]

    @property
    def partition_counts(self) -> dict[str, int]:
        return dict(Counter(slot.partition for slot in self.slots))

    def assignment(self, slot_id: str) -> GoalManagerAssignment:
        try:
            slot = next(item for item in self.slots if item.slot_id == slot_id)
        except StopIteration as error:
            raise GoalManagerProtocolError("unknown goal-manager collection slot") from error
        collection_ordinal = self.slots.index(slot) + 1
        same_partition = tuple(item for item in self.slots if item.partition == slot.partition)
        partition_ordinal = same_partition.index(slot) + 1
        assignment_id = collection_document_sha256(
            {
                "collection_id": GOAL_MANAGER_COLLECTION_ID,
                "focus_kind": slot.focus_kind.value,
                "focus_need": slot.focus_need.value,
                "harness_seed": slot.harness_seed,
                "partition": slot.partition,
                "registry_sha256": self.registry_sha256,
                "schema": GOAL_MANAGER_ASSIGNMENT_SCHEMA,
                "slot_id": slot.slot_id,
                "teacher_execution_sha256": self.execution.teacher_execution_sha256,
            }
        )
        return GoalManagerAssignment(
            collection_id=GOAL_MANAGER_COLLECTION_ID,
            registry_sha256=self.registry_sha256,
            slot_id=slot.slot_id,
            partition=slot.partition,
            harness_seed=slot.harness_seed,
            focus_need=slot.focus_need,
            focus_kind=slot.focus_kind,
            assignment_id=assignment_id,
            root_lineage_id=f"red-goal-root-{assignment_id}",
            episode_id=f"{GOAL_MANAGER_EPISODE_PREFIX}{assignment_id}",
            collection_slot_ordinal=collection_ordinal,
            declared_collection_slots=len(self.slots),
            partition_slot_ordinal=partition_ordinal,
            declared_partition_slots=self.partition_counts[slot.partition],
            source_bundle_sha256=self.execution.source_bundle_sha256,
            teacher_execution_sha256=self.execution.teacher_execution_sha256,
            source_commit=self.execution.source_commit,
        )


def goal_manager_contract_document() -> dict[str, object]:
    """The frozen V1 collection contract, not the expanding player vocabulary."""
    rules = GoalCurriculumRequirements()
    return {
        "admission": {
            "minimum_context_dependent_menus": rules.minimum_context_dependent_menus,
            "minimum_multiway_train_examples": rules.minimum_multiway_train_examples,
            "minimum_train_examples": rules.minimum_train_examples,
            "minimum_train_examples_per_need": rules.minimum_train_examples_per_need,
            "minimum_train_selections_per_kind": rules.minimum_train_selections_per_kind,
            "minimum_validation_examples": rules.minimum_validation_examples,
            "minimum_validation_examples_per_need": (
                rules.minimum_validation_examples_per_need
            ),
            "minimum_validation_selections_per_kind": (
                rules.minimum_validation_selections_per_kind
            ),
        },
        "fit": goal_manager_fit_configuration(),
        "red_adapter": red_goal_manager_contract_document(),
        "availability": sorted(item.value for item in GoalAvailability),
        # Historical registry identity must not drift when the development
        # player adds an outcome. A successor collection needs a new contract.
        "failure_reasons": sorted(item.value for item in (
            GoalFailureReason.BINDING_FAILED,
            GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED,
            GoalFailureReason.EXTERNAL_INTERRUPTION,
            GoalFailureReason.OUTCOME_NOT_VERIFIED,
            GoalFailureReason.RESOURCE_LOST,
            GoalFailureReason.WORLD_STATE_DIVERGED,
        )),
        "goal_kinds": sorted(item.value for item in GoalKind),
        "goal_needs": sorted(item.value for item in GoalNeed),
        "kind_need_mapping": {
            kind.value: [need.value for need in GOAL_KIND_NEEDS[kind]] for kind in GoalKind
        },
        "model_input_excludes": [
            "candidate_position_identity",
            "curation_focus",
            "environment_identity",
            "private_binding_identity",
            "raw_memory",
            "species_identity",
        ],
        "outcomes": sorted(item.value for item in GoalDecisionOutcome),
        "record_before_action": True,
        "schema": GOAL_MANAGER_CONTRACT_SCHEMA,
        "successful_teacher_outcome_required_for_imitation": True,
        "unavailable_reasons": sorted(item.value for item in GoalUnavailableReason),
    }


def parse_goal_manager_registry(payload: bytes) -> GoalManagerCollectionRegistry:
    if not isinstance(payload, bytes):
        raise TypeError("goal-manager registry must be bytes")
    if not payload or len(payload) > _MAX_REGISTRY_BYTES:
        raise GoalManagerProtocolError("goal-manager registry size is invalid")
    try:
        document = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise GoalManagerProtocolError(
            "goal-manager registry is not canonical ASCII JSON"
        ) from None
    if not isinstance(document, dict) or _canonical_line(document) != payload:
        raise GoalManagerProtocolError("goal-manager registry is not canonical ASCII JSON")
    _exact_keys(
        document,
        {
            "adapter_id",
            "collection_id",
            "execution",
            "game_id",
            "ontology_id",
            "policy",
            "regime",
            "schema",
            "slots",
        },
        "goal-manager registry",
    )
    expected = {
        "adapter_id": GOAL_MANAGER_ADAPTER_ID,
        "collection_id": GOAL_MANAGER_COLLECTION_ID,
        "game_id": GOAL_MANAGER_GAME_ID,
        "ontology_id": GOAL_MANAGER_ONTOLOGY_ID,
        "regime": GOAL_MANAGER_REGIME,
        "schema": GOAL_MANAGER_REGISTRY_SCHEMA,
    }
    if any(document[key] != value for key, value in expected.items()):
        raise GoalManagerProtocolError("goal-manager registry identity is unsupported")
    policy = _mapping(document["policy"], "goal-manager policy")
    if policy != {"actor": GOAL_MANAGER_ACTOR, "policy_id": GOAL_MANAGER_POLICY_ID}:
        raise GoalManagerProtocolError("goal-manager collection policy is unsupported")
    execution = _parse_execution(document["execution"])
    slots = _parse_slots(document["slots"])
    return GoalManagerCollectionRegistry(
        registry_sha256=hashlib.sha256(payload).hexdigest(),
        execution=execution,
        slots=slots,
    )


def load_committed_goal_manager_registry(
    repository_root: str | Path,
) -> GoalManagerCollectionRegistry:
    """Load the registry committed at ``HEAD`` and bind it to that source."""

    return load_committed_goal_manager_registry_at_revision(repository_root, "HEAD")


def load_committed_goal_manager_registry_at_revision(
    repository_root: str | Path,
    revision: str,
) -> GoalManagerCollectionRegistry:
    """Authenticate a historical registry against its exact committed source.

    Counted corpora and fitted models remain permanently bound to the commit
    that declared them.  Promotion code may evolve afterwards, so evaluating a
    frozen candidate must resolve its registry at the recorded training commit
    instead of silently reinterpreting it as the registry at ``HEAD``.
    """

    if not isinstance(revision, str) or not revision or "\x00" in revision:
        raise GoalManagerProtocolError("goal-manager revision identity is invalid")
    root = Path(repository_root).resolve()
    commit = _git(
        root,
        ["rev-parse", "--verify", f"{revision}^{{commit}}"],
        256,
    ).decode("ascii").strip()
    if _GIT_OID.fullmatch(commit) is None:
        raise GoalManagerProtocolError("goal-manager commit identity is invalid")
    digest_payload = _git(
        root,
        ["show", f"{commit}:{GOAL_MANAGER_REGISTRY_DIGEST_RELATIVE_PATH}"],
        _MAX_DIGEST_BYTES,
    )
    registry_payload = _git(
        root,
        ["show", f"{commit}:{GOAL_MANAGER_REGISTRY_RELATIVE_PATH}"],
        _MAX_REGISTRY_BYTES,
    )
    expected_bytes, expected_digest = _parse_digest(digest_payload)
    if (
        len(registry_payload) != expected_bytes
        or hashlib.sha256(registry_payload).hexdigest() != expected_digest
    ):
        raise GoalManagerProtocolError("committed goal-manager registry digest differs")
    registry = parse_goal_manager_registry(registry_payload)
    source = committed_source_bundle_sha256(root, revision=commit)
    if registry.execution.source_bundle_sha256 != source:
        raise GoalManagerProtocolError(
            "committed source does not match the goal-manager registry"
        )
    return replace(registry, execution=replace(registry.execution, source_commit=commit))


def _parse_execution(value: object) -> GoalManagerExecution:
    row = _mapping(value, "goal-manager execution")
    _exact_keys(
        row,
        {
            "decision_contract_sha256",
            "schema",
            "source_bundle_sha256",
            "teacher_configuration_sha256",
            "teacher_execution_sha256",
        },
        "goal-manager execution",
    )
    for key in (
        "decision_contract_sha256",
        "source_bundle_sha256",
        "teacher_configuration_sha256",
        "teacher_execution_sha256",
    ):
        _digest(row[key], key.replace("_", " "))
    if row["schema"] != GOAL_MANAGER_EXECUTION_SCHEMA:
        raise GoalManagerProtocolError("goal-manager execution schema differs")
    contract_digest = collection_document_sha256(goal_manager_contract_document())
    teacher_digest = collection_document_sha256(CompletionFirstGoalTeacher().public_dict())
    if row["decision_contract_sha256"] != contract_digest:
        raise GoalManagerProtocolError("goal-manager decision contract digest differs")
    if row["teacher_configuration_sha256"] != teacher_digest:
        raise GoalManagerProtocolError("goal-manager teacher configuration digest differs")
    expected_execution = collection_document_sha256(
        {
            "actor": GOAL_MANAGER_ACTOR,
            "adapter_id": GOAL_MANAGER_ADAPTER_ID,
            "collection_id": GOAL_MANAGER_COLLECTION_ID,
            "decision_contract_sha256": contract_digest,
            "game_id": GOAL_MANAGER_GAME_ID,
            "ontology_id": GOAL_MANAGER_ONTOLOGY_ID,
            "policy_id": GOAL_MANAGER_POLICY_ID,
            "schema": GOAL_MANAGER_EXECUTION_SCHEMA,
            "source_bundle_sha256": row["source_bundle_sha256"],
            "teacher_configuration_sha256": teacher_digest,
        }
    )
    if row["teacher_execution_sha256"] != expected_execution:
        raise GoalManagerProtocolError("goal-manager teacher execution digest differs")
    return GoalManagerExecution(
        source_bundle_sha256=str(row["source_bundle_sha256"]),
        decision_contract_sha256=contract_digest,
        teacher_configuration_sha256=teacher_digest,
        teacher_execution_sha256=expected_execution,
    )


def _parse_slots(value: object) -> tuple[GoalManagerCollectionSlot, ...]:
    if not isinstance(value, list) or len(value) != _SLOT_COUNT:
        raise GoalManagerProtocolError("goal-manager collection slot count differs")
    result: list[GoalManagerCollectionSlot] = []
    ordinal = 0
    for kind in GoalKind:
        for partition, count in _PARTITION_COUNTS_PER_KIND.items():
            for local_ordinal in range(1, count + 1):
                ordinal += 1
                row = _mapping(value[ordinal - 1], "goal-manager collection slot")
                _exact_keys(
                    row,
                    {"focus_kind", "focus_need", "harness_seed", "partition", "slot_id"},
                    "goal-manager collection slot",
                )
                expected_id = (
                    f"red-goal-v1-{ordinal:03d}-{kind.value}-{partition}-{local_ordinal:02d}"
                )
                if row["slot_id"] != expected_id or row["partition"] != partition:
                    raise GoalManagerProtocolError("goal-manager collection slot order differs")
                if row["focus_kind"] != kind.value:
                    raise GoalManagerProtocolError("goal-manager collection focus kind differs")
                focus_need = GOAL_MANAGER_PRIMARY_NEED[kind]
                if row["focus_need"] != focus_need.value:
                    raise GoalManagerProtocolError("goal-manager collection focus need differs")
                result.append(
                    GoalManagerCollectionSlot(
                        slot_id=_safe_id(row["slot_id"], "slot identity"),
                        partition=partition,
                        harness_seed=_seed(row["harness_seed"]),
                        focus_need=focus_need,
                        focus_kind=kind,
                    )
                )
    slots = tuple(result)
    if Counter(item.partition for item in slots) != Counter(_PARTITION_COUNTS):
        raise GoalManagerProtocolError("goal-manager partition counts differ")
    if len({item.slot_id for item in slots}) != len(slots):
        raise GoalManagerProtocolError("goal-manager slot identities are duplicated")
    if len({item.harness_seed for item in slots}) != len(slots):
        raise GoalManagerProtocolError("goal-manager harness seeds are duplicated")
    return slots


def _parse_digest(payload: bytes) -> tuple[int, str]:
    try:
        row = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise GoalManagerProtocolError("goal-manager digest is invalid") from None
    if not isinstance(row, dict) or _canonical_line(row) != payload:
        raise GoalManagerProtocolError("goal-manager digest is invalid")
    _exact_keys(row, {"bytes", "schema", "sha256"}, "goal-manager digest")
    if row["schema"] != GOAL_MANAGER_REGISTRY_DIGEST_SCHEMA:
        raise GoalManagerProtocolError("goal-manager digest schema differs")
    size = row["bytes"]
    if type(size) is not int or not 1 <= size <= _MAX_REGISTRY_BYTES:  # noqa: E721
        raise GoalManagerProtocolError("goal-manager digest size differs")
    return size, _digest(row["sha256"], "goal-manager registry digest")


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GoalManagerProtocolError(f"{subject} must be an object")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], subject: str) -> None:
    if set(value) != expected:
        raise GoalManagerProtocolError(f"{subject} fields differ")


def _safe_id(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise GoalManagerProtocolError(f"{subject} is invalid")
    return value


def _digest(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise GoalManagerProtocolError(f"{subject} is invalid")
    return value


def _seed(value: object) -> int:
    if type(value) is not int or not 0 <= value < 2**64:  # noqa: E721
        raise GoalManagerProtocolError("goal-manager harness seed is invalid")
    return value


def _git(root: Path, arguments: list[str], maximum_bytes: int) -> bytes:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        raise GoalManagerProtocolError("goal-manager committed artifact is unavailable") from None
    if len(result.stdout) > maximum_bytes:
        raise GoalManagerProtocolError("goal-manager committed artifact is too large")
    return result.stdout
