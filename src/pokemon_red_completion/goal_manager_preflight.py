"""Canonical path-free receipts for prospective goal-manager contexts.

A receipt is produced before any counted action.  It binds an authenticated
capture, the identity-free question, the private executable manifest, and the
teacher's prospective selection to one committed assignment.  The complete
set of 81 receipts can then be frozen into a context catalog without reopening
or executing any cartridge state.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_collection_runtime import (
    GoalManagerContextPreflight,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalogEntry,
)
from pokemon_red_completion.goal_manager_protocol import GoalManagerAssignment

GOAL_MANAGER_PREFLIGHT_SCHEMA = "pokemon-red-goal-manager-context-preflight-v1"


class GoalManagerPreflightError(RuntimeError):
    """Raised when prospective context evidence is incomplete or altered."""


def build_goal_manager_preflight_payload(
    preflight: GoalManagerContextPreflight,
    assignment: GoalManagerAssignment,
) -> bytes:
    """Serialize one passed preflight against its exact committed assignment."""

    _require_assignment(preflight, assignment)
    return _canonical_line(
        {
            "schema": GOAL_MANAGER_PREFLIGHT_SCHEMA,
            "collection_id": assignment.collection_id,
            "registry_sha256": assignment.registry_sha256,
            "source_bundle_sha256": assignment.source_bundle_sha256,
            "source_commit": assignment.source_commit,
            "assignment_id": preflight.assignment_id,
            "slot_id": preflight.slot_id,
            "capture_id": preflight.capture_id,
            "state_sha256": preflight.state_sha256,
            "envelope_sha256": preflight.envelope_sha256,
            "focus_kind": preflight.focus_kind.value,
            "selected_kind": preflight.selected_kind.value,
            "available_goal_count": preflight.available_goal_count,
            "available_goal_kinds": [
                kind.value for kind in preflight.available_goal_kinds
            ],
            "focus_pressure": preflight.focus_pressure,
            "question_sha256": preflight.question_sha256,
            "binding_manifest_sha256": preflight.binding_manifest_sha256,
            "passed": True,
            "actions_executed": 0,
            "episode_created": False,
            "private_path_fields": 0,
        }
    )


def parse_goal_manager_preflight(
    payload: bytes,
    assignment: GoalManagerAssignment,
) -> GoalManagerContextPreflight:
    """Parse canonical bytes and bind them back to one public assignment."""

    if not isinstance(payload, bytes):
        raise TypeError("goal-manager preflight payload must be bytes")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise GoalManagerPreflightError(
            "goal-manager preflight is not canonical ASCII JSON"
        ) from None
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise GoalManagerPreflightError(
            "goal-manager preflight is not canonical ASCII JSON"
        )
    _exact_keys(
        value,
        {
            "schema",
            "collection_id",
            "registry_sha256",
            "source_bundle_sha256",
            "source_commit",
            "assignment_id",
            "slot_id",
            "capture_id",
            "state_sha256",
            "envelope_sha256",
            "focus_kind",
            "selected_kind",
            "available_goal_count",
            "available_goal_kinds",
            "focus_pressure",
            "question_sha256",
            "binding_manifest_sha256",
            "passed",
            "actions_executed",
            "episode_created",
            "private_path_fields",
        },
    )
    expected = {
        "schema": GOAL_MANAGER_PREFLIGHT_SCHEMA,
        "collection_id": assignment.collection_id,
        "registry_sha256": assignment.registry_sha256,
        "source_bundle_sha256": assignment.source_bundle_sha256,
        "source_commit": assignment.source_commit,
        "assignment_id": assignment.assignment_id,
        "slot_id": assignment.slot_id,
        "focus_kind": assignment.focus_kind.value,
        "passed": True,
        "actions_executed": 0,
        "episode_created": False,
        "private_path_fields": 0,
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise GoalManagerPreflightError(
            "goal-manager preflight differs from its committed assignment"
        )
    raw_available = value.get("available_goal_kinds")
    try:
        selected = GoalKind(_text(value, "selected_kind"))
        if not isinstance(raw_available, list):
            raise TypeError
        available = tuple(GoalKind(item) for item in raw_available)
    except (TypeError, ValueError):
        raise GoalManagerPreflightError("goal-manager preflight kinds are invalid") from None
    preflight = GoalManagerContextPreflight(
        assignment_id=_text(value, "assignment_id"),
        slot_id=_text(value, "slot_id"),
        capture_id=_text(value, "capture_id"),
        state_sha256=_text(value, "state_sha256"),
        envelope_sha256=_text(value, "envelope_sha256"),
        focus_kind=assignment.focus_kind,
        selected_kind=selected,
        available_goal_count=_integer(value, "available_goal_count"),
        available_goal_kinds=available,
        focus_pressure=_number(value, "focus_pressure"),
        question_sha256=_text(value, "question_sha256"),
        binding_manifest_sha256=_text(value, "binding_manifest_sha256"),
    )
    _require_assignment(preflight, assignment)
    return preflight


def context_entry_from_preflight(
    assignment: GoalManagerAssignment,
    preflight: GoalManagerContextPreflight,
) -> GoalManagerContextCatalogEntry:
    """Convert a passed prospective receipt into one frozen catalog row."""

    _require_assignment(preflight, assignment)
    return GoalManagerContextCatalogEntry.build(
        assignment=assignment,
        capture_id=preflight.capture_id,
        state_sha256=preflight.state_sha256,
        envelope_sha256=preflight.envelope_sha256,
        question_sha256=preflight.question_sha256,
        binding_manifest_sha256=preflight.binding_manifest_sha256,
        focus_pressure=preflight.focus_pressure,
        selected_kind=preflight.selected_kind,
        available_goal_kinds=preflight.available_goal_kinds,
    )


def _require_assignment(
    preflight: GoalManagerContextPreflight,
    assignment: GoalManagerAssignment,
) -> None:
    if not isinstance(preflight, GoalManagerContextPreflight):
        raise TypeError("preflight must be a GoalManagerContextPreflight")
    if not isinstance(assignment, GoalManagerAssignment):
        raise TypeError("assignment must be a GoalManagerAssignment")
    if assignment.source_commit is None:
        raise GoalManagerPreflightError("preflight requires committed source")
    if (
        not preflight.passed
        or preflight.assignment_id != assignment.assignment_id
        or preflight.slot_id != assignment.slot_id
        or preflight.focus_kind is not assignment.focus_kind
    ):
        raise GoalManagerPreflightError(
            "goal-manager preflight differs from its committed assignment"
        )


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _exact_keys(value: Mapping[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise GoalManagerPreflightError("goal-manager preflight fields differ")


def _text(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise GoalManagerPreflightError(f"goal-manager preflight {key} is invalid")
    return result


def _integer(value: Mapping[str, object], key: str) -> int:
    result = value.get(key)
    if type(result) is not int or result < 0:  # noqa: E721
        raise GoalManagerPreflightError(f"goal-manager preflight {key} is invalid")
    return result


def _number(value: Mapping[str, object], key: str) -> float:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, (int, float)):
        raise GoalManagerPreflightError(f"goal-manager preflight {key} is invalid")
    return float(result)
