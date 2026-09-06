"""Read-only local dashboard for live game and learning progress.

The dashboard is an observer, never an actor.  It exposes no controller route,
accepts no writes over HTTP, and keeps ROM bytes, save states, filesystem paths,
raw addresses, and private binding identities out of its status payload.  A run
may publish semantic snapshots and rendered emulator frames without giving the
browser any way to influence execution.
"""

# The embedded HTML/CSS/JavaScript remains readable as source and is exempt
# from Python's line-length rule.
# ruff: noqa: E501

from __future__ import annotations

import binascii
import json
import math
import re
import struct
import threading
import time
import zlib
from collections.abc import Callable
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType

DASHBOARD_SCHEMA = "pokemon.core.progress-dashboard.v1"
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_DEFAULT_PORT = 8765
DASHBOARD_FRAME_WIDTH = 160
DASHBOARD_FRAME_HEIGHT = 144
_MAX_FRAME_BYTES = 2 * 1024 * 1024
_MAX_EVENTS = 24


class ProgressDashboardError(ValueError):
    """Raised when dashboard data is unsafe or internally inconsistent."""


def _plain_text(value: object, *, subject: str, maximum: int = 160) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ProgressDashboardError(f"{subject} must be non-empty text")
    if any(character in value for character in ("\n", "\r", "\x00")):
        raise ProgressDashboardError(f"{subject} must be one line")
    return value


def _count(value: object, *, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise ProgressDashboardError(f"{subject} must be a non-negative integer")
    return value


def _unit_interval(value: object, *, subject: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ProgressDashboardError(f"{subject} must be between zero and one")
    return float(value)


@dataclass(frozen=True, slots=True)
class DashboardPartyMember:
    slot: int
    label: str
    level: int
    hp: int
    max_hp: int
    status: str = "healthy"

    def __post_init__(self) -> None:
        if type(self.slot) is not int or not 1 <= self.slot <= 6:
            raise ProgressDashboardError("party slot must be between one and six")
        _plain_text(self.label, subject="party label", maximum=48)
        if type(self.level) is not int or not 1 <= self.level <= 100:
            raise ProgressDashboardError("party level must be between one and one hundred")
        if type(self.max_hp) is not int or self.max_hp <= 0:
            raise ProgressDashboardError("party maximum HP must be positive")
        if type(self.hp) is not int or not 0 <= self.hp <= self.max_hp:
            raise ProgressDashboardError("party HP must be between zero and maximum HP")
        _plain_text(self.status, subject="party status", maximum=32)

    def public_dict(self) -> dict[str, object]:
        return {
            "slot": self.slot,
            "label": self.label,
            "level": self.level,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "status": self.status,
            "hp_ratio": self.hp / self.max_hp,
        }


@dataclass(frozen=True, slots=True)
class DashboardGoalPressure:
    goal: str
    pressure: float
    available: bool
    selected: bool = False

    def __post_init__(self) -> None:
        _plain_text(self.goal, subject="goal", maximum=48)
        _unit_interval(self.pressure, subject="goal pressure")
        if not isinstance(self.available, bool) or not isinstance(self.selected, bool):
            raise ProgressDashboardError("goal availability and selection must be boolean")
        if self.selected and not self.available:
            raise ProgressDashboardError("an unavailable goal cannot be selected")

    def public_dict(self) -> dict[str, object]:
        return {
            "goal": self.goal,
            "pressure": self.pressure,
            "available": self.available,
            "selected": self.selected,
        }


@dataclass(frozen=True, slots=True)
class DashboardModelState:
    mode: str = "waiting"
    candidate: str = "Red frozen goal manager"
    choice: str | None = None
    confidence: float | None = None
    decisions: int = 0
    teacher_queries: int = 0
    fallbacks: int = 0

    def __post_init__(self) -> None:
        if self.mode not in {"waiting", "zero_shot", "shadow", "teacher", "model", "fitting"}:
            raise ProgressDashboardError("model mode is unknown")
        _plain_text(self.candidate, subject="model candidate", maximum=96)
        if self.choice is not None:
            _plain_text(self.choice, subject="model choice", maximum=96)
        if self.confidence is not None:
            _unit_interval(self.confidence, subject="model confidence")
        _count(self.decisions, subject="model decisions")
        _count(self.teacher_queries, subject="teacher queries")
        _count(self.fallbacks, subject="model fallbacks")

    def public_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "candidate": self.candidate,
            "choice": self.choice,
            "confidence": self.confidence,
            "decisions": self.decisions,
            "teacher_queries": self.teacher_queries,
            "fallbacks": self.fallbacks,
        }


@dataclass(frozen=True, slots=True)
class DashboardLearningComponent:
    """One path-free learned head and the evidence supporting it."""

    name: str
    scope: str
    status: str
    authority: str
    train_examples: int
    validation_examples: int
    validation_correct: int
    baseline_correct: int | None
    model_sha256: str
    independent_validation_units: int
    baseline_id: str | None = None
    paired_wins: int | None = None
    paired_losses: int | None = None
    paired_two_sided_exact_p: float | None = None
    candidate_count_results: tuple[tuple[int, int, int], ...] = ()

    def __post_init__(self) -> None:
        _plain_text(self.name, subject="learning component name", maximum=64)
        _plain_text(self.scope, subject="learning component scope", maximum=120)
        if self.status not in {"fitting", "passed", "shadow", "offline", "causal", "blocked"}:
            raise ProgressDashboardError("learning component status is unknown")
        if self.authority not in {"offline", "shadow_only", "teacher_supervised", "causal"}:
            raise ProgressDashboardError("learning component authority is unknown")
        _count(self.train_examples, subject="learning component train examples")
        _count(self.validation_examples, subject="learning component validation examples")
        _count(self.validation_correct, subject="learning component validation correct")
        if self.validation_correct > self.validation_examples:
            raise ProgressDashboardError(
                "learning component validation correct cannot exceed examples"
            )
        if self.baseline_correct is not None:
            _count(self.baseline_correct, subject="learning component baseline correct")
            if self.baseline_correct > self.validation_examples:
                raise ProgressDashboardError(
                    "learning component baseline correct cannot exceed examples"
                )
        _count(
            self.independent_validation_units,
            subject="learning component independent validation units",
        )
        if self.independent_validation_units > self.validation_examples:
            raise ProgressDashboardError(
                "independent validation units cannot exceed validation examples"
            )
        if self.baseline_id is not None:
            _plain_text(self.baseline_id, subject="learning component baseline", maximum=64)
        paired = (self.paired_wins, self.paired_losses, self.paired_two_sided_exact_p)
        if any(value is not None for value in paired):
            if any(value is None for value in paired):
                raise ProgressDashboardError("paired comparison must be complete")
            assert self.paired_wins is not None
            assert self.paired_losses is not None
            assert self.paired_two_sided_exact_p is not None
            _count(self.paired_wins, subject="learning component paired wins")
            _count(self.paired_losses, subject="learning component paired losses")
            _unit_interval(
                self.paired_two_sided_exact_p,
                subject="learning component paired p-value",
            )
        seen_candidate_counts: set[int] = set()
        for candidate_count, correct, total in self.candidate_count_results:
            if candidate_count < 2 or candidate_count in seen_candidate_counts:
                raise ProgressDashboardError("candidate-count result identity is invalid")
            seen_candidate_counts.add(candidate_count)
            _count(correct, subject="candidate-count correct")
            _count(total, subject="candidate-count total")
            if total == 0 or correct > total:
                raise ProgressDashboardError("candidate-count result is invalid")
        if re.fullmatch(r"[0-9a-f]{64}", self.model_sha256) is None:
            raise ProgressDashboardError("learning component model SHA-256 is invalid")

    @property
    def validation_accuracy(self) -> float | None:
        return (
            self.validation_correct / self.validation_examples
            if self.validation_examples
            else None
        )

    @property
    def baseline_accuracy(self) -> float | None:
        return (
            self.baseline_correct / self.validation_examples
            if self.baseline_correct is not None and self.validation_examples
            else None
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "scope": self.scope,
            "status": self.status,
            "authority": self.authority,
            "train_examples": self.train_examples,
            "validation_examples": self.validation_examples,
            "validation_correct": self.validation_correct,
            "validation_accuracy": self.validation_accuracy,
            "baseline_correct": self.baseline_correct,
            "baseline_accuracy": self.baseline_accuracy,
            "baseline_id": self.baseline_id,
            "independent_validation_units": self.independent_validation_units,
            "paired_comparison": (
                {
                    "wins": self.paired_wins,
                    "losses": self.paired_losses,
                    "two_sided_exact_p": self.paired_two_sided_exact_p,
                }
                if self.paired_wins is not None
                else None
            ),
            "candidate_count_results": {
                str(candidate_count): {
                    "correct": correct,
                    "total": total,
                    "accuracy": correct / total,
                }
                for candidate_count, correct, total in self.candidate_count_results
            },
            "model_sha256": self.model_sha256,
        }


@dataclass(frozen=True, slots=True)
class DashboardLiveEvaluationState:
    """Exact counters from a teacher-supervised live evaluation."""

    battle_decisions: int = 0
    teacher_agreements: int = 0
    teacher_disagreements: int = 0
    teacher_queries: int = 0
    teacher_fallbacks: int = 0
    corrections_saved: int = 0
    low_confidence_fallbacks: int = 0
    unsupported_observations: int = 0
    non_move_control_decisions: int = 0
    failed_decisions: int = 0
    interrupted_decisions: int = 0
    unclassified_decisions: int = 0
    team_decisions: int = 0
    team_agreements: int = 0

    def __post_init__(self) -> None:
        for name in (
            "battle_decisions",
            "teacher_agreements",
            "teacher_disagreements",
            "teacher_queries",
            "teacher_fallbacks",
            "corrections_saved",
            "low_confidence_fallbacks",
            "unsupported_observations",
            "non_move_control_decisions",
            "failed_decisions",
            "interrupted_decisions",
            "unclassified_decisions",
            "team_decisions",
            "team_agreements",
        ):
            _count(getattr(self, name), subject=name.replace("_", " "))
        comparisons = self.teacher_agreements + self.teacher_disagreements
        if comparisons > self.teacher_queries:
            raise ProgressDashboardError("teacher comparisons cannot exceed teacher queries")
        if self.teacher_fallbacks > self.teacher_queries:
            raise ProgressDashboardError("teacher fallbacks cannot exceed teacher queries")
        if self.corrections_saved > self.teacher_fallbacks:
            raise ProgressDashboardError("saved corrections cannot exceed teacher fallbacks")
        if self.low_confidence_fallbacks > self.teacher_fallbacks:
            raise ProgressDashboardError(
                "low-confidence fallbacks cannot exceed teacher fallbacks"
            )
        if self.unsupported_observations > (
            self.teacher_fallbacks
            + self.non_move_control_decisions
            + self.failed_decisions
            + self.interrupted_decisions
        ):
            raise ProgressDashboardError(
                "unsupported observations exceed their terminal outcomes"
            )
        if self.low_confidence_fallbacks + self.unsupported_observations > (
            self.teacher_fallbacks
            + self.non_move_control_decisions
            + self.failed_decisions
            + self.interrupted_decisions
        ):
            raise ProgressDashboardError(
                "typed fallback triggers exceed their terminal outcomes"
            )
        if self.team_agreements > self.team_decisions:
            raise ProgressDashboardError("team agreements cannot exceed team decisions")
        accounted = (
            self.teacher_agreements
            + self.teacher_fallbacks
            + self.non_move_control_decisions
            + self.failed_decisions
            + self.interrupted_decisions
            + self.unclassified_decisions
        )
        if accounted != self.battle_decisions:
            raise ProgressDashboardError(
                "battle decisions must equal model executions, teacher fallbacks, control "
                "decisions, failures, and explicitly unclassified decisions"
            )

    def public_dict(self) -> dict[str, object]:
        comparisons = self.teacher_agreements + self.teacher_disagreements
        return {
            "battle_decisions": self.battle_decisions,
            "teacher_agreements": self.teacher_agreements,
            "teacher_disagreements": self.teacher_disagreements,
            "teacher_queries": self.teacher_queries,
            "teacher_fallbacks": self.teacher_fallbacks,
            "corrections_saved": self.corrections_saved,
            "low_confidence_fallbacks": self.low_confidence_fallbacks,
            "unsupported_observations": self.unsupported_observations,
            "non_move_control_decisions": self.non_move_control_decisions,
            "failed_decisions": self.failed_decisions,
            "interrupted_decisions": self.interrupted_decisions,
            "unclassified_decisions": self.unclassified_decisions,
            "accounted_decisions": self.battle_decisions,
            "decision_accounting_complete": self.unclassified_decisions == 0,
            "teacher_agreement_rate": (
                self.teacher_agreements / comparisons if comparisons else None
            ),
            "teacher_agreement_denominator": comparisons,
            "model_execution_rate": (
                self.teacher_agreements / self.battle_decisions
                if self.battle_decisions
                else None
            ),
            "model_execution_denominator": self.battle_decisions,
            "team_decisions": self.team_decisions,
            "team_agreements": self.team_agreements,
            "team_accuracy": (
                self.team_agreements / self.team_decisions if self.team_decisions else None
            ),
        }


@dataclass(frozen=True, slots=True)
class DashboardExperimentState:
    phase: str = "qualification"
    zero_shot_completed: int = 0
    zero_shot_total: int = 18
    adaptation_completed: int = 0
    adaptation_total: int = 27
    sealed_completed: int = 0
    sealed_total: int = 27
    predictions_committed: bool = False
    heading: str = "Transfer experiment"
    eyebrow: str = "Transfer learning run"
    counter_labels: tuple[str, str, str] = (
        "Zero-shot probe",
        "Adaptation examples",
        "Sealed test",
    )

    def __post_init__(self) -> None:
        if self.phase not in {
            "qualification",
            "catalog",
            "zero_shot",
            "adaptation",
            "fitting",
            "prediction_commit",
            "sealed_test",
            "complete",
            "blocked",
            "training",
            "live_evaluation",
        }:
            raise ProgressDashboardError("experiment phase is unknown")
        for prefix in ("zero_shot", "adaptation", "sealed"):
            completed = _count(getattr(self, f"{prefix}_completed"), subject=f"{prefix} completed")
            total = _count(getattr(self, f"{prefix}_total"), subject=f"{prefix} total")
            if completed > total:
                raise ProgressDashboardError(f"{prefix} completed cannot exceed total")
        if not isinstance(self.predictions_committed, bool):
            raise ProgressDashboardError("prediction commitment flag must be boolean")
        _plain_text(self.heading, subject="experiment heading", maximum=64)
        _plain_text(self.eyebrow, subject="experiment eyebrow", maximum=64)
        if (
            not isinstance(self.counter_labels, tuple)
            or len(self.counter_labels) != 3
        ):
            raise ProgressDashboardError("experiment counter labels must contain three entries")
        for label in self.counter_labels:
            _plain_text(label, subject="experiment counter label", maximum=64)

    def public_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "zero_shot": {
                "completed": self.zero_shot_completed,
                "total": self.zero_shot_total,
            },
            "adaptation": {
                "completed": self.adaptation_completed,
                "total": self.adaptation_total,
            },
            "sealed_test": {
                "completed": self.sealed_completed,
                "total": self.sealed_total,
            },
            "predictions_committed": self.predictions_committed,
            "heading": self.heading,
            "eyebrow": self.eyebrow,
            "counter_labels": {
                "zero_shot": self.counter_labels[0],
                "adaptation": self.counter_labels[1],
                "sealed_test": self.counter_labels[2],
            },
        }


