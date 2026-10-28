"""Keep the earned continuation and its stop distinct from a Giovanni win."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/evidence/red-forward-gym-clearance-2026-09-22.json"


def test_forward_clearance_preserves_chain_costs_and_authority() -> None:
    report = json.loads(REPORT.read_text())
    rows = report["battles"]
    assert [row["stage"] for row in rows] == list(range(286, 291))
    for previous, current in zip(rows[:-1], rows[1:], strict=True):
        assert previous["final_sha256"] == current["source_sha256"]
    assert rows[-1]["final_sha256"] == report["terminal_sha256"]
    assert sum(row["decisions"] for row in rows) == report["model_decisions"] == 61
    assert sum(report["action_counts"].values()) == 61
    assert sum(row["income"] for row in rows) == report["net_income"] == 6305
    assert report["cash"] - report["cash_before"] == 6305
    for key in ("actions", "frames", "native_seconds"):
        assert sum(row[key] for row in rows) == pytest.approx(report[key])
    assert all(row["full_recovery"] and row["outcome"] == "won" for row in rows)
    assert report["metrics"]["party_faints"] == 5
    assert report["metrics"]["teacher_interventions"] == 0
    assert report["metrics"]["invalid_action_failures"] == 0


def test_forward_clearance_does_not_turn_a_routing_stop_into_completion() -> None:
    report = json.loads(REPORT.read_text())
    assert not report["leader_defeated"] and report["badges"] == 7
    assert report["safe_adjacent_candidates"] == 0
    assert report["total_gym_contracts_used"] == 9 < report["maximum_total_gym_contracts"]
    assert [row["object_index"] for row in report["remaining_trainers"]] == [1, 6, 9]
    assert not report["gameplay_running"] and report["primary_unchanged"]
    for key in ("new_fits", "new_registrations", "new_goal_choices", "authority_promotions",
                "source_replays", "save_edits", "preparation_refills", "audit_frames"):
        assert report[key] == 0


def test_forward_clearance_latency_aggregation_uses_extrema_and_weights() -> None:
    report = json.loads(REPORT.read_text())
    rows = report["battles"]
    metrics = report["metrics"]
    assert metrics["policy_latency_ns_max"] == max(
        row["metrics"]["policy_latency_ns_max"] for row in rows
    )
    assert metrics["policy_latency_ns_min"] == min(
        row["metrics"]["policy_latency_ns_min"] for row in rows
    )
    weighted = sum(row["decisions"] * row["metrics"]["policy_latency_ns_mean"] for row in rows)
    assert metrics["policy_latency_ns_mean"] == pytest.approx(weighted / report["model_decisions"])
