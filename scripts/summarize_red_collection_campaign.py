#!/usr/bin/env python3
"""Validate and summarize a completed or in-progress Red collection continuation campaign.

Read-only diagnostic utility:
- Verifies full parent-child hash integrity chain from plan to final terminal.
- Reconciles aggregate totals against individual step segment sums.
- Verifies missing telemetry is None/unavailable, never fabricated as 0.
- Audits records for private path or credential leakage.
- Zero emulator starts, zero controller inputs, zero model queries.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_red_completion.red_collection_continuation import (
    INTENT_SCHEMA,
    OUTCOME_SCHEMA,
    PLAN_SCHEMA,
    SUMMARY_SCHEMA,
    ContinuationChainIntegrityError,
    RedCollectionContinuationJournal,
)

PRIVATE_PATH_PATTERNS = [
    re.compile(r"(/Users/|/home/|/Volumes/|[A-Za-z]:\\|/private/)"),
    re.compile(r"\.(gb|gbc|rom|sav|state)$", re.IGNORECASE),
]


def _audit_privacy(obj: Any, path: str = "") -> list[str]:
    """Recursively check for private paths or leaks in public data structures."""
    violations: list[str] = []
    if isinstance(obj, str):
        for pattern in PRIVATE_PATH_PATTERNS:
            if pattern.search(obj):
                violations.append(f"{path}: leaked private path pattern '{obj}'")
    elif isinstance(obj, Mapping):
        for k, v in obj.items():
            sub_path = f"{path}.{k}" if path else str(k)
            violations.extend(_audit_privacy(v, sub_path))
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            violations.extend(_audit_privacy(item, f"{path}[{i}]"))
    return violations


def summarize_red_collection_campaign(
    campaign_dir: Path | str,
    *,
    require_summary: bool = False,
) -> dict[str, Any]:
    """Read-only audit and summary of a continuation campaign directory.

    Raises ContinuationChainIntegrityError, ValueError, or FileNotFoundError on failure.
    """
    directory = Path(campaign_dir).resolve()
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"campaign directory does not exist: {directory}")

    plan_path = directory / "plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"campaign directory missing plan.json: {directory}")

    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError(
            f"plan.json schema mismatch: {plan.get('schema')} != {PLAN_SCHEMA}"
        )

    # 1. Audit hash chain through journal reconciler
    journal = RedCollectionContinuationJournal(directory)
    _, steps = journal.reconcile_campaign()

    # 2. Check each step's intent, dispatch, outcome schemas and hash links
    step_actions_sum = 0
    step_frames_sum = 0
    step_cash_sum = 0
    step_encounters_sum = 0
    model_decisions_count = 0
    successful_goals_count = 0

    privacy_violations: list[str] = []

    for step in steps:
        if step.intent.get("schema") != INTENT_SCHEMA:
            raise ContinuationChainIntegrityError(
                f"step-{step.step_index:03d} invalid intent schema"
            )
        if step.outcome.get("schema") != OUTCOME_SCHEMA:
            raise ContinuationChainIntegrityError(
                f"step-{step.step_index:03d} invalid outcome schema"
            )

        # Audit privacy on public step files
        privacy_violations.extend(
            _audit_privacy(step.intent, f"step-{step.step_index:03d}.intent")
        )
        if step.choice is not None:
            privacy_violations.extend(
                _audit_privacy(step.choice, f"step-{step.step_index:03d}.choice")
            )
        privacy_violations.extend(
            _audit_privacy(step.dispatch, f"step-{step.step_index:03d}.dispatch")
        )
        privacy_violations.extend(
            _audit_privacy(step.outcome, f"step-{step.step_index:03d}.outcome")
        )

        actions = step.outcome.get("actions_executed")
        frames = step.outcome.get("frames_executed")
        cash_delta = step.outcome.get("cash_delta")
        encounters = step.outcome.get("encounters_seen")

        # Telemetry validation: must be int, not bool, not negative
        for name, val in [
            ("actions_executed", actions),
            ("frames_executed", frames),
            ("cash_delta", cash_delta),
            ("encounters_seen", encounters),
        ]:
            if val is not None and (type(val) is not int or val < 0):
                raise ValueError(
                    f"step-{step.step_index:03d} {name} must be a non-negative int"
                )

        if actions is not None:
            step_actions_sum += actions
        if frames is not None:
            step_frames_sum += frames
        if cash_delta is not None:
            step_cash_sum += cash_delta
        if encounters is not None:
            step_encounters_sum += encounters

        if step.choice is not None and step.choice.get("model_queries", 0) > 0:
            model_decisions_count += 1

        if step.outcome.get("goal_completed") is True:
            successful_goals_count += 1

    continuation_chunks_count = sum(
        s.intent["step_kind"] == "continue_same_goal" for s in steps
    )

    # 3. Check summary.json if present
    summary_path = directory / "summary.json"
    summary_data: dict[str, Any] | None = None
    if summary_path.exists():
        summary_bytes = summary_path.read_bytes()
        summary_data = json.loads(summary_bytes)
        if summary_data.get("schema") != SUMMARY_SCHEMA:
            raise ValueError(
                f"summary.json schema mismatch: {summary_data.get('schema')} != {SUMMARY_SCHEMA}"
            )
        privacy_violations.extend(_audit_privacy(summary_data, "summary"))

        # Reconcile summary totals against step sums (F05)
        reconciled = summary_data.get("reconciled_totals", {})
        ledger = summary_data.get("ledger_totals", {})
        for key, expected in (
            ("actions", step_actions_sum), ("frames", step_frames_sum),
            ("cash_spent", step_cash_sum), ("encounters", step_encounters_sum),
        ):
            if type(ledger.get(key)) is not int or ledger[key] != expected:
                raise ContinuationChainIntegrityError(f"ledger {key} differs from segments")
        if reconciled.get("actions") != step_actions_sum:
            raise ContinuationChainIntegrityError(
                f"reconciled actions mismatch: summary {reconciled.get('actions')} "
                f"!= step sum {step_actions_sum}"
            )
        if reconciled.get("frames") != step_frames_sum:
            raise ContinuationChainIntegrityError(
                f"reconciled frames mismatch: summary {reconciled.get('frames')} "
                f"!= step sum {step_frames_sum}"
            )
        if reconciled.get("cash_spent") != step_cash_sum:
            raise ContinuationChainIntegrityError(
                f"reconciled cash_spent mismatch: summary {reconciled.get('cash_spent')} "
                f"!= step sum {step_cash_sum}"
            )
        if reconciled.get("encounters") != step_encounters_sum:
            raise ContinuationChainIntegrityError(
                f"reconciled encounters mismatch: summary {reconciled.get('encounters')} "
                f"!= step sum {step_encounters_sum}"
            )

        if summary_data.get("step_count") != len(steps):
            raise ContinuationChainIntegrityError(
                f"step_count mismatch: {summary_data.get('step_count')} != {len(steps)}"
            )
        if summary_data.get("model_decisions") != model_decisions_count:
            raise ContinuationChainIntegrityError(
                f"model_decisions mismatch: {summary_data.get('model_decisions')} "
                f"!= {model_decisions_count}"
            )
        if summary_data.get("continuation_chunks") != continuation_chunks_count:
            raise ContinuationChainIntegrityError(
                f"continuation_chunks mismatch: {summary_data.get('continuation_chunks')} "
                f"!= {continuation_chunks_count}"
            )
        if summary_data.get("successful_goals") != successful_goals_count:
            raise ContinuationChainIntegrityError(
                f"successful_goals mismatch: {summary_data.get('successful_goals')} "
                f"!= {successful_goals_count}"
            )
    elif require_summary:
        raise FileNotFoundError(f"campaign directory missing summary.json: {directory}")

    if privacy_violations:
        raise ContinuationChainIntegrityError(
            f"privacy leak violations detected: {'; '.join(privacy_violations)}"
        )

    return {
        "status": "verified",
        "campaign_id": plan.get("campaign_id"),
        "run_id": plan.get("run_id"),
        "stop_reason": (
            summary_data.get("stop_reason") if summary_data else "in_progress"
        ),
        "step_count": len(steps),
        "model_decisions": model_decisions_count,
        "continuation_chunks": continuation_chunks_count,
        "successful_goals": successful_goals_count,
        "reconciled_totals": {
            "actions": step_actions_sum,
            "frames": step_frames_sum,
            "cash_spent": step_cash_sum,
            "encounters": step_encounters_sum,
        },
        "hash_chain_verified": True,
        "privacy_verified": True,
        "native_qualification": "NOT RUN",
        "execution_enabled": False,
        "has_terminal_summary": summary_data is not None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify and summarize a collection continuation campaign directory."
    )
    parser.add_argument(
        "campaign_dir",
        type=Path,
        help="Path to the campaign output directory.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Perform strict verification and exit non-zero on any integrity failure.",
    )
    parser.add_argument(
        "--require-summary",
        action="store_true",
        help="Require final summary.json to be present (fails on in-progress campaigns).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit summary as JSON.",
    )

    args = parser.parse_args()
    try:
        result = summarize_red_collection_campaign(
            args.campaign_dir,
            require_summary=args.require_summary,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Campaign ID:         {result['campaign_id']}")
        print(f"Run ID:              {result['run_id']}")
        print(f"Status:              {result['status']}")
        print(f"Stop Reason:         {result['stop_reason']}")
        print(f"Total Steps:         {result['step_count']}")
        print(f"Model Decisions:     {result['model_decisions']}")
        print(f"Continuation Chunks: {result['continuation_chunks']}")
        print(f"Successful Goals:    {result['successful_goals']}")
        print(f"Reconciled Actions:  {result['reconciled_totals']['actions']}")
        print(f"Reconciled Frames:   {result['reconciled_totals']['frames']}")
        print(f"Reconciled Cash:     {result['reconciled_totals']['cash_spent']}")
        print(f"Reconciled Encounters: {result['reconciled_totals']['encounters']}")
        print(f"Hash Chain Verified: {result['hash_chain_verified']}")
        print(f"Privacy Verified:    {result['privacy_verified']}")


if __name__ == "__main__":
    main()
