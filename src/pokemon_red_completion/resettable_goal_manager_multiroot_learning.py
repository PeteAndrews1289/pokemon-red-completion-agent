"""Root-diverse, train/development learning contract for the goal manager.

This is deliberately a small Red curriculum, not a completion benchmark.  It
fits once from eight predeclared one-decision train resets and evaluates once
on four untouched resets from two root-disjoint development roots.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalKind, GoalManagerExample
from pokemon_red_completion.goal_manager_development import (
    AdmittedGoalManagerDevelopmentEpisode,
    GoalManagerDevelopmentTarget,
)
from pokemon_red_completion.goal_manager_model import GoalManagerLinearModel
from pokemon_red_completion.goal_manager_outcome_learning import (
    OUTCOME_UPDATE_MENU_KL_CAP,
    GoalManagerOutcomeFitMetrics,
    GoalManagerOutcomeUpdate,
    evaluate_goal_manager_outcomes,
    fit_goal_manager_train_outcome_update,
    maximum_policy_kl,
    require_unchanged_guard_winners,
)

MULTIROOT_TRAIN_ROOTS = 4
MULTIROOT_DEVELOPMENT_ROOTS = 2
MULTIROOT_EPISODES_PER_ROOT = 2
MULTIROOT_TRAIN_EPISODES = 8
MULTIROOT_DEVELOPMENT_EPISODES = 4
MULTIROOT_MINIMUM_TRAIN_TARGETS = 6
MULTIROOT_MINIMUM_TRAIN_ROOTS = 3
MULTIROOT_MINIMUM_TRAIN_GOAL_KINDS = 3


class ResettableGoalManagerLearningError(ValueError):
    """Raised when the frozen multi-root learning boundary is violated."""


@dataclass(frozen=True, slots=True)
class ResettableGoalManagerTrainSet:
    """The admitted train-only rows that may enter the one fixed update."""

    rows: tuple[tuple[GoalManagerExample, GoalManagerDevelopmentTarget], ...]
    roots: tuple[str, ...]
    selected_goal_kinds: tuple[str, ...]
    planned_episodes: int = MULTIROOT_TRAIN_EPISODES

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.resettable-goal-manager-train-set.v1",
            "planned_episodes": self.planned_episodes,
            "admitted_targets": len(self.rows),
            "admitted_roots": len(self.roots),
            "selected_goal_kinds": list(self.selected_goal_kinds),
            "partition": "train",
        }


@dataclass(frozen=True, slots=True)
class ResettableGoalManagerFit:
    """One accepted train-only update under the frozen safety gates."""

    update: GoalManagerOutcomeUpdate
    maximum_train_menu_kl: float
    train_roots: tuple[str, ...]
    train_goal_kinds: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.resettable-goal-manager-fit.v1",
            "update": self.update.public_dict(),
            "maximum_train_menu_kl": self.maximum_train_menu_kl,
            "train_roots": len(self.train_roots),
            "train_goal_kinds": list(self.train_goal_kinds),
            "partition": "train",
            "model_updates": 1,
        }


@dataclass(frozen=True, slots=True)
class ResettableGoalManagerComparison:
    """One fixed-denominator comparison on four untouched development resets."""

    base: GoalManagerOutcomeFitMetrics
    candidate: GoalManagerOutcomeFitMetrics
    directional_wins: int
    directional_losses: int
    directional_ties: int
    development_roots: tuple[str, ...]
    favorable: bool

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.resettable-goal-manager-comparison.v1",
            "base": self.base.public_dict(),
            "candidate": self.candidate.public_dict(),
            "fixed_denominator": MULTIROOT_DEVELOPMENT_EPISODES,
            "development_roots": len(self.development_roots),
            "directional_wins": self.directional_wins,
            "directional_losses": self.directional_losses,
            "directional_ties": self.directional_ties,
            "decision_rule": {
                "candidate_cross_entropy": "strictly_lower",
                "minimum_directional_wins": 3,
                "maximum_directional_losses": 0,
            },
            "favorable": self.favorable,
            "claim_boundary": (
                "descriptive root-disjoint Red single-decision comparison only"
            ),
        }


def admit_resettable_goal_manager_train_set(
    episodes: Iterable[AdmittedGoalManagerDevelopmentEpisode],
) -> ResettableGoalManagerTrainSet:
    """Admit only a sufficiently diverse subset of the fixed eight train resets."""

    admitted = tuple(episodes)
    if len(admitted) > MULTIROOT_TRAIN_EPISODES:
        raise ResettableGoalManagerLearningError("train denominator exceeds eight episodes")
    rows: list[tuple[GoalManagerExample, GoalManagerDevelopmentTarget]] = []
    roots: list[str] = []
    kinds: list[str] = []
    for episode in admitted:
        if not isinstance(episode, AdmittedGoalManagerDevelopmentEpisode):
            raise TypeError("train episodes are invalid")
        if (
            episode.dataset.partition != "train"
            or len(episode.dataset.examples) != 1
            or len(episode.targets) != 1
        ):
            raise ResettableGoalManagerLearningError(
                "train episode must contain one settled train target"
            )
        example = episode.dataset.examples[0]
        target = episode.targets[0]
        rows.append((example, target))
        roots.append(episode.dataset.root_lineage_id)
        kinds.append(example.selected_kind.value)
    if len({target.decision_id for _, target in rows}) != len(rows):
        raise ResettableGoalManagerLearningError("train decision identities repeat")
    root_counts = Counter(roots)
    if any(count > MULTIROOT_EPISODES_PER_ROOT for count in root_counts.values()):
        raise ResettableGoalManagerLearningError("train root exceeds two reset episodes")
    unique_kinds = tuple(sorted(set(kinds)))
    if (
        len(rows) < MULTIROOT_MINIMUM_TRAIN_TARGETS
        or len(root_counts) < MULTIROOT_MINIMUM_TRAIN_ROOTS
        or len(unique_kinds) < MULTIROOT_MINIMUM_TRAIN_GOAL_KINDS
        or GoalKind.ACQUIRE_SPECIES.value not in unique_kinds
    ):
        raise ResettableGoalManagerLearningError(
            "train evidence misses the frozen root, kind, or collection threshold"
        )
    return ResettableGoalManagerTrainSet(
        rows=tuple(rows),
        roots=tuple(sorted(root_counts)),
        selected_goal_kinds=unique_kinds,
    )


def fit_resettable_goal_manager_train_set(
    base_model: GoalManagerLinearModel,
    episodes: Iterable[AdmittedGoalManagerDevelopmentEpisode],
    *,
    guard_examples: Sequence[GoalManagerExample],
    kl_examples: Sequence[GoalManagerExample],
) -> ResettableGoalManagerFit:
    """Perform the single fixed fit and enforce all train-only safety gates."""

    train_set = admit_resettable_goal_manager_train_set(episodes)
    if len(guard_examples) != 18 or len(kl_examples) != 54:
        raise ResettableGoalManagerLearningError(
            "train update requires the frozen 18-winner and 54-menu guard surfaces"
        )
    update = fit_goal_manager_train_outcome_update(base_model, train_set.rows)
    require_unchanged_guard_winners(base_model, update.model, guard_examples)
    maximum_kl = maximum_policy_kl(base_model, update.model, kl_examples)
    if maximum_kl > OUTCOME_UPDATE_MENU_KL_CAP + 1e-12:
        raise ResettableGoalManagerLearningError("train update exceeds the menu KL cap")
    return ResettableGoalManagerFit(
        update=update,
        maximum_train_menu_kl=maximum_kl,
        train_roots=train_set.roots,
        train_goal_kinds=train_set.selected_goal_kinds,
    )


def compare_resettable_goal_manager_development(
    base_model: GoalManagerLinearModel,
    candidate_model: GoalManagerLinearModel,
    episodes: Iterable[AdmittedGoalManagerDevelopmentEpisode],
    *,
    train_roots: Iterable[str],
) -> ResettableGoalManagerComparison:
    """Compare once on all four root-disjoint development episodes."""

    admitted = tuple(episodes)
    if len(admitted) != MULTIROOT_DEVELOPMENT_EPISODES:
        raise ResettableGoalManagerLearningError(
            "development comparison requires all four planned episodes"
        )
    rows: list[tuple[GoalManagerExample, GoalManagerDevelopmentTarget]] = []
    roots: list[str] = []
    for episode in admitted:
        if not isinstance(episode, AdmittedGoalManagerDevelopmentEpisode):
            raise TypeError("development episodes are invalid")
        if (
            episode.dataset.partition != "development"
            or len(episode.dataset.examples) != 1
            or len(episode.targets) != 1
        ):
            raise ResettableGoalManagerLearningError(
                "development episode must contain one settled development target"
            )
        rows.append((episode.dataset.examples[0], episode.targets[0]))
        roots.append(episode.dataset.root_lineage_id)
    root_counts = Counter(roots)
    if (
        len(root_counts) != MULTIROOT_DEVELOPMENT_ROOTS
        or any(count != MULTIROOT_EPISODES_PER_ROOT for count in root_counts.values())
        or set(root_counts) & set(train_roots)
    ):
        raise ResettableGoalManagerLearningError(
            "development roots violate the frozen two-by-two disjoint split"
        )
    base = evaluate_goal_manager_outcomes(
        base_model,
        rows,
        expected_partition="development",
    )
    candidate = evaluate_goal_manager_outcomes(
        candidate_model,
        rows,
        expected_partition="development",
    )
    wins = 0
    losses = 0
    ties = 0
    for (_example, target), old, new in zip(
        rows,
        base.selected_probabilities,
        candidate.selected_probabilities,
        strict=True,
    ):
        delta = new - old if target.reward == 1.0 else old - new
        if delta > 1e-12:
            wins += 1
        elif delta < -1e-12:
            losses += 1
        else:
            ties += 1
    favorable = (
        candidate.weighted_binary_cross_entropy
        < base.weighted_binary_cross_entropy - 1e-12
        and wins >= 3
        and losses == 0
    )
    return ResettableGoalManagerComparison(
        base=base,
        candidate=candidate,
        directional_wins=wins,
        directional_losses=losses,
        directional_ties=ties,
        development_roots=tuple(sorted(root_counts)),
        favorable=favorable,
    )


__all__ = [
    "MULTIROOT_DEVELOPMENT_EPISODES",
    "MULTIROOT_DEVELOPMENT_ROOTS",
    "MULTIROOT_EPISODES_PER_ROOT",
    "MULTIROOT_MINIMUM_TRAIN_GOAL_KINDS",
    "MULTIROOT_MINIMUM_TRAIN_ROOTS",
    "MULTIROOT_MINIMUM_TRAIN_TARGETS",
    "MULTIROOT_TRAIN_EPISODES",
    "MULTIROOT_TRAIN_ROOTS",
    "ResettableGoalManagerComparison",
    "ResettableGoalManagerFit",
    "ResettableGoalManagerLearningError",
    "ResettableGoalManagerTrainSet",
    "admit_resettable_goal_manager_train_set",
    "compare_resettable_goal_manager_development",
    "fit_resettable_goal_manager_train_set",
]
