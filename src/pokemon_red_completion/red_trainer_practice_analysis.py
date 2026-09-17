"""Authenticate and aggregate battle logs without mistaking siblings for roots."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log


def summarize_trainer_practice_runs(directories: Iterable[Path]) -> dict[str, object]:
    """Report outcomes, costs, failures, and lineage counts for retained runs.

    The caller chooses the run directories. Grouping by lineage prevents a
    parameter or RNG sweep from appearing to contain independent cases.
    """
    rows: list[dict[str, object]] = []
    for directory in directories:
        log_dir = directory / "events"
        verified = verify_trainer_practice_event_log(log_dir)
        if not verified["complete"]:
            raise ValueError("trainer practice run has no terminal event")
        first = _event(log_dir / "event-00001.json")
        identity = first.get("identity")
        if first.get("event") != "run_identity" or not isinstance(identity, dict):
            raise ValueError("trainer practice run identity is missing")
        final_sequence = verified["event_count"]
        assert isinstance(final_sequence, int)
        terminal = _event(log_dir / f"event-{final_sequence:05d}.json")
        partition = identity.get("partition")
        if partition not in {"train", "development"}:
            raise ValueError("trainer practice run partition is not admissible")
        capture_id = identity.get("capture_id")
        root = identity.get("root_lineage_id")
        policy = identity.get("policy_id")
        if not all(isinstance(value, str) and value for value in (capture_id, root, policy)):
            raise ValueError("trainer practice run identity is incomplete")
        row: dict[str, object] = {
            "capture_id": capture_id,
            "root_lineage_id": root,
            "partition": partition,
            "policy_id": policy,
            "complete": True,
            "event_count": final_sequence,
            "started_decisions": verified["started_decisions"],
            "completed_decisions": verified["completed_decisions"],
            "incomplete_decisions": verified["incomplete_decisions"],
            "last_record_sha256": verified["last_record_sha256"],
        }
        if terminal.get("event") == "run_finished":
            outcome = json.loads((directory / "outcome.json").read_bytes())
            terminal_outcome = terminal.get("outcome")
            if (
                not isinstance(outcome, dict)
                or not isinstance(terminal_outcome, dict)
                or terminal_outcome.get("outcome_sha256") != canonical_sha256(outcome)
                or outcome.get("capture_id") != capture_id
                or outcome.get("policy_id") != policy
            ):
                raise ValueError("trainer practice outcome differs from terminal event")
            row.update({
                "status": "finished",
                "battle_won": outcome.get("battle_won"),
                "stop_reason": outcome.get("stop_reason"),
                "decision_count": outcome.get("decision_count"),
                "player_turn_count": outcome.get("player_turn_count"),
                "elapsed_ns": outcome.get("elapsed_ns"),
                "policy_elapsed_ns": outcome.get("policy_elapsed_ns"),
                "frames_executed": outcome.get("frames_executed"),
                "action_counts": outcome.get("action_counts"),
                "metrics": outcome.get("metrics"),
            })
        elif terminal.get("event") == "run_failed":
            row.update({
                "status": "failed",
                "battle_won": False,
                "failure_type": terminal.get("error_type"),
                "failure_after_event": terminal.get("failure_after_event"),
            })
        else:
            raise ValueError("trainer practice run terminal differs")
        rows.append(row)
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["partition"]), str(row["policy_id"]))].append(row)
    summaries = []
    for (partition, policy), group in sorted(groups.items()):
        completed = [row for row in group if row["status"] == "finished"]
        roots = {str(row["root_lineage_id"]) for row in group}
        summaries.append({
            "partition": partition,
            "policy_id": policy,
            "runs": len(group),
            "upstream_roots": len(roots),
            "repeat_or_variant_runs": len(group) - len(roots),
            "battle_wins": sum(row["battle_won"] is True for row in completed),
            "battle_losses": sum(row["battle_won"] is False for row in completed),
            "failed_runs": len(group) - len(completed),
            "incomplete_decisions": sum(
                value for row in group
                if type(value := row["incomplete_decisions"]) is int
            ),
            "frames_executed": sum(
                int(row["frames_executed"])
                for row in completed if type(row["frames_executed"]) is int
            ),
            "elapsed_ns": sum(
                int(row["elapsed_ns"])
                for row in completed if type(row["elapsed_ns"]) is int
            ),
        })
    return {
        "schema": "pokemon.red.trainer-practice-cohort-summary.v1",
        "run_count": len(rows),
        "runs": rows,
        "groups": summaries,
        "model_updates": 0,
        "authority_promotions": 0,
    }


def _event(path: Path) -> dict[str, object]:
    record = json.loads(path.read_bytes())
    payload = record.get("payload") if isinstance(record, dict) else None
    if not isinstance(payload, dict):
        raise ValueError("trainer practice event payload differs")
    return payload
