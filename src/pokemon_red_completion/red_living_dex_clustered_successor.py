"""Outcome-blind design for the first clustered Red train successor.

The eight-row integration tranche yielded five settled examples and three
setup-only terminals.  A successor aimed at exactly the remaining integration
minimum would repeat the same process failure: normal setup attrition could
force another freezer/consumer cycle.  This module freezes a larger, still
bounded tranche before any successor arm or outcome is observed.

Every selected scenario belongs to a distinct authenticated upstream episode
lineage.  Development remains a four-lineage read-only holdout.  The design is
only a schedule policy; it has no cartridge, controller, claim, teacher,
outcome, scorer, or fitter surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from pokemon_red_completion.living_dex_clustered_curriculum import (
    LivingDexClusteredCurriculumPolicy,
)
from pokemon_red_completion.provenance import canonical_sha256

RED_LIVING_DEX_CLUSTERED_SUCCESSOR_SCHEMA = (
    "pokemon.red.living-dex-clustered-successor-design.v1"
)

RED_LIVING_DEX_CLUSTERED_SUCCESSOR_POLICY = LivingDexClusteredCurriculumPolicy(
    train_scenarios=16,
    development_scenarios=4,
    minimum_train_lineages=16,
    minimum_development_lineages=4,
    minimum_train_option_kinds=7,
    minimum_development_option_kinds=7,
    maximum_scenarios_per_lineage=1,
    eventual_minimum_train_outcomes=60,
)


class RedLivingDexClusteredSuccessorDesignError(ValueError):
    """The fixed successor stopped matching its prospective design."""


@dataclass(frozen=True, slots=True)
class RedLivingDexClusteredSuccessorDesign:
    """Public attrition rationale plus the exact action-free policy."""

    prior_assignments: int = 8
    prior_settled_examples: int = 5
    minimum_new_settled_examples: int = 3
    authentic_examples_before: int = 6
    integration_minimum_examples: int = 8
    policy: LivingDexClusteredCurriculumPolicy = (
        RED_LIVING_DEX_CLUSTERED_SUCCESSOR_POLICY
    )

    def __post_init__(self) -> None:
        for value, subject in (
            (self.prior_assignments, "prior assignments"),
            (self.prior_settled_examples, "prior settled examples"),
            (
                self.minimum_new_settled_examples,
                "minimum new settled examples",
            ),
            (self.authentic_examples_before, "authentic examples before"),
            (self.integration_minimum_examples, "integration minimum"),
        ):
            if type(value) is not int or value <= 0:  # noqa: E721
                raise RedLivingDexClusteredSuccessorDesignError(
                    f"{subject} must be positive"
                )
        if (
            self.prior_settled_examples > self.prior_assignments
            or self.authentic_examples_before
            + self.minimum_new_settled_examples
            < self.integration_minimum_examples
            or self.policy != RED_LIVING_DEX_CLUSTERED_SUCCESSOR_POLICY
            or self.policy.maximum_scenarios_per_lineage != 1
            or self.policy.minimum_train_lineages
            != self.policy.train_scenarios
            or self.policy.minimum_development_lineages
            != self.policy.development_scenarios
        ):
            raise RedLivingDexClusteredSuccessorDesignError(
                "successor attrition or independence contract differs"
            )

    @property
    def observed_setup_yield(self) -> Fraction:
        return Fraction(self.prior_settled_examples, self.prior_assignments)

    @property
    def expected_settled_examples_at_observed_yield(self) -> Fraction:
        return self.observed_setup_yield * self.policy.train_scenarios

    @property
    def design_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        expected = self.expected_settled_examples_at_observed_yield
        return {
            "authentic_examples_before": self.authentic_examples_before,
            "development_is_read_only": True,
            "expected_settled_examples_at_observed_yield": {
                "denominator": expected.denominator,
                "numerator": expected.numerator,
            },
            "integration_minimum_examples": self.integration_minimum_examples,
            "minimum_new_settled_examples": self.minimum_new_settled_examples,
            "observed_setup_yield": {
                "denominator": self.observed_setup_yield.denominator,
                "numerator": self.observed_setup_yield.numerator,
            },
            "outcome_aware_admission": False,
            "policy": self.policy.public_dict(),
            "policy_sha256": self.policy.policy_sha256,
            "prior_assignments": self.prior_assignments,
            "prior_settled_examples": self.prior_settled_examples,
            "schema": RED_LIVING_DEX_CLUSTERED_SUCCESSOR_SCHEMA,
        }


__all__ = [
    "RED_LIVING_DEX_CLUSTERED_SUCCESSOR_POLICY",
    "RED_LIVING_DEX_CLUSTERED_SUCCESSOR_SCHEMA",
    "RedLivingDexClusteredSuccessorDesign",
    "RedLivingDexClusteredSuccessorDesignError",
]
