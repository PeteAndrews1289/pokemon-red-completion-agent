"""TRAIN-only passive decision snapshots, bound to the actor's logged observation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    BattleScenarioCapture,
    build_battle_scenario_capture_payload,
)
from .provenance import canonical_sha256
from .red_trainer_practice_log import TrainerPracticeEventLog
from .scenario_lab import ScenarioPartition


def validate_capture_indices(indices: tuple[int, ...], parent: BattleScenarioCapture) -> None:
    if (not indices or len(indices) > 8 or len(set(indices)) != len(indices)
            or any(type(i) is not int or not 2 <= i <= 40 for i in indices)
            or parent.manifest.partition is not ScenarioPartition.TRAIN
            or parent.manifest.observation_schema != OBSERVATION_SCHEMA_V2):
        raise ValueError("trajectory snapshots require bounded unique TRAIN decision indices")


class TrajectoryCaptureSink:
    """Observe events only; no action, mutable policy or controller interface is provided.

    snapshot returns native bytes plus both semantic views of that exact boundary.
    No snapshot is requested at unsampled decisions or after the episode has ended.
    """

    def __init__(self, *, parent: BattleScenarioCapture, directory: Path,
                 indices: tuple[int, ...], source_commit: str, log: TrainerPracticeEventLog,
                 snapshot: Callable[[], Mapping[str, Any]]) -> None:
        validate_capture_indices(indices, parent)
        self.parent, self.directory, self.indices = parent, directory, indices
        self.source_commit, self.log, self.snapshot = source_commit, log, snapshot
        self.seen: set[int] = set()

    def __call__(self, event: Mapping[str, Any]) -> None:
        self.log.emit(event)
        if event.get("event") != "decision_started" or event["decision_index"] not in self.indices:
            return
        index = event["decision_index"]
        if index in self.seen:
            raise ValueError("duplicate trajectory decision boundary")
        self.seen.add(index)
        if event["mode"] != "main":
            self.log.emit({"event": "trajectory_capture_censored", "decision_index": index,
                           "reason": "non_main_boundary"})
            return
        observed = self.snapshot()
        observation_sha = canonical_sha256(observed["policy_observation"])
        if (observation_sha != event["observation_sha256"]
                or observed["map_id"] != self.parent.manifest.expected_map
                or observed["battle_state"] != 2):
            raise ValueError("snapshot differs from actor decision boundary")
        state = observed["state_bytes"]
        if not isinstance(state, bytes) or not state:
            raise ValueError("snapshot has no native state")
        manifest = build_battle_scenario_capture_payload(
            capture_id=f"trajectory-{self.directory.parent.name}-{index:03d}",
            root_lineage_id=self.parent.manifest.root_lineage_id,
            partition=ScenarioPartition.TRAIN, state_bytes=state,
            initial_observation_sha256=observed["initial_observation_sha256"],
            source_commit=self.source_commit, expected_map=observed["map_id"],
            expected_battle_state=2, observation_schema=OBSERVATION_SCHEMA_V2,
            source_state_sha256=self.parent.manifest.state_sha256)
        folder = self.directory / f"decision-{index:03d}"
        folder.mkdir(mode=0o700, parents=True, exist_ok=False)
        binding = {"schema": "pokemon.red.trajectory-decision-capture.v1",
                   "decision_index": index, "parent_capture_id": self.parent.manifest.capture_id,
                   "parent_manifest_sha256": self.parent.manifest_sha256,
                   "decision_event_sha256": self.log.previous_sha256,
                   "policy_observation_sha256": observation_sha,
                   "state_sha256": hashlib.sha256(state).hexdigest()}
        for name, value in (("capture.state", state), ("capture.state.json", manifest),
                            ("binding.json", binding)):
            payload = value if isinstance(value, bytes) else (
                json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
            with (folder / name).open("xb") as handle:
                handle.write(payload)
        self.log.emit({"event": "trajectory_capture_saved", **binding,
                       "binding_sha256": canonical_sha256(binding)})