@dataclass(frozen=True, slots=True)
class DashboardWorkState:
    """Human-readable, path-free status for the current engineering session."""

    status: str = "idle"
    headline: str = "No engineering session is active"
    detail: str = "The dashboard is available and waiting for the next project update."
    current_step: str = "Waiting"
    next_step: str = "Start the next bounded project session"
    completed_units: int = 0
    total_units: int = 0
    updated_at_utc: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {
            "idle",
            "working",
            "testing",
            "waiting",
            "blocked",
            "complete",
        }:
            raise ProgressDashboardError("work status is unknown")
        _plain_text(self.headline, subject="work headline", maximum=120)
        _plain_text(self.detail, subject="work detail", maximum=240)
        _plain_text(self.current_step, subject="current work step", maximum=120)
        _plain_text(self.next_step, subject="next work step", maximum=160)
        completed = _count(self.completed_units, subject="completed work units")
        total = _count(self.total_units, subject="total work units")
        if completed > total:
            raise ProgressDashboardError("completed work units cannot exceed total")
        if self.updated_at_utc is not None and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
            self.updated_at_utc,
        ) is None:
            raise ProgressDashboardError("work update timestamp is invalid")

    @property
    def progress(self) -> float | None:
        return self.completed_units / self.total_units if self.total_units else None

    def public_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "headline": self.headline,
            "detail": self.detail,
            "current_step": self.current_step,
            "next_step": self.next_step,
            "completed_units": self.completed_units,
            "total_units": self.total_units,
            "progress": self.progress,
            "updated_at_utc": self.updated_at_utc,
        }


