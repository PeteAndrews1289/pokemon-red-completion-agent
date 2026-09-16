"""Bounded model decisions with durable choices and changed-state replanning.

The environment supplies observed executable options; it never supplies a chosen
goal. Every choice is persisted before checking its authority or executing it.
Existing run directories are refused, including incomplete ones.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from .goal_manager import GoalDecisionOutcome, GoalKind
from .living_dex_option_value import LivingDexOptionValueModel
from .provenance import canonical_sha256
from .red_live_option_menu import (
    RedLiveOptionSelectionMode,
    RedLiveOptionSet,
    select_red_live_option,
)


@dataclass(frozen=True)
class AutonomousSnapshot:
    state: bytes
    facts: Mapping[str, object]
    safe: bool

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.state).hexdigest()


def _write(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _record(path: Path, document: Mapping[str, object]) -> None:
    _write(path, (json.dumps(document, sort_keys=True, indent=2) + "\n").encode())


def run_autonomous_options(
    *,
    model: LivingDexOptionValueModel,
    output: Path,
    snapshot: Callable[[], AutonomousSnapshot],
    observe: Callable[[int], RedLiveOptionSet],
    seed: int,
    maximum_decisions: int = 3,
    maximum_seconds: float = 1_800,
    provenance: Mapping[str, object],
) -> dict[str, object]:
    """Run up to N learned goals without a teacher action or resetting state.

    Primitive action/frame limits belong to the environment's executor. The
    wall-time limit here governs admission of the next decision. Outcomes and
    terminal saves survive ordinary execution/verification errors; any such
    error stops this continuation rather than invoking a fallback.
    """
    if type(seed) is not int or seed < 0:
        raise ValueError("autonomous seed must be a nonnegative integer")
    if type(maximum_decisions) is not int or not 1 <= maximum_decisions <= 10:
        raise ValueError("autonomous run requires one through ten decisions")
    if maximum_seconds <= 0:
        raise ValueError("autonomous run requires a positive time limit")
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    _record(
        output / "plan.json",
        {
            "schema": "pokemon.red.autonomous-option-run.v1",
            "seed": seed,
            "maximum_decisions": maximum_decisions,
            "maximum_seconds": maximum_seconds,
            "model_sha256": model.model_sha256,
            "exploration_mix": 0.25,
            "teacher_actions_allowed": False,
            "independent_evaluation": False,
            "provenance": dict(provenance),
        },
    )
    started = monotonic()
    outcomes: list[dict[str, object]] = []
    stop = "decision_budget"
    for ordinal in range(maximum_decisions):
        if monotonic() - started >= maximum_seconds:
            stop = "wall_time_budget"
            break
        step = output / f"step-{ordinal:03d}"
        step.mkdir()
        before = snapshot()
        _write(step / "before.state", before.state)
        _record(
            step / "before.json",
            {
                "state_sha256": before.sha256,
                "facts": dict(before.facts),
                "safe": before.safe,
            },
        )
        if not before.safe:
            stop = "unsafe_decision_boundary"
            break
        try:
            options = observe(ordinal)
            after_menu = snapshot()
            if after_menu != before:
                raise ValueError("menu construction changed the game")
            if len(options.menu.available_indices) < 2:
                raise ValueError("autonomous decision requires real alternatives")
        except Exception as error:
            _record(
                step / "admission-failure.json",
                {
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
            )
            terminal = snapshot()
            _write(step / "terminal.state", terminal.state)
            stop = "menu_unavailable"
            break
        decision_seed = int(canonical_sha256({"seed": seed, "ordinal": ordinal})[:16], 16)
        _record(
            step / "intent.json",
            {
                "menu": options.public_dict(),
                "state_sha256": before.sha256,
                "model_sha256": model.model_sha256,
                "selection_seed": decision_seed,
                "query_may_be_consumed": True,
            },
        )
        # Keep persistence adjacent to selection. No enum assertion, selected
        # callback resolution, or result-dependent validation precedes the write.
        choice = select_red_live_option(model, options, seed=decision_seed)
        _record(step / "decision.json", choice.public_dict())
        deterministic_storage = (
            choice.mode is RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY
            and choice.selected_binding.kind is GoalKind.MANAGE_STORAGE
        )
        if (
            choice.mode is not RedLiveOptionSelectionMode.MODEL_EXPLORATION
            and not deterministic_storage
        ):
            stop = "safety_boundary_requires_separate_recovery"
            break
        selected = choice.selected_binding
        _record(
            step / "execution-started.json",
            {
                "selected_binding_ref": selected.binding_ref,
                "selected_kind": selected.kind.value,
                "menu_sha256": options.menu.policy_sha256,
                "state_sha256": before.sha256,
            },
        )
        report = None
        verification = None
        execution_error: BaseException | None = None
        try:
            report = selected.execute()
            verification = selected.verify(report)
        except BaseException as error:
            execution_error = error
        finally:
            terminal = snapshot()
            _write(step / "terminal.state", terminal.state)
            outcome: dict[str, object] = {
                "ordinal": ordinal,
                "selected_kind": selected.kind.value,
                "choice": choice.public_dict(),
                "learning_eligible": choice.mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION,
                "support_role": ("deterministic_storage_safety" if deterministic_storage else None),
                "before_state_sha256": before.sha256,
                "terminal_state_sha256": terminal.sha256,
                "before": dict(before.facts),
                "after": dict(terminal.facts),
                "safe_terminal": terminal.safe,
                "verification": None if verification is None else verification.status.value,
                "failure_reason": (
                    None
                    if verification is None or verification.failure_reason is None
                    else verification.failure_reason.value
                ),
                "evidence": None if report is None else dict(report.evidence),
                "error_type": None if execution_error is None else type(execution_error).__name__,
                "error": None if execution_error is None else str(execution_error),
            }
            _record(step / "outcome.json", outcome)
            outcomes.append(outcome)
        if execution_error is not None:
            if not isinstance(execution_error, Exception):
                raise execution_error
            stop = "execution_failed"
            break
        if verification is None or verification.status is not GoalDecisionOutcome.SUCCEEDED:
            stop = "verification_failed"
            break
        if not terminal.safe:
            stop = "unsafe_terminal"
            break
        if terminal.state == before.state:
            stop = "no_state_progress"
            break
    result: dict[str, object] = {
        "schema": "pokemon.red.autonomous-option-result.v1",
        "stop_reason": stop,
        "executed_decisions": len(outcomes),
        "successful_decisions": sum(row["verification"] == "succeeded" for row in outcomes),
        "teacher_actions": 0,
        "model_decisions": sum(row["learning_eligible"] is True for row in outcomes),
        "support_decisions": sum(row["support_role"] is not None for row in outcomes),
        "model_sha256": model.model_sha256,
        "outcomes": outcomes,
    }
    _record(output / "result.json", result)
    return result
