"""Durable records and read-only validation for bounded collection continuation.

This module enforces immutable step journaling, authenticated parent-child hash
chains, exclusive claims, and conservative crash recovery. No uncertain state
is ever retried or guessed. Automatic execution/resume is not integrated.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pokemon_red_completion.collection_continuation import (
    ContinuationBudgetCaps,
    ContinuationBudgetLedger,
    ContinuationDirective,
    ContinuationPolicy,
)

PLAN_SCHEMA = "pokemon.red.collection-continuation-plan.v1"
INTENT_SCHEMA = "pokemon.red.collection-continuation-intent.v1"
CHOICE_SCHEMA = "pokemon.red.collection-continuation-choice.v1"
DISPATCH_SCHEMA = "pokemon.red.collection-continuation-dispatch.v1"
OUTCOME_SCHEMA = "pokemon.red.collection-continuation-outcome.v1"
SUMMARY_SCHEMA = "pokemon.red.collection-continuation-summary.v1"


class RedCollectionContinuationError(RuntimeError):
    """Base error for continuation coordinator and journal failures."""


class ContinuationClaimError(RedCollectionContinuationError):
    """Raised when an exclusive campaign claim cannot be acquired."""


class ContinuationAmbiguityError(RedCollectionContinuationError):
    """Raised when execution or query state is ambiguous and cannot be recovered safely."""


class ContinuationChainIntegrityError(RedCollectionContinuationError):
    """Raised when parent-child hash chains, schemas, or terminals are broken."""


def _write_atomic(path: Path, payload: bytes) -> None:
    """Exclusively create and flush a record; interrupted partial files fail validation."""
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _record_json(path: Path, document: Mapping[str, Any]) -> None:
    """Write a canonical pretty-printed JSON file."""
    _write_atomic(path, (json.dumps(document, sort_keys=True, indent=2) + "\n").encode())


def _read_json(path: Path, *, expected_schema: str | None = None) -> dict[str, Any]:
    """Read and validate a required JSON document."""
    if not path.is_file():
        raise ContinuationChainIntegrityError(f"missing required record: {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ContinuationChainIntegrityError(
            f"corrupted JSON document in {path.name}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ContinuationChainIntegrityError(f"record {path.name} is not a JSON object")
    if expected_schema is not None:
        schema = data.get("schema")
        if schema != expected_schema:
            raise ContinuationChainIntegrityError(
                f"schema mismatch in {path.name}: expected {expected_schema}, got {schema}"
            )
    return data


class CampaignClaimLease:
    """Exclusive process-level file lock on the campaign output directory."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.lock_path = output_dir / "claim.lock"
        self._descriptor = -1

    def __enter__(self) -> CampaignClaimLease:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> Literal[False]:
        self.release_claim()
        return False

    def acquire(self) -> None:
        if self._descriptor >= 0:
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            os.close(descriptor)
            raise ContinuationClaimError(
                f"campaign directory {self.output_dir} is already locked by another process"
            ) from exc
        self._descriptor = descriptor

    def release_claim(self) -> None:
        if self._descriptor >= 0:
            with suppress(OSError):
                fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            with suppress(OSError):
                os.close(self._descriptor)
            self._descriptor = -1


@dataclass(frozen=True, slots=True)
class ReconciledStep:
    """One verified immutable step in the durable journal."""

    step_index: int
    step_dir: Path
    intent: dict[str, Any]
    choice: dict[str, Any] | None
    dispatch: dict[str, Any]
    terminal_state_sha256: str
    outcome: dict[str, Any]
    safe_terminal: bool


