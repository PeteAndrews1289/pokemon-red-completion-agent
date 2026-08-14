from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_collection_runtime import (
    GoalManagerContextPreflight,
)
from pokemon_red_completion.goal_manager_preflight import (
    GoalManagerPreflightError,
    build_goal_manager_preflight_payload,
    context_entry_from_preflight,
    parse_goal_manager_preflight,
)
from pokemon_red_completion.goal_manager_protocol import (
    GOAL_MANAGER_REGISTRY_RELATIVE_PATH,
    parse_goal_manager_registry,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _assignment():  # type: ignore[no-untyped-def]
    registry = parse_goal_manager_registry(
        (PROJECT_ROOT / GOAL_MANAGER_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    committed = replace(
        registry,
        execution=replace(registry.execution, source_commit="a" * 40),
    )
    return committed.assignment(committed.slots[0].slot_id)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _preflight():
    assignment = _assignment()
    available = {
        GoalKind.ADVANCE_STORY,
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.EXPLORE,
    }
    question = GoalManagerQuestion(
        GoalSituation(0.75, 0.75, 0.1, 0.1, 0.0, 0.2, 0.0, 0.0, 0.5),
        tuple(
            GoalOpportunity(
                binding_ref=f"test:{kind.value}",
                kind=kind,
                availability=(
                    GoalAvailability.AVAILABLE
                    if kind in available
                    else GoalAvailability.UNAVAILABLE
                ),
                estimated_effort=0.1 if kind in available else None,
                estimated_risk=0.1 if kind in available else None,
                unavailable_reason=(
                    None
                    if kind in available
                    else GoalUnavailableReason.MISSING_CAPABILITY
                ),
            )
            for kind in GoalKind
        ),
    )
    return GoalManagerContextPreflight(
        assignment_id=assignment.assignment_id,
        slot_id=assignment.slot_id,
        capture_id="authenticated-context-001",
        state_sha256=_digest("state"),
        envelope_sha256=_digest("envelope"),
        focus_kind=assignment.focus_kind,
        selected_kind=assignment.focus_kind,
        available_goal_count=3,
        available_goal_kinds=(
            GoalKind.ADVANCE_STORY,
            GoalKind.ACQUIRE_SPECIES,
            GoalKind.EXPLORE,
        ),
        focus_pressure=0.75,
        question_sha256=question.ordered_policy_input_sha256,
        policy_context_sha256=question.policy_context_sha256,
        available_menu_sha256=question.available_menu_sha256,
        selected_candidate_index=0,
        candidate_goal_kinds=tuple(item.kind for item in question.opportunities),
        binding_manifest_sha256=_digest("bindings"),
    )


def test_preflight_receipt_round_trips_into_one_catalog_entry() -> None:
    assignment = _assignment()
    preflight = _preflight()

    payload = build_goal_manager_preflight_payload(preflight, assignment)
    parsed = parse_goal_manager_preflight(payload, assignment)
    entry = context_entry_from_preflight(assignment, parsed)

    assert parsed == preflight
    assert entry.capture_id == preflight.capture_id
    assert entry.binding_manifest_sha256 == preflight.binding_manifest_sha256
    assert entry.policy_context_sha256 == preflight.policy_context_sha256
    assert entry.available_menu_sha256 == preflight.available_menu_sha256
    assert b"/Users/" not in payload


def test_preflight_receipt_rejects_assignment_or_action_drift() -> None:
    assignment = _assignment()
    document = json.loads(build_goal_manager_preflight_payload(_preflight(), assignment))
    document["actions_executed"] = 1
    drifted = (
        json.dumps(document, separators=(",", ":"), sort_keys=True).encode("ascii")
        + b"\n"
    )

    with pytest.raises(GoalManagerPreflightError, match="committed assignment"):
        parse_goal_manager_preflight(drifted, assignment)
