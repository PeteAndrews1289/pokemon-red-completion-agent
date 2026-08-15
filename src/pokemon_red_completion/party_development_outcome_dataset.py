"""Diversity and leakage gates for completion-aware party outcome catalogs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
    EvolutionRouteKind,
    PartyDevelopmentGoal,
)
from pokemon_red_completion.scenario_lab import ScenarioFamily, ScenarioPartition
from pokemon_red_completion.scenario_outcomes import (
    ScenarioOutcomeCatalog,
    ScenarioOutcomeError,
    ScenarioOutcomeExample,
)
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind


@dataclass(frozen=True, slots=True)
class PartyDevelopmentReadinessPolicy:
    """Prospective minimums for the first descriptive outcome fit."""

    minimum_train_examples: int = 8
    minimum_development_examples: int = 6
    minimum_goals_per_partition: int = 2
    minimum_candidate_count_observed: int = 3
    minimum_health_bins: int = 2
    minimum_pp_bins: int = 2
    minimum_evolution_route_kinds: int = 2
    require_both_choice_kinds: bool = True
    require_complete_venue_priors: bool = True

    def __post_init__(self) -> None:
        for name in (
            "minimum_train_examples",
            "minimum_development_examples",
            "minimum_goals_per_partition",
            "minimum_candidate_count_observed",
            "minimum_health_bins",
            "minimum_pp_bins",
            "minimum_evolution_route_kinds",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:  # noqa: E721
                raise ValueError(f"{name.replace('_', ' ')} must be positive")
        for name in ("require_both_choice_kinds", "require_complete_venue_priors"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be boolean")

    def public_dict(self) -> dict[str, object]:
        return {
            "minimum_train_examples": self.minimum_train_examples,
            "minimum_development_examples": self.minimum_development_examples,
            "minimum_goals_per_partition": self.minimum_goals_per_partition,
            "minimum_candidate_count_observed": self.minimum_candidate_count_observed,
            "minimum_health_bins": self.minimum_health_bins,
            "minimum_pp_bins": self.minimum_pp_bins,
            "minimum_evolution_route_kinds": self.minimum_evolution_route_kinds,
            "require_both_choice_kinds": self.require_both_choice_kinds,
            "require_complete_venue_priors": self.require_complete_venue_priors,
        }


DEFAULT_PARTY_DEVELOPMENT_READINESS_POLICY = PartyDevelopmentReadinessPolicy()


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeCatalogAudit:
    """Path-free readiness receipt for a prospective train/development catalog."""

    example_count: int
    fully_measured_examples: int
    learner_update_eligible_examples: int
    partition_counts: tuple[tuple[str, int], ...]
    partition_eligible_counts: tuple[tuple[str, int], ...]
    goal_partition_counts: tuple[tuple[str, int], ...]
    choice_kind_partition_counts: tuple[tuple[str, int], ...]
    candidate_count_counts: tuple[tuple[int, int], ...]
    health_bins: tuple[str, ...]
    pp_bins: tuple[str, ...]
    survival_bins: tuple[str, ...]
    evolution_route_kinds: tuple[str, ...]
    venue_prior_available_candidates: int
    venue_examples: int
    venue_examples_with_complete_priors: int
    unique_candidate_menus: int
    policy: PartyDevelopmentReadinessPolicy
    initial_fit_ready: bool
    reasons: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.party-development-outcome-catalog-audit.v2",
            "example_count": self.example_count,
            "fully_measured_examples": self.fully_measured_examples,
            "learner_update_eligible_examples": self.learner_update_eligible_examples,
            "partition_counts": dict(self.partition_counts),
            "partition_eligible_counts": dict(self.partition_eligible_counts),
            "goal_partition_counts": dict(self.goal_partition_counts),
            "choice_kind_partition_counts": dict(
                self.choice_kind_partition_counts
            ),
            "candidate_count_counts": {
                str(count): examples for count, examples in self.candidate_count_counts
            },
            "health_bins": list(self.health_bins),
            "pp_bins": list(self.pp_bins),
            "survival_bins": list(self.survival_bins),
            "evolution_route_kinds": list(self.evolution_route_kinds),
            "venue_prior_available_candidates": self.venue_prior_available_candidates,
            "venue_examples": self.venue_examples,
            "venue_examples_with_complete_priors": (
                self.venue_examples_with_complete_priors
            ),
            "unique_candidate_menus": self.unique_candidate_menus,
            "policy": self.policy.public_dict(),
            "initial_fit_ready": self.initial_fit_ready,
            "reasons": list(self.reasons),
            "paired_development_evaluation_required": True,
            "inferential_claim": False,
            "sealed_test_cases_opened": 0,
            "teacher_choice_targets": 0,
            "authority_promoted": False,
            "candidate_feature_values_public": False,
            "private_path_fields": 0,
        }


def audit_party_development_outcome_catalog(
    examples: tuple[ScenarioOutcomeExample, ...],
    *,
    policy: PartyDevelopmentReadinessPolicy = DEFAULT_PARTY_DEVELOPMENT_READINESS_POLICY,
) -> PartyDevelopmentOutcomeCatalogAudit:
    """Validate isolation and measure whether a first outcome fit is informative."""

    if not isinstance(examples, tuple) or not examples:
        raise ScenarioOutcomeError("party-development outcome catalog cannot be empty")
    if not isinstance(policy, PartyDevelopmentReadinessPolicy):
        raise TypeError("policy must be a PartyDevelopmentReadinessPolicy")
    for example in examples:
        if not isinstance(example, ScenarioOutcomeExample):
            raise ScenarioOutcomeError("party-development catalog example is invalid")
        if example.family is not ScenarioFamily.PARTY_DEVELOPMENT:
            raise ScenarioOutcomeError("party-development catalog contains another family")
        if (
            example.feature_schema_id != PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID
            or example.feature_names != PARTY_DEVELOPMENT_FEATURE_NAMES
        ):
            raise ScenarioOutcomeError(
                "party-development catalog feature schema is incompatible"
            )
    ScenarioOutcomeCatalog(examples)

    partition_counts: Counter[str] = Counter()
    eligible_counts: Counter[str] = Counter()
    goal_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    candidate_counts: Counter[int] = Counter()
    health_bins: set[str] = set()
    pp_bins: set[str] = set()
    survival_bins: set[str] = set()
    route_kinds: set[str] = set()
    prior_candidates = 0
    venue_examples = 0
    venue_examples_with_complete_priors = 0
    unique_menus: set[tuple[tuple[float, ...], ...]] = set()
    for example in examples:
        partition = example.partition.value
        goal = _example_goal(example)
        kind = _example_kind(example)
        partition_counts[partition] += 1
        eligible_counts[partition] += int(example.learner_update_eligible)
        goal_counts[f"{partition}:{goal.value}"] += 1
        kind_counts[f"{partition}:{kind.value}"] += 1
        candidate_counts[len(example.available_candidate_indices)] += 1
        unique_menus.add(tuple(item.features for item in example.candidates))
        if kind is TrainingChoiceKind.VENUE:
            venue_examples += 1
            if all(
                candidate.features[_feature_index("venue.prior_available")] == 1.0
                for candidate in example.candidates
                if candidate.available
            ):
                venue_examples_with_complete_priors += 1
        for candidate in example.candidates:
            if not candidate.available:
                continue
            features = candidate.features
            health_bins.add(
                _unit_bin(features[_feature_index("candidate.hp_ratio")])
            )
            pp_bins.add(_unit_bin(features[_feature_index("candidate.attack_pp")]))
            survival_bins.add(
                _signed_bin(
                    features[_feature_index("candidate.projected_survival_margin")]
                )
            )
            route_kinds.add(_evolution_route(features).value)
            prior_candidates += int(
                features[_feature_index("venue.prior_available")] == 1.0
            )

    reasons: set[str] = set()
    train_eligible = eligible_counts[ScenarioPartition.TRAIN.value]
    development_eligible = eligible_counts[ScenarioPartition.DEVELOPMENT.value]
    if train_eligible < policy.minimum_train_examples:
        reasons.add("insufficient_train_preferences")
    if development_eligible < policy.minimum_development_examples:
        reasons.add("insufficient_development_preferences")
    for partition in (ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT):
        goals = {
            key.split(":", 1)[1]
            for key in goal_counts
            if key.startswith(f"{partition.value}:")
        }
        if len(goals) < policy.minimum_goals_per_partition:
            reasons.add(f"insufficient_{partition.value}_goal_diversity")
        if policy.require_both_choice_kinds:
            kinds = {
                key.split(":", 1)[1]
                for key in kind_counts
                if key.startswith(f"{partition.value}:")
            }
            if kinds != {item.value for item in TrainingChoiceKind}:
                reasons.add(f"missing_{partition.value}_choice_kind")
    if max(candidate_counts, default=0) < policy.minimum_candidate_count_observed:
        reasons.add("candidate_menus_never_reach_required_width")
    if len(health_bins) < policy.minimum_health_bins:
        reasons.add("insufficient_health_diversity")
    if len(pp_bins) < policy.minimum_pp_bins:
        reasons.add("insufficient_pp_diversity")
    if len(route_kinds) < policy.minimum_evolution_route_kinds:
        reasons.add("insufficient_evolution_route_diversity")
    if (
        policy.require_complete_venue_priors
        and venue_examples_with_complete_priors != venue_examples
    ):
        reasons.add("venue_outcomes_lack_complete_prospective_priors")

    return PartyDevelopmentOutcomeCatalogAudit(
        example_count=len(examples),
        fully_measured_examples=sum(item.fully_measured for item in examples),
        learner_update_eligible_examples=sum(
            item.learner_update_eligible for item in examples
        ),
        partition_counts=tuple(sorted(partition_counts.items())),
        partition_eligible_counts=tuple(sorted(eligible_counts.items())),
        goal_partition_counts=tuple(sorted(goal_counts.items())),
        choice_kind_partition_counts=tuple(sorted(kind_counts.items())),
        candidate_count_counts=tuple(sorted(candidate_counts.items())),
        health_bins=tuple(sorted(health_bins)),
        pp_bins=tuple(sorted(pp_bins)),
        survival_bins=tuple(sorted(survival_bins)),
        evolution_route_kinds=tuple(sorted(route_kinds)),
        venue_prior_available_candidates=prior_candidates,
        venue_examples=venue_examples,
        venue_examples_with_complete_priors=venue_examples_with_complete_priors,
        unique_candidate_menus=len(unique_menus),
        policy=policy,
        initial_fit_ready=not reasons,
        reasons=tuple(sorted(reasons)),
    )


def _example_goal(example: ScenarioOutcomeExample) -> PartyDevelopmentGoal:
    goals = tuple(
        goal
        for goal in PartyDevelopmentGoal
        if all(
            candidate.features[_feature_index(f"context.goal.{goal.value}")] == 1.0
            for candidate in example.candidates
        )
    )
    active_counts = tuple(
        sum(
            candidate.features[_feature_index(f"context.goal.{goal.value}")] == 1.0
            for goal in PartyDevelopmentGoal
        )
        for candidate in example.candidates
    )
    binary = all(
        candidate.features[_feature_index(f"context.goal.{goal.value}")]
        in (0.0, 1.0)
        for candidate in example.candidates
        for goal in PartyDevelopmentGoal
    )
    if not binary or len(goals) != 1 or any(count != 1 for count in active_counts):
        raise ScenarioOutcomeError("party-development goal features are not one-hot")
    return goals[0]


def _example_kind(example: ScenarioOutcomeExample) -> TrainingChoiceKind:
    values = {
        candidate.features[_feature_index("choice.trainee")]
        for candidate in example.candidates
    }
    if values == {1.0}:
        return TrainingChoiceKind.TRAINEE
    if values == {0.0}:
        return TrainingChoiceKind.VENUE
    raise ScenarioOutcomeError("party-development choice-kind features are invalid")


def _evolution_route(features: tuple[float, ...]) -> EvolutionRouteKind:
    active = tuple(
        kind
        for kind in EvolutionRouteKind
        if features[_feature_index(f"candidate.evolution_method.{kind.value}")] == 1.0
    )
    count = sum(
        features[_feature_index(f"candidate.evolution_method.{kind.value}")] == 1.0
        for kind in EvolutionRouteKind
    )
    if len(active) != 1 or count != 1:
        raise ScenarioOutcomeError(
            "party-development evolution-route features are not one-hot"
        )
    return active[0]


def _feature_index(name: str) -> int:
    return PARTY_DEVELOPMENT_FEATURE_NAMES.index(name)


def _unit_bin(value: float) -> str:
    if value <= 0.0:
        return "empty"
    if value < 0.34:
        return "low"
    if value < 0.67:
        return "middle"
    return "high"


def _signed_bin(value: float) -> str:
    if value < -0.05:
        return "negative"
    if value > 0.05:
        return "positive"
    return "neutral"


__all__ = [
    "DEFAULT_PARTY_DEVELOPMENT_READINESS_POLICY",
    "PartyDevelopmentOutcomeCatalogAudit",
    "PartyDevelopmentReadinessPolicy",
    "audit_party_development_outcome_catalog",
]
