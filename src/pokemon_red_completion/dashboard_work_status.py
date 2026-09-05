"""Path-free live engineering status consumed by the local dashboard."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pokemon_red_completion.progress_dashboard import DashboardWorkState

DASHBOARD_WORK_STATUS_SCHEMA = "pokemon.core.dashboard-work-status.v1"


class DashboardWorkStatusError(ValueError):
    """A dashboard work-status record is missing, malformed, or unsafe."""


def load_dashboard_work_status(path: Path) -> DashboardWorkState:
    """Load one status record, returning an honest idle state when absent."""

    if not isinstance(path, Path):
        raise TypeError("dashboard work-status path must be a Path")
    if not path.exists():
        return DashboardWorkState()
    try:
        document = json.loads(path.read_text(encoding="ascii"))
        if not isinstance(document, dict) or set(document) != {
            "completed_units",
            "current_step",
            "detail",
            "headline",
            "next_step",
            "schema",
            "status",
            "total_units",
            "updated_at_utc",
        }:
            raise ValueError("fields")
        if document["schema"] != DASHBOARD_WORK_STATUS_SCHEMA:
            raise ValueError("schema")
        return DashboardWorkState(
            status=document["status"],
            headline=document["headline"],
            detail=document["detail"],
            current_step=document["current_step"],
            next_step=document["next_step"],
            completed_units=document["completed_units"],
            total_units=document["total_units"],
            updated_at_utc=document["updated_at_utc"],
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise DashboardWorkStatusError("dashboard work-status authentication failed") from None


def write_dashboard_work_status(path: Path, status: DashboardWorkState) -> None:
    """Atomically replace the local path-free observer record."""

    if not isinstance(path, Path):
        raise TypeError("dashboard work-status path must be a Path")
    if not isinstance(status, DashboardWorkState):
        raise TypeError("dashboard work status differs")
    status.__post_init__()
    document = {"schema": DASHBOARD_WORK_STATUS_SCHEMA, **status.public_dict()}
    document.pop("progress")
    payload = json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "DASHBOARD_WORK_STATUS_SCHEMA",
    "DashboardWorkStatusError",
    "load_dashboard_work_status",
    "write_dashboard_work_status",
]
