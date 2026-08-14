"""Observer-only runtime bridge for the first full Red shadow evaluation."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from pokemon_red_completion.progress_dashboard import (
    DashboardFrameObserver,
    DashboardState,
)
from pokemon_red_completion.red_training_dashboard import (
    red_training_dashboard_snapshot,
)

if TYPE_CHECKING:
    from pokemon_red_completion.play import QualifiedPlayProgress, QualifiedPlayReport


class RedTrainingDashboardTracker:
    """Keep the dashboard current without influencing emulator inputs."""

    def __init__(
        self,
        state: DashboardState,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(state, DashboardState):
            raise TypeError("state must be DashboardState")
        self._state = state
        self._clock = clock
        self._started_at = clock()
        self._status = "waiting"
        self._stage = "Clean-power Red evaluation"
        self._message = "Authenticated models are ready; waiting to power on Pokémon Red."
        self._frame_count = 0
        self._actions = 0
        self._progress = 0.0
        self._location: str | None = None
        self._battle_policy: dict[str, object] = {}
        self._team_policy: dict[str, object] = {}
        self._registered_species = 0
        self._living_species = 0
        self._level_cap_species = 0
        self._completed_runs = 0
        self._events = [
            "Four learned heads refitted from Red teacher data",
            "Battle proposals require teacher agreement",
            "Team-development choices are measured in shadow only",
            "Goal and destination heads remain offline in this fixed route",
            "Red sealed destinations and all Crystal contexts remain unopened",
        ]
        self._seen_checkpoints: set[str] = set()
        self.publish()

    @property
    def frame_observer(self) -> RedTrainingFrameObserver:
        return RedTrainingFrameObserver(self, DashboardFrameObserver(self._state))

    def start(self) -> None:
        self._status = "running"
        self._message = (
            "The model is proposing battle and team-development choices while the teacher "
            "retains safety authority."
        )
        self._append_event("Clean-power Red shadow evaluation started")
        self.publish()

    def on_progress(self, progress: QualifiedPlayProgress) -> None:
        self._stage = progress.label
        self._frame_count = progress.frames_executed
        self._progress = progress.completed / progress.total if progress.total else 0.0
        self._location = progress.label
        if progress.checkpoint_id not in self._seen_checkpoints:
            self._seen_checkpoints.add(progress.checkpoint_id)
            self._append_event(
                f"Verified checkpoint {progress.completed}/{progress.total}: {progress.label}"
            )
        self.publish()

    def on_battle_policy(self, report: Mapping[str, object]) -> None:
        self._battle_policy = dict(report)
        self.publish()

    def on_team_policy(self, report: Mapping[str, object]) -> None:
        self._team_policy = dict(report)
        self.publish()

    def on_frame(self, logical_frame: int) -> None:
        self._frame_count = logical_frame
        self.publish()

    def pass_run(self, report: QualifiedPlayReport) -> None:
        self._status = "passed"
        self._stage = "Champion and Hall of Fame verified"
        self._message = (
            "The teacher-supervised Red shadow run completed. Live disagreements are preserved "
            "as the next correction set."
        )
        self._frame_count = report.frames_executed
        self._actions = report.actions_executed
        self._progress = 1.0
        self._location = "Hall of Fame"
        self._battle_policy = dict(report.battle_policy_report or self._battle_policy)
        self._team_policy = dict(report.training_candidate_policy_report or self._team_policy)
        if report.collection_progress is not None:
            collection = report.collection_progress.collection
            self._registered_species = collection.pokedex_owned_count
            self._living_species = collection.living_count
            self._level_cap_species = collection.level_cap_count
        self._completed_runs = 1
        self._append_event("Champion event and Hall of Fame state verified concurrently")
        self.publish()

    def fail_run(self, *, exception_type: str) -> None:
        self._status = "failed"
        self._message = (
            "The run stopped at the current verified boundary. Private diagnostics and collected "
            "corrections were retained; no failed result is promoted."
        )
        self._append_event(f"Shadow evaluation stopped safely ({exception_type})")
        self.publish()

    def publish(self) -> None:
        elapsed = max(self._clock() - self._started_at, 1e-9)
        speed = self._frame_count / (elapsed * 60.0)
        self._state.publish(
            red_training_dashboard_snapshot(
                run_status=self._status,
                stage=self._stage,
                message=self._message,
                frame_count=self._frame_count,
                actions=self._actions,
                stage_progress=self._progress,
                live_evaluations_completed=self._completed_runs,
                live_evaluations_total=1,
                battle_policy=self._battle_policy,
                team_policy=self._team_policy,
                emulation_speed=speed if self._status == "running" else 0.0,
                location=self._location,
                registered_species=self._registered_species,
                living_species=self._living_species,
                level_cap_species=self._level_cap_species,
                events=tuple(self._events),
            )
        )

    def _append_event(self, event: str) -> None:
        self._events.append(event)
        del self._events[:-24]


class RedTrainingFrameObserver:
    """Rendered-frame observer that also drives dashboard heartbeat updates."""

    def __init__(
        self,
        tracker: RedTrainingDashboardTracker,
        delegate: DashboardFrameObserver,
    ) -> None:
        self._tracker = tracker
        self._delegate = delegate

    def wants_frame(self, logical_frame: int) -> bool:
        return self._delegate.wants_frame(logical_frame)

    def publish_frame(
        self,
        width: int,
        height: int,
        rgb: bytes,
        logical_frame: int,
    ) -> None:
        self._delegate.publish_frame(width, height, rgb, logical_frame)
        self._tracker.on_frame(logical_frame)


__all__ = ["RedTrainingDashboardTracker", "RedTrainingFrameObserver"]
