"""Prospective powered curriculum contract for living-Pokedex option learning.

The first authentic Red causal row proved that a randomly selected option can
cross the crash-safe journal and become a selected-arm outcome.  It did not
provide enough information to fit or evaluate the 24-feature, nine-head option
value model.  This module separates that integration fact from the next two
experiments:

* a block-randomized Red training curriculum with enough settled, diverse
  selected-arm rows to fit the inspectable outcome model; and
* an untouched, same-reset paired policy comparison against a preregistered
  envelope of random, cost-only, and myopic-greedy controls.

Everything in this module is action-free.  It contains no ROM, state, route,
species, map, private path, behavior draw, prediction, outcome, model fit, or
execution authority.  Title adapters supply private capacity rows later; only
aggregate counts and the title-neutral statistical contract are public.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from pokemon_red_completion.evaluation_design import (
    PairedExactDesign,
    paired_one_sided_exact_power_with_forced_losses,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_FEATURE_NAMES,
    LIVING_DEX_OPTION_OUTCOME_NAMES,
    LivingDexOptionContext,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
)
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_CAUSAL_CURRICULUM_DESIGN_SCHEMA = "pokemon.core.living-dex-causal-curriculum-design.v1"
LIVING_DEX_CAUSAL_CAPACITY_SCHEMA = "pokemon.core.living-dex-causal-curriculum-capacity.v1"
LIVING_DEX_CAUSAL_TRAINING_BEHAVIOR = "blocked-random-permutation-full-support-uniform-marginal-v1"
LIVING_DEX_CAUSAL_EVALUATION_ENDPOINT = (
    "same-reset-realized-success-versus-best-of-three-baseline-envelope-v1"
)
RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK = 16
RED_SETUP_POLICY_STRUCTURALLY_ZERO_FEATURES = (
    "kind.trade",
    "resource_cost",
    "irreversibility_risk",
    "uncertainty",
    "resource_pressure_x_resource_cost",
    "knowledge_pressure_x_uncertainty",
)
RED_SETUP_POLICY_LINEAR_DEPENDENCIES = (
    "completion_gain_is_a_linear_combination_of_red_kind_indicators",
    "dependency_unlock_gain_is_a_linear_combination_of_red_kind_indicators",
)

LivingDexCausalPartition = Literal["train", "development"]

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PARTITIONS = frozenset({"train", "development"})

# Red can exercise seven portable collection intents directly.  Trade remains
# in the shared schema and is an explicit Crystal-shaped transfer falsifier;
# manufacturing a Red trade row would be title-specific label fiction.
RED_DIRECT_CAUSAL_OPTION_KINDS = tuple(
    kind for kind in LivingDexOptionKind if kind is not LivingDexOptionKind.TRADE
)

_RED_PROSPECTIVE_SELECTED_KIND_COUNTS: Mapping[LivingDexOptionKind, int] = {
    LivingDexOptionKind.ACQUIRE: 12,
    LivingDexOptionKind.EVOLVE: 12,
    LivingDexOptionKind.DEVELOP: 12,
    LivingDexOptionKind.MANAGE_STORAGE: 15,
    LivingDexOptionKind.RESUPPLY: 12,
    LivingDexOptionKind.UNLOCK_ACCESS: 12,
    LivingDexOptionKind.EXPLORE: 15,
}
_RED_SETUP_COMPLETION_PRIOR: Mapping[LivingDexOptionKind, float] = {
    LivingDexOptionKind.ACQUIRE: 1.0,
    LivingDexOptionKind.EVOLVE: 1.0,
}
_RED_SETUP_DEPENDENCY_PRIOR: Mapping[LivingDexOptionKind, float] = {
    LivingDexOptionKind.UNLOCK_ACCESS: 1.0,
    LivingDexOptionKind.EXPLORE: 0.5,
    LivingDexOptionKind.DEVELOP: 0.25,
    LivingDexOptionKind.MANAGE_STORAGE: 0.25,
    LivingDexOptionKind.RESUPPLY: 0.25,
}


class LivingDexCausalCurriculumError(ValueError):
    """A proposed causal curriculum weakens power, independence, or transfer."""


def red_setup_policy_feature_row_supported(
    features: LivingDexOptionFeatures,
) -> bool:
    """Whether a feature row lies on the frozen reachable Red projection."""

    if not isinstance(features, LivingDexOptionFeatures):
        return False
    features.__post_init__()
    return bool(
        features.kind in RED_DIRECT_CAUSAL_OPTION_KINDS
        and features.completion_gain == _RED_SETUP_COMPLETION_PRIOR.get(features.kind, 0.0)
        and features.dependency_unlock_gain == _RED_SETUP_DEPENDENCY_PRIOR.get(features.kind, 0.0)
        and features.resource_cost == 0.0
        and features.irreversibility_risk == 0.0
        and features.uncertainty == 0.0
        and (features.kind is LivingDexOptionKind.ACQUIRE or features.storage_cost == 0.0)
    )


@dataclass(frozen=True, slots=True)
class LivingDexCausalCurriculumDesign:
    """Frozen sample, baseline, and stop-rule design before private access."""

    prospective_train_contexts: int = 90
    minimum_settled_train_examples: int = 60
    minimum_settled_train_examples_per_kind: int = 8
    prospective_development_contexts: int = 105
    minimum_complete_development_pairs: int = 102
    minimum_development_contexts_per_focus_kind: int = 15
    minimum_distinct_train_feature_rows: int = 50
    minimum_train_feature_rank: int = RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK
    minimum_successful_train_examples: int = 8
    minimum_unsuccessful_train_examples: int = 8
    minimum_variable_outcome_heads: int = 5
    minimum_variable_outcome_range: float = 0.10
    minimum_train_semantic_families: int = 18
    minimum_development_semantic_families: int = 12
    train_menu_templates: int = 10
    train_contexts_per_menu_template: int = 9
    minimum_development_menu_templates: int = 5
    minimum_train_locations: int = 5
    minimum_development_locations: int = 5
    minimum_train_pressure_values_per_axis: int = 3
    minimum_development_pressure_values_per_axis: int = 2
    existing_development_rigor_prefix_examples: int = 1
    paired_design: PairedExactDesign = field(
        default_factory=lambda: PairedExactDesign(
            independent_contexts=105,
            alpha=0.05,
            smallest_useful_win_probability=0.30,
            smallest_useful_loss_probability=0.10,
            target_power=0.80,
        )
    )

    def __post_init__(self) -> None:
        positive = (
            self.prospective_train_contexts,
            self.minimum_settled_train_examples,
            self.minimum_settled_train_examples_per_kind,
            self.prospective_development_contexts,
            self.minimum_complete_development_pairs,
            self.minimum_development_contexts_per_focus_kind,
            self.minimum_distinct_train_feature_rows,
            self.minimum_train_feature_rank,
            self.minimum_successful_train_examples,
            self.minimum_unsuccessful_train_examples,
            self.minimum_variable_outcome_heads,
            self.minimum_train_semantic_families,
            self.minimum_development_semantic_families,
            self.train_menu_templates,
            self.train_contexts_per_menu_template,
            self.minimum_development_menu_templates,
            self.minimum_train_locations,
            self.minimum_development_locations,
            self.minimum_train_pressure_values_per_axis,
            self.minimum_development_pressure_values_per_axis,
        )
        if any(type(value) is not int or value <= 0 for value in positive):  # noqa: E721
            raise LivingDexCausalCurriculumError(
                "causal curriculum thresholds must be positive integers"
            )
        if (
            type(self.existing_development_rigor_prefix_examples) is not int  # noqa: E721
            or self.existing_development_rigor_prefix_examples != 1
        ):
            raise LivingDexCausalCurriculumError(
                "causal curriculum must retain the one authentic prefix row"
            )
        if (
            isinstance(self.minimum_variable_outcome_range, bool)
            or not isinstance(self.minimum_variable_outcome_range, (int, float))
            or not 0.0 < float(self.minimum_variable_outcome_range) <= 1.0
        ):
            raise LivingDexCausalCurriculumError(
                "causal curriculum outcome-variation range differs"
            )
        object.__setattr__(
            self,
            "minimum_variable_outcome_range",
            float(self.minimum_variable_outcome_range),
        )
        if not isinstance(self.paired_design, PairedExactDesign):
            raise TypeError("causal curriculum needs an exact paired design")
        self.paired_design.__post_init__()
        if (
            self.prospective_train_contexts != 90
            or sum(_RED_PROSPECTIVE_SELECTED_KIND_COUNTS.values())
            != self.prospective_train_contexts
            or self.minimum_settled_train_examples < 2 * 25
            or self.minimum_distinct_train_feature_rows > self.minimum_settled_train_examples
            or self.minimum_train_feature_rank != RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK
            or self.minimum_successful_train_examples + self.minimum_unsuccessful_train_examples
            > self.minimum_settled_train_examples
            or self.minimum_variable_outcome_heads > len(LIVING_DEX_OPTION_OUTCOME_NAMES)
            or self.train_menu_templates * self.train_contexts_per_menu_template
            != self.prospective_train_contexts
            or self.prospective_development_contexts != self.paired_design.independent_contexts
            or self.minimum_complete_development_pairs < self.paired_design.minimum_contexts
            or self.minimum_complete_development_pairs > self.prospective_development_contexts
            or self.minimum_development_contexts_per_focus_kind
            * len(RED_DIRECT_CAUSAL_OPTION_KINDS)
            != self.prospective_development_contexts
            or not self.paired_design.adequately_powered
            or self.worst_case_censoring_power + 1e-15
            < self.paired_design.target_power
        ):
            raise LivingDexCausalCurriculumError(
                "causal curriculum no longer separates fit capacity from powered evaluation"
            )
        if set(_RED_PROSPECTIVE_SELECTED_KIND_COUNTS) != set(RED_DIRECT_CAUSAL_OPTION_KINDS) or min(
            _RED_PROSPECTIVE_SELECTED_KIND_COUNTS.values()
        ) < (self.minimum_settled_train_examples_per_kind):
            raise LivingDexCausalCurriculumError(
                "causal curriculum no longer covers every directly executable kind"
            )

    @property
    def maximum_censored_development_contexts(self) -> int:
        return self.prospective_development_contexts - self.minimum_complete_development_pairs

    @property
    def worst_case_censoring_power(self) -> float:
        """Power when every allowed incomplete context is scored as a loss."""

        return paired_one_sided_exact_power_with_forced_losses(
            self.prospective_development_contexts,
            forced_losses=self.maximum_censored_development_contexts,
            win_probability=self.paired_design.smallest_useful_win_probability,
            loss_probability=self.paired_design.smallest_useful_loss_probability,
            alpha=self.paired_design.alpha,
        )

    @property
    def prospective_selected_kind_counts(self) -> dict[str, int]:
        return {
            kind.value: _RED_PROSPECTIVE_SELECTED_KIND_COUNTS[kind]
            for kind in RED_DIRECT_CAUSAL_OPTION_KINDS
        }

    @property
    def design_sha256(self) -> str:
        return canonical_sha256(self.public_dict(include_digest=False))

    def public_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        document: dict[str, object] = {
            "authorization": {
                "crystal_execution": False,
                "full_game_replay": False,
                "model_fit": False,
                "private_context_access": False,
                "red_gameplay": False,
                "sealed_red": False,
            },
            "evaluation": {
                "absolute_candidate_success_floor": 0.50,
                "baseline_envelope": [
                    "frozen_random",
                    "cost_only",
                    "myopic_completion_greedy",
                ],
                "baseline_envelope_rule": (
                    "baseline_success_if_any_preregistered_control_succeeds_and_"
                    "every_incomplete_context_is_a_candidate_loss"
                ),
                "candidate_and_controls_receive_same_identity_free_menu": True,
                "complete_pairs_required": self.minimum_complete_development_pairs,
                "contexts_per_focus_kind": (self.minimum_development_contexts_per_focus_kind),
                "minimum_menu_templates": self.minimum_development_menu_templates,
                "endpoint": LIVING_DEX_CAUSAL_EVALUATION_ENDPOINT,
                "maximum_censored_contexts": (self.maximum_censored_development_contexts),
                "incomplete_context_inference_rule": (
                    "score_every_incomplete_context_as_a_candidate_loss_never_drop_it"
                ),
                "model_choice_committed_before_branch_outcomes": True,
                "paired_design": self.paired_design.public_dict(),
                "power_after_maximum_worst_case_censoring": (
                    self.worst_case_censoring_power
                ),
                "power_after_maximum_worst_case_censoring_passed": (
                    self.worst_case_censoring_power + 1e-15
                    >= self.paired_design.target_power
                ),
                "policy_branches": 4,
                "primary_outcome": (
                    "independently_verified_success_with_incomplete_contexts_"
                    "scored_against_candidate"
                ),
                "same_reset_and_rng_for_every_branch": True,
                "training_targets_emitted": 0,
            },
            "feature_contract": {
                "feature_count": len(LIVING_DEX_OPTION_FEATURE_NAMES),
                "feature_names": list(LIVING_DEX_OPTION_FEATURE_NAMES),
                "minimum_distinct_train_feature_rows": (self.minimum_distinct_train_feature_rows),
                "minimum_train_feature_rank": self.minimum_train_feature_rank,
                "red_setup_policy_linear_dependencies": list(RED_SETUP_POLICY_LINEAR_DEPENDENCIES),
                "red_setup_policy_maximum_feature_rank": (RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK),
                "red_setup_policy_structurally_zero_features": list(
                    RED_SETUP_POLICY_STRUCTURALLY_ZERO_FEATURES
                ),
                "rank_requirement_role": (
                    "full_reachable_red_projection_not_full_cross_title_schema"
                ),
                "outcome_head_count": len(LIVING_DEX_OPTION_OUTCOME_NAMES),
                "outcome_names": list(LIVING_DEX_OPTION_OUTCOME_NAMES),
                "portable_option_kinds": [kind.value for kind in LivingDexOptionKind],
                "red_direct_option_kinds": [kind.value for kind in RED_DIRECT_CAUSAL_OPTION_KINDS],
                "red_trade_rows_fabricated": 0,
                "transfer_falsifiers": [
                    "trade",
                    "time_dependent_availability",
                    "breeding_recoverability",
                    "held_item_state",
                ],
            },
            "independence": {
                "byte_clone_or_local_rng_perturbation_inherits_parent_lineage": True,
                "development_parent_lineages_unique": True,
                "development_contexts": self.prospective_development_contexts,
                "family_overlap_between_partitions": 0,
                "independence_unit": (
                    "prospectively_assigned_harness_episode_lineage_not_state_digest"
                ),
                "lineage_overlap_between_partitions": 0,
                "location_overlap_between_partitions": 0,
                "physical_root_overlap": 0,
                "root_expansion_cannot_mint_independence_by_rehashing_a_clone": True,
                "same_reset_branch_isolation_required": True,
                "train_contexts": self.prospective_train_contexts,
            },
            "integration_floor": {
                "development_examples": 4,
                "grants_authority": False,
                "purpose": "plumbing_shapes_and_censoring_only",
                "train_examples": 8,
            },
            "pressure_variation": {
                "axes": [
                    "collection_pressure",
                    "dependency_pressure",
                    "access_pressure",
                    "resource_pressure",
                    "storage_pressure",
                    "party_pressure",
                    "knowledge_pressure",
                ],
                "minimum_development_values_per_axis": (
                    self.minimum_development_pressure_values_per_axis
                ),
                "minimum_train_values_per_axis": (self.minimum_train_pressure_values_per_axis),
                "physical_location_count_is_not_a_pressure_proxy": True,
            },
            "transfer_authority": {
                "crystal_adaptation_required_for_trade_authority": True,
                "red_unseen_kinds_receive_zero_kind_coefficient": ["trade"],
                "red_unseen_mechanics_are_abstention_falsifiers": [
                    "trade",
                    "time_dependent_availability",
                    "breeding_recoverability",
                    "held_item_state",
                ],
                "zero_shot_crystal_claim_scope": ("shared_supported_kinds_only_before_adaptation"),
            },
            "schema": LIVING_DEX_CAUSAL_CURRICULUM_DESIGN_SCHEMA,
            "status": "design_only_capacity_unproven",
            "stop_conditions": [
                "insufficient_independent_context_capacity",
                "insufficient_abstract_pressure_variation",
                "partition_family_location_or_lineage_overlap",
                "outcome_dependent_row_selection",
                "teacher_choice_or_fallback",
                "unexecuted_action_target",
                "unpowered_policy_claim",
            ],
            "training": {
                "behavior_policy": LIVING_DEX_CAUSAL_TRAINING_BEHAVIOR,
                "candidate_index_counts": {"0": 30, "1": 30, "2": 30},
                "existing_development_rigor_prefix_examples": (
                    self.existing_development_rigor_prefix_examples
                ),
                "existing_prefix_counts_toward_prospective_thresholds": False,
                "contexts_per_menu_template": (self.train_contexts_per_menu_template),
                "menu_template_count": self.train_menu_templates,
                "minimum_locations": self.minimum_train_locations,
                "minimum_semantic_families": self.minimum_train_semantic_families,
                "minimum_settled_examples": self.minimum_settled_train_examples,
                "minimum_settled_examples_per_kind": (self.minimum_settled_train_examples_per_kind),
                "minimum_successful_examples": (self.minimum_successful_train_examples),
                "minimum_unsuccessful_examples": (self.minimum_unsuccessful_train_examples),
                "minimum_variable_outcome_heads": (self.minimum_variable_outcome_heads),
                "minimum_variable_outcome_range": (self.minimum_variable_outcome_range),
                "prospective_contexts": self.prospective_train_contexts,
                "prospective_selected_kind_counts": (self.prospective_selected_kind_counts),
                "selected_arm_targets_only": True,
                "teacher_queries": 0,
                "unselected_action_targets": 0,
            },
        }
        if include_digest:
            document["design_sha256"] = self.design_sha256
        return document


@dataclass(frozen=True, slots=True)
class LivingDexCausalCapacityContext:
    """One private action-free context considered by the capacity gate."""

    context_identity_sha256: str
    physical_root_sha256: str
    independence_lineage_sha256: str
    family_scope_sha256: str
    location_scope_sha256: str
    template_scope_sha256: str
    menu_shape_sha256: str
    semantic_family_sha256s: tuple[str, ...]
    partition: LivingDexCausalPartition
    option_kinds: tuple[LivingDexOptionKind, ...]
    focus_kind: LivingDexOptionKind
    option_context: LivingDexOptionContext
    assigned_candidate_index: int | None
    root_available: bool
    same_reset_policy_forks_feasible: bool

    def __post_init__(self) -> None:
        for value, subject in (
            (self.context_identity_sha256, "capacity context"),
            (self.physical_root_sha256, "capacity physical root"),
            (self.independence_lineage_sha256, "capacity lineage"),
            (self.family_scope_sha256, "capacity family scope"),
            (self.location_scope_sha256, "capacity location scope"),
            (self.template_scope_sha256, "capacity template scope"),
            (self.menu_shape_sha256, "capacity menu shape"),
        ):
            _require_sha256(value, subject=subject)
        if self.partition not in _PARTITIONS:
            raise LivingDexCausalCurriculumError("capacity partition differs")
        if (
            not isinstance(self.option_kinds, tuple)
            or len(self.option_kinds) != 3
            or len(set(self.option_kinds)) != len(self.option_kinds)
            or any(kind not in RED_DIRECT_CAUSAL_OPTION_KINDS for kind in self.option_kinds)
        ):
            raise LivingDexCausalCurriculumError(
                "capacity context needs three distinct directly executable kinds"
            )
        if (
            not isinstance(self.semantic_family_sha256s, tuple)
            or len(self.semantic_family_sha256s) != len(self.option_kinds)
            or len(set(self.semantic_family_sha256s)) != len(self.semantic_family_sha256s)
        ):
            raise LivingDexCausalCurriculumError(
                "capacity context needs one distinct semantic family per option"
            )
        for value in self.semantic_family_sha256s:
            _require_sha256(value, subject="capacity semantic family")
        if not isinstance(self.focus_kind, LivingDexOptionKind) or (
            self.focus_kind not in self.option_kinds
        ):
            raise LivingDexCausalCurriculumError("capacity focus kind is absent from its menu")
        if not isinstance(self.option_context, LivingDexOptionContext):
            raise TypeError("capacity context needs title-neutral pressures")
        self.option_context.__post_init__()
        if self.partition == "train":
            if (
                type(self.assigned_candidate_index) is not int  # noqa: E721
                or not 0 <= self.assigned_candidate_index < len(self.option_kinds)
                or self.option_kinds[self.assigned_candidate_index] is not self.focus_kind
            ):
                raise LivingDexCausalCurriculumError(
                    "train capacity needs a prospectively assigned focus arm"
                )
        elif self.assigned_candidate_index is not None:
            raise LivingDexCausalCurriculumError(
                "development capacity cannot contain a model or control choice"
            )
        if (
            type(self.root_available) is not bool
            or type(  # noqa: E721
                self.same_reset_policy_forks_feasible
            )
            is not bool
        ):  # noqa: E721
            raise TypeError("capacity availability and fork feasibility must be booleans")

    @property
    def pressure_vector(self) -> tuple[float, ...]:
        return tuple(
            float(getattr(self.option_context, name))
            for name in (
                "collection_pressure",
                "dependency_pressure",
                "access_pressure",
                "resource_pressure",
                "storage_pressure",
                "party_pressure",
                "knowledge_pressure",
            )
        )


@dataclass(frozen=True, slots=True)
class LivingDexCausalCapacityAudit:
    """Path-free proof or falsification of the prospective sample design."""

    design_sha256: str
    contexts_observed: int
    available_contexts: int
    train_contexts: int
    development_contexts: int
    distinct_physical_roots: int
    distinct_independence_lineages: int
    train_semantic_families: int
    development_semantic_families: int
    train_locations: int
    development_locations: int
    train_menu_templates: int
    development_menu_templates: int
    train_template_context_counts: tuple[int, ...]
    train_template_candidate_schedules_balanced: int
    train_focus_kind_counts: tuple[tuple[str, int], ...]
    development_focus_kind_counts: tuple[tuple[str, int], ...]
    train_pressure_value_counts: tuple[int, ...]
    development_pressure_value_counts: tuple[int, ...]
    family_overlap: int
    location_overlap: int
    lineage_overlap: int
    root_overlap: int
    duplicate_context_identities: int
    train_candidate_index_counts: tuple[tuple[str, int], ...]
    development_same_reset_fork_contexts: int
    reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.reasons

    def public_dict(self) -> dict[str, object]:
        return {
            "available_contexts": self.available_contexts,
            "contexts_observed": self.contexts_observed,
            "design_sha256": self.design_sha256,
            "development_contexts": self.development_contexts,
            "development_focus_kind_counts": dict(self.development_focus_kind_counts),
            "development_locations": self.development_locations,
            "development_menu_templates": self.development_menu_templates,
            "development_pressure_value_counts": list(self.development_pressure_value_counts),
            "development_same_reset_fork_contexts": (self.development_same_reset_fork_contexts),
            "development_semantic_families": (self.development_semantic_families),
            "distinct_independence_lineages": (self.distinct_independence_lineages),
            "distinct_physical_roots": self.distinct_physical_roots,
            "duplicate_context_identities": self.duplicate_context_identities,
            "family_overlap": self.family_overlap,
            "lineage_overlap": self.lineage_overlap,
            "location_overlap": self.location_overlap,
            "model_fits": 0,
            "model_predictions": 0,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "ready": self.ready,
            "reasons": list(self.reasons),
            "red_gameplay_executions": 0,
            "root_claims": 0,
            "root_overlap": self.root_overlap,
            "schema": LIVING_DEX_CAUSAL_CAPACITY_SCHEMA,
            "teacher_queries": 0,
            "train_candidate_index_counts": dict(self.train_candidate_index_counts),
            "train_contexts": self.train_contexts,
            "train_focus_kind_counts": dict(self.train_focus_kind_counts),
            "train_locations": self.train_locations,
            "train_menu_templates": self.train_menu_templates,
            "train_template_candidate_schedules_balanced": (
                self.train_template_candidate_schedules_balanced
            ),
            "train_template_context_counts": list(self.train_template_context_counts),
            "train_pressure_value_counts": list(self.train_pressure_value_counts),
            "train_semantic_families": self.train_semantic_families,
        }


def audit_living_dex_causal_capacity(
    contexts: Iterable[LivingDexCausalCapacityContext],
    *,
    design: LivingDexCausalCurriculumDesign | None = None,
) -> LivingDexCausalCapacityAudit:
    """Audit private capacity while returning only aggregate path-free facts."""

    active_design = LivingDexCausalCurriculumDesign() if design is None else design
    if not isinstance(active_design, LivingDexCausalCurriculumDesign):
        raise TypeError("causal capacity needs a curriculum design")
    active_design.__post_init__()
    rows = tuple(contexts)
    if any(not isinstance(row, LivingDexCausalCapacityContext) for row in rows):
        raise TypeError("causal capacity rows differ")
    for row in rows:
        row.__post_init__()
    available = tuple(row for row in rows if row.root_available)
    train = tuple(row for row in available if row.partition == "train")
    development = tuple(row for row in available if row.partition == "development")

    train_families = {family for row in train for family in row.semantic_family_sha256s}
    development_families = {family for row in development for family in row.semantic_family_sha256s}
    train_locations = {row.location_scope_sha256 for row in train}
    development_locations = {row.location_scope_sha256 for row in development}
    train_templates = Counter(row.template_scope_sha256 for row in train)
    development_templates = Counter(row.template_scope_sha256 for row in development)
    train_lineages = {row.independence_lineage_sha256 for row in train}
    development_lineages = {row.independence_lineage_sha256 for row in development}
    train_roots = {row.physical_root_sha256 for row in train}
    development_roots = {row.physical_root_sha256 for row in development}
    context_ids = tuple(row.context_identity_sha256 for row in available)
    train_kind_counts = Counter(row.focus_kind.value for row in train)
    development_kind_counts = Counter(row.focus_kind.value for row in development)
    candidate_counts = Counter(
        str(row.assigned_candidate_index)
        for row in train
        if row.assigned_candidate_index is not None
    )
    train_pressure_counts = _pressure_value_counts(train)
    development_pressure_counts = _pressure_value_counts(development)
    balanced_train_templates = sum(
        Counter(
            row.assigned_candidate_index for row in train if row.template_scope_sha256 == template
        )
        == Counter({0: 3, 1: 3, 2: 3})
        for template in train_templates
    )

    reasons: list[str] = []
    if len(train) < active_design.prospective_train_contexts:
        reasons.append("insufficient_train_contexts")
    if len(development) < active_design.prospective_development_contexts:
        reasons.append("insufficient_development_contexts")
    if len(context_ids) != len(set(context_ids)):
        reasons.append("duplicate_context_identity")
    if len(available) != len({row.physical_root_sha256 for row in available}):
        reasons.append("duplicate_physical_root")
    if len(available) != len({row.independence_lineage_sha256 for row in available}):
        reasons.append("duplicate_independence_lineage")
    if train_families & development_families:
        reasons.append("family_partition_overlap")
    if train_locations & development_locations:
        reasons.append("location_partition_overlap")
    if train_lineages & development_lineages:
        reasons.append("lineage_partition_overlap")
    if train_roots & development_roots:
        reasons.append("root_partition_overlap")
    if len(train_families) < active_design.minimum_train_semantic_families:
        reasons.append("insufficient_train_semantic_families")
    if len(development_families) < active_design.minimum_development_semantic_families:
        reasons.append("insufficient_development_semantic_families")
    if len(train_locations) < active_design.minimum_train_locations:
        reasons.append("insufficient_train_locations")
    if len(development_locations) < active_design.minimum_development_locations:
        reasons.append("insufficient_development_locations")
    if len(train_templates) != active_design.train_menu_templates or any(
        count != active_design.train_contexts_per_menu_template
        for count in train_templates.values()
    ):
        reasons.append("train_menu_template_schedule_differs")
    if balanced_train_templates != active_design.train_menu_templates:
        reasons.append("train_template_candidate_schedule_differs")
    if len(development_templates) < active_design.minimum_development_menu_templates:
        reasons.append("insufficient_development_menu_templates")
    if any(
        train_kind_counts[kind.value] < _RED_PROSPECTIVE_SELECTED_KIND_COUNTS[kind]
        for kind in RED_DIRECT_CAUSAL_OPTION_KINDS
    ):
        reasons.append("insufficient_train_kind_schedule")
    if any(
        development_kind_counts[kind.value]
        < active_design.minimum_development_contexts_per_focus_kind
        for kind in RED_DIRECT_CAUSAL_OPTION_KINDS
    ):
        reasons.append("insufficient_development_kind_schedule")
    if any(candidate_counts[str(index)] < 30 for index in range(3)):
        reasons.append("train_candidate_position_imbalance")
    if any(
        count < active_design.minimum_train_pressure_values_per_axis
        for count in train_pressure_counts
    ):
        reasons.append("insufficient_train_pressure_variation")
    if any(
        count < active_design.minimum_development_pressure_values_per_axis
        for count in development_pressure_counts
    ):
        reasons.append("insufficient_development_pressure_variation")
    fork_contexts = sum(row.same_reset_policy_forks_feasible for row in development)
    if fork_contexts < active_design.prospective_development_contexts:
        reasons.append("insufficient_same_reset_policy_fork_capacity")

    return LivingDexCausalCapacityAudit(
        design_sha256=active_design.design_sha256,
        contexts_observed=len(rows),
        available_contexts=len(available),
        train_contexts=len(train),
        development_contexts=len(development),
        distinct_physical_roots=len({row.physical_root_sha256 for row in available}),
        distinct_independence_lineages=len({row.independence_lineage_sha256 for row in available}),
        train_semantic_families=len(train_families),
        development_semantic_families=len(development_families),
        train_locations=len(train_locations),
        development_locations=len(development_locations),
        train_menu_templates=len(train_templates),
        development_menu_templates=len(development_templates),
        train_template_context_counts=tuple(sorted(train_templates.values())),
        train_template_candidate_schedules_balanced=balanced_train_templates,
        train_focus_kind_counts=_counter_rows(train_kind_counts),
        development_focus_kind_counts=_counter_rows(development_kind_counts),
        train_pressure_value_counts=train_pressure_counts,
        development_pressure_value_counts=development_pressure_counts,
        family_overlap=len(train_families & development_families),
        location_overlap=len(train_locations & development_locations),
        lineage_overlap=len(train_lineages & development_lineages),
        root_overlap=len(train_roots & development_roots),
        duplicate_context_identities=len(context_ids) - len(set(context_ids)),
        train_candidate_index_counts=_counter_rows(candidate_counts),
        development_same_reset_fork_contexts=fork_contexts,
        reasons=tuple(sorted(set(reasons))),
    )


def canonical_living_dex_causal_curriculum_bytes() -> bytes:
    """Return stable public design bytes; no private capacity is included."""

    import json

    return (
        json.dumps(
            LivingDexCausalCurriculumDesign().public_dict(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _pressure_value_counts(
    rows: tuple[LivingDexCausalCapacityContext, ...],
) -> tuple[int, ...]:
    if not rows:
        return (0,) * 7
    return tuple(len({row.pressure_vector[index] for row in rows}) for index in range(7))


def _counter_rows(counter: Counter[str]) -> tuple[tuple[str, int], ...]:
    return tuple((key, counter[key]) for key in sorted(counter))


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise LivingDexCausalCurriculumError(f"{subject} SHA-256 differs")
    return value


__all__ = [
    "LIVING_DEX_CAUSAL_CAPACITY_SCHEMA",
    "LIVING_DEX_CAUSAL_CURRICULUM_DESIGN_SCHEMA",
    "LIVING_DEX_CAUSAL_EVALUATION_ENDPOINT",
    "LIVING_DEX_CAUSAL_TRAINING_BEHAVIOR",
    "RED_DIRECT_CAUSAL_OPTION_KINDS",
    "RED_SETUP_POLICY_LINEAR_DEPENDENCIES",
    "RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK",
    "RED_SETUP_POLICY_STRUCTURALLY_ZERO_FEATURES",
    "LivingDexCausalCapacityAudit",
    "LivingDexCausalCapacityContext",
    "LivingDexCausalCurriculumDesign",
    "LivingDexCausalCurriculumError",
    "LivingDexCausalPartition",
    "audit_living_dex_causal_capacity",
    "canonical_living_dex_causal_curriculum_bytes",
    "red_setup_policy_feature_row_supported",
]