@dataclass(frozen=True, slots=True)
class DashboardTrainingState:
    """Completed training evidence, never a claim of live or held-out performance."""

    samples_before: int
    samples_after: int
    newly_collected: int
    previously_unfitted: int
    successful_examples: int
    terminal_lessons: int
    total_lessons: int
    setup_censors: int
    fit_count: int
    weighted_mse_before: float
    weighted_mse_after: float
    training_choice_changes: int

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            if key.startswith("weighted_mse"):
                if (
                    isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0
                ):
                    raise ProgressDashboardError("training error must be finite and non-negative")
            else:
                _count(value, subject=f"training {key}")
        if (
            self.samples_after
            != self.samples_before + self.previously_unfitted + self.newly_collected
            or self.successful_examples > self.samples_after
            or self.terminal_lessons != self.total_lessons
            or self.setup_censors + self.newly_collected != self.terminal_lessons
            or self.fit_count != 1
            or self.training_choice_changes > self.samples_after
        ):
            raise ProgressDashboardError("completed training evidence accounting differs")

    def public_dict(self) -> dict[str, object]:
        return {**asdict(self), "evidence_scope": "training_only", "held_out_claim": False}


@dataclass(frozen=True, slots=True)
class DashboardRunStep:
    goal: str
    authority: str
    status: str
    actions: int
    frames: int
    new_living_species: int
    needed_specimens_gained: int

    def __post_init__(self) -> None:
        _plain_text(self.goal, subject="saved goal", maximum=40)
        if self.authority not in {"model", "safety", "unsupported", "forced"}:
            raise ProgressDashboardError("saved step authority differs")
        if self.status not in {"succeeded", "failed", "interrupted"}:
            raise ProgressDashboardError("saved step status differs")
        for key in ("actions", "frames", "new_living_species", "needed_specimens_gained"):
            _count(getattr(self, key), subject=key)


@dataclass(frozen=True, slots=True)
class DashboardRunRecap:
    """Receipt-backed historical play, completely separate from live freshness."""

    heading: str
    scope: str
    limitation: str
    steps: tuple[DashboardRunStep, ...]
    living_before: int
    living_after: int
    money_before: int
    money_after: int
    capture_items_before: int
    capture_items_after: int
    controller_actions: int
    emulator_frames: int
    control_successes: int
    control_decisions: int
    control_failed: bool

    def __post_init__(self) -> None:
        _plain_text(self.heading, subject="saved run heading", maximum=80)
        _plain_text(self.scope, subject="saved run scope", maximum=160)
        _plain_text(self.limitation, subject="saved run limitation", maximum=240)
        if not isinstance(self.steps, tuple) or not 1 <= len(self.steps) <= 4:
            raise ProgressDashboardError("saved run step count differs")
        for step in self.steps:
            if not isinstance(step, DashboardRunStep):
                raise ProgressDashboardError("saved run step must be typed")
            step.__post_init__()
        for key in (
            "living_before", "living_after", "money_before", "money_after",
            "capture_items_before", "capture_items_after", "controller_actions",
            "emulator_frames", "control_successes", "control_decisions",
        ):
            _count(getattr(self, key), subject=key)
        if (
            sum(step.actions for step in self.steps) != self.controller_actions
            or sum(step.frames for step in self.steps) != self.emulator_frames
            or sum(step.new_living_species for step in self.steps)
            != self.living_after - self.living_before
            or self.control_successes > self.control_decisions
            or not isinstance(self.control_failed, bool)
        ):
            raise ProgressDashboardError("saved run accounting differs")

    def public_dict(self) -> dict[str, object]:
        return {
            **asdict(self), "live": False, "training_data": False,
            "independent_generalization_claim": False,
        }


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    """One identity-safe, human-facing status update."""

    game: str
    run_status: str
    stage: str
    message: str
    frame_count: int = 0
    actions: int = 0
    emulation_speed: float = 0.0
    stage_progress: float = 0.0
    location: str | None = None
    registered_species: int = 0
    living_species: int = 0
    level_cap_species: int = 0
    collection_target: int = 250
    capture_items: int = 0
    free_storage_slots: int = 0
    party: tuple[DashboardPartyMember, ...] = ()
    goals: tuple[DashboardGoalPressure, ...] = ()
    model: DashboardModelState = DashboardModelState()
    experiment: DashboardExperimentState = DashboardExperimentState()
    learning_components: tuple[DashboardLearningComponent, ...] = ()
    live_evaluation: DashboardLiveEvaluationState | None = None
    work: DashboardWorkState = DashboardWorkState()
    events: tuple[str, ...] = ()
    collection_observed: bool = True
    training: DashboardTrainingState | None = None
    last_run: DashboardRunRecap | None = None

    def __post_init__(self) -> None:
        _plain_text(self.game, subject="game", maximum=64)
        if not isinstance(self.collection_observed, bool):
            raise ProgressDashboardError("collection observation flag must be boolean")
        if self.training is not None:
            if not isinstance(self.training, DashboardTrainingState):
                raise ProgressDashboardError("training evidence must be typed")
            self.training.__post_init__()
        if self.last_run is not None:
            if not isinstance(self.last_run, DashboardRunRecap):
                raise ProgressDashboardError("saved run must be typed")
            self.last_run.__post_init__()
        if self.run_status not in {"waiting", "running", "paused", "passed", "failed", "blocked"}:
            raise ProgressDashboardError("run status is unknown")
        _plain_text(self.stage, subject="stage", maximum=96)
        _plain_text(self.message, subject="message", maximum=240)
        _count(self.frame_count, subject="frame count")
        _count(self.actions, subject="actions")
        if (
            not isinstance(self.emulation_speed, (int, float))
            or isinstance(self.emulation_speed, bool)
            or not math.isfinite(float(self.emulation_speed))
            or float(self.emulation_speed) < 0.0
        ):
            raise ProgressDashboardError("emulation speed must be non-negative")
        _unit_interval(self.stage_progress, subject="stage progress")
        if self.location is not None:
            _plain_text(self.location, subject="location", maximum=96)
        for name in (
            "registered_species",
            "living_species",
            "level_cap_species",
            "collection_target",
            "capture_items",
            "free_storage_slots",
        ):
            _count(getattr(self, name), subject=name.replace("_", " "))
        if self.collection_target < 1:
            raise ProgressDashboardError("collection target must be positive")
        if not 0 <= self.level_cap_species <= self.living_species <= self.registered_species:
            raise ProgressDashboardError("collection counts are inconsistent")
        if self.registered_species > self.collection_target:
            raise ProgressDashboardError("registered collection exceeds its target")
        if any(not isinstance(item, DashboardPartyMember) for item in self.party):
            raise ProgressDashboardError("party entries are invalid")
        if tuple(item.slot for item in self.party) != tuple(range(1, len(self.party) + 1)):
            raise ProgressDashboardError("party entries must use contiguous slots")
        if any(not isinstance(item, DashboardGoalPressure) for item in self.goals):
            raise ProgressDashboardError("goal pressures are invalid")
        if sum(item.selected for item in self.goals) > 1:
            raise ProgressDashboardError("at most one goal can be selected")
        if not isinstance(self.model, DashboardModelState):
            raise ProgressDashboardError("model state is invalid")
        if not isinstance(self.experiment, DashboardExperimentState):
            raise ProgressDashboardError("experiment state is invalid")
        if any(
            not isinstance(item, DashboardLearningComponent)
            for item in self.learning_components
        ):
            raise ProgressDashboardError("learning components are invalid")
        component_names = tuple(item.name for item in self.learning_components)
        if len(component_names) != len(set(component_names)):
            raise ProgressDashboardError("learning component names must be unique")
        if self.live_evaluation is not None:
            if not isinstance(self.live_evaluation, DashboardLiveEvaluationState):
                raise ProgressDashboardError("live evaluation state is invalid")
            if self.live_evaluation.battle_decisions != self.model.decisions:
                raise ProgressDashboardError("live battle decisions must match model decisions")
            if self.live_evaluation.teacher_queries != self.model.teacher_queries:
                raise ProgressDashboardError("live teacher queries must match model state")
            if self.live_evaluation.teacher_fallbacks != self.model.fallbacks:
                raise ProgressDashboardError("live teacher fallbacks must match model state")
        if not isinstance(self.work, DashboardWorkState):
            raise ProgressDashboardError("dashboard work state is invalid")
        self.work.__post_init__()
        if len(self.events) > _MAX_EVENTS:
            raise ProgressDashboardError("dashboard event history is too long")
        for event in self.events:
            _plain_text(event, subject="dashboard event", maximum=180)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": DASHBOARD_SCHEMA,
            "game": self.game,
            "run_status": self.run_status,
            "stage": self.stage,
            "message": self.message,
            "frame_count": self.frame_count,
            "actions": self.actions,
            "emulation_speed": float(self.emulation_speed),
            "stage_progress": float(self.stage_progress),
            "location": self.location,
            "collection": {
                "observed": self.collection_observed,
                "registered": self.registered_species,
                "living": self.living_species,
                "level_cap": self.level_cap_species,
                "target": self.collection_target,
            },
            "resources": {
                "capture_items": self.capture_items,
                "free_storage_slots": self.free_storage_slots,
            },
            "party": [item.public_dict() for item in self.party],
            "goals": [item.public_dict() for item in self.goals],
            "model": self.model.public_dict(),
            "experiment": self.experiment.public_dict(),
            "learning_components": [
                component.public_dict() for component in self.learning_components
            ],
            "live_evaluation": (
                self.live_evaluation.public_dict()
                if self.live_evaluation is not None
                else None
            ),
            "work": self.work.public_dict(),
            "training": self.training.public_dict() if self.training is not None else None,
            **({"last_run": self.last_run.public_dict()} if self.last_run is not None else {}),
            "events": list(self.events),
            "private_path_fields": 0,
            "raw_address_fields": 0,
            "controller_endpoints": 0,
        }


