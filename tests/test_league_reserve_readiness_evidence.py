"""Preparation closes early on actual targets, not a lowered gate or model fit."""
import json
from pathlib import Path

REPORT = (
    Path(__file__).resolve().parents[1]
    / "docs/evidence/red-league-reserve-readiness-2026-09-22.json"
)


def test_actual_targets_and_early_stop() -> None:
    r = json.loads(REPORT.read_text())
    assert r["outings"] == 20 and r["maximum_new_outings"] == 24
    assert r["prior_outings_preserved"] == 11 and r["unused_outings"] == 4
    assert r["preparation_complete"] and r["story_preparation_gate_passed"]
    assert r["targets_met"] == r["targets_total"] == 3
    assert r["reserve_xp_remaining"] == 0 and r["stop_reason"] == "all_targets_reached"
    targets = [x for x in r["party"] if x["target_level"] is not None]
    assert all(x["target_level"] == x["level_after"] == 42 for x in targets)
    assert sum(x["xp_gained"] for x in targets) == r["reserve_xp"] == 20190
    assert r["encounters"] == r["wins"] == 150
    assert sum(x["decisions"] for x in r["episodes"]) == r["model_decisions"] == 367
    assert sum(r["action_counts"].values()) == 367


def test_retained_chain_resources_and_scope() -> None:
    r = json.loads(REPORT.read_text())
    for a, b in zip(r["stages"][:-1], r["stages"][1:], strict=True):
        assert a["terminal_sha256"] == b["source_sha256"]
    assert r["stages"][0]["source_sha256"] == r["source_sha256"]
    assert r["stages"][-1]["terminal_sha256"] == r["terminal_sha256"]
    assert all(x["error"] is None for x in r["stages"])
    assert r["terminal_stage"] == 326 and r["next_unused_stage"] == 327
    assert r["cash"] == 39387 and r["bag_stacks"] == 19
    assert r["fully_restored"] and r["primary_unchanged"]
    assert not r["gameplay_running"] and not r["publication"]
    assert not r["learned_preparation"]
    for key in ("new_fits", "new_goal_choices", "new_registrations",
                "authority_promotions", "source_replays", "save_edits", "sales"):
        assert r[key] == 0
