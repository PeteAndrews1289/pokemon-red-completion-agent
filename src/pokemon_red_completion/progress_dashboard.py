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
from dataclasses import dataclass
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
        if (
            self.low_confidence_fallbacks + self.unsupported_observations
            > self.teacher_fallbacks
        ):
            raise ProgressDashboardError("typed fallbacks cannot exceed teacher fallbacks")
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
    events: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _plain_text(self.game, subject="game", maximum=64)
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

    def __init__(self, snapshot: DashboardSnapshot | None = None) -> None:
        self._lock = threading.Lock()
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

    def status_bytes(self) -> tuple[bytes, int]:
        with self._lock:
            document = self._snapshot.public_dict()
            document["dashboard"] = {
                "snapshot_version": self._snapshot_version,
                "frame_version": self._frame_version,
                "frame_ready": self._frame_version > 0,
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


_DASHBOARD_HTML = """<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pokémon Learning Observatory</title>
<main id="observatory">
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #07100d; color: #eff8ee; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  #observatory { min-height: 100vh; padding: 24px; background: radial-gradient(circle at 15% 0%, #17342a 0, transparent 34rem), #07100d; }
  .top { max-width: 1440px; margin: 0 auto 18px; display: flex; align-items: end; justify-content: space-between; gap: 16px; }
  .eyebrow { color: #77e2a6; font: 700 12px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: .16em; text-transform: uppercase; }
  h1 { margin: 4px 0 0; font-size: clamp(24px, 4vw, 42px); letter-spacing: -.04em; }
  .live { display: flex; gap: 9px; align-items: center; color: #bcd0c4; font-size: 13px; }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: #86938b; box-shadow: 0 0 0 4px #ffffff0a; }
  .dot.running { background: #5af09a; box-shadow: 0 0 18px #5af09aaa; }
  .dot.failed, .dot.blocked { background: #ff7a7a; }
  .layout { max-width: 1440px; margin: auto; display: grid; grid-template-columns: minmax(420px, 1.2fr) minmax(400px, .8fr); gap: 18px; align-items: start; }
  .panel { background: #0d1915ee; border: 1px solid #294338; border-radius: 18px; overflow: hidden; box-shadow: 0 20px 70px #0008; }
  .screen-panel { padding: 18px; }
  .screen-shell { padding: 18px; border-radius: 22px 22px 42px 22px; background: linear-gradient(145deg, #b8bec0, #686f72); box-shadow: inset 0 0 0 1px #edf1f288, 0 12px 30px #0008; }
  .screen-bezel { position: relative; aspect-ratio: 160 / 144; border-radius: 10px 10px 26px 10px; overflow: hidden; background: #111715; border: 14px solid #343c3e; }
  #game-frame { width: 100%; height: 100%; object-fit: fill; image-rendering: pixelated; display: block; }
  .frame-label { position: absolute; top: 8px; right: 9px; padding: 4px 7px; border-radius: 6px; background: #06100dcc; color: #77e2a6; font: 700 10px ui-monospace, monospace; letter-spacing: .1em; }
  .stage { margin-top: 18px; }
  .stage-row, .section-head, .metric-row, .party-top, .goal-row, .counter-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .stage strong { font-size: 18px; }
  .muted { color: #93a79b; }
  .message { margin: 7px 0 12px; color: #c9d9cf; line-height: 1.45; }
  .bar { height: 8px; overflow: hidden; border-radius: 99px; background: #213229; }
  .bar > i { display: block; height: 100%; width: 0; border-radius: inherit; background: linear-gradient(90deg, #4fd58c, #baf268); transition: width .3s ease; }
  .right { display: grid; gap: 18px; }
  .section { padding: 17px 18px; }
  .section h2 { margin: 0; font-size: 15px; letter-spacing: -.01em; }
  .view-only { color: #77e2a6; font: 700 10px ui-monospace, monospace; letter-spacing: .12em; }
  .model-choice { margin: 13px 0 4px; font-size: 24px; font-weight: 750; letter-spacing: -.03em; }
  .model-meta { color: #a9bcb0; font-size: 13px; }
  .triplet { display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; margin-top: 14px; }
  .metric { padding: 11px; border: 1px solid #263e34; border-radius: 11px; background: #0a1411; }
  .metric b { display: block; font-size: 22px; margin-top: 4px; }
  .metric span { color: #8da096; font-size: 11px; }
  .counter { margin-top: 13px; }
  .counter-row { font-size: 12px; margin-bottom: 5px; }
  .score-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 9px; margin-top: 13px; }
  .score { min-width: 0; padding: 10px; border-left: 2px solid #355647; background: #0a1411; }
  .score span { display: block; color: #8da096; font-size: 10px; }
  .score b { display: block; margin-top: 3px; font-size: 18px; }
  .score-detail { margin-top: 10px; color: #8da096; font: 11px/1.5 ui-monospace, monospace; }
  .components { display: grid; gap: 8px; margin-top: 13px; }
  .component { display: grid; grid-template-columns: minmax(130px, 1.25fr) 90px 112px 115px 72px; gap: 9px; align-items: center; padding: 9px 0; border-top: 1px solid #22372e; font-size: 11px; }
  .component:first-child { border-top: 0; }
  .component-name strong, .component-name span { display: block; }
  .component-name span { margin-top: 3px; color: #82978a; line-height: 1.35; }
  .component-status { color: #77e2a6; text-transform: uppercase; letter-spacing: .08em; }
  .component-stat { color: #b6c8bd; font-family: ui-monospace, monospace; }
  .component-digest { color: #82978a; font-family: ui-monospace, monospace; }
  .party { display: grid; gap: 9px; margin-top: 13px; }
  .party-member { padding: 10px 11px; border: 1px solid #223a30; border-radius: 11px; background: #0a1411; }
  .party-top strong { font-size: 13px; }
  .party-top span { color: #9db0a4; font: 12px ui-monospace, monospace; }
  .hp { height: 5px; margin-top: 8px; border-radius: 9px; background: #25352d; overflow: hidden; }
  .hp i { display: block; height: 100%; background: #5ee69a; }
  .goals { display: grid; gap: 8px; margin-top: 13px; }
  .goal { display: grid; grid-template-columns: 128px 1fr 42px; gap: 8px; align-items: center; font-size: 12px; color: #aebfb5; }
  .goal.selected { color: #f4ffe8; font-weight: 700; }
  .goal.unavailable { opacity: .36; }
  .goal .bar { height: 6px; }
  .events { margin: 12px 0 0; padding: 0; list-style: none; display: grid; gap: 7px; max-height: 150px; overflow: auto; }
  .events li { padding-left: 13px; position: relative; color: #aebfb5; font-size: 12px; line-height: 1.4; }
  .events li::before { content: ""; position: absolute; left: 0; top: .55em; width: 5px; height: 5px; border-radius: 50%; background: #5bdc93; }
  @media (max-width: 920px) { #observatory { padding: 14px; } .layout { grid-template-columns: 1fr; } .screen-panel { padding: 12px; } }
  @media (max-width: 640px) { .component { grid-template-columns: 1fr 1fr; } .component-name { grid-column: 1 / -1; } .score-grid { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 500px) { .triplet { grid-template-columns: 1fr 1fr; } .goal { grid-template-columns: 102px 1fr 36px; } .top { align-items: start; flex-direction: column; } }
</style>
<header class="top">
  <div><div class="eyebrow" id="eyebrow">Transfer learning run</div><h1>Pokémon Learning Observatory</h1></div>
  <div class="live"><span id="status-dot" class="dot"></span><span id="connection">Connecting</span><span>·</span><span id="game">Pokémon Crystal 1.1</span></div>
</header>
<div class="layout">
  <section class="panel screen-panel">
    <div class="screen-shell"><div class="screen-bezel"><img id="game-frame" src="/frame.png" alt="Live emulator frame"><span class="frame-label">LIVE FRAME</span></div></div>
    <div class="stage">
      <div class="stage-row"><strong id="stage">Waiting</strong><span class="muted" id="stage-percent">0%</span></div>
      <p class="message" id="message">Waiting for an authenticated emulator session.</p>
      <div class="bar"><i id="stage-bar"></i></div>
      <div class="metric-row muted" style="font-size:12px;margin-top:10px"><span id="location">Location unavailable</span><span><span id="actions">0</span> actions · <span id="frames">0</span> frames</span></div>
    </div>
  </section>
  <div class="right">
    <section class="panel section">
      <div class="section-head"><h2>Current decision</h2><span class="view-only">VIEW ONLY</span></div>
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
    <section class="panel section">
      <div class="section-head"><h2 id="experiment-heading">Transfer experiment</h2><span class="muted" id="phase">qualification</span></div>
      <div id="experiment"></div>
    </section>
    <section class="panel section" id="learning-components-panel" hidden>
      <div class="section-head"><h2>Learned stack</h2><span class="muted">held-out Red evidence</span></div>
      <div class="components" id="learning-components"></div>
    </section>
    <section class="panel section">
      <div class="section-head"><h2>Collection and party</h2><span class="muted" id="resources">0 balls · 0 free slots</span></div>
      <div class="triplet">
        <div class="metric"><span>Registered</span><b id="registered">0</b></div>
        <div class="metric"><span>Living</span><b id="living">0</b></div>
        <div class="metric"><span>Level 100</span><b id="level-cap">0</b></div>
      </div>
      <div class="party" id="party"><span class="muted">Party unavailable</span></div>
    </section>
    <section class="panel section"><div class="section-head"><h2>Goal pressures</h2><span class="muted">identity-free model input</span></div><div class="goals" id="goals"><span class="muted">Waiting for semantic state</span></div></section>
    <section class="panel section"><div class="section-head"><h2>Recent evidence</h2><span class="muted" id="speed">0×</span></div><ul class="events" id="events"></ul></section>
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
  const samples = document.createElement("div"); samples.className = "component-stat"; samples.textContent = `${fmt(component.train_examples)} train · ${fmt(component.independent_validation_units)} independent val units`;
  const score = document.createElement("div"); score.className = "component-stat"; score.textContent = `${exactScore(component.validation_correct, component.validation_examples)} vs ${exactScore(component.baseline_correct, component.validation_examples)}`;
  const digest = document.createElement("div"); digest.className = "component-digest"; digest.textContent = component.model_sha256.slice(0, 10);
  row.append(name, authority, samples, score, digest); return row;
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
  safeText("registered", `${data.collection.registered}/${data.collection.target}`); safeText("living", data.collection.living); safeText("level-cap", data.collection.level_cap);
  safeText("resources", `${data.resources.capture_items} capture items · ${data.resources.free_storage_slots} free slots`);
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
  const frameVersion = Number(data.dashboard.frame_version);
  if (frameVersion !== lastFrame) { lastFrame = frameVersion; el("game-frame").src = `/frame.png?v=${frameVersion}`; }
}
async function refresh() {
  try { const response = await fetch("/api/status", {cache:"no-store"}); if (!response.ok) throw new Error(); render(await response.json()); }
  catch { safeText("connection", "disconnected"); el("status-dot").className = "dot failed"; }
}
refresh(); setInterval(refresh, 350);
</script>
</main>
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
    "ProgressDashboardError",
    "ProgressDashboardServer",
    "encode_rgb_png",
    "waiting_dashboard_snapshot",
]