def waiting_dashboard_snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        game="Pokémon Crystal 1.1",
        run_status="waiting",
        stage="Live adapter qualification",
        message="Waiting for the authenticated emulator session.",
        experiment=DashboardExperimentState(),
        events=("Crystal 1.1 cartridge identity verified",),
    )


def encode_rgb_png(width: int, height: int, rgb: bytes) -> bytes:
    """Encode an 8-bit RGB frame as a dependency-free PNG."""

    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise ProgressDashboardError("frame dimensions must be positive integers")
    if not isinstance(rgb, bytes) or len(rgb) != width * height * 3:
        raise ProgressDashboardError("RGB frame length differs from its dimensions")

    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = binascii.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    rows = b"".join(
        b"\x00" + rgb[row * width * 3 : (row + 1) * width * 3]
        for row in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(
        b"IDAT", zlib.compress(rows, level=6)
    ) + chunk(b"IEND", b"")


class DashboardState:
    """Thread-safe latest-value store shared by the run and local HTTP server."""

    def __init__(
        self,
        snapshot: DashboardSnapshot | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self._snapshot_updated_at = clock()
        self._frame_updated_at: float | None = None
        self._snapshot = snapshot or waiting_dashboard_snapshot()
        self._snapshot_version = 1
        self._frame_png = encode_rgb_png(
            DASHBOARD_FRAME_WIDTH,
            DASHBOARD_FRAME_HEIGHT,
            bytes((20, 28, 26)) * DASHBOARD_FRAME_WIDTH * DASHBOARD_FRAME_HEIGHT,
        )
        self._frame_version = 0
        self._logical_frame = 0

    def publish(self, snapshot: DashboardSnapshot) -> None:
        if not isinstance(snapshot, DashboardSnapshot):
            raise TypeError("snapshot must be DashboardSnapshot")
        with self._lock:
            self._snapshot = snapshot
            self._snapshot_version += 1
            self._snapshot_updated_at = self._clock()

    def publish_png(self, payload: bytes, *, logical_frame: int) -> None:
        if (
            not isinstance(payload, bytes)
            or not payload.startswith(b"\x89PNG\r\n\x1a\n")
            or len(payload) > _MAX_FRAME_BYTES
        ):
            raise ProgressDashboardError("dashboard frame must be a bounded PNG")
        _count(logical_frame, subject="logical frame")
        with self._lock:
            if logical_frame < self._logical_frame:
                raise ProgressDashboardError("dashboard frame count cannot move backward")
            self._frame_png = payload
            self._logical_frame = logical_frame
            self._frame_version += 1
            self._frame_updated_at = self._clock()

    def status_bytes(self) -> tuple[bytes, int]:
        with self._lock:
            document = self._snapshot.public_dict()
            now = self._clock()
            document["dashboard"] = {
                "snapshot_version": self._snapshot_version,
                "frame_version": self._frame_version,
                "frame_ready": self._frame_version > 0,
                "frame_age_seconds": (
                    max(0.0, now - self._frame_updated_at)
                    if self._frame_updated_at is not None else None
                ),
                "snapshot_age_seconds": max(0.0, now - self._snapshot_updated_at),
                "logical_frame": self._logical_frame,
                "view_only": True,
            }
            version = self._snapshot_version
        payload = json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        return payload, version

    def frame_bytes(self) -> tuple[bytes, int]:
        with self._lock:
            return self._frame_png, self._frame_version


class DashboardFrameObserver:
    """Rate-limited RGB frame sink used by :class:`PyBoyAdapter`."""

    def __init__(
        self,
        state: DashboardState,
        *,
        maximum_fps: float = 8.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(state, DashboardState):
            raise TypeError("state must be DashboardState")
        if (
            not isinstance(maximum_fps, (int, float))
            or isinstance(maximum_fps, bool)
            or not math.isfinite(float(maximum_fps))
            or not 1.0 <= float(maximum_fps) <= 30.0
        ):
            raise ProgressDashboardError("dashboard frame rate must be between 1 and 30")
        self._state = state
        self._minimum_interval = 1.0 / float(maximum_fps)
        self._clock = clock
        self._next_capture_at = 0.0

    def wants_frame(self, logical_frame: int) -> bool:
        _count(logical_frame, subject="logical frame")
        now = self._clock()
        if now < self._next_capture_at:
            return False
        self._next_capture_at = now + self._minimum_interval
        return True

    def publish_frame(self, width: int, height: int, rgb: bytes, logical_frame: int) -> None:
        self._state.publish_png(
            encode_rgb_png(width, height, rgb),
            logical_frame=logical_frame,
        )


class _DashboardHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: DashboardState) -> None:
        self.dashboard_state = state
        super().__init__(address, _DashboardRequestHandler)


class _DashboardRequestHandler(BaseHTTPRequestHandler):
    server: _DashboardHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", _DASHBOARD_HTML)
            return
        if path == "/api/status":
            payload, version = self.server.dashboard_state.status_bytes()
            self._send(
                HTTPStatus.OK,
                "application/json; charset=ascii",
                payload,
                etag=f'"status-{version}"',
            )
            return
        if path == "/frame.png":
            payload, version = self.server.dashboard_state.frame_bytes()
            self._send(HTTPStatus.OK, "image/png", payload, etag=f'"frame-{version}"')
            return
        if path == "/healthz":
            self._send(HTTPStatus.OK, "text/plain; charset=ascii", b"ok\n")
            return
        self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=ascii", b"not found\n")

    def do_POST(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "GET")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_PUT(self) -> None:  # noqa: N802
        self.do_POST()

    def do_DELETE(self) -> None:  # noqa: N802
        self.do_POST()

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _send(
        self,
        status: HTTPStatus,
        content_type: str,
        payload: bytes,
        *,
        etag: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
        )
        if etag is not None:
            self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(payload)


class ProgressDashboardServer:
    """Lifecycle wrapper around the loopback-only observer server."""

    def __init__(
        self,
        state: DashboardState | None = None,
        *,
        host: str = DASHBOARD_HOST,
        port: int = DASHBOARD_DEFAULT_PORT,
    ) -> None:
        if host != DASHBOARD_HOST:
            raise ProgressDashboardError("dashboard must bind to loopback only")
        if type(port) is not int or not 0 <= port <= 65_535:
            raise ProgressDashboardError("dashboard port must be between zero and 65535")
        self.state = state or DashboardState()
        self._server = _DashboardHTTPServer((host, port), self.state)
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        host_text = host.decode("ascii") if isinstance(host, bytes) else host
        return f"http://{host_text}:{port}/"

    def start(self) -> ProgressDashboardServer:
        if self._thread is not None:
            raise ProgressDashboardError("dashboard is already running")
        thread = threading.Thread(
            target=self._server.serve_forever,
            name="pokemon-progress-dashboard",
            daemon=True,
        )
        thread.start()
        self._thread = thread
        return self

    def close(self) -> None:
        thread = self._thread
        self._thread = None
        if thread is not None:
            self._server.shutdown()
            thread.join(timeout=5.0)
        self._server.server_close()

    def __enter__(self) -> ProgressDashboardServer:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


_DASHBOARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pokémon Learning Observatory</title>
</head><body>
<main id="observatory" aria-label="Pokémon live learning dashboard">
<style>
:root { color-scheme:dark; --bg:#0b0d13; --panel:#121620; --line:#2b303d; --muted:#a1a9ba; --text:#f4f5f8; --accent:#ff815c; --lime:#c2f785; --mono:ui-monospace,SFMono-Regular,Menlo,monospace; }
* { box-sizing:border-box; }
[hidden] { display:none !important; }
body { margin:0; color:var(--text); background:var(--bg); font:16px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }
#observatory { max-width:1640px; margin:auto; padding:26px 34px 48px; }
.top { display:flex; align-items:center; justify-content:space-between; gap:20px; margin-bottom:24px; padding-bottom:22px; border-bottom:1px solid var(--line); }
.eyebrow { color:var(--accent); font:600 12px/1.5 var(--mono); letter-spacing:.13em; text-transform:uppercase; }
h1 { margin:5px 0 0; font-size:clamp(22px,2.7vw,36px); font-weight:650; line-height:1.2; letter-spacing:-.045em; }
h2 { margin:0; font-size:17px; font-weight:600; letter-spacing:-.02em; }
.live { display:flex; align-items:center; flex-wrap:wrap; gap:10px; color:var(--muted); font:13px var(--mono); }
.dot { width:8px; height:8px; background:var(--muted); border-radius:50%; }
.dot.running { background:var(--lime); box-shadow:0 0 0 5px #c2f78512; }
.dot.failed,.dot.blocked { background:var(--accent); }
button { color:var(--text); background:#1b202d; border:1px solid #42495a; border-radius:6px; padding:9px 13px; font:500 14px/1.4 ui-sans-serif,system-ui,sans-serif; cursor:pointer; }
button:hover { border-color:var(--accent); }
button:focus-visible { outline:3px solid var(--lime); outline-offset:4px; }
.telemetry { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); border:1px solid var(--line); border-radius:10px; background:#10141c; margin-bottom:22px; }
.telemetry > div { padding:14px 20px; border-right:1px solid var(--line); }
.telemetry > div:last-child { border-right:0; }
.telemetry span { display:block; color:var(--muted); font:12px var(--mono); text-transform:uppercase; letter-spacing:.07em; }
.telemetry b { display:block; margin-top:5px; font-size:21px; letter-spacing:-.03em; font-weight:550; }
.telemetry .signal { color:var(--lime); }
.layout { display:grid; grid-template-columns:minmax(0,1.55fr) minmax(320px,1fr); grid-template-areas:"screen decision" "screen work" "recap recap" "party training" "goals stack" "events events" "mission mission"; gap:18px; align-items:start; }
#recap-panel { grid-area:recap; border-top:2px solid var(--lime); }
.recap-heading { display:flex; align-items:start; justify-content:space-between; gap:18px; flex-wrap:wrap; }
.recap-heading h2 { margin:0 0 7px; }
.recap-heading p { margin:0; }
.recap-metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin:22px 0; }
.recap-metrics span { display:block; font-size:14px; color:var(--muted); margin-bottom:6px; }
.recap-metrics b { font-size:clamp(20px,2.5vw,30px); font-variant-numeric:tabular-nums; }
.recap-metrics .cash { color:var(--accent); }
.recap-steps { list-style:none; padding:0; margin:18px 0; display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
.recap-step { background:#171c26; border:1px solid var(--line); border-top:3px solid #6b768b; border-radius:6px; padding:16px; min-width:0; }
.recap-step.model { border-top-color:var(--lime); }
.recap-step.safety { border-top-color:var(--accent); }
.recap-step strong { display:block; font-size:17px; margin:12px 0 8px; }
.recap-step small { display:block; color:var(--muted); font-size:13px; line-height:1.6; }
.recap-step .gain { color:var(--lime); font-size:14px; margin:12px 0 5px; }
.recap-step .authority { font:500 12px/1.4 ui-monospace,monospace; text-transform:uppercase; letter-spacing:.05em; }
.recap-foot { display:flex; flex-wrap:wrap; justify-content:space-between; gap:12px; font-size:14px; }
.recap-caution { color:#d5d9e3; font-size:14px; line-height:1.6; border-left:2px solid var(--accent); padding-left:12px; margin-bottom:0; }
.right { display:contents; }
.panel { min-width:0; background:var(--panel); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
.section { padding:22px; }
.screen-panel { grid-area:screen; padding:20px; border-top:3px solid var(--accent); background:#10141b; }
#decision-panel { grid-area:decision; border-top:3px solid var(--lime); }
#work-panel { grid-area:work; }
#collection-panel { grid-area:party; }
#experiment-panel { grid-area:training; }
#learning-components-panel { grid-area:stack; }
#goals-panel { grid-area:goals; }
#activity-panel { grid-area:events; }
#mission-panel { grid-area:mission; background:transparent; border-color:var(--line); }
#live-evaluation-panel { grid-column:1 / -1; }
.screen-heading { display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; color:var(--muted); font:12px var(--mono); letter-spacing:.08em; text-transform:uppercase; }
.screen-heading b { color:var(--accent); font-weight:500; }
.screen-shell { padding:18px; background:#080b10; border:1px solid #222734; border-radius:6px; }
.screen-bezel { position:relative; width:min(100%,560px); aspect-ratio:160/144; margin:auto; overflow:hidden; background:#11171a; }
#game-frame { display:block; width:100%; height:100%; object-fit:contain; image-rendering:pixelated; }
.frame-label { position:absolute; bottom:12px; left:12px; padding:6px 9px; border-radius:3px; background:#080b11ed; color:var(--lime); font:600 12px var(--mono); letter-spacing:.07em; }
.frame-empty { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:30px; text-align:center; background:#0b1019; border:1px dashed #3e4758; }
.frame-empty .empty-number { font:500 clamp(46px,7vw,82px)/1 var(--mono); color:#354154; margin-bottom:22px; letter-spacing:-.09em; }
.frame-empty strong { font-size:23px; letter-spacing:-.03em; }
.frame-empty p { max-width:320px; color:var(--muted); font-size:15px; }
.frame-empty small { color:var(--accent); font:12px var(--mono); letter-spacing:.07em; }
.stage { padding:20px 2px 0; }
.stage-row,.section-head,.metric-row,.party-top,.goal-row,.counter-row { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.stage strong { font-size:18px; line-height:1.35; }
.muted { color:var(--muted); }
.message { margin:10px 0 15px; color:#bec5d2; line-height:1.55; }
.bar { height:5px; overflow:hidden; border-radius:2px; background:#2b303c; }
.bar > i { display:block; height:100%; width:0; background:var(--lime); transition:width .25s ease; }
.view-only { color:var(--muted); font:12px var(--mono); letter-spacing:.06em; }
.model-choice { margin:18px 0 10px; font-size:clamp(22px,2.5vw,32px); line-height:1.18; font-weight:550; letter-spacing:-.045em; overflow-wrap:anywhere; }
.model-meta { color:var(--muted); font:13px/1.6 var(--mono); }
.triplet { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:20px; }
.metric { min-width:0; border-top:1px solid var(--line); padding-top:12px; }
.metric b { display:block; font:500 24px/1.4 var(--mono); margin-top:5px; letter-spacing:-.05em; }
.metric span { color:var(--muted); font-size:13px; }
.counter { margin-top:16px; }
.counter-row { font-size:14px; margin-bottom:7px; }
.score-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-top:16px; }
.score { padding:12px; background:#0d1119; border-left:2px solid var(--accent); }
.score span { display:block; color:var(--muted); font-size:13px; }
.score b { display:block; margin-top:5px; font-size:22px; }
.score-detail { margin-top:12px; color:var(--muted); font:13px/1.6 var(--mono); }
.components { display:grid; gap:12px; margin-top:14px; }
.component { display:grid; grid-template-columns:1fr 1fr; gap:10px 15px; grid-template-areas:"name name" "status samples" "score score" "digest digest"; padding:13px 0; border-top:1px solid var(--line); font-size:13px; }
.component > * { min-width:0; overflow-wrap:anywhere; }
.component-name { grid-area:name; }
.component-name strong,.component-name span { display:block; }
.component-name strong { font-size:16px; }
.component-name span { margin-top:5px; color:var(--muted); }
.component-status { grid-area:status; color:var(--lime); }
.component-stat { color:#bdc6d5; font:13px/1.5 var(--mono); }
.component-samples { grid-area:samples; }
.component-score { grid-area:score; }
.component-digest { grid-area:digest; color:var(--muted); font:12px var(--mono); }
.party { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-top:18px; }
.party-member { padding:13px; background:#0d1119; border:1px solid #252d3b; border-radius:6px; }
.party-top { align-items:start; flex-direction:column; gap:5px; }
.party-top strong { font-size:15px; }
.party-top span { color:var(--muted); font:12px var(--mono); }
.hp { height:5px; margin-top:12px; background:#2b303c; overflow:hidden; border-radius:2px; }
.hp i { display:block; height:100%; background:var(--lime); }
.goals { display:grid; gap:14px; margin-top:20px; }
.goal { display:grid; grid-template-columns:142px 1fr 42px; align-items:center; gap:12px; color:var(--muted); font-size:14px; }
.goal.selected { color:var(--lime); font-weight:650; }
.goal.unavailable { opacity:.55; }
.events { margin:18px 0 0; padding:0; list-style:none; display:grid; gap:0; max-height:290px; overflow:auto; counter-reset:steps; }
.events li { padding:12px 12px 12px 48px; position:relative; color:#c5ccda; font-size:14px; border-top:1px solid #242b38; line-height:1.6; counter-increment:steps; }
.events li::before { content:counter(steps,decimal-leading-zero); position:absolute; top:14px; left:8px; color:var(--accent); font:12px var(--mono); }
.work-card { margin-top:15px; }
.work-headline { margin:0; font-size:19px; font-weight:550; letter-spacing:-.025em; }
.work-detail { color:var(--muted); font-size:15px; margin:9px 0 15px; line-height:1.55; }
.work-steps { display:grid; gap:10px; margin-top:15px; }
.work-step { padding-left:12px; border-left:2px solid #394356; }
.work-step span { display:block; color:var(--muted); font:12px var(--mono); text-transform:uppercase; letter-spacing:.06em; }
.work-step b { display:block; margin-top:4px; font-size:14px; font-weight:500; line-height:1.45; }
.status-pill { background:#262c3a; color:#b6c4d7; padding:5px 8px; border-radius:4px; font:600 12px var(--mono); text-transform:uppercase; }
.status-pill.working,.status-pill.testing { color:#101610; background:var(--lime); }
.status-pill.blocked { color:#121012; background:var(--accent); }
.status-pill.complete { color:var(--lime); background:#233128; }
.mission { margin:12px 0 0; color:#bdc6d5; font-size:16px; }
.legend { color:var(--muted); font-size:14px; margin-top:12px; line-height:1.55; }
.fit-chart { margin-top:23px; padding-top:18px; border-top:1px solid var(--line); }
.fit-chart h3 { margin:0 0 12px; font-size:15px; font-weight:550; }
.fit-row { display:grid; grid-template-columns:52px 1fr 85px; align-items:center; gap:10px; margin:10px 0; font:12px var(--mono); color:var(--muted); }
.fit-track { height:12px; background:#242b36; }
.fit-track i { display:block; height:100%; background:var(--accent); }
.fit-row.after .fit-track i { background:var(--lime); }
.fit-note { color:var(--muted); font-size:13px; line-height:1.5; }
.viewer-mode .layout { grid-template-areas:"screen decision" "screen work" "recap recap" "party training"; }
.viewer-mode #learning-components-panel,.viewer-mode #goals-panel,.viewer-mode #activity-panel,.viewer-mode #mission-panel,.viewer-mode #live-evaluation-panel { display:none; }
@media(min-width:1200px) { .party { grid-template-columns:repeat(3,minmax(0,1fr)); } }
@media(max-width:950px) { #observatory { padding:18px; } .layout,.viewer-mode .layout { grid-template-columns:1fr; grid-template-areas:"screen" "decision" "work" "recap" "party" "training" "goals" "stack" "events" "mission"; } .screen-bezel { max-width:500px; } .top { align-items:flex-start; } .telemetry { grid-template-columns:1fr 1fr; } .telemetry > div:nth-child(2) { border-right:0; } .telemetry > div:nth-child(-n+2) { border-bottom:1px solid var(--line); } .recap-steps,.recap-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media(max-width:460px) { .recap-steps { grid-template-columns:1fr; } }
@media(max-width:540px) { #observatory { padding:12px; } .top { flex-direction:column; gap:15px; } .section,.screen-panel { padding:16px; } .screen-shell { padding:8px; } .party,.triplet { grid-template-columns:1fr; } .goal { grid-template-columns:115px 1fr 40px; gap:8px; } .score-grid { grid-template-columns:1fr 1fr; } .telemetry > div { padding:12px; } .telemetry b { font-size:18px; } }
@media(prefers-reduced-motion:reduce) { * { transition:none !important; animation:none !important; } }
</style>
<header class="top">
  <div><div class="eyebrow" id="eyebrow">Red field lab / Living Pokédex project</div><h1>Pokémon Learning Observatory</h1></div>
  <div class="live"><span id="status-dot" class="dot"></span><span id="connection">Connecting</span><span>·</span><span id="game">Waiting for session</span><button id="viewer-toggle" type="button" aria-pressed="false">Focus view</button></div>
</header>
<div class="telemetry" aria-label="Current evidence summary">
<div><span>Model experience</span><b id="headline-samples">—</b></div>
<div><span>Actor status</span><b class="signal" id="headline-actor">Waiting</b></div>
<div><span>Game connection</span><b id="headline-game">Not connected</b></div>
<div><span>Model scope</span><b id="headline-scope">Checking evidence</b></div>
</div>
<div class="layout">
  <section class="panel screen-panel"><div class="screen-heading"><b>01 / Game feed</b><span>Read-only observer</span></div>
    <div class="screen-shell"><div class="screen-bezel"><img id="game-frame" src="/frame.png" alt="Emulator frame"><div class="frame-empty" id="frame-empty"><span class="empty-number" aria-hidden="true">[ · · · ]</span><strong id="empty-heading">No live game connected</strong><p id="empty-detail">Saved learning results remain visible. This screen lights up only when an emulator publishes real frames.</p><small>NO SIMULATED ACTIVITY</small></div><span class="frame-label" id="frame-label">NO LIVE RUN</span></div></div>
    <div class="stage">
      <div class="stage-row"><strong id="stage">Waiting</strong><span class="muted" id="stage-percent">0%</span></div>
      <p class="message" id="message">Waiting for an authenticated emulator session.</p>
      <div class="bar"><i id="stage-bar"></i></div>
      <div class="metric-row muted" style="font-size:14px;margin-top:12px;flex-wrap:wrap"><span id="location">Location unavailable</span><span><span id="actions">0</span> actions · <span id="frames">0</span> frames</span></div>
    </div>
  </section>
  <div class="right">
    <section class="panel section" id="recap-panel" hidden>
      <div class="recap-heading"><div><h2 id="recap-heading">Last completed run</h2><p class="muted" id="recap-scope">Saved evidence, not live</p></div><span class="view-only">SAVED RUN / NOT LIVE</span></div>
      <div class="recap-metrics">
        <div><span>Goals completed</span><b id="recap-completed">—</b></div>
        <div><span>Living species</span><b id="recap-living">—</b></div>
        <div><span>Capture supplies</span><b id="recap-balls">—</b></div>
        <div><span>Money remaining</span><b class="cash" id="recap-money">—</b></div>
      </div>
      <ol class="recap-steps" id="recap-steps" aria-label="Goals in the saved run"></ol>
      <div class="recap-foot muted"><span id="recap-authority">—</span><span id="recap-cost">—</span></div>
      <p class="recap-caution" id="recap-limitation"></p>
    </section>
    <section class="panel section" id="work-panel">
      <div class="section-head"><h2>Work happening now</h2><span class="status-pill" id="work-status">idle</span></div>
      <div class="work-card">
        <h3 class="work-headline" id="work-headline">No engineering session is active</h3>
        <p class="work-detail" id="work-detail">Waiting for the next project update.</p>
        <div class="bar"><i id="work-bar"></i></div>
        <div class="counter-row muted" style="margin-top:7px"><span id="work-count">No fixed unit count</span><span id="work-updated">Not updated</span></div>
        <div class="work-steps">
          <div class="work-step"><span>Current step</span><b id="work-current">Waiting</b></div>
          <div class="work-step"><span>Next step</span><b id="work-next">Start the next bounded project session</b></div>
        </div>
      </div>
    </section>
    <section class="panel section" id="mission-panel">
      <div class="section-head"><h2>The mission</h2><span class="view-only">RED FIRST</span></div>
      <p class="mission">Build an agent that can complete Pokémon games and maintain a living Pokédex. The learned layer chooses portable semantic goals; deterministic skills retain movement, battle, capture, menus, verification and safety.</p>
      <p class="legend">Authority is shown per model and per session. Training error is not an unseen gameplay score. Version exclusives, trades and event requirements remain explicit parts of the long-term collection goal.</p>
    </section>
    <section class="panel section" id="decision-panel">
      <div class="section-head"><h2>02 / Current decision</h2><span class="view-only">VIEW ONLY</span></div>
      <div class="model-choice" id="choice">Waiting for context</div>
      <div class="model-meta"><span id="candidate">Red frozen goal manager</span> · <span id="mode">waiting</span> · <span id="confidence">—</span></div>
      <div class="triplet">
        <div class="metric"><span>Decisions</span><b id="decisions">0</b></div>
        <div class="metric"><span>Teacher queries</span><b id="teacher">0</b></div>
        <div class="metric"><span>Fallbacks</span><b id="fallbacks">0</b></div>
      </div>
    </section>
    <section class="panel section" id="live-evaluation-panel" hidden>
      <div class="section-head"><h2>Live shadow scorecard</h2><span class="muted">teacher is safety authority</span></div>
      <div class="score-grid">
        <div class="score"><span>Teacher agreement</span><b id="agreement-rate">—</b></div>
        <div class="score"><span>Model executed</span><b id="execution-rate">—</b></div>
        <div class="score"><span>Corrections saved</span><b id="corrections">0</b></div>
        <div class="score"><span>Team ranker</span><b id="team-accuracy">—</b></div>
      </div>
      <div class="score-detail" id="evaluation-detail">Waiting for the first live decision.</div>
    </section>
    <section class="panel section" id="experiment-panel">
      <div class="section-head"><h2 id="experiment-heading">Transfer experiment</h2><span class="muted" id="phase">qualification</span></div>
      <div id="experiment"></div><div class="fit-chart" id="fit-chart" hidden><h3>Training error / before &amp; after</h3><div class="fit-row"><span>Before</span><div class="fit-track"><i id="fit-before-bar"></i></div><span id="fit-before">—</span></div><div class="fit-row after"><span>After</span><div class="fit-track"><i id="fit-after-bar"></i></div><span id="fit-after">—</span></div><p class="fit-note" id="fit-note">In-sample calibration, not independent playing ability.</p></div>
    </section>
    <section class="panel section" id="learning-components-panel" hidden>
      <div class="section-head"><h2>Model evidence</h2><span class="muted">limits included</span></div>
      <div class="components" id="learning-components"></div>
    </section>
    <section class="panel section" id="collection-panel">
      <div class="section-head"><h2>03 / Collection and party</h2><span class="muted" id="resources">Not observed</span></div>
      <div class="triplet">
        <div class="metric"><span>Registered</span><b id="registered">0</b></div>
        <div class="metric"><span>Retained species</span><b id="living">0</b></div>
        <div class="metric"><span>Level 100</span><b id="level-cap">0</b></div>
      </div>
      <div class="party" id="party"><span class="muted">Party unavailable</span></div>
    </section>
    <section class="panel section" id="goals-panel"><div class="section-head"><h2>What matters next</h2><span class="muted">identity-free model input</span></div><div class="goals" id="goals"><span class="muted">Waiting for semantic state</span></div></section>
    <section class="panel section" id="activity-panel"><div class="section-head"><h2>Session evidence</h2><span class="muted" id="speed">0×</span></div><ul class="events" id="events"></ul></section>
  </div>
</div>
<script>
const el = id => document.getElementById(id);
const fmt = value => Number(value || 0).toLocaleString();
const pct = value => `${Math.round(Number(value || 0) * 100)}%`;
let lastFrame = -1;
function safeText(id, value) { el(id).textContent = value == null ? "—" : String(value); }
function barRow(label, value) {
  const total = Math.max(0, Number(value.total));
  const done = Math.max(0, Number(value.completed));
  const ratio = total ? Math.min(1, done / total) : 0;
  const wrap = document.createElement("div"); wrap.className = "counter";
  const row = document.createElement("div"); row.className = "counter-row";
  const name = document.createElement("span"); name.textContent = label;
  const count = document.createElement("span"); count.textContent = `${done} / ${total}`;
  row.append(name, count);
  const bar = document.createElement("div"); bar.className = "bar";
  const fill = document.createElement("i"); fill.style.width = `${ratio * 100}%`; bar.append(fill);
  wrap.append(row, bar); return wrap;
}
function accuracy(value) { return value == null ? "—" : pct(value); }
function exactScore(correct, total) {
  if (correct == null || total == null || Number(total) === 0) return "—";
  return `${fmt(correct)}/${fmt(total)} (${accuracy(Number(correct) / Number(total))})`;
}
function componentRow(component) {
  const row = document.createElement("div"); row.className = "component";
  const name = document.createElement("div"); name.className = "component-name";
  const title = document.createElement("strong"); title.textContent = component.name;
  const scope = document.createElement("span");
  const candidateAudit = Object.entries(component.candidate_count_results || {}).map(([count, result]) => `${count}-way ${result.correct}/${result.total}`).join(" · ");
  scope.textContent = candidateAudit ? `${component.scope} · candidate audit: ${candidateAudit}` : component.scope; name.append(title, scope);
  const authority = document.createElement("div"); authority.className = "component-status"; authority.textContent = `${component.status} · ${component.authority.replaceAll("_", " ")}`;
  const samples = document.createElement("div"); samples.className = "component-stat component-samples"; samples.textContent = `${fmt(component.train_examples)} train · ${fmt(component.independent_validation_units)} independent val units`;
  const score = document.createElement("div"); score.className = "component-stat component-score"; score.textContent = `candidate ${exactScore(component.validation_correct, component.validation_examples)} · prior ${exactScore(component.baseline_correct, component.validation_examples)}`;
  const digest = document.createElement("div"); digest.className = "component-digest"; digest.textContent = `model ${component.model_sha256.slice(0, 10)}`;
  row.append(name, authority, samples, score, digest); return row;
}
function relativeTime(timestamp) {
  if (!timestamp) return "Not updated";
  const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(timestamp)) / 1000));
  if (!Number.isFinite(seconds)) return "Update time unavailable";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}
function framePresentation(data) {
  const signal = data.dashboard;
  if (!signal.frame_ready) return {label:"NO LIVE RUN", connection:"No emulator"};
  if (data.run_status !== "running") return {label:"LAST FRAME / SESSION ENDED", connection:"Session ended"};
  if (signal.frame_age_seconds == null || signal.frame_age_seconds >= 3 || signal.snapshot_age_seconds >= 5)
    return {label:"LAST FRAME / WAITING FOR UPDATE", connection:"Feed paused"};
  return {label:"LIVE FRAME", connection:"Live emulator"};
}
function render(data) {
  safeText("game", data.game);
  safeText("connection", data.run_status);
  el("status-dot").className = `dot ${data.run_status}`;
  safeText("stage", data.stage); safeText("message", data.message);
  safeText("stage-percent", pct(data.stage_progress)); el("stage-bar").style.width = pct(data.stage_progress);
  safeText("location", data.location || "Location unavailable"); safeText("actions", fmt(data.actions)); safeText("frames", fmt(data.frame_count));
  safeText("choice", data.model.choice || "Waiting for context"); safeText("candidate", data.model.candidate); safeText("mode", data.model.mode);
  safeText("confidence", data.model.confidence == null ? "confidence —" : `confidence ${pct(data.model.confidence)}`);
  safeText("decisions", fmt(data.model.decisions)); safeText("teacher", fmt(data.model.teacher_queries)); safeText("fallbacks", fmt(data.model.fallbacks));
  const work = data.work || {};
  safeText("work-status", work.status || "idle"); el("work-status").className = `status-pill ${work.status || "idle"}`;
  safeText("work-headline", work.headline); safeText("work-detail", work.detail);
  safeText("work-current", work.current_step); safeText("work-next", work.next_step);
  const workProgress = work.progress == null ? 0 : Number(work.progress);
  el("work-bar").style.width = pct(workProgress);
  safeText("work-count", work.total_units ? `${fmt(work.completed_units)} / ${fmt(work.total_units)} units` : "No fixed unit count");
  safeText("work-updated", relativeTime(work.updated_at_utc));
  safeText("eyebrow", data.experiment.eyebrow || "Transfer learning run");
  safeText("experiment-heading", data.experiment.heading || "Transfer experiment");
  safeText("phase", data.experiment.phase.replaceAll("_", " "));
  const labels = data.experiment.counter_labels || {};
  const experiment = el("experiment"); experiment.replaceChildren(
    barRow(labels.zero_shot || "Zero-shot probe", data.experiment.zero_shot),
    barRow(labels.adaptation || "Adaptation examples", data.experiment.adaptation),
    barRow(labels.sealed_test || "Sealed test", data.experiment.sealed_test)
  );
  const live = data.live_evaluation;
  el("live-evaluation-panel").hidden = !live;
  if (live) {
    safeText("agreement-rate", exactScore(live.teacher_agreements, live.teacher_agreement_denominator)); safeText("execution-rate", exactScore(live.teacher_agreements, live.model_execution_denominator));
    safeText("corrections", fmt(live.corrections_saved)); safeText("team-accuracy", exactScore(live.team_agreements, live.team_decisions));
    const accounting = live.decision_accounting_complete ? "complete accounting" : `${fmt(live.unclassified_decisions)} historical unclassified`;
    safeText("evaluation-detail", `${fmt(live.battle_decisions)} battle choices · ${fmt(live.teacher_disagreements)} typed disagreements · ${fmt(live.low_confidence_fallbacks)} low-confidence · ${fmt(live.unsupported_observations)} unsupported · ${fmt(live.non_move_control_decisions)} non-move · ${fmt(live.failed_decisions)} failed · ${fmt(live.interrupted_decisions)} interrupted · ${accounting}`);
  }
  const componentPanel = el("learning-components-panel"); const components = el("learning-components");
  componentPanel.hidden = !data.learning_components.length; components.replaceChildren(...data.learning_components.map(componentRow));
  const observed = data.collection.observed !== false;
  safeText("registered", observed ? `${data.collection.registered}/${data.collection.target}` : "—");
  safeText("living", observed ? data.collection.living : "—");
  safeText("level-cap", observed ? data.collection.level_cap : "—");
  safeText("resources", observed ? `${data.resources.capture_items} capture items · ${data.resources.free_storage_slots} free slots` : "No live inventory observation");
  const training = data.training;
  const recap = data.last_run;
  el("recap-panel").hidden = !recap;
  if (recap) {
    safeText("recap-heading", recap.heading); safeText("recap-scope", recap.scope);
    safeText("recap-limitation", recap.limitation);
    safeText("recap-completed", `${recap.steps.filter(s => s.status === "succeeded").length} / ${recap.steps.length}`);
    safeText("recap-living", `${fmt(recap.living_before)} → ${fmt(recap.living_after)}`);
    safeText("recap-balls", `${fmt(recap.capture_items_before)} → ${fmt(recap.capture_items_after)}`);
    safeText("recap-money", `${fmt(recap.money_before)} → ${fmt(recap.money_after)}`);
    safeText("recap-authority", `${recap.steps.filter(s => s.authority === "model").length} model-ranked choices · others safety or unsupported-choice bridges`);
    safeText("recap-cost", `${fmt(recap.controller_actions)} actions · ${fmt(recap.emulator_frames)} frames · recorded, not currently running`);
    const labels = { model:"Model-ranked", safety:"Safety rule", unsupported:"Single supported kind", forced:"Forced bridge" };
    el("recap-steps").replaceChildren(...recap.steps.map((step, index) => {
      const card = document.createElement("li"); card.className = `recap-step ${step.authority}`;
      const authority = document.createElement("span"); authority.className = "authority"; authority.textContent = `${index + 1} / ${labels[step.authority]}`;
      const goal = document.createElement("strong"); goal.textContent = step.goal.replaceAll("_", " ");
      const status = document.createElement("small"); status.textContent = `${step.status} · ${fmt(step.actions)} actions`;
      const gain = document.createElement("div"); gain.className = "gain";
      gain.textContent = step.new_living_species ? `+${step.new_living_species} living species` : step.needed_specimens_gained ? `+${step.needed_specimens_gained} needed duplicate` : "Resource maintenance";
      card.append(authority, goal, status, gain); return card;
    }));
  }
  const primary = data.learning_components[0];
  safeText("headline-samples", primary ? `${fmt(primary.train_examples)} examples` : "Not reported");
  safeText("headline-scope", primary ? primary.authority.replaceAll("_", " ") : data.model.mode.replaceAll("_", " "));
  safeText("headline-actor", data.model.decisions && data.run_status === "running" ? data.model.mode.replaceAll("_", " ") : "No live choice");
  el("fit-chart").hidden = !training;
  if (training) {
    const scale = Math.max(training.weighted_mse_before, training.weighted_mse_after, 1e-9);
    safeText("fit-before", Number(training.weighted_mse_before).toFixed(6));
    safeText("fit-after", Number(training.weighted_mse_after).toFixed(6));
    el("fit-before-bar").style.width = pct(training.weighted_mse_before / scale);
    el("fit-after-bar").style.width = pct(training.weighted_mse_after / scale);
    safeText("fit-note", `${training.newly_collected} new examples + ${training.previously_unfitted} earlier unfitted. ${training.training_choice_changes} changed training-menu choices. In-sample calibration, not unseen gameplay ability.`);
  }
  const party = el("party"); party.replaceChildren();
  if (!data.party.length) { const empty = document.createElement("span"); empty.className = "muted"; empty.textContent = "Party unavailable"; party.append(empty); }
  data.party.forEach(member => {
    const item = document.createElement("div"); item.className = "party-member";
    const top = document.createElement("div"); top.className = "party-top";
    const name = document.createElement("strong"); name.textContent = `${member.slot}. ${member.label}`;
    const detail = document.createElement("span"); detail.textContent = `Lv ${member.level} · ${member.hp}/${member.max_hp} · ${member.status}`;
    top.append(name, detail); const hp = document.createElement("div"); hp.className = "hp"; const fill = document.createElement("i"); fill.style.width = pct(member.hp_ratio); hp.append(fill); item.append(top, hp); party.append(item);
  });
  const goals = el("goals"); goals.replaceChildren();
  if (!data.goals.length) { const empty = document.createElement("span"); empty.className = "muted"; empty.textContent = "Waiting for semantic state"; goals.append(empty); }
  data.goals.forEach(goal => {
    const row = document.createElement("div"); row.className = `goal${goal.selected ? " selected" : ""}${goal.available ? "" : " unavailable"}`;
    const label = document.createElement("span"); label.textContent = goal.goal.replaceAll("_", " "); const bar = document.createElement("div"); bar.className = "bar"; const fill = document.createElement("i"); fill.style.width = pct(goal.pressure); bar.append(fill); const value = document.createElement("span"); value.textContent = pct(goal.pressure); row.append(label, bar, value); goals.append(row);
  });
  const events = el("events"); events.replaceChildren(); data.events.slice().reverse().forEach(event => { const li = document.createElement("li"); li.textContent = event; events.append(li); });
  safeText("speed", `${Number(data.emulation_speed || 0).toFixed(1)}× emulation`);
  const feed = framePresentation(data);
  safeText("frame-label", feed.label); safeText("headline-game", feed.connection);
  el("frame-empty").hidden = Boolean(data.dashboard.frame_ready);
  const frameVersion = Number(data.dashboard.frame_version);
  if (frameVersion !== lastFrame) { lastFrame = frameVersion; el("game-frame").src = `/frame.png?v=${frameVersion}`; }
}
async function refresh() {
  try { const response = await fetch("/api/status", {cache:"no-store", signal:AbortSignal.timeout(4000)}); if (!response.ok) throw new Error(); render(await response.json()); }
  catch {
    safeText("connection", "disconnected"); el("status-dot").className = "dot failed";
    safeText("frame-label", "CONNECTION LOST / LAST FRAME"); safeText("headline-game", "Disconnected");
    safeText("headline-actor", "Not observable");
  } finally { setTimeout(refresh, 500); }
}
el("viewer-toggle").addEventListener("click", () => {
  const enabled = document.body.classList.toggle("viewer-mode");
  el("viewer-toggle").setAttribute("aria-pressed", String(enabled));
  safeText("viewer-toggle", enabled ? "Full detail" : "Focus view");
});
refresh();
</script>
</main>
</body>
</html>
""".encode()


__all__ = [
    "DASHBOARD_DEFAULT_PORT",
    "DASHBOARD_FRAME_HEIGHT",
    "DASHBOARD_FRAME_WIDTH",
    "DASHBOARD_HOST",
    "DASHBOARD_SCHEMA",
    "DashboardExperimentState",
    "DashboardFrameObserver",
    "DashboardGoalPressure",
    "DashboardLearningComponent",
    "DashboardLiveEvaluationState",
    "DashboardModelState",
    "DashboardPartyMember",
    "DashboardSnapshot",
    "DashboardState",
    "DashboardWorkState",
    "DashboardTrainingState",
    "ProgressDashboardError",
    "ProgressDashboardServer",
    "encode_rgb_png",
    "waiting_dashboard_snapshot",
]
