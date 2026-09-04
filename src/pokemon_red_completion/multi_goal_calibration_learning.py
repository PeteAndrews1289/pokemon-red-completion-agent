"""Train-only learning from the fixed Red multi-goal calibration campaign."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalKind, GoalManagerExample
from pokemon_red_completion.goal_manager_development import GoalManagerDevelopmentTarget
from pokemon_red_completion.goal_manager_model import GoalManagerLinearModel
from pokemon_red_completion.goal_manager_outcome_learning import (
    OUTCOME_UPDATE_MENU_KL_CAP,
    GoalManagerOutcomeUpdate,
    fit_goal_manager_train_outcome_update,
    maximum_policy_kl,
    require_unchanged_guard_winners,
)
from pokemon_red_completion.multi_goal_calibration_admission import (
    AdmittedMultiGoalCalibrationOutcome,
)

CALIBRATION_TRAIN_TARGETS = 7
CALIBRATION_TRAIN_ROOTS = 4
CALIBRATION_TRAIN_KIND_COUNTS = {
    GoalKind.ADVANCE_STORY: 2,
    GoalKind.DEVELOP_TEAM: 2,
    GoalKind.EVOLVE_SPECIES: 1,
    GoalKind.MANAGE_STORAGE: 2,
}
CALIBRATION_TRAIN_POSITIVES = 4
CALIBRATION_TRAIN_NEGATIVES = 3


class MultiGoalCalibrationLearningError(ValueError):
    """Raised when the fixed campaign cannot support its one train-only update."""


@dataclass(frozen=True, slots=True)
class MultiGoalCalibrationTrainSet:
    """The exact fixed-denominator outcome rows admitted for calibration."""

    rows: tuple[tuple[GoalManagerExample, GoalManagerDevelopmentTarget], ...]
    root_lineages: tuple[str, ...]
    manifest_sha256s: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        rewards = [target.reward for _, target in self.rows]
        kinds = Counter(example.selected_kind.value for example, _ in self.rows)
        return {
            "schema": "pokemon.red.multi-goal-calibration-train-set.v1",
            "targets": len(self.rows),
            "roots": len(self.root_lineages),
            "positive_targets": rewards.count(1.0),
            "negative_targets": rewards.count(-1.0),
            "selected_goal_kind_counts": dict(sorted(kinds.items())),
            "unique_episode_manifests": len(set(self.manifest_sha256s)),
            "teacher_queries": 0,
            "private_path_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class MultiGoalCalibrationFit:
    """One bounded update plus preservation measurements."""

    train_set: MultiGoalCalibrationTrainSet
    update: GoalManagerOutcomeUpdate
    maximum_guard_menu_kl: float

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.multi-goal-calibration-fit.v1",
            "train_set": self.train_set.public_dict(),
            "update": self.update.public_dict(),
            "maximum_guard_menu_kl": self.maximum_guard_menu_kl,
            "guard_menu_kl_cap": OUTCOME_UPDATE_MENU_KL_CAP,
        }


def admit_multi_goal_calibration_train_set(
    outcomes: Iterable[AdmittedMultiGoalCalibrationOutcome],
) -> MultiGoalCalibrationTrainSet:
    """Convert the fixed completed campaign into authenticated outcome targets."""

    admitted = tuple(outcomes)
    rows: list[tuple[GoalManagerExample, GoalManagerDevelopmentTarget]] = []
    roots: list[str] = []
    manifests: list[str] = []
    for outcome in admitted:
        if not isinstance(outcome, AdmittedMultiGoalCalibrationOutcome):
            raise TypeError("calibration outcomes are invalid")
        if len(outcome.dataset.examples) != 1:
            raise MultiGoalCalibrationLearningError("calibration target count differs")
        example = outcome.dataset.examples[0]
        if (
            example.partition != "train"
            or example.selected_kind is not outcome.selected_goal_kind
            or example.outcome_status is not outcome.status
            or outcome.reward not in {-1.0, 1.0}
        ):
            raise MultiGoalCalibrationLearningError("calibration target differs")
        rows.append(
            (
                example,
                GoalManagerDevelopmentTarget(
                    decision_id=example.decision_id,
                    selected_candidate_index=example.selected_candidate_index,
                    reward=outcome.reward,
                    behavior_probability=1.0,
                    importance_weight=1.0,
                ),
            )
        )
        roots.append(outcome.dataset.root_lineage_id)
        manifests.append(outcome.dataset.manifest_sha256)

    root_lineages = tuple(sorted(set(roots)))
    kind_counts = Counter(example.selected_kind for example, _ in rows)
    rewards = [target.reward for _, target in rows]
    if (
        len(rows) != CALIBRATION_TRAIN_TARGETS
        or len({example.decision_id for example, _ in rows}) != len(rows)
        or len(set(manifests)) != len(rows)
        or len(root_lineages) != CALIBRATION_TRAIN_ROOTS
        or kind_counts != Counter(CALIBRATION_TRAIN_KIND_COUNTS)
        or rewards.count(1.0) != CALIBRATION_TRAIN_POSITIVES
        or rewards.count(-1.0) != CALIBRATION_TRAIN_NEGATIVES
    ):
        raise MultiGoalCalibrationLearningError("calibration denominator differs")
    return MultiGoalCalibrationTrainSet(
        rows=tuple(rows),
        root_lineages=root_lineages,
        manifest_sha256s=tuple(manifests),
    )


def fit_multi_goal_calibration_train_set(
    base_model: GoalManagerLinearModel,
    train_set: MultiGoalCalibrationTrainSet,
    *,
    guard_winners: Sequence[GoalManagerExample],
    guard_menus: Sequence[GoalManagerExample],
) -> MultiGoalCalibrationFit:
    """Apply one capped update while preserving the original Red policy surface."""

    if not isinstance(train_set, MultiGoalCalibrationTrainSet):
        raise TypeError("train_set must be a MultiGoalCalibrationTrainSet")
    if len(guard_winners) != 18 or len(guard_menus) != 54:
        raise MultiGoalCalibrationLearningError("calibration guard set differs")
    update = fit_goal_manager_train_outcome_update(base_model, train_set.rows)
    require_unchanged_guard_winners(base_model, update.model, guard_winners)
    maximum_kl = maximum_policy_kl(base_model, update.model, guard_menus)
    if maximum_kl > OUTCOME_UPDATE_MENU_KL_CAP:
        raise MultiGoalCalibrationLearningError("calibration guard KL exceeds cap")
    return MultiGoalCalibrationFit(
        train_set=train_set,
        update=update,
        maximum_guard_menu_kl=maximum_kl,
    )


__all__ = [
    "CALIBRATION_TRAIN_KIND_COUNTS",
    "CALIBRATION_TRAIN_NEGATIVES",
    "CALIBRATION_TRAIN_POSITIVES",
    "CALIBRATION_TRAIN_ROOTS",
    "CALIBRATION_TRAIN_TARGETS",
    "MultiGoalCalibrationFit",
    "MultiGoalCalibrationLearningError",
    "MultiGoalCalibrationTrainSet",
    "admit_multi_goal_calibration_train_set",
    "fit_multi_goal_calibration_train_set",
]
