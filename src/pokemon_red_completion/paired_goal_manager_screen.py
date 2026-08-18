"""Frozen contract for one descriptive base-versus-candidate Red screen."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_development import (
    DEVELOPMENT_BEHAVIOR_POLICY_ID,
    DEVELOPMENT_EXPLORATION_MIX,
    DEVELOPMENT_MAX_DECISIONS,
    DEVELOPMENT_TEMPERATURE,
)
from pokemon_red_completion.goal_manager_protocol import GoalManagerAssignment
from pokemon_red_completion.provenance import canonical_sha256

PAIRED_SCREEN_SCHEMA = "pokemon.red.paired-goal-manager-outcome-screen.v1"
PAIRED_SCREEN_SEED = 20_000
PAIRED_SCREEN_ARM_ORDER = ("base", "candidate")


class PairedGoalManagerScreenError(ValueError):
    """Raised when the one-root paired screen crosses its frozen boundary."""


@dataclass(frozen=True, slots=True)
class PairedScreenAdjudication:
    result: str
    base_safe_retained_acquisition: bool | None
    candidate_safe_retained_acquisition: bool | None

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.paired-goal-manager-adjudication.v1",
            "result": self.result,
            "base_safe_retained_acquisition": (
                self.base_safe_retained_acquisition
            ),
            "candidate_safe_retained_acquisition": (
                self.candidate_safe_retained_acquisition
            ),
            "primary_endpoint": "safe_retained_acquisition",
        }


def select_development_outcome_unused_acquisition_root(
    assignments: Iterable[GoalManagerAssignment],
    *,
    excluded_root_lineages: frozenset[str],
) -> GoalManagerAssignment:
    """Select the first eligible train assignment without model scoring or state access."""

    if not isinstance(excluded_root_lineages, frozenset) or any(
        not isinstance(value, str) for value in excluded_root_lineages
    ):
        raise TypeError("excluded_root_lineages must be a frozenset of strings")
    eligible = tuple(
        assignment
        for assignment in assignments
        if assignment.partition == "train"
        and assignment.focus_kind is GoalKind.ACQUIRE_SPECIES
        and assignment.root_lineage_id not in excluded_root_lineages
    )
    if not eligible:
        raise PairedGoalManagerScreenError(
            "paired screen has no development-outcome-unused acquisition root"
        )
    return eligible[0]


def paired_screen_behavior_contract() -> dict[str, object]:
    """Return the exact shared behavior and stopping contract for both arms."""

    return {
        "schema": "pokemon.core.paired-goal-manager-behavior-contract.v1",
        "arm_order": list(PAIRED_SCREEN_ARM_ORDER),
        "seed": PAIRED_SCREEN_SEED,
        "policy_id": DEVELOPMENT_BEHAVIOR_POLICY_ID,
        "exploration_mix": DEVELOPMENT_EXPLORATION_MIX,
        "temperature": DEVELOPMENT_TEMPERATURE,
        "maximum_decisions_per_arm": DEVELOPMENT_MAX_DECISIONS,
        "independent_reset_per_arm": True,
        "post_choice_trajectory_divergence_allowed": True,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "retry_or_replacement_allowed": False,
    }


def paired_screen_endpoint_contract() -> dict[str, object]:
    """Return the descriptive primary and secondary endpoint contract."""

    return {
        "schema": "pokemon.core.paired-goal-manager-endpoint-contract.v1",
        "primary_endpoint": "safe_retained_acquisition",
        "primary_requirements": [
            "acquire_species_selected",
            "acquisition_independently_verified",
            "required_specimen_or_ledger_progress",
            "collection_nonregression",
        ],
        "adjudication": "candidate_minus_base_boolean",
        "results": ["win", "loss", "tie", "uninterpretable"],
        "secondary_reports": [
            "episode_completion",
            "verified_outcomes",
            "changed_state_replanning",
            "controller_actions",
            "emulator_frames",
        ],
        "unseen_comparison": False,
        "promotion_authorized": False,
    }


def paired_screen_arm_claim(
    *,
    screen_id: str,
    arm: str,
    model_canonical_sha256: str,
) -> str:
    """Return the stable one-shot identity for one exact paired arm."""

    if arm not in PAIRED_SCREEN_ARM_ORDER:
        raise PairedGoalManagerScreenError("paired screen arm is invalid")
    return canonical_sha256(
        {
            "schema": "pokemon.red.paired-goal-manager-arm-claim.v1",
            "screen_id": screen_id,
            "arm": arm,
            "model_canonical_sha256": model_canonical_sha256,
        }
    )


def adjudicate_paired_screen(
    *,
    base_safe_retained_acquisition: bool | None,
    candidate_safe_retained_acquisition: bool | None,
) -> PairedScreenAdjudication:
    """Adjudicate only the frozen acquisition endpoint; never use a tie-breaker."""

    for value in (
        base_safe_retained_acquisition,
        candidate_safe_retained_acquisition,
    ):
        if value is not None and type(value) is not bool:  # noqa: E721
            raise TypeError("paired screen endpoint must be bool or None")
    if (
        base_safe_retained_acquisition is None
        or candidate_safe_retained_acquisition is None
    ):
        result = "uninterpretable"
    elif candidate_safe_retained_acquisition and not base_safe_retained_acquisition:
        result = "win"
    elif base_safe_retained_acquisition and not candidate_safe_retained_acquisition:
        result = "loss"
    else:
        result = "tie"
    return PairedScreenAdjudication(
        result=result,
        base_safe_retained_acquisition=base_safe_retained_acquisition,
        candidate_safe_retained_acquisition=candidate_safe_retained_acquisition,
    )


__all__ = [
    "PAIRED_SCREEN_ARM_ORDER",
    "PAIRED_SCREEN_SCHEMA",
    "PAIRED_SCREEN_SEED",
    "PairedGoalManagerScreenError",
    "PairedScreenAdjudication",
    "adjudicate_paired_screen",
    "paired_screen_arm_claim",
    "paired_screen_behavior_contract",
    "paired_screen_endpoint_contract",
    "select_development_outcome_unused_acquisition_root",
]
