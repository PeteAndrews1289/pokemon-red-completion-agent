"""Read-only, loopback-only live feed for the persistent spectator overview.

The relay accepts only the dashboard's typed public projection and PNG frames.
It has no controller or model reference, never follows HTTP redirects, and falls
back to the saved overview when the live producer ends or becomes unavailable.
"""

from __future__ import annotations

import json
import math
import re
import time
import urllib.error
import urllib.request
from dataclasses import fields
from typing import Any, TypeVar, cast

from pokemon_red_completion.progress_dashboard import (
    DASHBOARD_SCHEMA,
    DashboardExperimentState,
    DashboardGoalPressure,
    DashboardLearningComponent,
    DashboardLiveEvaluationState,
    DashboardModelState,
    DashboardPartyMember,
    DashboardSnapshot,
    DashboardState,
    DashboardTrainingState,
    DashboardWorkState,
    ProgressDashboardError,
)

T = TypeVar("T")
_LIMIT = 2 * 1024 * 1024
_PRIVATE_TEXT = re.compile(
    r"(?:file://|/(?:Users|Volumes|home|private|tmp)/|[A-Z]:\\|0x[0-9a-f]{4,})", re.I
)


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ProgressDashboardError("live observer object differs")
    return value


def _typed(kind: type[T], value: object) -> T:
    document = _object(value)
    return kind(
        **{
            field.name: document[field.name]
            for field in fields(cast(Any, kind))
            if field.name in document
        }
    )


