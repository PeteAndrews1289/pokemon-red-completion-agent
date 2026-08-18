"""Title-neutral contract for learning acquisition followed by replanning.

The curriculum is intentionally separate from execution.  It freezes a repeatable,
fixed-denominator experiment that can later collect causal goal-manager outcomes without
turning one successful Red capture into a claim of full-game or cross-title competence.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_development import GoalManagerDevelopmentResult
from pokemon_red_completion.provenance import canonical_sha256

ACQUISITION_REPLANNING_SCHEMA = (
    "pokemon.core.acquisition-replanning-curriculum.v1"
)
ACQUISITION_REPLANNING_ROOTS = 4
ACQUISITION_REPLANNING_TRIALS_PER_ROOT = 4
ACQUISITION_REPLANNING_EPISODES = (
    ACQUISITION_REPLANNING_ROOTS * ACQUISITION_REPLANNING_TRIALS_PER_ROOT
)
ACQUISITION_REPLANNING_MAX_DECISIONS = 2
ACQUISITION_REPLANNING_MIN_POST_CHOICES = 2
ACQUISITION_REPLANNING_MIN_ADMITTED_ACQUISITIONS = 4
ACQUISITION_REPLANNING_MIN_REPLANS = 4
ACQUISITION_REPLANNING_MIN_REPLAN_ROOTS = 3


class AcquisitionReplanningCurriculumError(ValueError):
    """Raised when a proposed curriculum weakens the frozen learning question."""


@dataclass(frozen=True, slots=True)
class AcquisitionReplanningInventory:
    """Path-free summary of the evidence available before curriculum execution."""

    acquisition_train_roots: int
    previously_used_roots: int
    unused_roots: int
    unused_roots_with_multiple_initial_choices: int
    authenticated_post_acquisition_captures: int
    prior_durable_post_acquisition_choice_count: int

    def __post_init__(self) -> None:
        values = (
            self.acquisition_train_roots,
            self.previously_used_roots,
            self.unused_roots,
            self.unused_roots_with_multiple_initial_choices,
            self.authenticated_post_acquisition_captures,
            self.prior_durable_post_acquisition_choice_count,
        )
        if any(type(value) is not int or value < 0 for value in values):  # noqa: E721
            raise AcquisitionReplanningCurriculumError(
                "curriculum inventory counts must be non-negative integers"
            )
        if self.previously_used_roots + self.unused_roots != self.acquisition_train_roots:
            raise AcquisitionReplanningCurriculumError(
                "curriculum inventory does not preserve the root denominator"
            )
        if self.unused_roots_with_multiple_initial_choices > self.unused_roots:
            raise AcquisitionReplanningCurriculumError(
                "curriculum initial-choice count exceeds unused roots"
            )
        if self.authenticated_post_acquisition_captures > self.unused_roots:
            raise AcquisitionReplanningCurriculumError(
                "curriculum post-acquisition captures exceed unused roots"
            )

    @property
    def existing_contexts_support_execution(self) -> bool:
        return (
            self.unused_roots >= ACQUISITION_REPLANNING_ROOTS
            and self.unused_roots_with_multiple_initial_choices
            >= ACQUISITION_REPLANNING_ROOTS
            and self.authenticated_post_acquisition_captures
            >= ACQUISITION_REPLANNING_ROOTS
            and self.prior_durable_post_acquisition_choice_count
            >= ACQUISITION_REPLANNING_MIN_POST_CHOICES
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.acquisition-replanning-inventory.v1",
            "status": (
                "existing_contexts_support_execution"
                if self.existing_contexts_support_execution
                else "existing_contexts_insufficient"
            ),
            "acquisition_train_roots": self.acquisition_train_roots,
            "previously_used_roots": self.previously_used_roots,
            "unused_roots": self.unused_roots,
            "unused_roots_with_multiple_initial_choices": (
                self.unused_roots_with_multiple_initial_choices
            ),
            "authenticated_post_acquisition_captures": (
                self.authenticated_post_acquisition_captures
            ),
            "prior_durable_post_acquisition_choice_count": (
                self.prior_durable_post_acquisition_choice_count
            ),
            "model_predictions": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "outcomes_added": 0,
        }


@dataclass(frozen=True, slots=True)
class AcquisitionReplanningEpisodeAssessment:
    """Strict, title-neutral eligibility result for one later collected episode."""

    qualifies: bool
    reasons: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.acquisition-replanning-episode-assessment.v1",
            "qualifies": self.qualifies,
            "reasons": list(self.reasons),
        }


def assess_acquisition_replanning_episode(
    result: GoalManagerDevelopmentResult,
) -> AcquisitionReplanningEpisodeAssessment:
    """Check one settled outcome without inventing success from infrastructure facts."""

    if not isinstance(result, GoalManagerDevelopmentResult):
        raise TypeError("result must be a GoalManagerDevelopmentResult")
    reasons: list[str] = []
    if len(result.steps) != ACQUISITION_REPLANNING_MAX_DECISIONS:
        reasons.append("not_exactly_two_learned_decisions")
        return AcquisitionReplanningEpisodeAssessment(False, tuple(reasons))

    acquisition, replan = result.steps
    if acquisition.selected_kind is not GoalKind.ACQUIRE_SPECIES:
        reasons.append("first_goal_not_acquire_species")
    if acquisition.status is not GoalDecisionOutcome.SUCCEEDED:
        reasons.append("acquisition_not_verified")
    if not acquisition.semantic_state_changed:
        reasons.append("acquisition_semantic_state_unchanged")
    if (
        acquisition.collection_after.required_specimens_remaining
        >= acquisition.collection_before.required_specimens_remaining
        or acquisition.collection_after.retained_captures
        <= acquisition.collection_before.retained_captures
        or sum(count for _species, count in acquisition.collection_after.specimen_counts)
        < sum(count for _species, count in acquisition.collection_before.specimen_counts)
    ):
        reasons.append("acquisition_did_not_advance_living_collection")
    if replan.available_goal_count < ACQUISITION_REPLANNING_MIN_POST_CHOICES:
        reasons.append("post_acquisition_menu_has_fewer_than_two_choices")
    if replan.selected_kind is GoalKind.ACQUIRE_SPECIES:
        reasons.append("second_goal_did_not_change")
    if replan.status is not GoalDecisionOutcome.SUCCEEDED:
        reasons.append("second_outcome_not_verified")
    if not replan.semantic_state_changed:
        reasons.append("second_semantic_state_unchanged")
    if (
        acquisition.policy_context_sha256 == replan.policy_context_sha256
        or result.policy_context_changes < 1
    ):
        reasons.append("policy_context_did_not_change")
    if (
        acquisition.available_menu_sha256 == replan.available_menu_sha256
        or result.available_menu_changes < 1
    ):
        reasons.append("available_menu_did_not_change")
    return AcquisitionReplanningEpisodeAssessment(not reasons, tuple(reasons))


def acquisition_replanning_behavior_contract() -> dict[str, object]:
    """Return the fixed-denominator intervention and stopping contract."""

    return {
        "schema": "pokemon.core.acquisition-replanning-behavior.v1",
        "root_lineages": ACQUISITION_REPLANNING_ROOTS,
        "trials_per_root": ACQUISITION_REPLANNING_TRIALS_PER_ROOT,
        "planned_episodes": ACQUISITION_REPLANNING_EPISODES,
        "maximum_controller_started_decisions_per_episode": (
            ACQUISITION_REPLANNING_MAX_DECISIONS
        ),
        "learned_choice_decisions_after_intervention": 1,
        "first_decision_schedule_per_root": [
            GoalKind.ACQUIRE_SPECIES.value,
            GoalKind.ACQUIRE_SPECIES.value,
            GoalKind.DEVELOP_TEAM.value,
            GoalKind.EXPLORE.value,
        ],
        "first_decision_schedule_scope": "per_trial_within_each_root",
        "first_decision_assignment": "frozen_intervention_before_outcomes",
        "first_decision_is_model_prediction": False,
        "second_decision_authority": "exploratory_goal_manager",
        "minimum_initial_executable_choices": 3,
        "minimum_post_acquisition_executable_choices": 2,
        "require_action_free_reobservation_after_first_outcome": True,
        "require_changed_policy_context_before_second_decision": True,
        "require_changed_available_menu_before_second_decision": True,
        "require_distinct_second_goal_kind_after_acquisition": True,
        "retain_all_claimed_failures": True,
        "replacement_or_retry_allowed": False,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
    }


def acquisition_replanning_evidence_contract() -> dict[str, object]:
    """Return the minimum evidence needed before this curriculum may fit a model."""

    return {
        "schema": "pokemon.core.acquisition-replanning-evidence-gate.v1",
        "minimum_admitted_acquisition_first_episodes": (
            ACQUISITION_REPLANNING_MIN_ADMITTED_ACQUISITIONS
        ),
        "minimum_verified_distinct_goal_replans": ACQUISITION_REPLANNING_MIN_REPLANS,
        "minimum_root_lineages_with_verified_replan": (
            ACQUISITION_REPLANNING_MIN_REPLAN_ROOTS
        ),
        "threshold_basis": (
            "provisional feasibility gate: four verified replans across at least three "
            "of four roots; all sixteen outcomes remain retained regardless of gate"
        ),
        "acquisition_requirements": [
            "independent_success_verification",
            "required_specimen_count_decreased",
            "living_collection_nonregression",
        ],
        "replanning_requirements": [
            "post_acquisition_menu_has_at_least_two_executable_choices",
            "policy_context_changed",
            "available_menu_changed",
            "second_selected_goal_differs_from_acquire_species",
            "second_outcome_independently_verified",
        ],
        "fit_partition": "train_only",
        "descriptive_development_result_only": True,
        "unseen_comparison": False,
        "authority_promotion": False,
        "transfer_claim": False,
    }


def acquisition_replanning_capability_gap() -> dict[str, object]:
    """Describe the smallest reusable capability missing from the current Red roots."""

    return {
        "schema": "pokemon.core.acquisition-replanning-capability-gap.v1",
        "status": "reusable_same_area_second_goal_required",
        "required_capability": (
            "Expose at least one title-neutral, independently verified non-acquisition "
            "choice at an encounter source after one retained acquisition."
        ),
        "preferred_candidate": GoalKind.DEVELOP_TEAM.value,
        "acceptable_goal_kinds": [
            GoalKind.DEVELOP_TEAM.value,
            GoalKind.RESTORE_TEAM.value,
            GoalKind.EXPLORE.value,
        ],
        "why_generic": (
            "The preferred team-development capability must consume an encounter-source "
            "adapter rather than a Pokemon Red map script so later titles can bind the "
            "same semantic skill. An existing alternative is acceptable only when it "
            "remains executable after acquisition and is not added merely to inflate "
            "menu cardinality."
        ),
        "must_not_add": [
            "fixed_route_walkthrough",
            "teacher_choice",
            "root_specific_rescue",
            "silent_singleton_dispatch_as_learned_choice",
        ],
        "execution_authorized": False,
    }


def acquisition_replanning_design_record(
    inventory: AcquisitionReplanningInventory,
) -> dict[str, object]:
    """Build the canonical path-free design record from an action-free inventory."""

    if not isinstance(inventory, AcquisitionReplanningInventory):
        raise TypeError("inventory must be an AcquisitionReplanningInventory")
    record = {
        "schema": ACQUISITION_REPLANNING_SCHEMA,
        "inventory": inventory.public_dict(),
        "behavior": acquisition_replanning_behavior_contract(),
        "evidence_gate": acquisition_replanning_evidence_contract(),
        "capability_gap": acquisition_replanning_capability_gap(),
        "claim_boundary": {
            "supported": (
                "The current Red inventory can seed a four-root acquisition curriculum, "
                "but it cannot yet expose a genuine multi-choice post-acquisition replan."
            ),
            "unsupported": (
                "This design is not gameplay, training evidence, learned replanning, Red "
                "completion, living-Pokedex completion, or cross-title transfer."
            ),
        },
        "zero_effects": {
            "model_predictions": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "episode_attempts": 0,
            "verified_outcomes": 0,
            "model_fits": 0,
            "unseen_comparisons": 0,
            "authority_promotions": 0,
            "transfer_results": 0,
        },
    }
    return {**record, "design_sha256": canonical_sha256(record)}


__all__ = (
    "ACQUISITION_REPLANNING_EPISODES",
    "ACQUISITION_REPLANNING_MAX_DECISIONS",
    "ACQUISITION_REPLANNING_MIN_ADMITTED_ACQUISITIONS",
    "ACQUISITION_REPLANNING_MIN_REPLAN_ROOTS",
    "ACQUISITION_REPLANNING_MIN_REPLANS",
    "ACQUISITION_REPLANNING_ROOTS",
    "ACQUISITION_REPLANNING_SCHEMA",
    "ACQUISITION_REPLANNING_TRIALS_PER_ROOT",
    "AcquisitionReplanningCurriculumError",
    "AcquisitionReplanningEpisodeAssessment",
    "AcquisitionReplanningInventory",
    "assess_acquisition_replanning_episode",
    "acquisition_replanning_behavior_contract",
    "acquisition_replanning_capability_gap",
    "acquisition_replanning_design_record",
    "acquisition_replanning_evidence_contract",
)
