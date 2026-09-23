"""Bounded model decisions with durable choices and changed-state replanning.

The environment supplies observed executable options; it never supplies a chosen
goal. Every choice is persisted before checking its authority or executing it.
Existing run directories are refused, including incomplete ones.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import cast

from .goal_manager import GoalDecisionOutcome, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding
from .goal_search_memory import GoalSearchMemory
from .living_dex_option_value import LivingDexOptionValueModel
from .provenance import canonical_sha256
from .red_integrated_play import (
    measured_cost,
    menu_with_search_history,
    objective_key,
    ordinary_paid_search_setback,
    search_objective_key,
    spending_bound,
)
from .red_live_option_menu import (
    RedLiveOptionSelectionMode,
    RedLiveOptionSet,
    select_red_live_option,
)


def _exception_chain(error: BaseException | None) -> list[dict[str, object]] | None:
    """Preserve bounded typed causes without losing the terminal state.

    Autonomous execution deliberately stops on the first failure.  Retaining
    only the wrapper text makes that safe stop needlessly opaque, especially
    when a route adapter has attached a more specific controller failure as
    ``__cause__``.  Eight links is well beyond the project's normal nesting
    depth while still bounding hostile or cyclic exception graphs.
    """

    if error is None:
        return None
    rows: list[dict[str, object]] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(rows) < 8:
        seen.add(id(current))
        row: dict[str, object] = {
            "error_type": type(current).__name__,
            "error": str(current),
        }
        reason_code = getattr(current, "reason_code", None)
        if isinstance(reason_code, str) and reason_code:
            row["reason_code"] = reason_code
        rows.append(row)
        current = current.__cause__
    return rows


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


def continuation_binding(
    options: RedLiveOptionSet | tuple[ExecutableGoalBinding, ...],
    prior_binding_ref: str,
) -> ExecutableGoalBinding:
    """Rebind one privately authenticated goal across changed origin states."""
    bindings = cast(tuple[ExecutableGoalBinding, ...], getattr(options, "bindings", options))
    if re.fullmatch(r"pokemon\.red:story:[a-z][a-z0-9_]*", prior_binding_ref):
        # Story references are stable objective identities, not origin-dependent
        # evolution configurations. Never substitute another available objective.
        matches = tuple(binding for binding in bindings
                        if binding.kind is GoalKind.ADVANCE_STORY
                        and binding.binding_ref == prior_binding_ref)
        if len(matches) != 1:
            raise ValueError("prior story goal has no unique live binding")
        return matches[0]
    fingerprint = prior_binding_ref.rsplit(":", 1)[-1]
    if re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
        raise ValueError("prior goal has no valid configuration fingerprint")
    matches = tuple(
        binding for binding in bindings
        if binding.kind is GoalKind.EVOLVE_SPECIES
        and binding.binding_ref.rsplit(":", 1)[-1] == fingerprint
    )
    if len(matches) != 1:
        raise ValueError("prior evolution goal has no unique live binding")
    return matches[0]


def run_autonomous_goal_continuation(
    *,
    output: Path,
    snapshot: Callable[[], AutonomousSnapshot],
    observe: Callable[[int], RedLiveOptionSet],
    prior_binding_ref: str,
    prior_outcome_sha256: str,
    provenance: Mapping[str, object],
    targeted_observe: Callable[[], tuple[ExecutableGoalBinding, ...]] | None = None,
) -> dict[str, object]:
    """Execute a saved model goal once, with no new model query or reward fit."""
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    _record(output / "plan.json", {
        "schema": "pokemon.red.autonomous-goal-continuation.v1",
        "prior_binding_ref": prior_binding_ref,
        "prior_outcome_sha256": prior_outcome_sha256,
        "model_queries": 0,
        "teacher_actions_allowed": False,
        "provenance": dict(provenance),
    })
    before = snapshot()
    _write(output / "before.state", before.state)
    _record(output / "before.json", {
        "state_sha256": before.sha256, "facts": dict(before.facts), "safe": before.safe,
    })
    if not before.safe:
        raise ValueError("unsafe continuation origin")
    try:
        options = None if targeted_observe is not None else observe(0)
        targeted = None if targeted_observe is None else targeted_observe()
        if snapshot() != before:
            raise ValueError("continuation inventory changed the game")
        selected = continuation_binding(
            options if options is not None else targeted or (), prior_binding_ref,
        )
    except Exception as admission_error:
        _record(output / "admission-failure.json", {
            "error_type": type(admission_error).__name__,
            "error": str(admission_error),
        })
        raise
    _record(output / "execution-started.json", {
        "selected_binding_ref": selected.binding_ref,
        "selected_kind": selected.kind.value,
        "prior_binding_ref": prior_binding_ref,
        "state_sha256": before.sha256,
        "menu_sha256": None if options is None else options.menu.policy_sha256,
        "private_inventory_sha256": (
            None if targeted is None else canonical_sha256([
                binding.binding_ref for binding in targeted
            ])
        ),
        "binding_scope": (
            "full_menu" if targeted is None else
            "targeted_story" if selected.kind is GoalKind.ADVANCE_STORY else "targeted_evolution"
        ),
    })
    report = None
    verification = None
    error: BaseException | None = None
    try:
        report = selected.execute()
        verification = selected.verify(report)
    except BaseException as caught:
        error = caught
    finally:
        terminal = snapshot()
        _write(output / "terminal.state", terminal.state)
        outcome = {
            "before_state_sha256": before.sha256,
            "terminal_state_sha256": terminal.sha256,
            "before": dict(before.facts),
            "after": dict(terminal.facts),
            "safe_terminal": terminal.safe,
            "verification": None if verification is None else verification.status.value,
            "evidence": None if report is None else dict(report.evidence),
            "error_chain": _exception_chain(error),
            "model_queries": 0,
            "learning_eligible": False,
        }
        _record(output / "outcome.json", outcome)
    if error is not None and not isinstance(error, Exception):
        raise error
    completed = (
        error is None and terminal.safe and verification is not None
        and verification.status is GoalDecisionOutcome.SUCCEEDED
    )
    status = "complete" if completed else "pending" if (
        terminal.safe and terminal.sha256 != before.sha256
        and _party_experience_gain(before.facts, terminal.facts) > 0
    ) else "stopped"
    result = {
        "schema": "pokemon.red.autonomous-goal-continuation-result.v1",
        "status": status,
        "experience_gain": _party_experience_gain(before.facts, terminal.facts),
        "model_queries": 0,
        "model_decisions": 0,
        "teacher_actions": 0,
        "outcome": outcome,
    }
    _record(output / "result.json", result)
    return result


def _party_experience_gain(before: Mapping[str, object], after: Mapping[str, object]) -> int:
    """Conservative slot/species-matched training delta, not a reward label."""
    old = before.get("party_training")
    new = after.get("party_training")
    if not isinstance(old, list) or not isinstance(new, list):
        return 0
    return sum(
        max(0, current[2] - prior[2])
        for prior, current in zip(old, new, strict=False)
        if prior[0] == current[0] and prior[1] == current[1]
    )


def run_assisted_safari_probe(
    *,
    output: Path,
    snapshot: Callable[[], AutonomousSnapshot],
    observe: Callable[[int], RedLiveOptionSet],
    provenance: Mapping[str, object],
) -> dict[str, object]:
    """Exercise one teacher-selected Safari binding without a model query or fit."""
    assistance = provenance.get("training_assistance")
    if (
        not isinstance(assistance, Mapping)
        or assistance.get("kind") != "money_override"
        or assistance.get("final_run_eligible") is not False
    ):
        raise ValueError("Safari training probe requires marked non-final assistance")
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    _record(output / "plan.json", {
        "schema": "pokemon.red.assisted-safari-mechanics.v1",
        "teacher_selected_skill": "safari",
        "model_queries": 0,
        "goal_value_fit_allowed": False,
        "independent_evaluation": False,
        "provenance": dict(provenance),
    })
    before = snapshot()
    _write(output / "before.state", before.state)
    _record(output / "before.json", {
        "state_sha256": before.sha256, "facts": dict(before.facts), "safe": before.safe,
    })
    if not before.safe:
        raise ValueError("unsafe Safari training origin")
    try:
        options = observe(0)
        if snapshot() != before:
            raise ValueError("Safari training inventory changed the game")
        selected_indices = [
            index for index in options.menu.available_indices
            if options.bindings[index].kind is GoalKind.ACQUIRE_SPECIES
            and options.bindings[index].binding_ref.startswith("pokemon.red:safari-live:")
        ]
        if len(selected_indices) != 1:
            raise ValueError("Safari training needs exactly one available live binding")
        selected = options.bindings[selected_indices[0]]
    except Exception as admission_error:
        _record(output / "admission-failure.json", {
            "error_type": type(admission_error).__name__, "error": str(admission_error),
        })
        raise
    _record(output / "execution-started.json", {
        "selected_binding_ref": selected.binding_ref,
        "selected_kind": selected.kind.value,
        "selected_candidate_index": selected_indices[0],
        "menu_sha256": options.menu.policy_sha256,
        "state_sha256": before.sha256,
        "selection_authority": "teacher_training_only",
        "model_queries": 0,
    })
    report = None
    verification = None
    execution_error: BaseException | None = None
    try:
        report = selected.execute()
        verification = selected.verify(report)
    except BaseException as caught:
        execution_error = caught
    finally:
        terminal = snapshot()
        _write(output / "terminal.state", terminal.state)
        outcome = {
            "before_state_sha256": before.sha256,
            "terminal_state_sha256": terminal.sha256,
            "before": dict(before.facts),
            "after": dict(terminal.facts),
            "safe_terminal": terminal.safe,
            "verification": None if verification is None else verification.status.value,
            "failure_reason": (
                None if verification is None or verification.failure_reason is None
                else verification.failure_reason.value
            ),
            "evidence": None if report is None else dict(report.evidence),
            "error_chain": _exception_chain(execution_error),
            "model_queries": 0,
            "learning_eligible": False,
            "goal_value_fit_allowed": False,
        }
        _record(output / "outcome.json", outcome)
    if execution_error is not None and not isinstance(execution_error, Exception):
        raise execution_error
    complete = (
        execution_error is None and terminal.safe and verification is not None
        and verification.status is GoalDecisionOutcome.SUCCEEDED
    )
    result: dict[str, object] = {
        "schema": "pokemon.red.assisted-safari-mechanics-result.v1",
        "status": "complete" if complete else "stopped",
        "model_queries": 0,
        "model_decisions": 0,
        "teacher_training_selections": 1,
        "goal_value_fit_allowed": False,
        "outcome": outcome,
    }
    _record(output / "result.json", result)
    return result


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
    integrated_play: bool = False,
    maximum_cash_spent: int = 0,
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
    if type(integrated_play) is not bool or type(maximum_cash_spent) is not int or (
        maximum_cash_spent < 0 or (not integrated_play and maximum_cash_spent != 0)
    ):
        raise ValueError("integrated play requires explicit scope and cash bound")
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
            "integrated_play": integrated_play,
            "maximum_cash_spent": maximum_cash_spent,
            "provenance": dict(provenance),
        },
    )
    started = monotonic()
    outcomes: list[dict[str, object]] = []
    stop = "decision_budget"
    memory = GoalSearchMemory()
    cash_spent = 0
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
            if integrated_play:
                objective = objective_key(before.facts)
                options = menu_with_search_history(options, memory, objective)
                _record(step / "search-memory-before.json", {
                    "state_sha256": before.sha256, "objective_sha256": objective,
                    "objectives_by_binding": {
                        binding.binding_ref: search_objective_key(binding, objective)
                        for binding in options.bindings
                    },
                    "memory": memory.private_dict(),
                })
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
                "query_may_be_consumed": len({
                    options.menu.candidate_vector(i)
                    for i in options.menu.available_indices
                }) > 1,
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
            choice.mode not in {
                RedLiveOptionSelectionMode.MODEL_EXPLORATION,
                RedLiveOptionSelectionMode.EQUIVALENT_EXPLORATION,
            }
            and not deterministic_storage
        ):
            stop = "safety_boundary_requires_separate_recovery"
            break
        selected = choice.selected_binding
        debit_bound = spending_bound(selected) if integrated_play else None
        if integrated_play and (
            debit_bound is None or cash_spent + debit_bound > maximum_cash_spent
        ):
            stop = "integrated_scope_or_spending_boundary"
            break
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
            cost = measured_cost(before.facts, terminal.facts, report)
            ordinary_setback = integrated_play and ordinary_paid_search_setback(
                selected, before, terminal, report, verification, execution_error,
            )
            outcome: dict[str, object] = {
                "ordinal": ordinal,
                "selected_kind": selected.kind.value,
                "choice": choice.public_dict(),
                "learning_eligible": choice.mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION,
                "support_role": (
                    "deterministic_storage_safety"
                    if deterministic_storage else
                    "equivalent_goal_exploration"
                    if choice.mode is RedLiveOptionSelectionMode.EQUIVALENT_EXPLORATION else None
                ),
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
                "error_chain": _exception_chain(execution_error),
                "measured_cost": cost,
                "ordinary_setback": ordinary_setback,
            }
            _record(step / "outcome.json", outcome)
            outcomes.append(outcome)
        if execution_error is not None:
            if not isinstance(execution_error, Exception):
                raise execution_error
            stop = "execution_failed"
            break
        if verification is None or (
            verification.status is not GoalDecisionOutcome.SUCCEEDED and not ordinary_setback
        ):
            stop = "verification_failed"
            break
        if not terminal.safe:
            stop = "unsafe_terminal"
            break
        if terminal.state == before.state:
            stop = "no_state_progress"
            break
        if integrated_play:
            if cost is None or not 0 <= cost["cash_spent"] <= debit_bound:
                stop = "unaccounted_integrated_cost"
                break
            cash_spent += cost["cash_spent"]
            selected_objective = search_objective_key(selected, objective)
            memory.record(selected.search_memory_source, selected_objective,
                          exhausted=ordinary_setback,
                          actions=cost["actions"], frames=cost["frames"])
            _record(step / "search-memory-after.json", {
                "state_sha256": terminal.sha256,
                "outcome_sha256": canonical_sha256(outcome),
                "objective_sha256": selected_objective, "memory": memory.private_dict(),
                "cumulative_cash_spent": cash_spent,
            })
    result: dict[str, object] = {
        "schema": "pokemon.red.autonomous-option-result.v1",
        "stop_reason": stop,
        "executed_decisions": len(outcomes),
        "successful_decisions": sum(row["verification"] == "succeeded" for row in outcomes),
        "teacher_actions": 0,
        "model_decisions": sum(row["learning_eligible"] is True for row in outcomes),
        "support_decisions": sum(row["support_role"] is not None for row in outcomes),
        "model_sha256": model.model_sha256,
        "integrated_play": integrated_play,
        "accounted_cash_spent": cash_spent,
        "ordinary_setbacks": sum(row["ordinary_setback"] for row in outcomes),
        "outcomes": outcomes,
    }
    _record(output / "result.json", result)
    return result
