"""Action-free powered V2 design for clustered living-Pokedex learning.

The existing Red corpus contains authentic selected-arm consequences, but its
rows are not permission to count descendants of one upstream episode as
independent experiments.  This module freezes the public design rules for the
next curriculum before any new private inventory, behavior draw, outcome,
model fit, or development result is opened.

Training may amortize setup with at most two scenarios per lineage.  Each
lineage receives equal total fit weight and correlated siblings cannot satisfy
the held-out power claim.  Development is deliberately stricter: exactly one
confirmatory question per untouched lineage.  This makes the independent unit
visible and prevents an assumed intracluster correlation from manufacturing
sample size.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from pokemon_red_completion.evaluation_design import (
    minimum_paired_contexts,
    minimum_paired_contexts_with_forced_losses,
    paired_one_sided_exact_power_with_forced_losses,
)
from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_DIRECT_CAUSAL_OPTION_KINDS,
    RED_SETUP_POLICY_LINEAR_DEPENDENCIES,
    RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK,
    RED_SETUP_POLICY_STRUCTURALLY_ZERO_FEATURES,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_FEATURE_NAMES,
    LIVING_DEX_OPTION_OUTCOME_NAMES,
    LivingDexOptionKind,
)
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_CLUSTERED_POWERED_DESIGN_SCHEMA = (
    "pokemon.core.living-dex-clustered-powered-design.v2"
)
LIVING_DEX_CLUSTERED_POWERED_ENDPOINT = (
    "one-confirmatory-question-per-lineage-versus-frozen-control-envelope-v2"
)

_HISTORICAL_SELECTED_KIND_COUNTS = (
    (LivingDexOptionKind.ACQUIRE, 1),
    (LivingDexOptionKind.EVOLVE, 5),
    (LivingDexOptionKind.DEVELOP, 3),
    (LivingDexOptionKind.MANAGE_STORAGE, 3),
    (LivingDexOptionKind.RESUPPLY, 2),
    (LivingDexOptionKind.UNLOCK_ACCESS, 1),
    (LivingDexOptionKind.EXPLORE, 3),
)
_TARGET_TOTAL_SELECTED_KIND_COUNTS = (
    (LivingDexOptionKind.ACQUIRE, 12),
    (LivingDexOptionKind.EVOLVE, 12),
    (LivingDexOptionKind.DEVELOP, 12),
    (LivingDexOptionKind.MANAGE_STORAGE, 15),
    (LivingDexOptionKind.RESUPPLY, 12),
    (LivingDexOptionKind.UNLOCK_ACCESS, 12),
    (LivingDexOptionKind.EXPLORE, 15),
)
_PROSPECTIVE_SELECTED_KIND_COUNTS = tuple(
    (kind, target - dict(_HISTORICAL_SELECTED_KIND_COUNTS)[kind])
    for kind, target in _TARGET_TOTAL_SELECTED_KIND_COUNTS
)

_HISTORICAL_CANDIDATE_POSITION_COUNTS = ((0, 6), (1, 8), (2, 4))
_TARGET_TOTAL_CANDIDATE_POSITION_COUNTS = ((0, 30), (1, 30), (2, 30))
_PROSPECTIVE_CANDIDATE_POSITION_COUNTS = tuple(
    (position, target - dict(_HISTORICAL_CANDIDATE_POSITION_COUNTS)[position])
    for position, target in _TARGET_TOTAL_CANDIDATE_POSITION_COUNTS
)

_DEVELOPMENT_FOCUS_KIND_COUNTS = (
    (LivingDexOptionKind.ACQUIRE, 15),
    (LivingDexOptionKind.EVOLVE, 15),
    (LivingDexOptionKind.DEVELOP, 14),
    (LivingDexOptionKind.MANAGE_STORAGE, 14),
    (LivingDexOptionKind.RESUPPLY, 14),
    (LivingDexOptionKind.UNLOCK_ACCESS, 14),
    (LivingDexOptionKind.EXPLORE, 14),
)
_DEVELOPMENT_FOCUS_POSITION_COUNTS = ((0, 34), (1, 33), (2, 33))

_CORRELATION_SENSITIVITY_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)
_FROZEN_CONTROLS = (
    "frozen_random",
    "cost_only",
    "myopic_completion_greedy",
)
_CRYSTAL_CAPABILITY_VOCABULARY = (
    "breeding_and_egg_workflow",
    "gender_constraints",
    "happiness_and_friendship_evolution",
    "held_item_acquire_equip_and_consume_workflow",
    "phone_contacts_and_calls",
    "renewable_berry_state",
    "roaming_legendaries",
    "time_of_day_and_day_of_week",
    "trade_and_trade_evolution",
    "weekly_and_calendar_events",
)


class LivingDexClusteredPoweredDesignError(ValueError):
    """The powered design weakened independence, information, or transfer."""


@dataclass(frozen=True, slots=True)
class LivingDexClusteredPoweredDesign:
    """Finite public design whose private capacity remains to be established."""

    historical_attempts: int = 25
    historical_settled_examples: int = 18
    historical_setup_only_attempts: int = 7
    historical_distinct_settled_lineages: int = 18

    prospective_train_attempts: int = 72
    prospective_train_lineages: int = 36
    maximum_train_attempts_per_lineage: int = 2
    minimum_total_settled_train_examples: int = 60
    minimum_distinct_settled_train_lineages: int = 50
    minimum_settled_train_examples_per_kind: int = 8
    minimum_distinct_selected_feature_rows: int = 50
    minimum_selected_feature_rank: int = RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK
    minimum_successful_train_examples: int = 8
    minimum_unsuccessful_train_examples: int = 8
    minimum_variable_outcome_heads: int = 5
    minimum_variable_outcome_range: float = 0.10
    minimum_available_candidates_per_question: int = 3
    minimum_train_semantic_families: int = 18
    minimum_development_semantic_families: int = 12
    minimum_train_menu_templates: int = 10
    minimum_development_menu_templates: int = 5
    minimum_train_locations: int = 5
    minimum_development_locations: int = 5
    minimum_train_pressure_values_per_axis: int = 3
    minimum_development_pressure_values_per_axis: int = 2
    minimum_development_questions_per_supported_kind: int = 14

    development_lineages: int = 100
    confirmatory_questions_per_development_lineage: int = 1
    maximum_forced_development_losses: int = 3
    contingency_lineages: int = 3
    alpha: float = 0.05
    smallest_useful_win_probability: float = 0.30
    smallest_useful_loss_probability: float = 0.10
    target_power: float = 0.80
    maximum_model_candidates: int = 1

    historical_selected_kind_counts: tuple[
        tuple[LivingDexOptionKind, int], ...
    ] = _HISTORICAL_SELECTED_KIND_COUNTS
    target_total_selected_kind_counts: tuple[
        tuple[LivingDexOptionKind, int], ...
    ] = _TARGET_TOTAL_SELECTED_KIND_COUNTS
    prospective_selected_kind_counts: tuple[
        tuple[LivingDexOptionKind, int], ...
    ] = _PROSPECTIVE_SELECTED_KIND_COUNTS
    historical_candidate_position_counts: tuple[tuple[int, int], ...] = (
        _HISTORICAL_CANDIDATE_POSITION_COUNTS
    )
    target_total_candidate_position_counts: tuple[tuple[int, int], ...] = (
        _TARGET_TOTAL_CANDIDATE_POSITION_COUNTS
    )
    prospective_candidate_position_counts: tuple[tuple[int, int], ...] = (
        _PROSPECTIVE_CANDIDATE_POSITION_COUNTS
    )
    development_focus_kind_counts: tuple[
        tuple[LivingDexOptionKind, int], ...
    ] = _DEVELOPMENT_FOCUS_KIND_COUNTS
    development_focus_position_counts: tuple[tuple[int, int], ...] = (
        _DEVELOPMENT_FOCUS_POSITION_COUNTS
    )
    correlation_sensitivity_grid: tuple[float, ...] = (
        _CORRELATION_SENSITIVITY_GRID
    )
    frozen_controls: tuple[str, ...] = _FROZEN_CONTROLS
    crystal_capability_vocabulary: tuple[str, ...] = (
        _CRYSTAL_CAPABILITY_VOCABULARY
    )

    def __post_init__(self) -> None:
        for integer_value, subject in (
            (self.historical_attempts, "historical attempts"),
            (self.historical_settled_examples, "historical settled examples"),
            (self.historical_setup_only_attempts, "historical setup-only attempts"),
            (
                self.historical_distinct_settled_lineages,
                "historical distinct settled lineages",
            ),
            (self.prospective_train_attempts, "prospective train attempts"),
            (self.prospective_train_lineages, "prospective train lineages"),
            (
                self.maximum_train_attempts_per_lineage,
                "maximum train attempts per lineage",
            ),
            (
                self.minimum_total_settled_train_examples,
                "minimum total settled train examples",
            ),
            (
                self.minimum_distinct_settled_train_lineages,
                "minimum distinct settled train lineages",
            ),
            (
                self.minimum_settled_train_examples_per_kind,
                "minimum settled examples per kind",
            ),
            (
                self.minimum_distinct_selected_feature_rows,
                "minimum distinct selected feature rows",
            ),
            (self.minimum_selected_feature_rank, "minimum selected feature rank"),
            (
                self.minimum_successful_train_examples,
                "minimum successful train examples",
            ),
            (
                self.minimum_unsuccessful_train_examples,
                "minimum unsuccessful train examples",
            ),
            (self.minimum_variable_outcome_heads, "minimum variable outcome heads"),
            (
                self.minimum_available_candidates_per_question,
                "minimum available candidates per question",
            ),
            (self.minimum_train_semantic_families, "minimum train semantic families"),
            (
                self.minimum_development_semantic_families,
                "minimum development semantic families",
            ),
            (self.minimum_train_menu_templates, "minimum train menu templates"),
            (
                self.minimum_development_menu_templates,
                "minimum development menu templates",
            ),
            (self.minimum_train_locations, "minimum train locations"),
            (self.minimum_development_locations, "minimum development locations"),
            (
                self.minimum_train_pressure_values_per_axis,
                "minimum train pressure values per axis",
            ),
            (
                self.minimum_development_pressure_values_per_axis,
                "minimum development pressure values per axis",
            ),
            (
                self.minimum_development_questions_per_supported_kind,
                "minimum development questions per supported kind",
            ),
            (self.development_lineages, "development lineages"),
            (
                self.confirmatory_questions_per_development_lineage,
                "confirmatory questions per development lineage",
            ),
            (
                self.maximum_forced_development_losses,
                "maximum forced development losses",
            ),
            (self.contingency_lineages, "contingency lineages"),
            (self.maximum_model_candidates, "maximum model candidates"),
        ):
            if type(integer_value) is not int or integer_value <= 0:  # noqa: E721
                raise LivingDexClusteredPoweredDesignError(
                    f"{subject} must be a positive integer"
                )
        for numeric_value, subject in (
            (self.alpha, "alpha"),
            (self.smallest_useful_win_probability, "smallest useful win probability"),
            (
                self.smallest_useful_loss_probability,
                "smallest useful loss probability",
            ),
            (self.target_power, "target power"),
            (self.minimum_variable_outcome_range, "minimum variable outcome range"),
        ):
            if (
                isinstance(numeric_value, bool)
                or not isinstance(numeric_value, (int, float))
                or not math.isfinite(float(numeric_value))
                or not 0.0 < float(numeric_value) < 1.0
            ):
                raise LivingDexClusteredPoweredDesignError(
                    f"{subject} must be strictly between zero and one"
                )

        if (
            self.historical_attempts
            != self.historical_settled_examples
            + self.historical_setup_only_attempts
            or self.historical_settled_examples != 18
            or self.historical_distinct_settled_lineages
            != self.historical_settled_examples
        ):
            raise LivingDexClusteredPoweredDesignError(
                "historical immutable prefix differs"
            )
        self._validate_count_schedule()

        if (
            self.prospective_train_attempts
            > self.prospective_train_lineages
            * self.maximum_train_attempts_per_lineage
            or self.maximum_train_attempts_per_lineage > 2
            or self.minimum_total_settled_train_examples < 60
            or self.minimum_distinct_settled_train_lineages < 50
            or self.minimum_distinct_settled_train_lineages
            > self.historical_distinct_settled_lineages
            + self.prospective_train_lineages
            or self.minimum_settled_train_examples_per_kind < 8
            or self.minimum_distinct_selected_feature_rows < 50
            or self.minimum_distinct_selected_feature_rows
            > self.minimum_total_settled_train_examples
            or self.minimum_selected_feature_rank
            != RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK
            or self.minimum_successful_train_examples < 8
            or self.minimum_unsuccessful_train_examples < 8
            or self.minimum_variable_outcome_heads < 5
            or self.minimum_variable_outcome_range < 0.10
            or self.minimum_available_candidates_per_question != 3
            or self.minimum_train_semantic_families < 18
            or self.minimum_development_semantic_families < 12
            or self.minimum_train_menu_templates < 10
            or self.minimum_development_menu_templates < 5
            or self.minimum_train_locations < 5
            or self.minimum_development_locations < 5
            or self.minimum_train_pressure_values_per_axis < 3
            or self.minimum_development_pressure_values_per_axis < 2
            or self.minimum_development_questions_per_supported_kind < 14
        ):
            raise LivingDexClusteredPoweredDesignError(
                "training information or lineage influence gate weakened"
            )

        if (
            self.confirmatory_questions_per_development_lineage != 1
            or self.maximum_forced_development_losses != self.contingency_lineages
            or self.development_lineages != self.k_min_with_forced_losses
            or self.development_lineages - 1 >= self.k_min_with_forced_losses
            or self.worst_case_development_power + 1e-15 < self.target_power
            or self.previous_development_power + 1e-15 >= self.target_power
            or self.maximum_model_candidates
            != self.development_lineages // self.k_min_with_forced_losses
            or self.maximum_model_candidates != 1
        ):
            raise LivingDexClusteredPoweredDesignError(
                "development denominator or candidate cap is not least-case powered"
            )
        if self.correlation_sensitivity_grid != _CORRELATION_SENSITIVITY_GRID:
            raise LivingDexClusteredPoweredDesignError(
                "correlation sensitivity grid differs"
            )
        if self.frozen_controls != _FROZEN_CONTROLS:
            raise LivingDexClusteredPoweredDesignError("frozen controls differ")
        if (
            self.crystal_capability_vocabulary != _CRYSTAL_CAPABILITY_VOCABULARY
            or len(set(self.crystal_capability_vocabulary))
            != len(self.crystal_capability_vocabulary)
        ):
            raise LivingDexClusteredPoweredDesignError(
                "Crystal capability vocabulary differs"
            )

    def _validate_count_schedule(self) -> None:
        expected_kinds = set(RED_DIRECT_CAUSAL_OPTION_KINDS)
        schedules = (
            self.historical_selected_kind_counts,
            self.target_total_selected_kind_counts,
            self.prospective_selected_kind_counts,
        )
        for kind_schedule in schedules:
            if (
                not isinstance(kind_schedule, tuple)
                or {kind for kind, _ in kind_schedule} != expected_kinds
                or len(kind_schedule) != len(expected_kinds)
                or any(
                    not isinstance(kind, LivingDexOptionKind)
                    or type(count) is not int  # noqa: E721
                    or count <= 0
                    for kind, count in kind_schedule
                )
            ):
                raise LivingDexClusteredPoweredDesignError(
                    "selected-kind schedule differs"
                )
        historical = dict(self.historical_selected_kind_counts)
        target = dict(self.target_total_selected_kind_counts)
        prospective = dict(self.prospective_selected_kind_counts)
        if (
            self.historical_selected_kind_counts
            != _HISTORICAL_SELECTED_KIND_COUNTS
            or self.target_total_selected_kind_counts
            != _TARGET_TOTAL_SELECTED_KIND_COUNTS
            or any(target[kind] != historical[kind] + prospective[kind] for kind in expected_kinds)
            or sum(historical.values()) != self.historical_settled_examples
            or sum(target.values()) != 90
            or sum(prospective.values()) != self.prospective_train_attempts
        ):
            raise LivingDexClusteredPoweredDesignError(
                "selected-kind totals do not preserve the immutable prefix"
            )

        position_schedules = (
            self.historical_candidate_position_counts,
            self.target_total_candidate_position_counts,
            self.prospective_candidate_position_counts,
        )
        for position_schedule in position_schedules:
            if (
                not isinstance(position_schedule, tuple)
                or tuple(position for position, _ in position_schedule) != (0, 1, 2)
                or any(type(count) is not int or count <= 0 for _, count in position_schedule)  # noqa: E721
            ):
                raise LivingDexClusteredPoweredDesignError(
                    "candidate-position schedule differs"
                )
        historical_positions = dict(self.historical_candidate_position_counts)
        target_positions = dict(self.target_total_candidate_position_counts)
        prospective_positions = dict(self.prospective_candidate_position_counts)
        if (
            self.historical_candidate_position_counts
            != _HISTORICAL_CANDIDATE_POSITION_COUNTS
            or self.target_total_candidate_position_counts
            != _TARGET_TOTAL_CANDIDATE_POSITION_COUNTS
            or any(
                target_positions[position]
                != historical_positions[position] + prospective_positions[position]
                for position in (0, 1, 2)
            )
            or sum(prospective_positions.values()) != self.prospective_train_attempts
        ):
            raise LivingDexClusteredPoweredDesignError(
                "candidate-position totals do not preserve the immutable prefix"
            )

        if (
            not isinstance(self.development_focus_kind_counts, tuple)
            or len(self.development_focus_kind_counts) != len(expected_kinds)
            or any(
                not isinstance(kind, LivingDexOptionKind)
                or type(count) is not int  # noqa: E721
                or count <= 0
                for kind, count in self.development_focus_kind_counts
            )
        ):
            raise LivingDexClusteredPoweredDesignError(
                "development focus-kind schedule differs"
            )
        development_kind_counts = dict(self.development_focus_kind_counts)
        if (
            self.development_focus_kind_counts != _DEVELOPMENT_FOCUS_KIND_COUNTS
            or set(development_kind_counts) != expected_kinds
            or sum(development_kind_counts.values()) != self.development_lineages
            or min(development_kind_counts.values())
            < self.minimum_development_questions_per_supported_kind
        ):
            raise LivingDexClusteredPoweredDesignError(
                "development focus-kind schedule differs"
            )
        if (
            not isinstance(self.development_focus_position_counts, tuple)
            or tuple(
                position for position, _ in self.development_focus_position_counts
            )
            != (0, 1, 2)
            or any(
                type(count) is not int or count <= 0  # noqa: E721
                for _, count in self.development_focus_position_counts
            )
            or self.development_focus_position_counts
            != _DEVELOPMENT_FOCUS_POSITION_COUNTS
            or sum(
                count for _, count in self.development_focus_position_counts
            )
            != self.development_lineages
        ):
            raise LivingDexClusteredPoweredDesignError(
                "development focus-position schedule differs"
            )

    @property
    def maximum_prospective_setup_only_attempts(self) -> int:
        return self.prospective_train_attempts - (
            self.minimum_total_settled_train_examples
            - self.historical_settled_examples
        )

    @property
    def k_min_without_forced_losses(self) -> int:
        return minimum_paired_contexts(
            win_probability=self.smallest_useful_win_probability,
            loss_probability=self.smallest_useful_loss_probability,
            alpha=self.alpha,
            target_power=self.target_power,
        )

    @property
    def k_min_with_forced_losses(self) -> int:
        return minimum_paired_contexts_with_forced_losses(
            forced_losses=self.maximum_forced_development_losses,
            win_probability=self.smallest_useful_win_probability,
            loss_probability=self.smallest_useful_loss_probability,
            alpha=self.alpha,
            target_power=self.target_power,
        )

    @property
    def worst_case_development_power(self) -> float:
        return paired_one_sided_exact_power_with_forced_losses(
            self.development_lineages,
            forced_losses=self.maximum_forced_development_losses,
            win_probability=self.smallest_useful_win_probability,
            loss_probability=self.smallest_useful_loss_probability,
            alpha=self.alpha,
        )

    @property
    def previous_development_power(self) -> float:
        return paired_one_sided_exact_power_with_forced_losses(
            self.development_lineages - 1,
            forced_losses=self.maximum_forced_development_losses,
            win_probability=self.smallest_useful_win_probability,
            loss_probability=self.smallest_useful_loss_probability,
            alpha=self.alpha,
        )

    @property
    def required_new_lineage_supply(self) -> int:
        return (
            self.prospective_train_lineages
            + self.development_lineages
            + self.contingency_lineages
        )

    @property
    def correlation_sensitivity(self) -> list[dict[str, object]]:
        points: list[dict[str, object]] = []
        for rho in self.correlation_sensitivity_grid:
            design_effect = 1.0 + (
                self.confirmatory_questions_per_development_lineage - 1
            ) * rho
            effective_lineages = self.development_lineages / design_effect
            exact_lineages = int(effective_lineages)
            if effective_lineages != exact_lineages:
                raise LivingDexClusteredPoweredDesignError(
                    "correlation sensitivity does not yield an exact lineage count"
                )
            points.append(
                {
                    "assumed_intracluster_correlation": rho,
                    "confirmatory_questions_per_lineage": (
                        self.confirmatory_questions_per_development_lineage
                    ),
                    "design_effect": design_effect,
                    "effective_independent_lineages": exact_lineages,
                    "worst_case_power": (
                        paired_one_sided_exact_power_with_forced_losses(
                            exact_lineages,
                            forced_losses=self.maximum_forced_development_losses,
                            win_probability=self.smallest_useful_win_probability,
                            loss_probability=self.smallest_useful_loss_probability,
                            alpha=self.alpha,
                        )
                    ),
                }
            )
        return points

    @property
    def design_sha256(self) -> str:
        return canonical_sha256(self.public_dict(include_digest=False))

    def public_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        document: dict[str, object] = {
            "authorization": {
                "crystal_execution": False,
                "development_outcome_access": False,
                "full_game_replay": False,
                "model_fit": False,
                "private_capacity_access": False,
                "private_schedule_freeze": False,
                "red_gameplay": False,
                "sealed_red": False,
                "teacher_access": False,
            },
            "capacity": {
                "allocation_must_precede_outcomes": True,
                "candidate_count_cap": self.maximum_model_candidates,
                "candidate_count_cap_formula": "floor(development_lineages/k_min)",
                "contingency_lineages": self.contingency_lineages,
                "contingency_use_rule": (
                    "replace_only_a_pre_branch_unread_invalid_lineage_before_any_"
                    "prediction_or_outcome_never_replace_a_claimed_or_incomplete_endpoint"
                ),
                "development_lineages": self.development_lineages,
                "exhaustion_rule": (
                    "close_the_lane_if_action_free_private_capacity_cannot_supply_"
                    "the_frozen_train_development_and_contingency_allocations"
                ),
                "private_capacity_proven": False,
                "prospective_train_lineages": self.prospective_train_lineages,
                "required_new_lineage_supply": self.required_new_lineage_supply,
            },
            "evaluation": {
                "absolute_candidate_success_floor": 0.50,
                "alpha": self.alpha,
                "baseline_envelope": list(self.frozen_controls),
                "candidate_and_controls_receive_same_identity_free_question": True,
                "confirmatory_questions_per_lineage": (
                    self.confirmatory_questions_per_development_lineage
                ),
                "correlation_sensitivity": self.correlation_sensitivity,
                "development_lineages": self.development_lineages,
                "focus_kind_schedule": {
                    kind.value: count
                    for kind, count in self.development_focus_kind_counts
                },
                "focus_position_schedule": {
                    str(position): count
                    for position, count in self.development_focus_position_counts
                },
                "minimum_available_candidates_per_question": (
                    self.minimum_available_candidates_per_question
                ),
                "minimum_locations": self.minimum_development_locations,
                "minimum_menu_templates": self.minimum_development_menu_templates,
                "minimum_pressure_values_per_axis": (
                    self.minimum_development_pressure_values_per_axis
                ),
                "minimum_semantic_families": (
                    self.minimum_development_semantic_families
                ),
                "development_receives_fit_weight": False,
                "endpoint": LIVING_DEX_CLUSTERED_POWERED_ENDPOINT,
                "incomplete_rule": "score_as_candidate_loss_never_drop",
                "incompletes_above_budget_rule": (
                    "declare_endpoint_underpowered_close_without_promotion"
                ),
                "k_min_with_forced_losses": self.k_min_with_forced_losses,
                "k_min_without_forced_losses": self.k_min_without_forced_losses,
                "maximum_forced_losses": self.maximum_forced_development_losses,
                "model_candidates_committed_before_any_development_branch": True,
                "previous_denominator_power": self.previous_development_power,
                "primary_unit": "authenticated_upstream_episode_lineage",
                "smallest_useful_effect": {
                    "loss_probability": self.smallest_useful_loss_probability,
                    "tie_probability": 1.0
                    - self.smallest_useful_win_probability
                    - self.smallest_useful_loss_probability,
                    "win_probability": self.smallest_useful_win_probability,
                },
                "target_power": self.target_power,
                "test": "one_sided_exact_sign_test_conditional_on_discordance",
                "policy_branches_per_question": 4,
                "same_reset_and_rng_for_every_branch": True,
                "within_lineage_siblings_count_toward_primary_endpoint": False,
                "worst_case_power": self.worst_case_development_power,
            },
            "historical_prefix": {
                "attempts": self.historical_attempts,
                "candidate_position_counts": dict(
                    (str(position), count)
                    for position, count in self.historical_candidate_position_counts
                ),
                "distinct_settled_lineages": (
                    self.historical_distinct_settled_lineages
                ),
                "selected_kind_counts": {
                    kind.value: count
                    for kind, count in self.historical_selected_kind_counts
                },
                "settled_examples": self.historical_settled_examples,
                "setup_only_attempts": self.historical_setup_only_attempts,
            },
            "feature_contract": {
                "all_candidate_feature_rows_must_be_supported": True,
                "feature_count": len(LIVING_DEX_OPTION_FEATURE_NAMES),
                "minimum_reachable_red_feature_rank": (
                    self.minimum_selected_feature_rank
                ),
                "outcome_head_count": len(LIVING_DEX_OPTION_OUTCOME_NAMES),
                "red_direct_option_kinds": [
                    kind.value for kind in RED_DIRECT_CAUSAL_OPTION_KINDS
                ],
                "red_setup_policy_linear_dependencies": list(
                    RED_SETUP_POLICY_LINEAR_DEPENDENCIES
                ),
                "red_setup_policy_structurally_zero_features": list(
                    RED_SETUP_POLICY_STRUCTURALLY_ZERO_FEATURES
                ),
                "red_trade_rows_fabricated": 0,
            },
            "mission": {
                "crystal_role": "first_transfer_falsifier",
                "product": (
                    "transferable_hierarchical_agent_for_story_and_living_"
                    "pokedex_completion"
                ),
                "red_role": "first_causal_curriculum_not_product",
            },
            "schema": LIVING_DEX_CLUSTERED_POWERED_DESIGN_SCHEMA,
            "status": "design_only_private_capacity_unproven",
            "training": {
                "admission": "all_claimed_selected_arm_outcomes_never_outcome_shopped",
                "behavior_policy": (
                    "blocked_random_permutation_full_support_uniform_marginal_v2"
                ),
                "candidate_position_schedule": {
                    "prospective": {
                        str(position): count
                        for position, count in self.prospective_candidate_position_counts
                    },
                    "target_total": {
                        str(position): count
                        for position, count in self.target_total_candidate_position_counts
                    },
                },
                "cluster_weighting": "equal_total_fit_weight_per_lineage",
                "information_floors": {
                    "distinct_selected_feature_rows": (
                        self.minimum_distinct_selected_feature_rows
                    ),
                    "distinct_settled_lineages": (
                        self.minimum_distinct_settled_train_lineages
                    ),
                    "feature_rank": self.minimum_selected_feature_rank,
                    "settled_examples": self.minimum_total_settled_train_examples,
                    "settled_examples_per_supported_kind": (
                        self.minimum_settled_train_examples_per_kind
                    ),
                    "successful_examples": self.minimum_successful_train_examples,
                    "unsuccessful_examples": self.minimum_unsuccessful_train_examples,
                    "variable_outcome_heads": self.minimum_variable_outcome_heads,
                    "variable_outcome_range": self.minimum_variable_outcome_range,
                },
                "maximum_attempts_per_lineage": (
                    self.maximum_train_attempts_per_lineage
                ),
                "maximum_prospective_setup_only_attempts": (
                    self.maximum_prospective_setup_only_attempts
                ),
                "minimum_available_candidates_per_question": (
                    self.minimum_available_candidates_per_question
                ),
                "minimum_locations": self.minimum_train_locations,
                "minimum_menu_templates": self.minimum_train_menu_templates,
                "minimum_pressure_values_per_axis": (
                    self.minimum_train_pressure_values_per_axis
                ),
                "minimum_semantic_families": self.minimum_train_semantic_families,
                "prospective_attempts": self.prospective_train_attempts,
                "prospective_lineages": self.prospective_train_lineages,
                "selected_kind_schedule": {
                    "prospective": {
                        kind.value: count
                        for kind, count in self.prospective_selected_kind_counts
                    },
                    "target_total": {
                        kind.value: count
                        for kind, count in self.target_total_selected_kind_counts
                    },
                },
                "teacher_actions_are_labels": False,
                "unselected_actions_are_targets": False,
                "upstream_lineage_cross_partition_overlap": 0,
            },
            "transfer_boundary": {
                "capability_vocabulary_required_before_classification": list(
                    self.crystal_capability_vocabulary
                ),
                "crystal_adaptation_is_separate_from_zero_shot": True,
                "crystal_supported_abstention_score": "failure",
                "crystal_supported_scope_requires": [
                    "frozen_red_model_beats_best_of_three_control_envelope",
                    "frozen_red_initialization_beats_zero_initialization",
                ],
                "prospectively_unsupported_mechanic_abstention": (
                    "correct_boundary_classification_not_completion_credit"
                ),
                "powered_transfer_plan_required_before_crystal_execution": True,
                "transfer_statistical_status": (
                    "unsized_execution_prohibited_until_separate_powered_plan"
                ),
                "red_unseen_kind_coefficients": {"trade": 0.0},
                "unsupported_mechanics_receive_gameplay_authority": False,
                "version_trade_event_catalog_scope": (
                    "complete_per_title_target_catalog_red_151_crystal_251_and_"
                    "future_declared_totals_with_solo_graph_as_a_subplan"
                ),
            },
        }
        if include_digest:
            document["design_sha256"] = canonical_sha256(document)
        return document


def canonical_living_dex_clustered_powered_design_bytes() -> bytes:
    """Return the path-free canonical design artifact."""

    return (
        json.dumps(
            LivingDexClusteredPoweredDesign().public_dict(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


__all__ = [
    "LIVING_DEX_CLUSTERED_POWERED_DESIGN_SCHEMA",
    "LIVING_DEX_CLUSTERED_POWERED_ENDPOINT",
    "LivingDexClusteredPoweredDesign",
    "LivingDexClusteredPoweredDesignError",
    "canonical_living_dex_clustered_powered_design_bytes",
]
