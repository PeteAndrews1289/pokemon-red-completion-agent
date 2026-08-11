"""Public-safe projections of deterministic route plans and live receipts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from pokemon_red_completion.route_executor import RouteExecutionReport
from pokemon_red_completion.route_plan import RoutePlan


def rom_adjacent_artifacts(
    rom_path: Path,
) -> tuple[tuple[bool, str | None], ...]:
    """Fingerprint emulator sidecars without exposing their filesystem names."""

    return tuple(
        _artifact_identity(Path(f"{rom_path}{suffix}"))
        for suffix in (".ram", ".rtc", ".state")
    )


def public_route_plan(
    plan: RoutePlan,
    *,
    map_name: Callable[[int], str],
) -> dict[str, object]:
    """Project a route plan into a JSON-safe evidence record."""

    return {
        "maps": [map_name(map_id) for map_id in plan.macro_path.maps],
        "map_ids": list(plan.macro_path.maps),
        "start_yx": list(plan.start_at),
        "terminal_yx": list(plan.terminal_at),
        "actions": list(plan.actions),
        "segments": [
            {
                "source_map": map_name(segment.source_map),
                "source_map_id": segment.source_map,
                "target_map": map_name(segment.target_map),
                "target_map_id": segment.target_map,
                "approach_coordinates_yx": [
                    list(coordinate) for coordinate in segment.approach.coordinates
                ],
                "actions": list(segment.actions),
                "transition": {
                    "exit_yx": list(segment.transition.exit_at),
                    "arrival_yx": list(segment.transition.arrival_at),
                    "action": segment.transition.action,
                    "action_in_approach": segment.transition_action_in_approach,
                },
            }
            for segment in plan.segments
        ],
    }


def public_route_execution(report: RouteExecutionReport) -> dict[str, object]:
    """Project acknowledgements without private state or raw memory."""

    return {
        "passed": report.passed,
        "movement_requests": report.movement_requests,
        "wait_actions": report.wait_actions,
        "acknowledged_steps": len(report.executed_steps),
        "steps": [
            {
                "source_map_id": receipt.step.source_map,
                "source_yx": list(receipt.step.source_at),
                "action": receipt.step.action,
                "expected_map_id": receipt.step.expected_map,
                "expected_yx": list(receipt.step.expected_at),
                "kind": receipt.step.kind,
                "movement_requests": receipt.movement_requests,
                "interruption_count": receipt.interruption_count,
            }
            for receipt in report.executed_steps
        ],
        "interruptions": [
            {
                "kind": receipt.kind,
                "resumed_map_id": receipt.resumed_map,
                "resumed_yx": list(receipt.resumed_at),
                "details": dict(receipt.details),
            }
            for receipt in report.interruptions
        ],
        "replans": [
            {
                "ordinal": receipt.ordinal,
                "map_id": receipt.map_id,
                "at_yx": list(receipt.at),
                "newly_blocked_yx": list(receipt.newly_blocked),
                "replacement_steps": receipt.replacement_steps,
            }
            for receipt in report.replans
        ],
        "terminal_map_id": report.terminal.map_id,
        "terminal_yx": list(report.terminal.at),
        "terminal_ready": report.terminal.ready,
        "terminal_last_outside_map_id": report.terminal.last_outside_map,
    }


def public_route_plan_summary(
    plan: RoutePlan,
    *,
    map_name: Callable[[int], str],
) -> dict[str, object]:
    """Compact a long plan while retaining a digest of its full projection."""

    full = public_route_plan(plan, map_name=map_name)
    return {
        "schema": "route-plan-summary-v1",
        "maps": full["maps"],
        "map_ids": full["map_ids"],
        "start_yx": full["start_yx"],
        "terminal_yx": full["terminal_yx"],
        "route_cost": plan.cost,
        "route_steps": len(plan.steps),
        "map_transitions": len(plan.segments),
        "full_projection_sha256": _canonical_sha256(full),
    }


def public_route_execution_summary(
    report: RouteExecutionReport,
) -> dict[str, object]:
    """Compact a long execution while retaining hashes of all acknowledgements."""

    full = public_route_execution(report)
    return {
        "schema": "route-execution-summary-v1",
        "passed": full["passed"],
        "movement_requests": full["movement_requests"],
        "wait_actions": full["wait_actions"],
        "acknowledged_steps": full["acknowledged_steps"],
        "interruptions": full["interruptions"],
        "replans": full["replans"],
        "terminal_map_id": full["terminal_map_id"],
        "terminal_yx": full["terminal_yx"],
        "terminal_ready": full["terminal_ready"],
        "terminal_last_outside_map_id": full["terminal_last_outside_map_id"],
        "executed_steps_sha256": _canonical_sha256(full["steps"]),
        "full_projection_sha256": _canonical_sha256(full),
    }


def _artifact_identity(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()
