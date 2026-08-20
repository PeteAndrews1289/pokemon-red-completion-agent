"""Path-free semantic inventory for read-only party-development checkpoints."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pokemon_red_completion.party_development_rank import (
    EvolutionRouteKind,
    PartyDevelopmentGoal,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UNIT_BINS = ("empty", "low", "middle", "high")
_DISTANCE_BINS = ("none", "ready", "near", "medium", "far", "unknown")


class PartyDevelopmentInventoryError(ValueError):
    """Raised when a checkpoint inventory contains identity or semantic drift."""


@dataclass(frozen=True, slots=True)
class PartyDevelopmentInventoryMember:
    """Identity-free member facts used only to assess checkpoint diversity."""

    level: int
    hp_bin: str
    pp_bin: str
    status_present: bool
    trainable: bool
    evolution_routes: tuple[EvolutionRouteKind, ...]
    level_evolution_distance_bin: str
    registration_target_needed: bool
    living_target_needed: bool
    role_complete: bool

    def __post_init__(self) -> None:
        if type(self.level) is not int or not 1 <= self.level <= 100:  # noqa: E721
            raise PartyDevelopmentInventoryError("inventory member level is invalid")
        if self.hp_bin not in _UNIT_BINS or self.pp_bin not in _UNIT_BINS:
            raise PartyDevelopmentInventoryError("inventory member resource bin is invalid")
        for value, subject in (
            (self.status_present, "status"),
            (self.trainable, "trainable"),
            (self.registration_target_needed, "registration target"),
            (self.living_target_needed, "living target"),
            (self.role_complete, "role completion"),
        ):
            if not isinstance(value, bool):
                raise PartyDevelopmentInventoryError(
                    f"inventory member {subject} flag is invalid"
                )
        if (
            not isinstance(self.evolution_routes, tuple)
            or any(
                not isinstance(item, EvolutionRouteKind)
                for item in self.evolution_routes
            )
            or len(self.evolution_routes) != len(set(self.evolution_routes))
            or self.evolution_routes
            != tuple(
                item for item in EvolutionRouteKind if item in self.evolution_routes
            )
        ):
            raise PartyDevelopmentInventoryError(
                "inventory member evolution routes are invalid"
            )
        if self.level_evolution_distance_bin not in _DISTANCE_BINS:
            raise PartyDevelopmentInventoryError(
                "inventory member evolution-distance bin is invalid"
            )
        has_level_route = EvolutionRouteKind.LEVEL in self.evolution_routes
        if has_level_route == (self.level_evolution_distance_bin in {"none", "unknown"}):
            raise PartyDevelopmentInventoryError(
                "inventory member level-evolution distance contradicts its routes"
            )

    def semantic_tuple(self) -> tuple[object, ...]:
        return (
            self.level,
            self.hp_bin,
            self.pp_bin,
            self.status_present,
            self.trainable,
            tuple(item.value for item in self.evolution_routes),
            self.level_evolution_distance_bin,
            self.registration_target_needed,
            self.living_target_needed,
            self.role_complete,
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "hp_bin": self.hp_bin,
            "pp_bin": self.pp_bin,
            "status_present": self.status_present,
            "trainable": self.trainable,
            "evolution_routes": [item.value for item in self.evolution_routes],
            "level_evolution_distance_bin": self.level_evolution_distance_bin,
            "registration_target_needed": self.registration_target_needed,
            "living_target_needed": self.living_target_needed,
            "role_complete": self.role_complete,
        }

    @classmethod
    def from_private_dict(
        cls, value: object
    ) -> PartyDevelopmentInventoryMember:
        """Restore one identity-free member from a private inventory row."""

        expected = {
            "evolution_routes",
            "hp_bin",
            "level",
            "level_evolution_distance_bin",
            "living_target_needed",
            "pp_bin",
            "registration_target_needed",
            "role_complete",
            "status_present",
            "trainable",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise PartyDevelopmentInventoryError(
                "inventory member document is invalid"
            )
        routes = value["evolution_routes"]
        if not isinstance(routes, list) or any(
            not isinstance(item, str) for item in routes
        ):
            raise PartyDevelopmentInventoryError(
                "inventory member evolution routes are invalid"
            )
        try:
            return cls(
                level=cast(int, value["level"]),
                hp_bin=cast(str, value["hp_bin"]),
                pp_bin=cast(str, value["pp_bin"]),
                status_present=cast(bool, value["status_present"]),
                trainable=cast(bool, value["trainable"]),
                evolution_routes=tuple(EvolutionRouteKind(item) for item in routes),
                level_evolution_distance_bin=cast(
                    str, value["level_evolution_distance_bin"]
                ),
                registration_target_needed=cast(
                    bool, value["registration_target_needed"]
                ),
                living_target_needed=cast(bool, value["living_target_needed"]),
                role_complete=cast(bool, value["role_complete"]),
            )
        except (TypeError, ValueError) as error:
            raise PartyDevelopmentInventoryError(
                "inventory member document is invalid"
            ) from error


@dataclass(frozen=True, slots=True)
class PartyDevelopmentInventoryEntry:
    """One authenticated state inspected without controller or teacher actions."""

    checkpoint_id: str
    partition: ScenarioPartition
    state_sha256: str
    envelope_sha256: str
    controls_ready: bool
    battle_active: bool
    members: tuple[PartyDevelopmentInventoryMember, ...]
    registration_owned_count: int
    registration_target_count: int
    living_unique_count: int
    living_target_count: int
    specimen_count: int
    role_coverage_count: int
    role_target_count: int
    storage_headroom: int
    goal_hints: tuple[PartyDevelopmentGoal, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.checkpoint_id, str) or _SAFE_ID.fullmatch(
            self.checkpoint_id
        ) is None:
            raise PartyDevelopmentInventoryError("inventory checkpoint id is invalid")
        if not isinstance(self.partition, ScenarioPartition):
            raise PartyDevelopmentInventoryError("inventory partition is invalid")
        for digest_value, digest_subject in (
            (self.state_sha256, "state"),
            (self.envelope_sha256, "envelope"),
        ):
            if (
                not isinstance(digest_value, str)
                or _SHA256.fullmatch(digest_value) is None
            ):
                raise PartyDevelopmentInventoryError(
                    f"inventory {digest_subject} digest is invalid"
                )
        if not isinstance(self.controls_ready, bool) or not isinstance(
            self.battle_active, bool
        ):
            raise PartyDevelopmentInventoryError("inventory readiness flags are invalid")
        if (
            not isinstance(self.members, tuple)
            or not 1 <= len(self.members) <= 6
            or any(
                not isinstance(item, PartyDevelopmentInventoryMember)
                for item in self.members
            )
            or self.members
            != tuple(sorted(self.members, key=lambda item: item.semantic_tuple()))
        ):
            raise PartyDevelopmentInventoryError(
                "inventory members must be identity-free semantic order"
            )
        for count_value, count_target, count_subject in (
            (
                self.registration_owned_count,
                self.registration_target_count,
                "registration",
            ),
            (self.living_unique_count, self.living_target_count, "living collection"),
            (self.role_coverage_count, self.role_target_count, "role coverage"),
        ):
            if (
                type(count_value) is not int  # noqa: E721
                or type(count_target) is not int  # noqa: E721
                or count_target < 1
                or not 0 <= count_value <= count_target
            ):
                raise PartyDevelopmentInventoryError(
                    f"inventory {count_subject} counts are invalid"
                )
        if (
            type(self.specimen_count) is not int  # noqa: E721
            or self.specimen_count < self.living_unique_count
            or type(self.storage_headroom) is not int  # noqa: E721
            or self.storage_headroom < 0
        ):
            raise PartyDevelopmentInventoryError(
                "inventory storage counts are invalid"
            )
        if (
            not isinstance(self.goal_hints, tuple)
            or not self.goal_hints
            or any(not isinstance(item, PartyDevelopmentGoal) for item in self.goal_hints)
            or len(self.goal_hints) != len(set(self.goal_hints))
            or self.goal_hints
            != tuple(item for item in PartyDevelopmentGoal if item in self.goal_hints)
        ):
            raise PartyDevelopmentInventoryError("inventory goal hints are invalid")

    @property
    def semantic_signature_sha256(self) -> str:
        return canonical_sha256(self.semantic_document())

    def semantic_document(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.party-development-checkpoint-semantics.v1",
            "partition": self.partition.value,
            "controls_ready": self.controls_ready,
            "battle_active": self.battle_active,
            "members": [item.public_dict() for item in self.members],
            "registration_owned_count": self.registration_owned_count,
            "registration_target_count": self.registration_target_count,
            "living_unique_count": self.living_unique_count,
            "living_target_count": self.living_target_count,
            "specimen_count": self.specimen_count,
            "role_coverage_count": self.role_coverage_count,
            "role_target_count": self.role_target_count,
            "storage_headroom": self.storage_headroom,
            "goal_hints": [item.value for item in self.goal_hints],
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.party-development-checkpoint-inventory-entry.v1",
            "checkpoint_id": self.checkpoint_id,
            "state_sha256": self.state_sha256,
            "envelope_sha256": self.envelope_sha256,
            "semantic_signature_sha256": self.semantic_signature_sha256,
            "semantics": self.semantic_document(),
            "map_identity_public": False,
            "species_identity_public": False,
            "party_slot_identity_public": False,
            "private_path_fields": 0,
        }

    @classmethod
    def from_private_dict(
        cls, value: object
    ) -> PartyDevelopmentInventoryEntry:
        """Restore and authenticate one checkpoint inventory entry."""

        expected = {
            "checkpoint_id",
            "envelope_sha256",
            "map_identity_public",
            "party_slot_identity_public",
            "private_path_fields",
            "schema",
            "semantic_signature_sha256",
            "semantics",
            "species_identity_public",
            "state_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise PartyDevelopmentInventoryError(
                "inventory checkpoint document is invalid"
            )
        if (
            value["schema"]
            != "pokemon.core.party-development-checkpoint-inventory-entry.v1"
            or value["map_identity_public"] is not False
            or value["party_slot_identity_public"] is not False
            or value["species_identity_public"] is not False
            or value["private_path_fields"] != 0
        ):
            raise PartyDevelopmentInventoryError(
                "inventory checkpoint privacy contract is invalid"
            )
        semantics = value["semantics"]
        semantic_expected = {
            "battle_active",
            "controls_ready",
            "goal_hints",
            "living_target_count",
            "living_unique_count",
            "members",
            "partition",
            "registration_owned_count",
            "registration_target_count",
            "role_coverage_count",
            "role_target_count",
            "schema",
            "specimen_count",
            "storage_headroom",
        }
        if (
            not isinstance(semantics, Mapping)
            or set(semantics) != semantic_expected
            or semantics["schema"]
            != "pokemon.core.party-development-checkpoint-semantics.v1"
        ):
            raise PartyDevelopmentInventoryError(
                "inventory checkpoint semantics are invalid"
            )
        member_rows = semantics["members"]
        goal_rows = semantics["goal_hints"]
        if (
            not isinstance(member_rows, list)
            or not isinstance(goal_rows, list)
            or any(not isinstance(item, str) for item in goal_rows)
        ):
            raise PartyDevelopmentInventoryError(
                "inventory checkpoint semantic rows are invalid"
            )
        try:
            result = cls(
                checkpoint_id=cast(str, value["checkpoint_id"]),
                partition=ScenarioPartition(cast(str, semantics["partition"])),
                state_sha256=cast(str, value["state_sha256"]),
                envelope_sha256=cast(str, value["envelope_sha256"]),
                controls_ready=cast(bool, semantics["controls_ready"]),
                battle_active=cast(bool, semantics["battle_active"]),
                members=tuple(
                    PartyDevelopmentInventoryMember.from_private_dict(item)
                    for item in member_rows
                ),
                registration_owned_count=cast(
                    int, semantics["registration_owned_count"]
                ),
                registration_target_count=cast(
                    int, semantics["registration_target_count"]
                ),
                living_unique_count=cast(int, semantics["living_unique_count"]),
                living_target_count=cast(int, semantics["living_target_count"]),
                specimen_count=cast(int, semantics["specimen_count"]),
                role_coverage_count=cast(int, semantics["role_coverage_count"]),
                role_target_count=cast(int, semantics["role_target_count"]),
                storage_headroom=cast(int, semantics["storage_headroom"]),
                goal_hints=tuple(PartyDevelopmentGoal(item) for item in goal_rows),
            )
        except (TypeError, ValueError) as error:
            raise PartyDevelopmentInventoryError(
                "inventory checkpoint document is invalid"
            ) from error
        if value["semantic_signature_sha256"] != result.semantic_signature_sha256:
            raise PartyDevelopmentInventoryError(
                "inventory checkpoint semantic digest differs"
            )
        return result


@dataclass(frozen=True, slots=True)
class PartyDevelopmentCheckpointInventory:
    """Diagnostic inventory; it cannot authorize collection or model fitting."""

    entries: tuple[PartyDevelopmentInventoryEntry, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.entries, tuple)
            or not self.entries
            or any(
                not isinstance(item, PartyDevelopmentInventoryEntry)
                for item in self.entries
            )
            or self.entries
            != tuple(sorted(self.entries, key=lambda item: item.checkpoint_id))
        ):
            raise PartyDevelopmentInventoryError(
                "checkpoint inventory entries must use checkpoint order"
            )
        for attribute, subject in (
            ("checkpoint_id", "checkpoint"),
            ("state_sha256", "state"),
            ("envelope_sha256", "envelope"),
        ):
            values = tuple(getattr(item, attribute) for item in self.entries)
            if len(values) != len(set(values)):
                raise PartyDevelopmentInventoryError(
                    f"checkpoint inventory repeats a {subject}"
                )

    @property
    def inventory_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.party-development-checkpoint-inventory.v1",
            "entries": [item.public_dict() for item in self.entries],
            "inspection_mode": "read_only_no_controller_no_teacher",
            "private_path_fields": 0,
        }

    @classmethod
    def from_private_dict(
        cls, value: object
    ) -> PartyDevelopmentCheckpointInventory:
        """Restore the exact read-only inventory emitted by the inspector."""

        expected = {
            "entries",
            "inspection_mode",
            "private_path_fields",
            "schema",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise PartyDevelopmentInventoryError(
                "checkpoint inventory document is invalid"
            )
        rows = value["entries"]
        if (
            value["schema"]
            != "pokemon.core.party-development-checkpoint-inventory.v1"
            or value["inspection_mode"]
            != "read_only_no_controller_no_teacher"
            or value["private_path_fields"] != 0
            or not isinstance(rows, list)
        ):
            raise PartyDevelopmentInventoryError(
                "checkpoint inventory provenance is invalid"
            )
        return cls(
            tuple(
                PartyDevelopmentInventoryEntry.from_private_dict(item)
                for item in rows
            )
        )

    def summary_dict(self) -> dict[str, object]:
        partitions = Counter(item.partition.value for item in self.entries)
        semantic_signatures: dict[str, set[str]] = {}
        hp_bins: dict[str, set[str]] = {}
        pp_bins: dict[str, set[str]] = {}
        routes: dict[str, set[str]] = {}
        goals: dict[str, set[str]] = {}
        ready_candidate_counts: dict[str, int] = Counter()
        for entry in self.entries:
            partition = entry.partition.value
            semantic_signatures.setdefault(partition, set()).add(
                entry.semantic_signature_sha256
            )
            hp_bins.setdefault(partition, set()).update(
                member.hp_bin for member in entry.members
            )
            pp_bins.setdefault(partition, set()).update(
                member.pp_bin for member in entry.members
            )
            routes.setdefault(partition, set()).update(
                route.value
                for member in entry.members
                for route in member.evolution_routes
            )
            goals.setdefault(partition, set()).update(
                goal.value for goal in entry.goal_hints
            )
            ready_candidate_counts[partition] += int(
                entry.controls_ready
                and not entry.battle_active
                and sum(member.trainable for member in entry.members) >= 2
            )
        return {
            "schema": "pokemon.core.party-development-checkpoint-inventory-summary.v1",
            "inventory_sha256": self.inventory_sha256,
            "checkpoint_count": len(self.entries),
            "partition_counts": dict(sorted(partitions.items())),
            "unique_semantic_contexts": {
                key: len(value) for key, value in sorted(semantic_signatures.items())
            },
            "hp_bins": {key: sorted(value) for key, value in sorted(hp_bins.items())},
            "pp_bins": {key: sorted(value) for key, value in sorted(pp_bins.items())},
            "evolution_routes": {
                key: sorted(value) for key, value in sorted(routes.items())
            },
            "goal_hints": {key: sorted(value) for key, value in sorted(goals.items())},
            "ready_multi_candidate_contexts": dict(
                sorted(ready_candidate_counts.items())
            ),
            "diagnostic_only": True,
            "prospective_catalog_frozen": False,
            "outcomes_collected": 0,
            "model_updates": 0,
            "teacher_queries": 0,
            "sealed_test_cases_opened": 0,
            "crystal_cases_opened": 0,
            "controller_actions": 0,
            "authority_promoted": False,
            "member_feature_values_public": False,
            "private_path_fields": 0,
        }


def unit_bin(value: float) -> str:
    if value <= 0.0:
        return "empty"
    if value < 0.34:
        return "low"
    if value < 0.67:
        return "middle"
    return "high"


def level_distance_bin(value: int | None) -> str:
    if value is None:
        return "unknown"
    if value <= 0:
        return "ready"
    if value <= 3:
        return "near"
    if value <= 10:
        return "medium"
    return "far"


__all__ = [
    "PartyDevelopmentCheckpointInventory",
    "PartyDevelopmentInventoryEntry",
    "PartyDevelopmentInventoryError",
    "PartyDevelopmentInventoryMember",
    "level_distance_bin",
    "unit_bin",
]