def snapshot_from_public_status(document: object) -> DashboardSnapshot:
    """Reconstruct known public fields through the same validators as a producer."""
    data = _object(document)
    if (
        data.get("schema") != DASHBOARD_SCHEMA
        or any(
            data.get(key) != 0
            for key in ("controller_endpoints", "private_path_fields", "raw_address_fields")
        )
        or _object(data.get("dashboard")).get("view_only") is not True
        or _PRIVATE_TEXT.search(json.dumps(data, ensure_ascii=True))
    ):
        raise ProgressDashboardError("live observer public boundary differs")
    collection = _object(data["collection"])
    resources = _object(data["resources"])
    for key, maximum in (("party", 6), ("goals", 32), ("learning_components", 16), ("events", 24)):
        if not isinstance(data.get(key), list) or len(data[key]) > maximum:
            raise ProgressDashboardError("live observer roster differs")
    experiment = _object(data["experiment"])
    labels = _object(experiment["counter_labels"])
    counters = {
        f"{field}_{part}": _object(experiment[key])[part]
        for key, field in (
            ("zero_shot", "zero_shot"),
            ("adaptation", "adaptation"),
            ("sealed_test", "sealed"),
        )
        for part in ("completed", "total")
    }
    components = []
    for item in data.get("learning_components", []):
        component = dict(_object(item))
        counts = _object(component.get("candidate_count_results", {}))
        component["candidate_count_results"] = tuple(
            (int(key), value["correct"], value["total"]) for key, value in counts.items()
        )
        components.append(_typed(DashboardLearningComponent, component))
    snapshot = DashboardSnapshot(
        game=data["game"],
        run_status=data["run_status"],
        stage=data["stage"],
        message=data["message"],
        frame_count=data["frame_count"],
        actions=data["actions"],
        emulation_speed=data["emulation_speed"],
        stage_progress=data["stage_progress"],
        location=data["location"],
        registered_species=collection["registered"],
        living_species=collection["living"],
        level_cap_species=collection["level_cap"],
        collection_target=collection["target"],
        collection_observed=collection.get("observed", True),
        capture_items=resources["capture_items"],
        free_storage_slots=resources["free_storage_slots"],
        party=tuple(_typed(DashboardPartyMember, item) for item in data["party"]),
        goals=tuple(_typed(DashboardGoalPressure, item) for item in data["goals"]),
        model=_typed(DashboardModelState, data["model"]),
        experiment=DashboardExperimentState(
            **counters,
            phase=experiment["phase"],
            predictions_committed=experiment["predictions_committed"],
            heading=experiment["heading"],
            eyebrow=experiment["eyebrow"],
            counter_labels=(labels["zero_shot"], labels["adaptation"], labels["sealed_test"]),
        ),
        learning_components=tuple(components),
        live_evaluation=(
            _typed(DashboardLiveEvaluationState, data["live_evaluation"])
            if data.get("live_evaluation") is not None
            else None
        ),
        training=(
            _typed(DashboardTrainingState, data["training"])
            if data.get("training") is not None
            else None
        ),
        work=_typed(DashboardWorkState, data["work"]),
        events=tuple(data["events"]),
    )
    return snapshot


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class DashboardRelayState(DashboardState):
    """A GET-only observer feed; failure restores the local evidence overview."""

    def __init__(self, snapshot: DashboardSnapshot, *, live_port: int) -> None:
        super().__init__(snapshot)
        if type(live_port) is not int or not 1024 <= live_port <= 65535:  # noqa: E721
            raise ProgressDashboardError("live observer port differs")
        self._origin = f"http://127.0.0.1:{live_port}"
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        self._remote: tuple[DashboardSnapshot, dict[str, Any], float] | None = None
        self._remote_frame: bytes | None = None
        self._remote_version: tuple[object, object] | None = None
        self._frame_received_at: float | None = None

    def _get(self, endpoint: str) -> bytes:
        if endpoint not in {"/api/status", "/frame.png"}:
            raise ProgressDashboardError("live observer endpoint differs")
        with self._opener.open(self._origin + endpoint, timeout=0.75) as response:
            payload = response.read(_LIMIT + 1)
        if len(payload) > _LIMIT:
            raise ProgressDashboardError("live observer payload is too large")
        return payload

    def poll(self) -> bool:
        try:
            data = _object(json.loads(self._get("/api/status")))
            snapshot = snapshot_from_public_status(data)
            metadata = _object(data["dashboard"])
            if not isinstance(metadata.get("frame_ready"), bool):
                raise ProgressDashboardError("live observer frame flag differs")
            for key in ("snapshot_version", "frame_version", "logical_frame"):
                if type(metadata.get(key)) is not int or metadata[key] < 0:  # noqa: E721
                    raise ProgressDashboardError("live observer counter differs")
            for key in ("frame_age_seconds", "snapshot_age_seconds"):
                age = metadata.get(key)
                if age is not None and (
                    isinstance(age, bool)
                    or not isinstance(age, (int, float))
                    or not math.isfinite(age)
                    or age < 0
                ):
                    raise ProgressDashboardError("live observer freshness differs")
            version = (metadata["frame_version"], metadata["logical_frame"])
            metadata = {
                key: metadata[key]
                for key in (
                    "snapshot_version",
                    "frame_version",
                    "logical_frame",
                    "frame_ready",
                    "view_only",
                    "frame_age_seconds",
                    "snapshot_age_seconds",
                )
                if key in metadata
            }
            frame = None
            if metadata["frame_ready"] and version != self._remote_version:
                frame = self._get("/frame.png")
                if not frame.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ProgressDashboardError("live observer frame differs")
            with self._lock:
                if frame is not None:
                    self._remote_frame = frame
                    self._frame_received_at = time.monotonic()
                self._remote_version = version
                self._remote = (snapshot, metadata, time.monotonic())
            return True
        except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
            with self._lock:
                self._remote = None
                self._remote_frame = None
                self._remote_version = None
                self._frame_received_at = None
            return False

    def status_bytes(self) -> tuple[bytes, int]:
        with self._lock:
            remote = self._remote
            if remote is not None:
                snapshot, metadata, received = remote
                now = time.monotonic()
                result = snapshot.public_dict()
                result["work"] = self._snapshot.work.public_dict()
                # Keep the saved training chart only when the live producer
                # identifies that exact fitted artifact and sample count.
                training = self._snapshot.training
                if snapshot.training is None and training is not None:
                    known_models = {
                        item.model_sha256
                        for item in self._snapshot.learning_components
                        if item.train_examples == training.samples_after
                    }
                    if any(
                        item.model_sha256 in known_models
                        and item.train_examples == training.samples_after
                        for item in snapshot.learning_components
                    ):
                        result["training"] = training.public_dict()
                result["dashboard"] = {
                    **metadata,
                    "frame_ready": self._remote_frame is not None,
                    "frame_age_seconds": max(
                        now - (self._frame_received_at or now),
                        float(metadata.get("frame_age_seconds") or 0) + now - received,
                    ),
                    "snapshot_age_seconds": float(metadata.get("snapshot_age_seconds") or 0)
                    + now
                    - received,
                }
                return json.dumps(result, allow_nan=False).encode(), self._snapshot_version
        return super().status_bytes()

    def frame_bytes(self) -> tuple[bytes, int]:
        with self._lock:
            if self._remote is not None and self._remote_frame is not None:
                return self._remote_frame, int(self._remote[1]["frame_version"])
        return super().frame_bytes()