def validate_collection_continuation_plan(plan: Mapping[str, Any]) -> None:
    """Validate an opt-in collection continuation plan before runtime loading (F03)."""
    if not isinstance(plan, Mapping):
        raise ValueError("collection continuation plan must be a mapping")
    if plan.get("mode") != "collection_continuation":
        raise ValueError(f"expected mode 'collection_continuation', got {plan.get('mode')!r}")
    run_id = plan.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    output = plan.get("output")
    if not isinstance(output, (str, Path)) or not str(output):
        raise ValueError("output must be a non-empty path string")
    model_sha256 = plan.get("model_sha256")
    if (
        not isinstance(model_sha256, str)
        or len(model_sha256) != 64
        or re.fullmatch(r"[0-9a-fA-F]{64}", model_sha256) is None
    ):
        raise ValueError("model_sha256 must be a 64-character hexadecimal string")
    caps_dict = plan.get("caps")
    if not isinstance(caps_dict, Mapping):
        raise ValueError("caps must be a mapping of continuation budget caps")
    try:
        ContinuationBudgetCaps(**caps_dict)
    except Exception as exc:
        raise ValueError(f"invalid continuation budget caps: {exc}") from exc
    policy_dict = plan.get("policy")
    if not isinstance(policy_dict, Mapping):
        raise ValueError("policy must be a mapping of continuation policy parameters")
    try:
        ContinuationPolicy(**policy_dict)
    except Exception as exc:
        raise ValueError(f"invalid continuation policy: {exc}") from exc
    for key in ("rom", "state", "checkpoint", "profile", "model"):
        if key not in plan or not isinstance(plan[key], Mapping):
            raise ValueError(f"collection continuation plan missing payload mapping: {key}")
        p = plan[key].get("path")
        if not isinstance(p, (str, Path)) or not str(p):
            raise ValueError(f"{key} path must be a non-empty path string")
        sha = plan[key].get("sha256")
        if (
            not isinstance(sha, str)
            or len(sha) != 64
            or re.fullmatch(r"[0-9a-fA-F]{64}", sha) is None
        ):
            raise ValueError(f"{key} sha256 must be a 64-character hexadecimal string")


