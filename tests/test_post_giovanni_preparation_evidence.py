"""Measured preparation is neither model fitting nor target completion."""
import json
from pathlib import Path

REPORT = (
    Path(__file__).resolve().parents[1]
    / "docs/evidence/red-post-giovanni-preparation-2026-09-22.json"
)


def test_preparation_chain_and_measured_progress() -> None:
    r = json.loads(REPORT.read_text())
    assert len(r["stages"]) == 13 and r["outings"] == 11
    assert r["encounters"] == r["wins"] == 88
    assert sum(x["decisions"] for x in r["episodes"]) == r["model_decisions"] == 217
    assert sum(r["action_counts"].values()) == 217
    for previous, current in zip(r["stages"][:-1], r["stages"][1:], strict=True):
        assert previous["terminal_sha256"] == current["source_sha256"]
    assert r["stages"][-1]["terminal_sha256"] == r["terminal_sha256"]
    assert sum(x["xp_gained"] for x in r["party"]) == r["total_xp"] == 19684
    reserves = [x for x in r["party"] if x["target_level"] is not None]
    assert sum(x["xp_gained"] for x in reserves) == r["reserve_xp"] == 14448
    assert sum(x["xp_remaining_to_target"] for x in reserves) == 17626
    assert all(x["target_level"] == 42 and not x["target_met"] for x in reserves)
    assert r["targets_met"] == 0 and not r["preparation_complete"]


def test_preparation_preserves_failure_resources_and_claim_boundaries() -> None:
    r = json.loads(REPORT.read_text())
    assert r["stages"][0]["error"] == ""
    assert all(x["error"] is None for x in r["stages"][1:])
    assert r["storage_conservation_verified"] and r["stored_tms"] == [227]
    assert r["cash"] == 39387 and r["bag_stacks"] == 19
    assert r["fully_restored"] and r["recovery_anchor_map"] == 6
    assert r["primary_unchanged"] and not r["gameplay_running"]
    for key in ("sales", "new_fits", "new_goal_choices", "new_registrations",
                "authority_promotions", "save_edits", "source_replays", "audit_frames"):
        assert r[key] == 0
    assert not r["learned_preparation"] and not r["publication"]
