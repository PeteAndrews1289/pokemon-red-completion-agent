"""Path-free audit of party-question prior exclusion effectiveness.

Goal-manager checkpoint IDs and goal-manager root-lineage IDs are different
namespaces.  The first reservation planner compared checkpoint IDs directly to
prior root-lineage IDs, while exact state-digest exclusion independently backed
the same boundary.  This audit makes all three effects visible without
publishing any identity: canonical root matches, legacy checkpoint-alias
matches, and exact state matches.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.party_development_inventory import (
    PartyDevelopmentCheckpointInventory,
)
from pokemon_red_completion.party_development_question_reservations import (
    PartyDevelopmentQuestionReservationPlan,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

PARTY_DEVELOPMENT_EXCLUSION_AUDIT_SCHEMA = (
    "pokemon.core.party-development-exclusion-effectiveness-audit.v1"
)
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_OPEN_PARTITIONS = (
    ScenarioPartition.DEVELOPMENT,
    ScenarioPartition.TRAIN,
)


class PartyDevelopmentExclusionAuditError(ValueError):
    """Raised when exclusion effectiveness cannot be measured exactly."""


@dataclass(frozen=True, slots=True)
class PartyDevelopmentPartitionExclusionCounts:
    """Path-free exclusion matches for one open curriculum partition."""

    inventory_count: int
    canonical_root_match_count: int
    legacy_checkpoint_alias_match_count: int
    state_digest_match_count: int
    canonical_root_or_state_match_count: int

    def __post_init__(self) -> None:
        values = (
            self.inventory_count,
            self.canonical_root_match_count,
            self.legacy_checkpoint_alias_match_count,
            self.state_digest_match_count,
            self.canonical_root_or_state_match_count,
        )
        if (
            any(type(value) is not int or value < 0 for value in values)  # noqa: E721
            or any(value > self.inventory_count for value in values[1:])
            or self.canonical_root_or_state_match_count
            < max(self.canonical_root_match_count, self.state_digest_match_count)
        ):
            raise PartyDevelopmentExclusionAuditError(
                "party exclusion counts are invalid"
            )

    def public_dict(self) -> dict[str, int]:
        return {
            "inventory_count": self.inventory_count,
            "canonical_root_match_count": self.canonical_root_match_count,
            "legacy_checkpoint_alias_match_count": (
                self.legacy_checkpoint_alias_match_count
            ),
            "state_digest_match_count": self.state_digest_match_count,
            "canonical_root_or_state_match_count": (
                self.canonical_root_or_state_match_count
            ),
        }


@dataclass(frozen=True, slots=True)
class PartyDevelopmentExclusionAudit:
    """Read-only proof of what each prior-exclusion namespace actually removed."""

    inventory_sha256: str
    plan_sha256: str
    partition_counts: tuple[
        tuple[ScenarioPartition, PartyDevelopmentPartitionExclusionCounts], ...
    ]
    reserved_root_overlap_count: int
    reserved_state_overlap_count: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.inventory_sha256, str)
            or _SHA256.fullmatch(self.inventory_sha256) is None
            or not isinstance(self.plan_sha256, str)
            or _SHA256.fullmatch(self.plan_sha256) is None
            or self.partition_counts
            != tuple(sorted(self.partition_counts, key=lambda item: item[0].value))
            or {partition for partition, _counts in self.partition_counts}
            != set(_OPEN_PARTITIONS)
            or any(
                not isinstance(partition, ScenarioPartition)
                or not isinstance(counts, PartyDevelopmentPartitionExclusionCounts)
                for partition, counts in self.partition_counts
            )
            or type(self.reserved_root_overlap_count) is not int  # noqa: E721
            or self.reserved_root_overlap_count < 0
            or type(self.reserved_state_overlap_count) is not int  # noqa: E721
            or self.reserved_state_overlap_count < 0
        ):
            raise PartyDevelopmentExclusionAuditError(
                "party exclusion audit is invalid"
            )
        if self.reserved_root_overlap_count or self.reserved_state_overlap_count:
            raise PartyDevelopmentExclusionAuditError(
                "reserved party questions overlap prior evidence"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": PARTY_DEVELOPMENT_EXCLUSION_AUDIT_SCHEMA,
            "inventory_sha256": self.inventory_sha256,
            "plan_sha256": self.plan_sha256,
            "partition_counts": {
                partition.value: counts.public_dict()
                for partition, counts in self.partition_counts
            },
            "reserved_root_overlap_count": self.reserved_root_overlap_count,
            "reserved_state_overlap_count": self.reserved_state_overlap_count,
            "checkpoint_id_is_root_lineage_id": False,
            "legacy_root_alias_is_authoritative": False,
            "state_digest_filter_is_independent": True,
            "current_reservations_prior_independent": True,
            "controller_actions": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "outcomes_opened": 0,
            "private_identity_values_public": False,
            "private_path_fields": 0,
        }


def audit_party_development_exclusions(
    inventory: PartyDevelopmentCheckpointInventory,
    plan: PartyDevelopmentQuestionReservationPlan,
    *,
    root_lineage_by_checkpoint_id: Mapping[str, str],
) -> PartyDevelopmentExclusionAudit:
    """Count exclusion matches without treating checkpoint IDs as root IDs."""

    if not isinstance(inventory, PartyDevelopmentCheckpointInventory):
        raise TypeError("inventory must be a PartyDevelopmentCheckpointInventory")
    if not isinstance(plan, PartyDevelopmentQuestionReservationPlan):
        raise TypeError("plan must be a PartyDevelopmentQuestionReservationPlan")
    if plan.inventory_sha256 != inventory.inventory_sha256:
        raise PartyDevelopmentExclusionAuditError(
            "party exclusion audit inventory differs from its plan"
        )
    checkpoint_ids = {item.checkpoint_id for item in inventory.entries}
    if (
        not isinstance(root_lineage_by_checkpoint_id, Mapping)
        or set(root_lineage_by_checkpoint_id) != checkpoint_ids
        or any(
            not isinstance(checkpoint, str)
            or not isinstance(root, str)
            or _SAFE_ID.fullmatch(root) is None
            for checkpoint, root in root_lineage_by_checkpoint_id.items()
        )
        or len(set(root_lineage_by_checkpoint_id.values()))
        != len(root_lineage_by_checkpoint_id)
    ):
        raise PartyDevelopmentExclusionAuditError(
            "party exclusion audit needs one explicit unique root per checkpoint"
        )

    excluded_roots = set(plan.excluded_root_lineage_ids)
    excluded_states = set(plan.excluded_state_sha256)
    partition_counts = []
    for partition in _OPEN_PARTITIONS:
        entries = tuple(
            item for item in inventory.entries if item.partition is partition
        )
        canonical = tuple(
            root_lineage_by_checkpoint_id[item.checkpoint_id] in excluded_roots
            for item in entries
        )
        legacy = tuple(
            item.checkpoint_id in excluded_roots for item in entries
        )
        states = tuple(item.state_sha256 in excluded_states for item in entries)
        partition_counts.append(
            (
                partition,
                PartyDevelopmentPartitionExclusionCounts(
                    inventory_count=len(entries),
                    canonical_root_match_count=sum(canonical),
                    legacy_checkpoint_alias_match_count=sum(legacy),
                    state_digest_match_count=sum(states),
                    canonical_root_or_state_match_count=sum(
                        root_match or state_match
                        for root_match, state_match in zip(
                            canonical,
                            states,
                            strict=True,
                        )
                    ),
                ),
            )
        )

    entries_by_checkpoint = {
        item.checkpoint_id: item for item in inventory.entries
    }
    missing_reservations = {
        item.source_checkpoint_id
        for item in plan.reservations
        if item.source_checkpoint_id not in entries_by_checkpoint
    }
    if missing_reservations:
        raise PartyDevelopmentExclusionAuditError(
            "party exclusion audit cannot resolve a reserved checkpoint"
        )
    reserved_root_overlap_count = sum(
        root_lineage_by_checkpoint_id[item.source_checkpoint_id] in excluded_roots
        for item in plan.reservations
    )
    reserved_state_overlap_count = sum(
        item.source_state_sha256 in excluded_states for item in plan.reservations
    )
    return PartyDevelopmentExclusionAudit(
        inventory_sha256=inventory.inventory_sha256,
        plan_sha256=plan.plan_sha256,
        partition_counts=tuple(
            sorted(partition_counts, key=lambda item: item[0].value)
        ),
        reserved_root_overlap_count=reserved_root_overlap_count,
        reserved_state_overlap_count=reserved_state_overlap_count,
    )


__all__ = [
    "PARTY_DEVELOPMENT_EXCLUSION_AUDIT_SCHEMA",
    "PartyDevelopmentExclusionAudit",
    "PartyDevelopmentExclusionAuditError",
    "PartyDevelopmentPartitionExclusionCounts",
    "audit_party_development_exclusions",
]