class RedCollectionContinuationJournal:
    """Manages the append-only record stream and verification of a campaign."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def initialize_campaign(
        self,
        *,
        campaign_id: str,
        run_id: str,
        caps: ContinuationBudgetCaps,
        policy: ContinuationPolicy,
        model_sha256: str,
        initial_state_sha256: str,
        provenance: Mapping[str, Any],
        clock: Callable[[], float],
    ) -> dict[str, Any]:
        """Initialize a new campaign plan. Refuses existing output if not empty."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        plan_path = self.output_dir / "plan.json"
        if plan_path.exists():
            raise FileExistsError(f"campaign plan already exists at {plan_path}")

        plan = {
            "schema": PLAN_SCHEMA,
            "campaign_id": campaign_id,
            "run_id": run_id,
            "created_at": clock(),
            "caps": {
                "maximum_decisions": caps.maximum_decisions,
                "maximum_continuation_chunks_per_goal": (caps.maximum_continuation_chunks_per_goal),
                "maximum_continuation_chunks_per_campaign": (
                    caps.maximum_continuation_chunks_per_campaign
                ),
                "maximum_actions": caps.maximum_actions,
                "maximum_frames": caps.maximum_frames,
                "maximum_cash_spend": caps.maximum_cash_spend,
                "maximum_encounters": caps.maximum_encounters,
                "maximum_consecutive_no_progress": (caps.maximum_consecutive_no_progress),
                "maximum_wall_seconds": caps.maximum_wall_seconds,
            },
            "policy": {
                "step_reserve": policy.step_reserve,
                "local_action_quantum": policy.local_action_quantum,
                "local_frame_quantum": policy.local_frame_quantum,
                "local_encounter_quantum": policy.local_encounter_quantum,
            },
            "model_sha256": model_sha256,
            "initial_state_sha256": initial_state_sha256,
            "provenance": dict(provenance),
        }
        _record_json(plan_path, plan)
        return plan

    def read_and_validate_plan(
        self,
        *,
        expected_caps: ContinuationBudgetCaps | None = None,
        expected_policy: ContinuationPolicy | None = None,
        expected_model_sha256: str | None = None,
        expected_initial_state_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Read plan.json and verify policy and identities are compatible (E15)."""
        plan = _read_json(self.output_dir / "plan.json", expected_schema=PLAN_SCHEMA)
        try:
            ContinuationBudgetCaps(**plan["caps"])
            ContinuationPolicy(**plan["policy"])
        except (KeyError, TypeError, ValueError) as error:
            raise ContinuationChainIntegrityError("invalid saved budget/policy") from error

        if expected_model_sha256 is not None and plan.get("model_sha256") != expected_model_sha256:
            raise ContinuationChainIntegrityError(
                f"plan model {plan.get('model_sha256')} != expected {expected_model_sha256}"
            )
        if (
            expected_initial_state_sha256 is not None
            and plan.get("initial_state_sha256") != expected_initial_state_sha256
        ):
            raise ContinuationChainIntegrityError("plan initial state differs from expected")

        if expected_caps is not None:
            saved_caps = plan.get("caps", {})
            for key in (
                "maximum_decisions",
                "maximum_continuation_chunks_per_goal",
                "maximum_continuation_chunks_per_campaign",
                "maximum_actions",
                "maximum_frames",
                "maximum_cash_spend",
                "maximum_encounters",
                "maximum_consecutive_no_progress",
                "maximum_wall_seconds",
            ):
                if saved_caps.get(key) != getattr(expected_caps, key):
                    raise ContinuationChainIntegrityError(
                        f"incompatible caps change on resume: {key} ({saved_caps.get(key)} "
                        f"!= {getattr(expected_caps, key)})"
                    )

        if expected_policy is not None:
            saved_policy = plan.get("policy", {})
            for key in (
                "step_reserve",
                "local_action_quantum",
                "local_frame_quantum",
                "local_encounter_quantum",
            ):
                if saved_policy.get(key) != getattr(expected_policy, key):
                    raise ContinuationChainIntegrityError(
                        f"incompatible policy change on resume: {key} ({saved_policy.get(key)} "
                        f"!= {getattr(expected_policy, key)})"
                    )
        return plan

    def reconcile_campaign(self) -> tuple[dict[str, Any], list[ReconciledStep]]:
        """Validate existing step chain and detect crash ambiguity (E01–E15)."""
        plan = self.read_and_validate_plan()
        steps: list[ReconciledStep] = []
        step_index = 0
        seen_parent_terminals: set[str] = set()
        expected_parent_state: str = plan["initial_state_sha256"]
        expected_parent_outcome: str | None = None
        directories = sorted(self.output_dir.glob("step-*"))
        if any(
            p.name != f"step-{i:03d}" or not p.is_dir() or p.is_symlink()
            for i, p in enumerate(directories)
        ):
            raise ContinuationChainIntegrityError("step sequence is missing or invalid")

        while True:
            step_dir = self.output_dir / f"step-{step_index:03d}"
            if not step_dir.exists():
                break

            intent_path = step_dir / "intent.json"
            if not intent_path.exists():
                raise ContinuationChainIntegrityError(f"step-{step_index:03d} missing intent.json")
            intent = _read_json(intent_path, expected_schema=INTENT_SCHEMA)

            # E08: No two children for one parent terminal
            parent_terminal = intent.get("parent_terminal_sha256")
            if not isinstance(parent_terminal, str):
                raise ContinuationChainIntegrityError(
                    f"step-{step_index:03d} invalid parent_terminal_sha256"
                )
            if parent_terminal != expected_parent_state:
                raise ContinuationChainIntegrityError(
                    f"step-{step_index:03d} parent terminal {parent_terminal} != "
                    f"expected {expected_parent_state}"
                )
            if parent_terminal in seen_parent_terminals:
                raise ContinuationChainIntegrityError(
                    f"step-{step_index:03d} parent terminal {parent_terminal} already has a child"
                )
            seen_parent_terminals.add(parent_terminal)

            parent_outcome = intent.get("parent_outcome_sha256")
            if parent_outcome != expected_parent_outcome:
                raise ContinuationChainIntegrityError(
                    f"step-{step_index:03d} parent outcome {parent_outcome} != "
                    f"expected {expected_parent_outcome}"
                )

            choice_path = step_dir / "choice.json"
            choice = (
                _read_json(choice_path, expected_schema=CHOICE_SCHEMA)
                if choice_path.exists()
                else None
            )

            dispatch_path = step_dir / "dispatch.json"
            terminal_state_path = step_dir / "terminal.state"
            outcome_path = step_dir / "outcome.json"

            # Check for crash ambiguity
            if not dispatch_path.exists():
                # Step wrote intent (and possibly choice) but not dispatch.
                # E02 / E03: uncertain whether query or work ran -> ambiguous stop!
                raise ContinuationAmbiguityError(
                    f"step-{step_index:03d} has intent/choice without dispatch; cannot retry"
                )

            dispatch = _read_json(dispatch_path, expected_schema=DISPATCH_SCHEMA)

            if not terminal_state_path.exists() or not outcome_path.exists():
                # E04 / E05: execution started but no trustworthy terminal or outcome
                raise ContinuationAmbiguityError(
                    f"step-{step_index:03d} has dispatch but missing terminal or outcome"
                )

            outcome = _read_json(outcome_path, expected_schema=OUTCOME_SCHEMA)
            terminal_bytes = terminal_state_path.read_bytes()
            actual_terminal_sha = hashlib.sha256(terminal_bytes).hexdigest()

            if outcome.get("terminal_state_sha256") != actual_terminal_sha:
                raise ContinuationChainIntegrityError(
                    f"step-{step_index:03d} terminal.state sha256 mismatch with outcome"
                )

            before_bytes = (step_dir / "before.state").read_bytes()
            before_doc = _read_json(step_dir / "before.json")
            terminal_doc = _read_json(step_dir / "terminal.json")
            if any(
                value != expected_parent_state
                for value in (
                    hashlib.sha256(before_bytes).hexdigest(),
                    outcome.get("before_state_sha256"),
                    before_doc.get("state_sha256"),
                    dispatch.get("before_state_sha256"),
                )
            ):
                raise ContinuationChainIntegrityError("before state differs from parent terminal")
            if terminal_doc.get("state_sha256") != actual_terminal_sha or terminal_doc.get(
                "safe_terminal"
            ) != outcome.get("safe_terminal"):
                raise ContinuationChainIntegrityError("terminal metadata differs from outcome")
            for name in ("safe_terminal", "made_progress", "goal_completed", "goal_pending"):
                if type(outcome.get(name)) is not bool:
                    raise ContinuationChainIntegrityError(f"invalid boolean: {name}")
            for name in ("actions_executed", "frames_executed", "encounters_seen", "cash_delta"):
                if type(outcome.get(name)) is not int or outcome[name] < 0:
                    raise ContinuationChainIntegrityError(f"missing/invalid telemetry: {name}")
            try:
                directive = ContinuationDirective(outcome["directive"])
            except (KeyError, ValueError) as error:
                raise ContinuationChainIntegrityError("invalid directive") from error
            safe_terminal = outcome["safe_terminal"]
            if outcome["goal_completed"] and (not safe_terminal or outcome["goal_pending"]):
                raise ContinuationChainIntegrityError("inconsistent completed goal")
            kind = intent.get("step_kind")
            if (
                type(intent.get("step_index")) is not int
                or intent["step_index"] != step_index
                or kind not in ("new_goal", "continue_same_goal")
                or dispatch.get("step_kind") != kind
            ):
                raise ContinuationChainIntegrityError("invalid step identity/kind")
            if kind == "new_goal":
                if choice is None:
                    raise ContinuationChainIntegrityError("new goal lacks a durable choice")
                if type(choice.get("model_queries")) is not int or choice["model_queries"] not in (
                    0,
                    1,
                ):
                    raise ContinuationChainIntegrityError("invalid model query count")
                for key in ("selected_kind", "selected_binding_ref"):
                    if not isinstance(choice.get(key), str) or choice[key] != dispatch.get(key):
                        raise ContinuationChainIntegrityError("choice/dispatch identity mismatch")
            else:
                if choice is not None or not steps:
                    raise ContinuationChainIntegrityError(
                        "continuation has new choice or no parent"
                    )
                if steps[-1].outcome["directive"] != ContinuationDirective.CONTINUE_SAME_GOAL.value:
                    raise ContinuationChainIntegrityError(
                        "parent did not permit same-goal continuation"
                    )
                for key in ("selected_kind", "selected_binding_ref"):
                    if dispatch.get(key) != steps[-1].dispatch.get(key):
                        raise ContinuationChainIntegrityError("continuation changed selected goal")
            if steps and (
                not steps[-1].safe_terminal
                or steps[-1].outcome["directive"]
                in (
                    ContinuationDirective.COMPLETE.value,
                    ContinuationDirective.SAFE_STOP.value,
                    ContinuationDirective.AMBIGUOUS_STOP.value,
                )
            ):
                raise ContinuationChainIntegrityError("terminal stop cannot have a child")
            if kind == "new_goal" and steps and steps[-1].outcome["directive"] != "replan":
                raise ContinuationChainIntegrityError("parent did not permit replanning")
            if not safe_terminal and directive in (
                ContinuationDirective.CONTINUE_SAME_GOAL,
                ContinuationDirective.REPLAN,
                ContinuationDirective.COMPLETE,
            ):
                raise ContinuationChainIntegrityError("unsafe terminal cannot authorize work")

            reconciled = ReconciledStep(
                step_index=step_index,
                step_dir=step_dir,
                intent=intent,
                choice=choice,
                dispatch=dispatch,
                terminal_state_sha256=actual_terminal_sha,
                outcome=outcome,
                safe_terminal=safe_terminal,
            )
            steps.append(reconciled)

            expected_parent_state = actual_terminal_sha
            expected_parent_outcome = hashlib.sha256(
                json.dumps(outcome, sort_keys=True).encode()
            ).hexdigest()
            step_index += 1

        return plan, steps

    def record_step_intent(
        self,
        step_index: int,
        *,
        step_kind: str,
        parent_terminal_sha256: str,
        parent_outcome_sha256: str | None,
        clock: Callable[[], float],
    ) -> Path:
        step_dir = self.output_dir / f"step-{step_index:03d}"
        step_dir.mkdir(parents=False, exist_ok=False)
        intent = {
            "schema": INTENT_SCHEMA,
            "step_index": step_index,
            "step_kind": step_kind,
            "parent_terminal_sha256": parent_terminal_sha256,
            "parent_outcome_sha256": parent_outcome_sha256,
            "timestamp": clock(),
        }
        _record_json(step_dir / "intent.json", intent)
        return step_dir

    def record_step_choice(
        self,
        step_dir: Path,
        *,
        selected_kind: str,
        selected_binding_ref: str,
        menu_sha256: str | None,
        model_queries: int,
        choice_provenance: Mapping[str, Any] | None = None,
    ) -> None:
        choice = {
            "schema": CHOICE_SCHEMA,
            "selected_kind": selected_kind,
            "selected_binding_ref": selected_binding_ref,
            "menu_sha256": menu_sha256,
            "model_queries": model_queries,
            "choice_provenance": dict(choice_provenance or {}),
        }
        _record_json(step_dir / "choice.json", choice)

    def record_step_dispatch(
        self,
        step_dir: Path,
        *,
        selected_kind: str,
        selected_binding_ref: str,
        before_state_sha256: str,
        step_kind: str,
        budget_snapshot: Mapping[str, Any],
    ) -> None:
        dispatch = {
            "schema": DISPATCH_SCHEMA,
            "selected_kind": selected_kind,
            "selected_binding_ref": selected_binding_ref,
            "before_state_sha256": before_state_sha256,
            "step_kind": step_kind,
            "budget_snapshot": dict(budget_snapshot),
        }
        _record_json(step_dir / "dispatch.json", dispatch)

    def record_step_terminal(
        self,
        step_dir: Path,
        *,
        before_state_bytes: bytes,
        before_facts: Mapping[str, Any],
        terminal_state_bytes: bytes,
        terminal_facts: Mapping[str, Any],
        safe_terminal: bool,
        directive: ContinuationDirective,
        stop_reason: str,
        actions_executed: int,
        frames_executed: int,
        encounters_seen: int,
        cash_delta: int,
        made_progress: bool,
        goal_completed: bool,
        goal_pending: bool,
        error_info: Mapping[str, Any] | None = None,
        evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        before_sha = hashlib.sha256(before_state_bytes).hexdigest()
        terminal_sha = hashlib.sha256(terminal_state_bytes).hexdigest()

        # Write state payloads atomically
        _write_atomic(step_dir / "before.state", before_state_bytes)
        _record_json(
            step_dir / "before.json",
            {"state_sha256": before_sha, "facts": dict(before_facts)},
        )

        _write_atomic(step_dir / "terminal.state", terminal_state_bytes)
        _record_json(
            step_dir / "terminal.json",
            {
                "state_sha256": terminal_sha,
                "facts": dict(terminal_facts),
                "safe_terminal": safe_terminal,
            },
        )

        outcome = {
            "schema": OUTCOME_SCHEMA,
            "before_state_sha256": before_sha,
            "terminal_state_sha256": terminal_sha,
            "safe_terminal": safe_terminal,
            "directive": directive.value,
            "stop_reason": stop_reason,
            "goal_completed": goal_completed,
            "goal_pending": goal_pending,
            "made_progress": made_progress,
            "actions_executed": actions_executed,
            "frames_executed": frames_executed,
            "encounters_seen": encounters_seen,
            "cash_delta": cash_delta,
            "error": dict(error_info) if error_info is not None else None,
            "evidence": dict(evidence) if evidence is not None else {},
        }
        _record_json(step_dir / "outcome.json", outcome)
        return outcome

    def record_summary(
        self,
        *,
        campaign_id: str,
        run_id: str,
        stop_reason: str,
        ledger: ContinuationBudgetLedger,
        steps: list[ReconciledStep],
        initial_facts: Mapping[str, Any],
        final_facts: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Re-read durable steps; do not trust caller-supplied in-memory choice counts."""
        _, steps = self.reconcile_campaign()
        total_actions = sum(s.outcome.get("actions_executed", 0) for s in steps)
        total_frames = sum(s.outcome.get("frames_executed", 0) for s in steps)
        total_cash_delta = sum(s.outcome.get("cash_delta", 0) for s in steps)
        total_encounters = sum(s.outcome.get("encounters_seen", 0) for s in steps)
        if (total_actions, total_frames, total_cash_delta, total_encounters) != (
            ledger.actions_spent,
            ledger.frames_spent,
            ledger.cash_spent,
            ledger.encounters_seen,
        ):
            raise ContinuationChainIntegrityError("ledger totals differ from durable segment sums")

        model_decisions = sum(
            1 for s in steps if s.choice is not None and s.choice.get("model_queries", 0) > 0
        )
        continuation_chunks = sum(s.intent["step_kind"] == "continue_same_goal" for s in steps)
        successful_goals = sum(1 for s in steps if s.outcome.get("goal_completed") is True)

        summary = {
            "schema": SUMMARY_SCHEMA,
            "campaign_id": campaign_id,
            "run_id": run_id,
            "stop_reason": stop_reason,
            "step_count": len(steps),
            "model_decisions": model_decisions,
            "continuation_chunks": continuation_chunks,
            "successful_goals": successful_goals,
            "reconciled_totals": {
                "actions": total_actions,
                "frames": total_frames,
                "cash_spent": total_cash_delta,
                "encounters": total_encounters,
                "elapsed_seconds": ledger.elapsed_seconds,
            },
            "ledger_totals": {
                "actions": ledger.actions_spent,
                "frames": ledger.frames_spent,
                "cash_spent": ledger.cash_spent,
                "encounters": ledger.encounters_seen,
                "elapsed_seconds": ledger.elapsed_seconds,
            },
            "remaining_budgets": ledger.remaining_budgets(),
            "initial_facts": {
                "registered_species": initial_facts.get("registered_species"),
                "specimens": initial_facts.get("specimens"),
                "cash": initial_facts.get("cash"),
            },
            "final_facts": {
                "registered_species": final_facts.get("registered_species"),
                "specimens": final_facts.get("specimens"),
                "cash": final_facts.get("cash"),
            },
            "native_qualification": "NOT RUN",
        }
        _record_json(self.output_dir / "summary.json", summary)
        return summary


class ContinuationUnavailableError(RedCollectionContinuationError):
    """The Flash execution draft was rejected; live orchestration is unavailable."""


def run_collection_continuation_campaign(**kwargs: Any) -> dict[str, Any]:
    """Reject before callbacks, model queries, artifact creation or controller inputs.

    Only the journal, ledger and read-only diagnostic components are integrated.
    Reintroducing execution requires model selection, bounded adapters and a qualified
    resume contract. The original draft is retained in Git, not callable here.
    """
    raise ContinuationUnavailableError("automatic collection continuation is not qualified")
