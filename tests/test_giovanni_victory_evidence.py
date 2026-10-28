"""Earned boss rewards remain distinct from final fresh-run completion."""
import json
from pathlib import Path

REPORT = (
    Path(__file__).resolve().parents[1]
    / "docs/evidence/red-giovanni-earned-victory-2026-09-22.json"
)


def test_native_boss_outcome_and_costs() -> None:
    r = json.loads(REPORT.read_text())
    assert r["leader_defeated"] and r["badges"] == 8
    assert r["cash"] - r["cash_before"] == r["net_income"] == 4950
    assert r["contract"]["trainer_identity"] == [229, 29, 3]
    assert r["reward"]["native_defeat_event"] == 81
    assert r["reward"]["native_reward_event"] == 80
    assert r["reward"]["item"] == 227 and r["bag_stacks"] == 20
    assert sum(r["action_counts"].values()) == r["model_decisions"] == 31
    assert r["metrics"]["opponent_faints"] == 5
    assert r["metrics"]["party_faints"] == 1
    assert r["fully_restored"] and r["event_log_verified"]
    for cost in ("actions", "frames", "native_seconds"):
        assert 0 < r[cost] <= r["maximum_" + cost]
    assert r["model_decisions"] <= r["maximum_decisions"]


def test_one_new_attempt_does_not_refill_or_promote() -> None:
    r = json.loads(REPORT.read_text())
    assert r["old_contracts_consumed"] == 10
    assert r["new_contracts_consumed"] == r["new_contract_allowance"] == 1
    assert r["source_stage"] == 292 and r["terminal_stage"] == 293
    assert r["next_unused_stage"] == 294 and not r["gameplay_running"]
    assert r["story_objectives"] == 29 and r["local_registrations"] == 17
    assert r["primary_unchanged"] and not r["publication"]
    for key in ("new_fits", "new_goal_choices", "new_registrations", "authority_promotions",
                "source_replays", "save_edits", "audit_frames"):
        assert r[key] == 0
    assert not r["preparation_executed"] and not r["preparation_is_learned"]
    assert [t["party_slot"] for t in r["preparation_targets"]] == [1, 2, 4]
    assert all(t["target_level"] == 42 for t in r["preparation_targets"])
