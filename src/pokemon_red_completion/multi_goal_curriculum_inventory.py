"""Action-free inventory for an honest multi-goal Red curriculum.

Different save-state bytes do not prove independent gameplay experience.  This
module authenticates the historical context bank while keeping exact-state
uniqueness, declared semantic breadth, and verified upstream lineage as three
separate facts.  Only an explicit prospective lineage manifest can make a row
eligible for a held-development claim.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pokemon_red_completion.captured_progress import parse_captured_progress
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_protocol import GoalManagerCollectionRegistry
from pokemon_red_completion.red_goal_context_profile import (
    parse_red_goal_context_profile,
)

MULTI_GOAL_LINEAGE_MANIFEST_SCHEMA = (
    "pokemon.red.multi-goal-curriculum-lineage-manifest.v1"
)
MULTI_GOAL_INVENTORY_SCHEMA = "pokemon.red.multi-goal-curriculum-inventory.v1"
PRIVATE_CONTEXT_PLAN_SCHEMA = "pokemon-red-private-goal-manager-context-plan-v1"
PROFILE_LINEAGE_SCHEMA = "pokemon.red.acquisition-replanning-profile-lineage.v1"
VERIFIED_LINEAGE_EVIDENCE = "prospective-independent-root-v1"

MINIMUM_TRAIN_LINEAGES = 8
MINIMUM_DEVELOPMENT_LINEAGES = 4
MINIMUM_TRAIN_GOAL_FAMILIES = 4
MINIMUM_DEVELOPMENT_GOAL_FAMILIES = 3

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_FORBIDDEN_KEY_PARTS = (
    "outcome",
    "prediction",
    "reward",
    "teacher_choice",
    "model_score",
    "selected_candidate",
)


class MultiGoalCurriculumInventoryError(ValueError):
    """Raised when inventory inputs cannot support a trustworthy census."""


@dataclass(frozen=True, slots=True)
class VerifiedLineageEntry:
    """One context bound to prospectively recorded upstream provenance."""

    slot_id: str
    partition: str
    focus_kind: GoalKind
    state_file_sha256: str
    envelope_file_sha256: str
    profile_file_sha256: str
    upstream_lineage_sha256: str
    physical_root_sha256: str
    evidence_kind: str

    def __post_init__(self) -> None:
        if _SAFE_ID.fullmatch(self.slot_id) is None:
            raise MultiGoalCurriculumInventoryError("lineage slot identity is invalid")
        if self.partition not in {"train", "development"}:
            raise MultiGoalCurriculumInventoryError("lineage partition is invalid")
        if not isinstance(self.focus_kind, GoalKind):
            raise MultiGoalCurriculumInventoryError("lineage goal family is invalid")
        for value, subject in (
            (self.state_file_sha256, "lineage state digest"),
            (self.envelope_file_sha256, "lineage envelope digest"),
            (self.profile_file_sha256, "lineage profile digest"),
            (self.upstream_lineage_sha256, "upstream lineage digest"),
            (self.physical_root_sha256, "physical root digest"),
        ):
            _digest(value, subject)
        if self.evidence_kind != VERIFIED_LINEAGE_EVIDENCE:
            raise MultiGoalCurriculumInventoryError(
                "lineage evidence is not prospective and independent"
            )


@dataclass(frozen=True, slots=True)
class MultiGoalCurriculumInventory:
    """Path-free separation of mechanical supply from learning-ready supply."""

    plan_sha256: str
    profile_lineage_sha256: str
    registry_sha256: str
    contexts: int
    unique_state_files: int
    unique_envelope_files: int
    unique_profile_files: int
    transformed_profiles: int
    partition_context_counts: tuple[tuple[str, int], ...]
    declared_provider_family_counts: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
    claim_availability_evaluated: bool
    open_root_count: int
    open_root_family_counts: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
    verified_lineage_entries: int
    verified_train_lineages: int
    verified_development_lineages: int
    verified_train_goal_families: int
    verified_development_goal_families: int
    train_lineage_deficit: int
    development_lineage_deficit: int
    lineage_overlap_evaluated: bool
    cross_partition_lineage_overlap: int
    cross_partition_physical_root_overlap: int
    reasons: tuple[str, ...]

    @property
    def ready_for_outcome_collection(self) -> bool:
        return not self.reasons

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": MULTI_GOAL_INVENTORY_SCHEMA,
            "status": (
                "ready_for_bounded_outcome_collection"
                if self.ready_for_outcome_collection
                else "lineage_evidence_required"
            ),
            "plan_sha256": self.plan_sha256,
            "profile_lineage_sha256": self.profile_lineage_sha256,
            "registry_sha256": self.registry_sha256,
            "contexts": self.contexts,
            "unique_state_files": self.unique_state_files,
            "unique_envelope_files": self.unique_envelope_files,
            "unique_profile_files": self.unique_profile_files,
            "transformed_profiles": self.transformed_profiles,
            "partition_context_counts": dict(self.partition_context_counts),
            "declared_provider_family_counts": {
                partition: dict(rows)
                for partition, rows in self.declared_provider_family_counts
            },
            "claim_availability_evaluated": self.claim_availability_evaluated,
            "open_root_count": self.open_root_count,
            "open_root_family_counts": {
                partition: dict(rows)
                for partition, rows in self.open_root_family_counts
            },
            "verified_lineage_entries": self.verified_lineage_entries,
            "verified_train_lineages": self.verified_train_lineages,
            "verified_development_lineages": self.verified_development_lineages,
            "verified_train_goal_families": self.verified_train_goal_families,
            "verified_development_goal_families": (
                self.verified_development_goal_families
            ),
            "minimum_train_lineages": MINIMUM_TRAIN_LINEAGES,
            "minimum_development_lineages": MINIMUM_DEVELOPMENT_LINEAGES,
            "minimum_train_goal_families": MINIMUM_TRAIN_GOAL_FAMILIES,
            "minimum_development_goal_families": (
                MINIMUM_DEVELOPMENT_GOAL_FAMILIES
            ),
            "train_lineage_deficit": self.train_lineage_deficit,
            "development_lineage_deficit": self.development_lineage_deficit,
            "lineage_overlap_evaluated": self.lineage_overlap_evaluated,
            "cross_partition_lineage_overlap": (
                self.cross_partition_lineage_overlap
            ),
            "cross_partition_physical_root_overlap": (
                self.cross_partition_physical_root_overlap
            ),
            "reasons": list(self.reasons),
            "calibration_contexts_available": self.contexts,
            "held_development_claim_allowed": self.ready_for_outcome_collection,
            "controller_actions": 0,
            "emulator_frames": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "model_fits": 0,
            "outcomes_opened": 0,
            "private_path_fields": 0,
            "private_identity_fields": 0,
        }


def audit_multi_goal_curriculum_inventory(
    *,
    plan_payload: bytes,
    profile_lineage_payload: bytes,
    registry: GoalManagerCollectionRegistry,
    read_file: Callable[[str], bytes],
    lineage_manifest_payload: bytes | None = None,
    root_is_available: Callable[[str, str], bool] | None = None,
) -> MultiGoalCurriculumInventory:
    """Authenticate a context bank without running a game, teacher, or model."""

    if not isinstance(registry, GoalManagerCollectionRegistry):
        raise TypeError("inventory needs a goal-manager registry")
    plan = _canonical_document(plan_payload, "context plan")
    lineage = _canonical_document(profile_lineage_payload, "profile lineage")
    _reject_learning_results(plan, "context plan")
    _reject_learning_results(lineage, "profile lineage")
    plan_sha256 = hashlib.sha256(plan_payload).hexdigest()
    profile_lineage_sha256 = hashlib.sha256(profile_lineage_payload).hexdigest()
    if (
        set(plan) != {"entries", "registry_sha256", "schema", "source_commit"}
        or plan.get("schema") != PRIVATE_CONTEXT_PLAN_SCHEMA
        or plan.get("registry_sha256") != registry.registry_sha256
        or plan.get("source_commit") != registry.execution.source_commit
    ):
        raise MultiGoalCurriculumInventoryError("context plan binding differs")
    expected_lineage_keys = {
        "builder_runner_sha256",
        "builder_source_bundle_sha256",
        "builder_source_commit",
        "context_catalog_sha256",
        "entries",
        "output_plan_sha256",
        "paired_plan_sha256",
        "prior_campaign_sha256",
        "schema",
        "source_plan_sha256",
        "source_profile_manifest_sha256",
    }
    if (
        set(lineage) != expected_lineage_keys
        or lineage.get("schema") != PROFILE_LINEAGE_SCHEMA
        or lineage.get("output_plan_sha256") != plan_sha256
    ):
        raise MultiGoalCurriculumInventoryError("profile lineage binding differs")

    raw_plan_entries = plan.get("entries")
    raw_profile_entries = lineage.get("entries")
    if not isinstance(raw_plan_entries, list) or not isinstance(
        raw_profile_entries, list
    ):
        raise MultiGoalCurriculumInventoryError("inventory entries are invalid")
    expected_slots = tuple(slot.slot_id for slot in registry.slots)
    if len(raw_plan_entries) != len(expected_slots) or len(raw_profile_entries) != len(
        expected_slots
    ):
        raise MultiGoalCurriculumInventoryError("inventory is incomplete")

    verified_manifest = _parse_verified_manifest(
        lineage_manifest_payload,
        plan_sha256=plan_sha256,
        profile_lineage_sha256=profile_lineage_sha256,
        expected_slots=expected_slots,
    )
    state_hashes: set[str] = set()
    envelope_hashes: set[str] = set()
    profile_hashes: set[str] = set()
    partition_counts: Counter[str] = Counter()
    provider_counts: dict[str, Counter[str]] = defaultdict(Counter)
    open_root_counts: dict[str, Counter[str]] = defaultdict(Counter)
    transformed_profiles = 0

    for index, slot_id in enumerate(expected_slots):
        plan_entry = _mapping(raw_plan_entries[index], "context plan entry")
        profile_entry = _mapping(raw_profile_entries[index], "profile lineage entry")
        if set(plan_entry) != {"envelope", "profile", "slot_id", "state"}:
            raise MultiGoalCurriculumInventoryError("context plan entry fields differ")
        expected_profile_keys = {
            "envelope_file_sha256",
            "output_profile_sha256",
            "slot_id",
            "source_profile_sha256",
            "state_file_sha256",
            "transformed",
        }
        if set(profile_entry) != expected_profile_keys:
            raise MultiGoalCurriculumInventoryError(
                "profile lineage entry fields differ"
            )
        if plan_entry.get("slot_id") != slot_id or profile_entry.get("slot_id") != slot_id:
            raise MultiGoalCurriculumInventoryError("inventory slot order differs")

        state_payload = read_file(_text(plan_entry.get("state"), "state location"))
        envelope_payload = read_file(
            _text(plan_entry.get("envelope"), "envelope location")
        )
        profile_payload = read_file(
            _text(plan_entry.get("profile"), "profile location")
        )
        state_file_sha256 = hashlib.sha256(state_payload).hexdigest()
        envelope_file_sha256 = hashlib.sha256(envelope_payload).hexdigest()
        profile_file_sha256 = hashlib.sha256(profile_payload).hexdigest()
        if (
            state_file_sha256
            != _digest(profile_entry.get("state_file_sha256"), "state digest")
            or envelope_file_sha256
            != _digest(profile_entry.get("envelope_file_sha256"), "envelope digest")
            or profile_file_sha256
            != _digest(profile_entry.get("output_profile_sha256"), "profile digest")
        ):
            raise MultiGoalCurriculumInventoryError("context bytes differ from lineage")
        envelope = parse_captured_progress(envelope_payload, state_bytes=state_payload)
        profile = parse_red_goal_context_profile(profile_payload)
        if envelope.checkpoint_id != slot_id or profile.profile_id != slot_id:
            raise MultiGoalCurriculumInventoryError("context semantic identity differs")
        if state_file_sha256 in state_hashes or envelope_file_sha256 in envelope_hashes:
            raise MultiGoalCurriculumInventoryError("context capture bytes are duplicated")
        state_hashes.add(state_file_sha256)
        envelope_hashes.add(envelope_file_sha256)
        profile_hashes.add(profile_file_sha256)
        assignment = registry.assignment(slot_id)
        partition = _public_partition(assignment.partition)
        partition_counts[partition] += 1
        provider_kinds = {provider.kind for provider in profile.providers}
        if assignment.focus_kind not in provider_kinds:
            raise MultiGoalCurriculumInventoryError(
                "declared focus kind has no provider"
            )
        for kind in provider_kinds:
            provider_counts[partition][kind.value] += 1
        transformed = profile_entry.get("transformed")
        if not isinstance(transformed, bool):
            raise MultiGoalCurriculumInventoryError("profile transform flag is invalid")
        transformed_profiles += int(transformed)
        if root_is_available is not None and root_is_available(
            envelope.state_sha256, envelope_file_sha256
        ):
            open_root_counts[partition][assignment.focus_kind.value] += 1

        manifest_entry = verified_manifest.get(slot_id)
        if manifest_entry is not None and (
            manifest_entry.partition != partition
            or manifest_entry.focus_kind is not assignment.focus_kind
            or manifest_entry.state_file_sha256 != state_file_sha256
            or manifest_entry.envelope_file_sha256 != envelope_file_sha256
            or manifest_entry.profile_file_sha256 != profile_file_sha256
        ):
            raise MultiGoalCurriculumInventoryError("verified lineage join differs")

    verified_entries = tuple(verified_manifest.values())
    train = tuple(item for item in verified_entries if item.partition == "train")
    development = tuple(
        item for item in verified_entries if item.partition == "development"
    )
    train_lineages = {item.upstream_lineage_sha256 for item in train}
    development_lineages = {item.upstream_lineage_sha256 for item in development}
    train_roots = {item.physical_root_sha256 for item in train}
    development_roots = {item.physical_root_sha256 for item in development}
    lineage_overlap = train_lineages & development_lineages
    root_overlap = train_roots & development_roots
    train_families = {item.focus_kind for item in train}
    development_families = {item.focus_kind for item in development}

    reasons: list[str] = []
    if len(verified_entries) != len(expected_slots):
        reasons.append("upstream_lineage_evidence_missing")
    if lineage_overlap:
        reasons.append("cross_partition_upstream_lineage_overlap")
    if root_overlap:
        reasons.append("cross_partition_physical_root_overlap")
    if len(train_lineages) < MINIMUM_TRAIN_LINEAGES:
        reasons.append("insufficient_verified_train_lineages")
    if len(development_lineages) < MINIMUM_DEVELOPMENT_LINEAGES:
        reasons.append("insufficient_verified_development_lineages")
    if len(train_families) < MINIMUM_TRAIN_GOAL_FAMILIES:
        reasons.append("insufficient_verified_train_goal_families")
    if len(development_families) < MINIMUM_DEVELOPMENT_GOAL_FAMILIES:
        reasons.append("insufficient_verified_development_goal_families")

    return MultiGoalCurriculumInventory(
        plan_sha256=plan_sha256,
        profile_lineage_sha256=profile_lineage_sha256,
        registry_sha256=registry.registry_sha256,
        contexts=len(expected_slots),
        unique_state_files=len(state_hashes),
        unique_envelope_files=len(envelope_hashes),
        unique_profile_files=len(profile_hashes),
        transformed_profiles=transformed_profiles,
        partition_context_counts=tuple(sorted(partition_counts.items())),
        declared_provider_family_counts=tuple(
            (partition, tuple(sorted(counts.items())))
            for partition, counts in sorted(provider_counts.items())
        ),
        claim_availability_evaluated=root_is_available is not None,
        open_root_count=sum(sum(counts.values()) for counts in open_root_counts.values()),
        open_root_family_counts=tuple(
            (partition, tuple(sorted(counts.items())))
            for partition, counts in sorted(open_root_counts.items())
        ),
        verified_lineage_entries=len(verified_entries),
        verified_train_lineages=len(train_lineages),
        verified_development_lineages=len(development_lineages),
        verified_train_goal_families=len(train_families),
        verified_development_goal_families=len(development_families),
        train_lineage_deficit=max(0, MINIMUM_TRAIN_LINEAGES - len(train_lineages)),
        development_lineage_deficit=max(
            0, MINIMUM_DEVELOPMENT_LINEAGES - len(development_lineages)
        ),
        lineage_overlap_evaluated=bool(verified_entries),
        cross_partition_lineage_overlap=len(lineage_overlap),
        cross_partition_physical_root_overlap=len(root_overlap),
        reasons=tuple(reasons),
    )


def _parse_verified_manifest(
    payload: bytes | None,
    *,
    plan_sha256: str,
    profile_lineage_sha256: str,
    expected_slots: tuple[str, ...],
) -> dict[str, VerifiedLineageEntry]:
    if payload is None:
        return {}
    document = _canonical_document(payload, "verified lineage manifest")
    _reject_learning_results(document, "verified lineage manifest")
    if set(document) != {
        "entries",
        "plan_sha256",
        "profile_lineage_sha256",
        "schema",
    } or document.get("schema") != MULTI_GOAL_LINEAGE_MANIFEST_SCHEMA:
        raise MultiGoalCurriculumInventoryError("verified lineage manifest differs")
    if (
        document.get("plan_sha256") != plan_sha256
        or document.get("profile_lineage_sha256") != profile_lineage_sha256
    ):
        raise MultiGoalCurriculumInventoryError("verified lineage manifest binding differs")
    rows = document.get("entries")
    if not isinstance(rows, list) or len(rows) != len(expected_slots):
        raise MultiGoalCurriculumInventoryError(
            "verified lineage manifest must cover every context"
        )
    result: dict[str, VerifiedLineageEntry] = {}
    expected_keys = {
        "envelope_file_sha256",
        "evidence_kind",
        "focus_kind",
        "partition",
        "physical_root_sha256",
        "profile_file_sha256",
        "slot_id",
        "state_file_sha256",
        "upstream_lineage_sha256",
    }
    for raw in rows:
        row = _mapping(raw, "verified lineage entry")
        if set(row) != expected_keys:
            raise MultiGoalCurriculumInventoryError(
                "verified lineage entry fields differ"
            )
        try:
            raw_focus_kind = row.get("focus_kind")
            if not isinstance(raw_focus_kind, str):
                raise TypeError
            entry = VerifiedLineageEntry(
                slot_id=_text(row.get("slot_id"), "lineage slot"),
                partition=_text(row.get("partition"), "lineage partition"),
                focus_kind=GoalKind(raw_focus_kind),
                state_file_sha256=_digest(
                    row.get("state_file_sha256"), "lineage state"
                ),
                envelope_file_sha256=_digest(
                    row.get("envelope_file_sha256"), "lineage envelope"
                ),
                profile_file_sha256=_digest(
                    row.get("profile_file_sha256"), "lineage profile"
                ),
                upstream_lineage_sha256=_digest(
                    row.get("upstream_lineage_sha256"), "upstream lineage"
                ),
                physical_root_sha256=_digest(
                    row.get("physical_root_sha256"), "physical root"
                ),
                evidence_kind=_text(row.get("evidence_kind"), "lineage evidence"),
            )
        except (TypeError, ValueError):
            raise MultiGoalCurriculumInventoryError(
                "verified lineage entry is invalid"
            ) from None
        if entry.slot_id in result:
            raise MultiGoalCurriculumInventoryError(
                "verified lineage slot is duplicated"
            )
        result[entry.slot_id] = entry
    if tuple(result) != expected_slots:
        raise MultiGoalCurriculumInventoryError(
            "verified lineage manifest slot order differs"
        )
    root_lineages: dict[str, set[str]] = defaultdict(set)
    for entry in result.values():
        root_lineages[entry.physical_root_sha256].add(
            entry.upstream_lineage_sha256
        )
    if any(len(lineages) != 1 for lineages in root_lineages.values()):
        raise MultiGoalCurriculumInventoryError(
            "one physical root maps to multiple upstream lineages"
        )
    return result


def _public_partition(partition: str) -> str:
    if partition == "validation":
        return "development"
    if partition == "train":
        return partition
    raise MultiGoalCurriculumInventoryError("registry partition is invalid")


def _canonical_document(payload: bytes, subject: str) -> dict[str, object]:
    if not isinstance(payload, bytes) or not payload:
        raise MultiGoalCurriculumInventoryError(f"{subject} is unavailable")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise MultiGoalCurriculumInventoryError(
            f"{subject} is not canonical JSON"
        ) from None
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise MultiGoalCurriculumInventoryError(f"{subject} is not canonical JSON")
    return value


def _reject_learning_results(value: object, subject: str) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or any(part in key for part in _FORBIDDEN_KEY_PARTS):
                raise MultiGoalCurriculumInventoryError(
                    f"{subject} contains a prohibited learning-result field"
                )
            _reject_learning_results(nested, subject)
    elif isinstance(value, list):
        for nested in value:
            _reject_learning_results(nested, subject)


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise MultiGoalCurriculumInventoryError(f"{subject} is invalid")
    return value


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise MultiGoalCurriculumInventoryError(f"{subject} is invalid")
    return value


def _digest(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise MultiGoalCurriculumInventoryError(f"{subject} is invalid")
    return value


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "ascii"
        )
        + b"\n"
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
