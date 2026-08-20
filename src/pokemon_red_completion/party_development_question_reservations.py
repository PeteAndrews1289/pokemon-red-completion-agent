"""Reserve an honest first party curriculum before any outcome is opened.

The checkpoint inventory is intentionally diagnostic: it can show that useful
states exist without pretending those states are already learner questions.
This module adds the next, still non-executing layer.  It reserves independent
source roots for the first 8 train and 6 development questions, balances the
portable goals and choice kinds, and freezes the natural PP-depletion protocol
needed to create the missing resource context.

A reservation is not a prospective binding.  It contains no candidate feature
rows, label, prediction, outcome, controller action, map, species, move, or
party-slot identity.  Materialized states must be inventoried again and the
real menus must still pass :mod:`party_development_catalog` before collection.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from pokemon_red_completion.party_development_inventory import (
    PartyDevelopmentCheckpointInventory,
    PartyDevelopmentInventoryEntry,
)
from pokemon_red_completion.party_development_outcome_dataset import (
    DEFAULT_PARTY_DEVELOPMENT_READINESS_POLICY,
    PartyDevelopmentReadinessPolicy,
)
from pokemon_red_completion.party_development_outcome_learning import (
    PartyDevelopmentTeacherPrior,
)
from pokemon_red_completion.party_development_rank import (
    EvolutionRouteKind,
    PartyDevelopmentGoal,
)
from pokemon_red_completion.party_development_venue_priors import (
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

PARTY_DEVELOPMENT_QUESTION_RESERVATION_SCHEMA = (
    "pokemon.core.party-development-question-reservation.v1"
)
PARTY_DEVELOPMENT_QUESTION_RESERVATION_PLAN_SCHEMA = (
    "pokemon.core.party-development-question-reservation-plan.v1"
)
PARTY_DEVELOPMENT_QUESTION_RESERVATION_SUMMARY_SCHEMA = (
    "pokemon.core.party-development-question-reservation-summary.v1"
)
PARTY_DEVELOPMENT_QUESTION_RESERVATION_REFRESH_SCHEMA = (
    "pokemon.core.party-development-question-reservation-refresh.v1"
)

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PP_BINS = ("empty", "low", "middle", "high")


class PartyDevelopmentQuestionReservationError(ValueError):
    """Raised when a reservation would overclaim independence or readiness."""


class PartyDevelopmentContextPreparation(StrEnum):
    """Prospectively declared work between a source state and a question."""

    NONE = "none"
    NATURAL_PP_DEPLETION = "natural_pp_depletion"


PP_CONTEXT_MATERIALIZATION_PROTOCOL = {
    "schema": "pokemon.core.party-development-pp-context-materialization.v1",
    "purpose": "create_naturally_depleted_pp_question_context",
    "source": "one_reserved_authenticated_non_sealed_checkpoint",
    "allowed_state_changes": [
        "ordinary_wild_battle_damage",
        "ordinary_wild_battle_experience",
        "ordinary_move_pp_consumption",
    ],
    "forbidden_operations": [
        "candidate_outcome_measurement",
        "direct_memory_edit",
        "healing_before_capture",
        "model_fit",
        "model_prediction",
        "sealed_context_access",
        "teacher_query",
    ],
    "deterministic_stop": "first_post_battle_middle_pp_bin",
    "abort_conditions": [
        "battle_loss",
        "faint",
        "party_membership_change",
        "persistent_status",
        "storage_or_capture_side_effect",
        "unexpected_story_progress",
    ],
    "retention": "write_new_authenticated_state_and_envelope_before_menu_projection",
    "replacement_policy": "never_replace_an_exposed_or_failed_identity",
    "required_recheck": (
        "read_only_inventory_then_exact_prospective_candidate_binding"
    ),
}
PP_CONTEXT_MATERIALIZATION_PROTOCOL_SHA256 = canonical_sha256(
    PP_CONTEXT_MATERIALIZATION_PROTOCOL
)


@dataclass(frozen=True, slots=True)
class PartyDevelopmentQuestionReservation:
    """One private source root assigned to one not-yet-frozen question."""

    scenario_id: str
    source_checkpoint_id: str
    source_state_sha256: str
    source_envelope_sha256: str
    source_semantic_signature_sha256: str
    partition: ScenarioPartition
    kind: TrainingChoiceKind
    goal: PartyDevelopmentGoal
    preparation: PartyDevelopmentContextPreparation
    target_pp_bin: str | None
    source_member_count: int
    source_trainable_count: int
    source_hp_bins: tuple[str, ...]
    source_pp_bins: tuple[str, ...]
    source_evolution_route_kinds: tuple[EvolutionRouteKind, ...]

    def __post_init__(self) -> None:
        for value, subject in (
            (self.scenario_id, "scenario"),
            (self.source_checkpoint_id, "source checkpoint"),
        ):
            if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
                raise PartyDevelopmentQuestionReservationError(
                    f"party question {subject} is invalid"
                )
        for value, subject in (
            (self.source_state_sha256, "source state"),
            (self.source_envelope_sha256, "source envelope"),
            (self.source_semantic_signature_sha256, "source semantics"),
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise PartyDevelopmentQuestionReservationError(
                    f"party question {subject} digest is invalid"
                )
        if (
            not isinstance(self.partition, ScenarioPartition)
            or not isinstance(self.kind, TrainingChoiceKind)
            or not isinstance(self.goal, PartyDevelopmentGoal)
            or not isinstance(self.preparation, PartyDevelopmentContextPreparation)
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question decision semantics are invalid"
            )
        if (
            type(self.source_member_count) is not int  # noqa: E721
            or not 1 <= self.source_member_count <= 6
            or type(self.source_trainable_count) is not int  # noqa: E721
            or not 2 <= self.source_trainable_count <= self.source_member_count
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question source party counts are invalid"
            )
        self._require_sorted_bins(self.source_hp_bins, subject="health")
        self._require_sorted_bins(self.source_pp_bins, subject="PP")
        routes = self.source_evolution_route_kinds
        if (
            not isinstance(routes, tuple)
            or not routes
            or any(not isinstance(item, EvolutionRouteKind) for item in routes)
            or routes
            != tuple(item for item in EvolutionRouteKind if item in set(routes))
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question source evolution routes are invalid"
            )
        if self.preparation is PartyDevelopmentContextPreparation.NONE:
            if self.target_pp_bin is not None:
                raise PartyDevelopmentQuestionReservationError(
                    "direct party questions cannot declare a target PP bin"
                )
        elif (
            self.target_pp_bin != "middle"
            or self.source_pp_bins != ("high",)
        ):
            raise PartyDevelopmentQuestionReservationError(
                "PP materialization must start high and target the middle bin"
            )

    @staticmethod
    def _require_sorted_bins(values: tuple[str, ...], *, subject: str) -> None:
        if (
            not isinstance(values, tuple)
            or not values
            or any(item not in _PP_BINS for item in values)
            or values != tuple(item for item in _PP_BINS if item in set(values))
        ):
            raise PartyDevelopmentQuestionReservationError(
                f"party question source {subject} bins are invalid"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "schema": PARTY_DEVELOPMENT_QUESTION_RESERVATION_SCHEMA,
            "scenario_id": self.scenario_id,
            "source_checkpoint_id": self.source_checkpoint_id,
            "source_state_sha256": self.source_state_sha256,
            "source_envelope_sha256": self.source_envelope_sha256,
            "source_semantic_signature_sha256": (
                self.source_semantic_signature_sha256
            ),
            "partition": self.partition.value,
            "kind": self.kind.value,
            "goal": self.goal.value,
            "preparation": self.preparation.value,
            "target_pp_bin": self.target_pp_bin,
            "source_member_count": self.source_member_count,
            "source_trainable_count": self.source_trainable_count,
            "source_hp_bins": list(self.source_hp_bins),
            "source_pp_bins": list(self.source_pp_bins),
            "source_evolution_route_kinds": [
                item.value for item in self.source_evolution_route_kinds
            ],
            "candidate_menu_frozen": False,
            "outcome_opened": False,
        }

    @classmethod
    def from_private_dict(
        cls, value: object
    ) -> PartyDevelopmentQuestionReservation:
        """Restore one reservation while rechecking its closed counters."""

        expected = {
            "candidate_menu_frozen",
            "goal",
            "kind",
            "outcome_opened",
            "partition",
            "preparation",
            "scenario_id",
            "schema",
            "source_checkpoint_id",
            "source_envelope_sha256",
            "source_evolution_route_kinds",
            "source_hp_bins",
            "source_member_count",
            "source_pp_bins",
            "source_semantic_signature_sha256",
            "source_state_sha256",
            "source_trainable_count",
            "target_pp_bin",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value["schema"] != PARTY_DEVELOPMENT_QUESTION_RESERVATION_SCHEMA
            or value["candidate_menu_frozen"] is not False
            or value["outcome_opened"] is not False
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question reservation document is invalid"
            )
        hp_bins = value["source_hp_bins"]
        pp_bins = value["source_pp_bins"]
        route_rows = value["source_evolution_route_kinds"]
        if (
            not isinstance(hp_bins, list)
            or any(not isinstance(item, str) for item in hp_bins)
            or not isinstance(pp_bins, list)
            or any(not isinstance(item, str) for item in pp_bins)
            or not isinstance(route_rows, list)
            or any(not isinstance(item, str) for item in route_rows)
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question reservation semantic rows are invalid"
            )
        try:
            return cls(
                scenario_id=cast(str, value["scenario_id"]),
                source_checkpoint_id=cast(str, value["source_checkpoint_id"]),
                source_state_sha256=cast(str, value["source_state_sha256"]),
                source_envelope_sha256=cast(
                    str, value["source_envelope_sha256"]
                ),
                source_semantic_signature_sha256=cast(
                    str, value["source_semantic_signature_sha256"]
                ),
                partition=ScenarioPartition(cast(str, value["partition"])),
                kind=TrainingChoiceKind(cast(str, value["kind"])),
                goal=PartyDevelopmentGoal(cast(str, value["goal"])),
                preparation=PartyDevelopmentContextPreparation(
                    cast(str, value["preparation"])
                ),
                target_pp_bin=cast(str | None, value["target_pp_bin"]),
                source_member_count=cast(int, value["source_member_count"]),
                source_trainable_count=cast(
                    int, value["source_trainable_count"]
                ),
                source_hp_bins=tuple(hp_bins),
                source_pp_bins=tuple(pp_bins),
                source_evolution_route_kinds=tuple(
                    EvolutionRouteKind(item) for item in route_rows
                ),
            )
        except (TypeError, ValueError) as error:
            raise PartyDevelopmentQuestionReservationError(
                "party question reservation document is invalid"
            ) from error


@dataclass(frozen=True, slots=True)
class PartyDevelopmentQuestionReservationPlan:
    """Exact private 8+6 root reservation with explicit remaining blockers."""

    inventory_sha256: str
    teacher_prior_sha256: str
    venue_prior_registry_sha256: str
    venue_prior_count: int
    excluded_root_lineage_ids: tuple[str, ...]
    excluded_state_sha256: tuple[str, ...]
    reservations: tuple[PartyDevelopmentQuestionReservation, ...]
    policy: PartyDevelopmentReadinessPolicy = (
        DEFAULT_PARTY_DEVELOPMENT_READINESS_POLICY
    )
    pp_materialization_protocol_sha256: str = (
        PP_CONTEXT_MATERIALIZATION_PROTOCOL_SHA256
    )

    def __post_init__(self) -> None:
        for value, subject in (
            (self.inventory_sha256, "inventory"),
            (self.teacher_prior_sha256, "teacher prior"),
            (self.venue_prior_registry_sha256, "venue registry"),
            (self.pp_materialization_protocol_sha256, "PP protocol"),
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise PartyDevelopmentQuestionReservationError(
                    f"party question plan {subject} digest is invalid"
                )
        if (
            type(self.venue_prior_count) is not int  # noqa: E721
            or self.venue_prior_count < 0
            or not isinstance(self.policy, PartyDevelopmentReadinessPolicy)
            or self.pp_materialization_protocol_sha256
            != PP_CONTEXT_MATERIALIZATION_PROTOCOL_SHA256
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question plan contract is invalid"
            )
        self._require_exclusions()
        reservations = self.reservations
        if (
            not isinstance(reservations, tuple)
            or any(
                not isinstance(item, PartyDevelopmentQuestionReservation)
                for item in reservations
            )
            or reservations
            != tuple(sorted(reservations, key=lambda item: item.scenario_id))
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question reservations must use scenario order"
            )
        for attribute, subject in (
            ("scenario_id", "scenario"),
            ("source_checkpoint_id", "source root"),
            ("source_state_sha256", "source state"),
            ("source_envelope_sha256", "source envelope"),
        ):
            values = tuple(getattr(item, attribute) for item in reservations)
            if len(values) != len(set(values)):
                raise PartyDevelopmentQuestionReservationError(
                    f"party question plan repeats a {subject}"
                )
        if set(item.source_checkpoint_id for item in reservations) & set(
            self.excluded_root_lineage_ids
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question source overlaps prior evidence roots"
            )
        if set(item.source_state_sha256 for item in reservations) & set(
            self.excluded_state_sha256
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question source overlaps prior evidence states"
            )
        self._require_partition(
            ScenarioPartition.TRAIN,
            expected=self.policy.minimum_train_examples,
        )
        self._require_partition(
            ScenarioPartition.DEVELOPMENT,
            expected=self.policy.minimum_development_examples,
        )

    def _require_exclusions(self) -> None:
        roots = self.excluded_root_lineage_ids
        states = self.excluded_state_sha256
        if (
            not isinstance(roots, tuple)
            or not roots
            or roots != tuple(sorted(set(roots)))
            or any(_SAFE_ID.fullmatch(item) is None for item in roots)
            or not isinstance(states, tuple)
            or not states
            or states != tuple(sorted(set(states)))
            or any(_SHA256.fullmatch(item) is None for item in states)
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question prior exclusions are invalid"
            )

    def _require_partition(
        self, partition: ScenarioPartition, *, expected: int
    ) -> None:
        items = tuple(
            item for item in self.reservations if item.partition is partition
        )
        if len(items) != expected:
            raise PartyDevelopmentQuestionReservationError(
                f"party question plan needs exactly {expected} {partition.value} roots"
            )
        if {item.kind for item in items} != set(TrainingChoiceKind):
            raise PartyDevelopmentQuestionReservationError(
                f"party question plan lacks a {partition.value} choice kind"
            )
        if len({item.goal for item in items}) < self.policy.minimum_goals_per_partition:
            raise PartyDevelopmentQuestionReservationError(
                f"party question plan lacks {partition.value} goal diversity"
            )
        if (
            max((item.source_trainable_count for item in items), default=0)
            < self.policy.minimum_candidate_count_observed
        ):
            raise PartyDevelopmentQuestionReservationError(
                f"party question plan lacks a wide {partition.value} source party"
            )
        hp_bins = {value for item in items for value in item.source_hp_bins}
        routes = {
            value for item in items for value in item.source_evolution_route_kinds
        }
        semantics = {item.source_semantic_signature_sha256 for item in items}
        projected_pp_bins = {
            value for item in items for value in item.source_pp_bins
        } | {item.target_pp_bin for item in items if item.target_pp_bin is not None}
        if len(hp_bins) < self.policy.minimum_health_bins:
            raise PartyDevelopmentQuestionReservationError(
                f"party question plan lacks {partition.value} health diversity"
            )
        if len(routes) < self.policy.minimum_evolution_route_kinds:
            raise PartyDevelopmentQuestionReservationError(
                f"party question plan lacks {partition.value} evolution diversity"
            )
        if len(semantics) < self.policy.minimum_semantic_menus_per_partition:
            raise PartyDevelopmentQuestionReservationError(
                f"party question plan lacks {partition.value} semantic diversity"
            )
        if len(projected_pp_bins) < self.policy.minimum_pp_bins:
            raise PartyDevelopmentQuestionReservationError(
                f"party question plan does not prospectively close {partition.value} PP diversity"
            )
        if not any(
            item.preparation
            is PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
            for item in items
        ):
            raise PartyDevelopmentQuestionReservationError(
                f"party question plan lacks a {partition.value} PP materialization"
            )

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(self._plan_document())

    @property
    def unresolved_blockers(self) -> tuple[str, ...]:
        blockers = [
            "concrete_red_candidate_bindings_not_frozen",
            "reserved_pp_contexts_not_materialized",
        ]
        if self.venue_prior_count < 2:
            blockers.append("second_compatible_venue_prior_missing")
        blockers.append("prospective_8_plus_6_catalog_not_frozen")
        return tuple(sorted(blockers))

    @property
    def catalog_freeze_ready(self) -> bool:
        return False

    def _plan_document(self) -> dict[str, object]:
        return {
            "schema": PARTY_DEVELOPMENT_QUESTION_RESERVATION_PLAN_SCHEMA,
            "inventory_sha256": self.inventory_sha256,
            "teacher_prior_sha256": self.teacher_prior_sha256,
            "venue_prior_registry_sha256": self.venue_prior_registry_sha256,
            "venue_prior_count": self.venue_prior_count,
            "excluded_root_lineage_ids": list(self.excluded_root_lineage_ids),
            "excluded_state_sha256": list(self.excluded_state_sha256),
            "pp_materialization_protocol": PP_CONTEXT_MATERIALIZATION_PROTOCOL,
            "pp_materialization_protocol_sha256": (
                self.pp_materialization_protocol_sha256
            ),
            "policy": self.policy.public_dict(),
            "reservations": [item.private_dict() for item in self.reservations],
            "catalog_freeze_ready": False,
            "unresolved_blockers": list(self.unresolved_blockers),
            "candidate_menus_frozen": 0,
            "outcomes_opened": 0,
            "model_updates": 0,
            "controller_actions": 0,
            "teacher_queries": 0,
            "sealed_test_cases_opened": 0,
            "crystal_cases_opened": 0,
            "authority_promoted": False,
            "private_path_fields": 0,
        }

    def private_dict(self) -> dict[str, object]:
        return {**self._plan_document(), "plan_sha256": self.plan_sha256}

    @classmethod
    def from_private_dict(
        cls, value: object
    ) -> PartyDevelopmentQuestionReservationPlan:
        """Restore the exact private plan without promoting it to a catalog."""

        expected = {
            "authority_promoted",
            "candidate_menus_frozen",
            "catalog_freeze_ready",
            "controller_actions",
            "crystal_cases_opened",
            "excluded_root_lineage_ids",
            "excluded_state_sha256",
            "inventory_sha256",
            "model_updates",
            "outcomes_opened",
            "plan_sha256",
            "policy",
            "pp_materialization_protocol",
            "pp_materialization_protocol_sha256",
            "private_path_fields",
            "reservations",
            "schema",
            "sealed_test_cases_opened",
            "teacher_prior_sha256",
            "teacher_queries",
            "unresolved_blockers",
            "venue_prior_count",
            "venue_prior_registry_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise PartyDevelopmentQuestionReservationError(
                "party question reservation plan document is invalid"
            )
        if (
            value["schema"]
            != PARTY_DEVELOPMENT_QUESTION_RESERVATION_PLAN_SCHEMA
            or value["catalog_freeze_ready"] is not False
            or value["authority_promoted"] is not False
            or value["candidate_menus_frozen"] != 0
            or value["outcomes_opened"] != 0
            or value["model_updates"] != 0
            or value["controller_actions"] != 0
            or value["teacher_queries"] != 0
            or value["sealed_test_cases_opened"] != 0
            or value["crystal_cases_opened"] != 0
            or value["private_path_fields"] != 0
            or value["pp_materialization_protocol"]
            != PP_CONTEXT_MATERIALIZATION_PROTOCOL
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question reservation plan provenance is invalid"
            )
        roots = value["excluded_root_lineage_ids"]
        states = value["excluded_state_sha256"]
        rows = value["reservations"]
        policy_value = value["policy"]
        blockers = value["unresolved_blockers"]
        if (
            not isinstance(roots, list)
            or any(not isinstance(item, str) for item in roots)
            or not isinstance(states, list)
            or any(not isinstance(item, str) for item in states)
            or not isinstance(rows, list)
            or not isinstance(policy_value, Mapping)
            or not isinstance(blockers, list)
            or any(not isinstance(item, str) for item in blockers)
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question reservation plan rows are invalid"
            )
        policy_expected = {
            "minimum_candidate_count_observed",
            "minimum_development_examples",
            "minimum_evolution_route_kinds",
            "minimum_goals_per_partition",
            "minimum_health_bins",
            "minimum_pp_bins",
            "minimum_semantic_menus_per_partition",
            "minimum_survival_bins",
            "minimum_train_examples",
            "require_both_choice_kinds",
            "require_complete_venue_priors",
        }
        if set(policy_value) != policy_expected:
            raise PartyDevelopmentQuestionReservationError(
                "party question reservation policy is invalid"
            )
        try:
            policy = PartyDevelopmentReadinessPolicy(
                minimum_train_examples=cast(
                    int, policy_value["minimum_train_examples"]
                ),
                minimum_development_examples=cast(
                    int, policy_value["minimum_development_examples"]
                ),
                minimum_goals_per_partition=cast(
                    int, policy_value["minimum_goals_per_partition"]
                ),
                minimum_candidate_count_observed=cast(
                    int, policy_value["minimum_candidate_count_observed"]
                ),
                minimum_health_bins=cast(
                    int, policy_value["minimum_health_bins"]
                ),
                minimum_pp_bins=cast(int, policy_value["minimum_pp_bins"]),
                minimum_survival_bins=cast(
                    int, policy_value["minimum_survival_bins"]
                ),
                minimum_evolution_route_kinds=cast(
                    int, policy_value["minimum_evolution_route_kinds"]
                ),
                minimum_semantic_menus_per_partition=cast(
                    int, policy_value["minimum_semantic_menus_per_partition"]
                ),
                require_both_choice_kinds=cast(
                    bool, policy_value["require_both_choice_kinds"]
                ),
                require_complete_venue_priors=cast(
                    bool, policy_value["require_complete_venue_priors"]
                ),
            )
            result = cls(
                inventory_sha256=cast(str, value["inventory_sha256"]),
                teacher_prior_sha256=cast(
                    str, value["teacher_prior_sha256"]
                ),
                venue_prior_registry_sha256=cast(
                    str, value["venue_prior_registry_sha256"]
                ),
                venue_prior_count=cast(int, value["venue_prior_count"]),
                excluded_root_lineage_ids=tuple(roots),
                excluded_state_sha256=tuple(states),
                reservations=tuple(
                    PartyDevelopmentQuestionReservation.from_private_dict(item)
                    for item in rows
                ),
                policy=policy,
                pp_materialization_protocol_sha256=cast(
                    str, value["pp_materialization_protocol_sha256"]
                ),
            )
        except (TypeError, ValueError) as error:
            raise PartyDevelopmentQuestionReservationError(
                "party question reservation plan document is invalid"
            ) from error
        if blockers != list(result.unresolved_blockers):
            raise PartyDevelopmentQuestionReservationError(
                "party question reservation blocker set differs"
            )
        if value["plan_sha256"] != result.plan_sha256:
            raise PartyDevelopmentQuestionReservationError(
                "party question reservation plan digest differs"
            )
        return result

    def public_summary(self) -> dict[str, object]:
        partition_counts = Counter(item.partition.value for item in self.reservations)
        kind_counts = Counter(
            f"{item.partition.value}:{item.kind.value}" for item in self.reservations
        )
        goal_counts = Counter(
            f"{item.partition.value}:{item.goal.value}" for item in self.reservations
        )
        preparation_counts = Counter(
            f"{item.partition.value}:{item.preparation.value}"
            for item in self.reservations
        )
        source_hp_bins: dict[str, set[str]] = {}
        source_pp_bins: dict[str, set[str]] = {}
        projected_pp_bins: dict[str, set[str]] = {}
        source_routes: dict[str, set[str]] = {}
        source_semantics: dict[str, set[str]] = {}
        source_widths: dict[str, set[int]] = {}
        for item in self.reservations:
            partition = item.partition.value
            source_hp_bins.setdefault(partition, set()).update(item.source_hp_bins)
            source_pp_bins.setdefault(partition, set()).update(item.source_pp_bins)
            projected_pp_bins.setdefault(partition, set()).update(item.source_pp_bins)
            if item.target_pp_bin is not None:
                projected_pp_bins[partition].add(item.target_pp_bin)
            source_routes.setdefault(partition, set()).update(
                route.value for route in item.source_evolution_route_kinds
            )
            source_semantics.setdefault(partition, set()).add(
                item.source_semantic_signature_sha256
            )
            source_widths.setdefault(partition, set()).add(
                item.source_trainable_count
            )
        return {
            "schema": PARTY_DEVELOPMENT_QUESTION_RESERVATION_SUMMARY_SCHEMA,
            "plan_sha256": self.plan_sha256,
            "inventory_sha256": self.inventory_sha256,
            "teacher_prior_sha256": self.teacher_prior_sha256,
            "venue_prior_registry_sha256": self.venue_prior_registry_sha256,
            "reservation_count": len(self.reservations),
            "partition_counts": dict(sorted(partition_counts.items())),
            "choice_kind_partition_counts": dict(sorted(kind_counts.items())),
            "goal_partition_counts": dict(sorted(goal_counts.items())),
            "preparation_partition_counts": dict(
                sorted(preparation_counts.items())
            ),
            "source_health_bins": {
                key: sorted(value) for key, value in sorted(source_hp_bins.items())
            },
            "source_pp_bins": {
                key: sorted(value) for key, value in sorted(source_pp_bins.items())
            },
            "prospective_pp_bins_after_materialization": {
                key: sorted(value)
                for key, value in sorted(projected_pp_bins.items())
            },
            "source_evolution_route_kinds": {
                key: sorted(value) for key, value in sorted(source_routes.items())
            },
            "source_semantic_context_counts": {
                key: len(value) for key, value in sorted(source_semantics.items())
            },
            "source_trainable_widths": {
                key: sorted(value) for key, value in sorted(source_widths.items())
            },
            "qualified_venue_priors": self.venue_prior_count,
            "minimum_venue_priors_for_genuine_venue_menu": 2,
            "pp_materialization_protocol_sha256": (
                self.pp_materialization_protocol_sha256
            ),
            "catalog_freeze_ready": False,
            "unresolved_blockers": list(self.unresolved_blockers),
            "source_checkpoint_identity_public": False,
            "candidate_feature_values_public": False,
            "candidate_menus_frozen": 0,
            "outcomes_opened": 0,
            "model_updates": 0,
            "controller_actions": 0,
            "teacher_queries": 0,
            "sealed_test_cases_opened": 0,
            "crystal_cases_opened": 0,
            "authority_promoted": False,
            "private_path_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class PartyDevelopmentQuestionReservationRefresh:
    """One zero-execution replacement of an unsafe prospective source.

    The first reservation plan was frozen before the live preparation contract
    had a source-readiness check. Refreshing is permitted only while every
    candidate, outcome, controller, teacher, model and protected-access counter
    is still zero. Direct questions and the semantic assignment of every
    scenario remain unchanged; only an unsafe, unexecuted PP source may move to
    another open root in the same partition.
    """

    previous_plan_sha256: str
    plan: PartyDevelopmentQuestionReservationPlan
    retained_reservation_count: int
    replaced_pp_preparation_count: int
    previous_venue_prior_registry_sha256: str
    previous_venue_prior_count: int
    venue_prior_entries_added: int

    def __post_init__(self) -> None:
        for value, subject in (
            (self.previous_plan_sha256, "previous plan"),
            (
                self.previous_venue_prior_registry_sha256,
                "previous venue registry",
            ),
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise PartyDevelopmentQuestionReservationError(
                    f"party question refresh {subject} digest is invalid"
                )
        counts = (
            self.retained_reservation_count,
            self.replaced_pp_preparation_count,
            self.previous_venue_prior_count,
            self.venue_prior_entries_added,
        )
        if any(type(value) is not int or value < 0 for value in counts):  # noqa: E721
            raise PartyDevelopmentQuestionReservationError(
                "party question refresh counts are invalid"
            )
        if not isinstance(self.plan, PartyDevelopmentQuestionReservationPlan):
            raise PartyDevelopmentQuestionReservationError(
                "party question refresh plan is invalid"
            )
        if (
            self.retained_reservation_count
            + self.replaced_pp_preparation_count
            != len(self.plan.reservations)
            or self.replaced_pp_preparation_count != 1
            or self.retained_reservation_count
            != len(self.plan.reservations) - 1
            or self.venue_prior_entries_added != 1
            or self.plan.venue_prior_count
            != self.previous_venue_prior_count + self.venue_prior_entries_added
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question refresh accounting is incomplete"
            )

    def public_summary(self) -> dict[str, object]:
        """Return the exact path-free boundary of the refreshed private plan."""

        return {
            "schema": PARTY_DEVELOPMENT_QUESTION_RESERVATION_REFRESH_SCHEMA,
            "status": "unsafe_unexecuted_sources_retired_before_materialization",
            "previous_plan_sha256": self.previous_plan_sha256,
            "current_plan": self.plan.public_summary(),
            "previous_venue_prior_registry_sha256": (
                self.previous_venue_prior_registry_sha256
            ),
            "previous_venue_prior_count": self.previous_venue_prior_count,
            "venue_prior_entries_added": self.venue_prior_entries_added,
            "retained_reservation_count": self.retained_reservation_count,
            "replaced_pp_preparation_count": (
                self.replaced_pp_preparation_count
            ),
            "replacement_reason_counts": {
                "preexisting_status_or_non_high_health": (
                    self.replaced_pp_preparation_count
                )
            },
            "scenario_semantics_changed": 0,
            "direct_question_sources_changed": 0,
            "previous_plan_materializations": 0,
            "previous_plan_candidate_menus_frozen": 0,
            "previous_plan_outcomes_opened": 0,
            "rom_reads": 0,
            "emulator_starts": 0,
            "controller_actions": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "model_updates": 0,
            "sealed_test_cases_opened": 0,
            "crystal_cases_opened": 0,
            "authority_promoted": False,
            "source_checkpoint_identity_public": False,
            "candidate_feature_values_public": False,
            "private_path_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class _ReservationTemplate:
    kind: TrainingChoiceKind
    goal: PartyDevelopmentGoal
    preparation: PartyDevelopmentContextPreparation


def pp_materialization_source_ready(
    entry: PartyDevelopmentInventoryEntry,
) -> bool:
    """Whether a source can enter the no-heal, zero-faint PP preparation.

    This is deliberately stricter than ordinary question eligibility. Damaged
    and status-bearing states are useful learner contexts, but they are unsafe
    *sources* for a preparation whose only intended party changes are natural
    battle damage, experience and PP consumption. Requiring every member to be
    healthy, high-HP and high-PP prevents the materializer from laundering a
    pre-existing abort condition into a successful output.
    """

    if not isinstance(entry, PartyDevelopmentInventoryEntry):
        raise TypeError("entry must be a PartyDevelopmentInventoryEntry")
    return (
        entry.controls_ready
        and not entry.battle_active
        and sum(member.trainable for member in entry.members) >= 2
        and all(
            not member.status_present
            and member.hp_bin == "high"
            and member.pp_bin == "high"
            for member in entry.members
        )
    )


def _pp_materialization_source_health_only_unsafe(
    entry: PartyDevelopmentInventoryEntry,
) -> bool:
    """Whether health/status is the sole reason an old PP source is unsafe."""

    return (
        entry.controls_ready
        and not entry.battle_active
        and sum(member.trainable for member in entry.members) >= 2
        and all(member.pp_bin == "high" for member in entry.members)
        and any(
            member.status_present or member.hp_bin != "high"
            for member in entry.members
        )
    )


def reserve_party_development_questions(
    inventory: PartyDevelopmentCheckpointInventory,
    *,
    teacher_prior: PartyDevelopmentTeacherPrior,
    venue_prior_registry: PartyDevelopmentVenuePriorRegistry,
    policy: PartyDevelopmentReadinessPolicy = (
        DEFAULT_PARTY_DEVELOPMENT_READINESS_POLICY
    ),
) -> PartyDevelopmentQuestionReservationPlan:
    """Deterministically reserve diverse, prior-independent 8+6 source roots."""

    if not isinstance(inventory, PartyDevelopmentCheckpointInventory):
        raise TypeError("inventory must be a PartyDevelopmentCheckpointInventory")
    if not isinstance(teacher_prior, PartyDevelopmentTeacherPrior):
        raise TypeError("teacher_prior must be a PartyDevelopmentTeacherPrior")
    if not isinstance(venue_prior_registry, PartyDevelopmentVenuePriorRegistry):
        raise TypeError(
            "venue_prior_registry must be a PartyDevelopmentVenuePriorRegistry"
        )
    if not isinstance(policy, PartyDevelopmentReadinessPolicy):
        raise TypeError("policy must be a PartyDevelopmentReadinessPolicy")

    venue_roots = {
        root
        for evidence in venue_prior_registry.entries
        for root in evidence.support_root_lineage_ids
    }
    venue_states = {
        state
        for evidence in venue_prior_registry.entries
        for state in evidence.support_state_sha256
    }
    excluded_roots = tuple(
        sorted(teacher_prior.consumed_root_lineage_ids | venue_roots)
    )
    excluded_states = tuple(
        sorted(teacher_prior.consumed_state_sha256 | venue_states)
    )
    reservations = []
    for partition, count in (
        (ScenarioPartition.TRAIN, policy.minimum_train_examples),
        (ScenarioPartition.DEVELOPMENT, policy.minimum_development_examples),
    ):
        eligible = tuple(
            item
            for item in inventory.entries
            if item.partition is partition
            and item.controls_ready
            and not item.battle_active
            and sum(member.trainable for member in item.members)
            >= policy.minimum_candidate_count_observed
            and item.checkpoint_id not in set(excluded_roots)
            and item.state_sha256 not in set(excluded_states)
        )
        templates = _reservation_templates(count)
        selected = _select_entries(eligible, templates=templates)
        for index, (entry, template) in enumerate(
            zip(selected, templates, strict=True), start=1
        ):
            reservations.append(
                _reservation_from_entry(
                    entry,
                    template=template,
                    scenario_id=(
                        f"party-development-{partition.value}-{index:02d}"
                    ),
                )
            )
    return PartyDevelopmentQuestionReservationPlan(
        inventory_sha256=inventory.inventory_sha256,
        teacher_prior_sha256=canonical_sha256(teacher_prior.to_dict()),
        venue_prior_registry_sha256=venue_prior_registry.registry_sha256,
        venue_prior_count=len(venue_prior_registry.entries),
        excluded_root_lineage_ids=excluded_roots,
        excluded_state_sha256=excluded_states,
        reservations=tuple(sorted(reservations, key=lambda item: item.scenario_id)),
        policy=policy,
    )


def refresh_party_development_question_reservations(
    inventory: PartyDevelopmentCheckpointInventory,
    *,
    teacher_prior: PartyDevelopmentTeacherPrior,
    previous_plan: PartyDevelopmentQuestionReservationPlan,
    previous_venue_prior_registry: PartyDevelopmentVenuePriorRegistry,
    venue_prior_registry: PartyDevelopmentVenuePriorRegistry,
) -> PartyDevelopmentQuestionReservationRefresh:
    """Refresh the zero-execution plan after one prior and source-safety change.

    The operation is intentionally not a general reselection API. It accepts
    only an append-only venue registry, preserves every scenario's goal/kind/
    partition/preparation assignment, preserves every direct source, and moves
    a PP source only when the old inventory row violates the new no-heal source
    readiness predicate. Any other difference fails closed.
    """

    for value, expected, subject in (
        (inventory, PartyDevelopmentCheckpointInventory, "inventory"),
        (teacher_prior, PartyDevelopmentTeacherPrior, "teacher prior"),
        (
            previous_plan,
            PartyDevelopmentQuestionReservationPlan,
            "previous plan",
        ),
        (
            previous_venue_prior_registry,
            PartyDevelopmentVenuePriorRegistry,
            "previous venue registry",
        ),
        (
            venue_prior_registry,
            PartyDevelopmentVenuePriorRegistry,
            "venue registry",
        ),
    ):
        if not isinstance(value, expected):
            raise TypeError(f"{subject} has the wrong type")

    if (
        previous_plan.inventory_sha256 != inventory.inventory_sha256
        or previous_plan.teacher_prior_sha256
        != canonical_sha256(teacher_prior.to_dict())
        or previous_plan.venue_prior_registry_sha256
        != previous_venue_prior_registry.registry_sha256
        or previous_plan.venue_prior_count
        != len(previous_venue_prior_registry.entries)
    ):
        raise PartyDevelopmentQuestionReservationError(
            "previous party question plan does not bind the refresh inputs"
        )

    previous_evidence = {
        item.evidence_sha256: item for item in previous_venue_prior_registry.entries
    }
    current_evidence = {
        item.evidence_sha256: item for item in venue_prior_registry.entries
    }
    added_evidence = set(current_evidence) - set(previous_evidence)
    if (
        not set(previous_evidence) < set(current_evidence)
        or any(
            current_evidence[digest] != evidence
            for digest, evidence in previous_evidence.items()
        )
        or len(added_evidence) != 1
    ):
        raise PartyDevelopmentQuestionReservationError(
            "party question refresh requires exactly one append-only venue prior"
        )

    plan = reserve_party_development_questions(
        inventory,
        teacher_prior=teacher_prior,
        venue_prior_registry=venue_prior_registry,
        policy=previous_plan.policy,
    )
    previous_by_scenario = {
        item.scenario_id: item for item in previous_plan.reservations
    }
    current_by_scenario = {item.scenario_id: item for item in plan.reservations}
    if set(previous_by_scenario) != set(current_by_scenario):
        raise PartyDevelopmentQuestionReservationError(
            "party question refresh changed the scenario set"
        )
    inventory_by_checkpoint = {
        item.checkpoint_id: item for item in inventory.entries
    }
    retained = 0
    replaced = 0
    for scenario_id in sorted(previous_by_scenario):
        previous = previous_by_scenario[scenario_id]
        current = current_by_scenario[scenario_id]
        previous_contract = (
            previous.scenario_id,
            previous.partition,
            previous.kind,
            previous.goal,
            previous.preparation,
            previous.target_pp_bin,
        )
        current_contract = (
            current.scenario_id,
            current.partition,
            current.kind,
            current.goal,
            current.preparation,
            current.target_pp_bin,
        )
        if previous_contract != current_contract:
            raise PartyDevelopmentQuestionReservationError(
                "party question refresh changed scenario semantics"
            )
        try:
            previous_entry = inventory_by_checkpoint[
                previous.source_checkpoint_id
            ]
            current_entry = inventory_by_checkpoint[current.source_checkpoint_id]
        except KeyError as error:
            raise PartyDevelopmentQuestionReservationError(
                "party question refresh source is absent from the inventory"
            ) from error
        for reservation, entry in (
            (previous, previous_entry),
            (current, current_entry),
        ):
            if (
                reservation.source_state_sha256 != entry.state_sha256
                or reservation.source_envelope_sha256 != entry.envelope_sha256
                or reservation.source_semantic_signature_sha256
                != entry.semantic_signature_sha256
            ):
                raise PartyDevelopmentQuestionReservationError(
                    "party question refresh source differs from the inventory"
                )
        if previous.source_checkpoint_id == current.source_checkpoint_id:
            retained += 1
            if (
                current.preparation
                is PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
                and not pp_materialization_source_ready(current_entry)
            ):
                raise PartyDevelopmentQuestionReservationError(
                    "party question refresh retained an unsafe PP source"
                )
            continue
        if (
            current.preparation
            is not PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
        ):
            raise PartyDevelopmentQuestionReservationError(
                "party question refresh changed a direct question source"
            )
        if pp_materialization_source_ready(previous_entry):
            raise PartyDevelopmentQuestionReservationError(
                "party question refresh replaced a safe PP source"
            )
        if not _pp_materialization_source_health_only_unsafe(previous_entry):
            raise PartyDevelopmentQuestionReservationError(
                "party question refresh cannot attribute the retired source to health"
            )
        if not pp_materialization_source_ready(current_entry):
            raise PartyDevelopmentQuestionReservationError(
                "party question refresh selected an unsafe PP source"
            )
        replaced += 1

    return PartyDevelopmentQuestionReservationRefresh(
        previous_plan_sha256=previous_plan.plan_sha256,
        plan=plan,
        retained_reservation_count=retained,
        replaced_pp_preparation_count=replaced,
        previous_venue_prior_registry_sha256=(
            previous_venue_prior_registry.registry_sha256
        ),
        previous_venue_prior_count=len(previous_venue_prior_registry.entries),
        venue_prior_entries_added=len(added_evidence),
    )


def _reservation_templates(count: int) -> tuple[_ReservationTemplate, ...]:
    goals = tuple(PartyDevelopmentGoal)
    kinds = tuple(TrainingChoiceKind)
    return tuple(
        _ReservationTemplate(
            kind=kinds[index % len(kinds)],
            goal=goals[index % len(goals)],
            preparation=(
                PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
                if index == count - 1
                else PartyDevelopmentContextPreparation.NONE
            ),
        )
        for index in range(count)
    )


def _select_entries(
    entries: tuple[PartyDevelopmentInventoryEntry, ...],
    *,
    templates: tuple[_ReservationTemplate, ...],
) -> tuple[PartyDevelopmentInventoryEntry, ...]:
    selected: list[PartyDevelopmentInventoryEntry] = []
    seen_hp: set[str] = set()
    seen_routes: set[EvolutionRouteKind] = set()
    seen_semantics: set[str] = set()
    for template in templates:
        candidates = tuple(
            item
            for item in entries
            if item not in selected
            and template.goal in item.goal_hints
            and (
                template.preparation
                is not PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
                or pp_materialization_source_ready(item)
            )
        )
        if not candidates:
            raise PartyDevelopmentQuestionReservationError(
                "checkpoint inventory cannot satisfy the question templates"
            )

        def priority(item: PartyDevelopmentInventoryEntry) -> tuple[int, ...]:
            hp = {member.hp_bin for member in item.members}
            routes = {
                route for member in item.members for route in member.evolution_routes
            }
            return (
                len(hp - seen_hp),
                len(routes - seen_routes),
                int(item.semantic_signature_sha256 not in seen_semantics),
                sum(member.trainable for member in item.members),
                len(item.goal_hints),
            )

        best_priority = max(priority(item) for item in candidates)
        selected_entry = min(
            (item for item in candidates if priority(item) == best_priority),
            key=lambda item: item.checkpoint_id,
        )
        selected.append(selected_entry)
        seen_hp.update(member.hp_bin for member in selected_entry.members)
        seen_routes.update(
            route
            for member in selected_entry.members
            for route in member.evolution_routes
        )
        seen_semantics.add(selected_entry.semantic_signature_sha256)
    return tuple(selected)


def _reservation_from_entry(
    entry: PartyDevelopmentInventoryEntry,
    *,
    template: _ReservationTemplate,
    scenario_id: str,
) -> PartyDevelopmentQuestionReservation:
    return PartyDevelopmentQuestionReservation(
        scenario_id=scenario_id,
        source_checkpoint_id=entry.checkpoint_id,
        source_state_sha256=entry.state_sha256,
        source_envelope_sha256=entry.envelope_sha256,
        source_semantic_signature_sha256=entry.semantic_signature_sha256,
        partition=entry.partition,
        kind=template.kind,
        goal=template.goal,
        preparation=template.preparation,
        target_pp_bin=(
            "middle"
            if template.preparation
            is PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
            else None
        ),
        source_member_count=len(entry.members),
        source_trainable_count=sum(member.trainable for member in entry.members),
        source_hp_bins=tuple(
            item for item in _PP_BINS if item in {member.hp_bin for member in entry.members}
        ),
        source_pp_bins=tuple(
            item for item in _PP_BINS if item in {member.pp_bin for member in entry.members}
        ),
        source_evolution_route_kinds=tuple(
            item
            for item in EvolutionRouteKind
            if item
            in {
                route
                for member in entry.members
                for route in member.evolution_routes
            }
        ),
    )


__all__ = [
    "PARTY_DEVELOPMENT_QUESTION_RESERVATION_PLAN_SCHEMA",
    "PARTY_DEVELOPMENT_QUESTION_RESERVATION_REFRESH_SCHEMA",
    "PARTY_DEVELOPMENT_QUESTION_RESERVATION_SCHEMA",
    "PARTY_DEVELOPMENT_QUESTION_RESERVATION_SUMMARY_SCHEMA",
    "PP_CONTEXT_MATERIALIZATION_PROTOCOL",
    "PP_CONTEXT_MATERIALIZATION_PROTOCOL_SHA256",
    "PartyDevelopmentContextPreparation",
    "PartyDevelopmentQuestionReservation",
    "PartyDevelopmentQuestionReservationError",
    "PartyDevelopmentQuestionReservationPlan",
    "PartyDevelopmentQuestionReservationRefresh",
    "pp_materialization_source_ready",
    "refresh_party_development_question_reservations",
    "reserve_party_development_questions",
]
