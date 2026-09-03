"""Outcome-blind scheduling for the first compact multi-goal Red calibration.

The schedule is intentionally smaller than an independent evaluation.  It uses
still-open historical train roots to measure the outcomes of every supported
model-controlled option from the same reset.  Selection is mechanical: frozen
source order, required goal-family quotas, and no model score, teacher choice,
or observed outcome.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.provenance import canonical_sha256

MULTI_GOAL_CALIBRATION_PLAN_SCHEMA = "pokemon.red.multi-goal-calibration-plan.v1"
MULTI_GOAL_CALIBRATION_SCHEDULE_SCHEMA = (
    "pokemon.red.multi-goal-calibration-schedule.v1"
)

CALIBRATION_ROOT_QUOTAS: tuple[tuple[GoalKind, int], ...] = (
    (GoalKind.DEVELOP_TEAM, 1),
    (GoalKind.EVOLVE_SPECIES, 1),
    (GoalKind.MANAGE_STORAGE, 2),
)
MODEL_CONTROLLED_GOAL_KINDS = frozenset(
    {
        GoalKind.ADVANCE_STORY,
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.DEVELOP_TEAM,
        GoalKind.EVOLVE_SPECIES,
        GoalKind.RESUPPLY,
        GoalKind.MANAGE_STORAGE,
        GoalKind.EXPLORE,
    }
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")


class MultiGoalCalibrationPlanError(ValueError):
    """Raised when an input bank cannot form the frozen calibration schedule."""


@dataclass(frozen=True, slots=True)
class CalibrationRootCandidate:
    """One action-free, claim-aware root in authenticated source order."""

    slot_id: str
    focus_kind: GoalKind
    state_sha256: str
    envelope_sha256: str
    profile_sha256: str
    physical_root_sha256: str
    available_goal_kinds: tuple[GoalKind, ...]
    claim_available: bool

    def __post_init__(self) -> None:
        if _SAFE_ID.fullmatch(self.slot_id) is None:
            raise MultiGoalCalibrationPlanError("calibration slot identity is invalid")
        if not isinstance(self.focus_kind, GoalKind):
            raise MultiGoalCalibrationPlanError("calibration focus kind is invalid")
        for value in (
            self.state_sha256,
            self.envelope_sha256,
            self.profile_sha256,
            self.physical_root_sha256,
        ):
            if _SHA256.fullmatch(value) is None:
                raise MultiGoalCalibrationPlanError(
                    "calibration root digest is invalid"
                )
        if (
            not self.available_goal_kinds
            or len(set(self.available_goal_kinds)) != len(self.available_goal_kinds)
            or any(not isinstance(kind, GoalKind) for kind in self.available_goal_kinds)
        ):
            raise MultiGoalCalibrationPlanError(
                "calibration available-goal menu is invalid"
            )
        if type(self.claim_available) is not bool:  # noqa: E721
            raise MultiGoalCalibrationPlanError("calibration claim state is invalid")

    @property
    def model_controlled_goal_kinds(self) -> tuple[GoalKind, ...]:
        return tuple(
            kind
            for kind in self.available_goal_kinds
            if kind in MODEL_CONTROLLED_GOAL_KINDS
        )

    @property
    def eligible(self) -> bool:
        learnable = self.model_controlled_goal_kinds
        return (
            self.claim_available
            and self.focus_kind in learnable
            and len(learnable) >= 2
        )


@dataclass(frozen=True, slots=True)
class CalibrationTrial:
    """One forced semantic option from an independently restored root."""

    trial_ordinal: int
    root_ordinal: int
    selected_candidate_index: int
    selected_goal_kind: GoalKind

    def __post_init__(self) -> None:
        if (
            type(self.trial_ordinal) is not int  # noqa: E721
            or self.trial_ordinal < 0
            or type(self.root_ordinal) is not int  # noqa: E721
            or self.root_ordinal < 0
            or type(self.selected_candidate_index) is not int  # noqa: E721
            or self.selected_candidate_index < 0
            or not isinstance(self.selected_goal_kind, GoalKind)
        ):
            raise MultiGoalCalibrationPlanError("calibration trial is invalid")

    def private_dict(self) -> dict[str, object]:
        return {
            "maximum_decisions": 1,
            "root_ordinal": self.root_ordinal,
            "selected_candidate_index": self.selected_candidate_index,
            "selected_goal_kind": self.selected_goal_kind.value,
            "trial_ordinal": self.trial_ordinal,
        }


@dataclass(frozen=True, slots=True)
class MultiGoalCalibrationSchedule:
    """Selected roots and their equal-reset candidate interventions."""

    roots: tuple[CalibrationRootCandidate, ...]
    trials: tuple[CalibrationTrial, ...]

    def __post_init__(self) -> None:
        if len(self.roots) != sum(count for _kind, count in CALIBRATION_ROOT_QUOTAS):
            raise MultiGoalCalibrationPlanError("calibration root denominator differs")
        if not self.trials:
            raise MultiGoalCalibrationPlanError("calibration trial denominator is empty")
        for trial in self.trials:
            if trial.root_ordinal >= len(self.roots):
                raise MultiGoalCalibrationPlanError("calibration trial root differs")
            root = self.roots[trial.root_ordinal]
            if (
                trial.selected_candidate_index >= len(root.available_goal_kinds)
                or root.available_goal_kinds[trial.selected_candidate_index]
                is not trial.selected_goal_kind
                or trial.selected_goal_kind not in MODEL_CONTROLLED_GOAL_KINDS
            ):
                raise MultiGoalCalibrationPlanError(
                    "calibration trial candidate binding differs"
                )

    @property
    def schedule_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "root_slot_ids": [root.slot_id for root in self.roots],
            "schema": MULTI_GOAL_CALIBRATION_SCHEDULE_SCHEMA,
            "trials": [trial.private_dict() for trial in self.trials],
        }

    def public_dict(self) -> dict[str, object]:
        root_counts = Counter(root.focus_kind.value for root in self.roots)
        trial_counts = Counter(trial.selected_goal_kind.value for trial in self.trials)
        return {
            "schema": MULTI_GOAL_CALIBRATION_PLAN_SCHEMA,
            "status": "compact_train_calibration_schedule_ready",
            "selection_rule": "first-eligible-open-train-root-in-authenticated-source-order",
            "candidate_rule": "every-model-controlled-option-from-identical-reset",
            "schedule_sha256": self.schedule_sha256,
            "root_count": len(self.roots),
            "root_family_counts": dict(sorted(root_counts.items())),
            "trial_count": len(self.trials),
            "trial_goal_counts": dict(sorted(trial_counts.items())),
            "partition": "train",
            "maximum_decisions_per_trial": 1,
            "teacher_queries": 0,
            "model_predictions": 0,
            "outcomes_opened": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "development_labels_opened": 0,
            "held_out_claim": False,
            "transfer_claim": False,
            "private_path_fields": 0,
        }


def build_multi_goal_calibration_schedule(
    candidates: tuple[CalibrationRootCandidate, ...],
) -> MultiGoalCalibrationSchedule:
    """Select the fixed root quotas and enumerate every learnable intervention."""

    if not candidates:
        raise MultiGoalCalibrationPlanError("calibration candidate bank is empty")
    selected: list[CalibrationRootCandidate] = []
    used_physical_roots: set[str] = set()
    used_capture_pairs: set[tuple[str, str]] = set()
    for focus_kind, required_count in CALIBRATION_ROOT_QUOTAS:
        matching = 0
        for candidate in candidates:
            capture_pair = (candidate.state_sha256, candidate.envelope_sha256)
            if (
                candidate.focus_kind is not focus_kind
                or not candidate.eligible
                or candidate.physical_root_sha256 in used_physical_roots
                or capture_pair in used_capture_pairs
            ):
                continue
            selected.append(candidate)
            used_physical_roots.add(candidate.physical_root_sha256)
            used_capture_pairs.add(capture_pair)
            matching += 1
            if matching == required_count:
                break
        if matching != required_count:
            raise MultiGoalCalibrationPlanError(
                f"insufficient open {focus_kind.value} calibration roots"
            )

    trials: list[CalibrationTrial] = []
    for root_ordinal, root in enumerate(selected):
        for candidate_index, goal_kind in enumerate(root.available_goal_kinds):
            if goal_kind not in MODEL_CONTROLLED_GOAL_KINDS:
                continue
            trials.append(
                CalibrationTrial(
                    trial_ordinal=len(trials),
                    root_ordinal=root_ordinal,
                    selected_candidate_index=candidate_index,
                    selected_goal_kind=goal_kind,
                )
            )
    return MultiGoalCalibrationSchedule(roots=tuple(selected), trials=tuple(trials))

