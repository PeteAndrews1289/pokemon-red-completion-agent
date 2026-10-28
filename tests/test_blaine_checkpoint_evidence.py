"""The closed checkpoint must separate native progress, support and learning."""
import json
from pathlib import Path


def test_closed_blaine_checkpoint_preserves_ownership_and_failures():
    root = Path(__file__).resolve().parents[1]
    path = root / "docs/evidence/red-blaine-continuation-2026-10-13.json"
    text = path.read_text()
    evidence = json.loads(text)
    assert evidence["partition"] == "development"
    assert evidence["status"] == "closed_all_requested_outcomes_complete"
    assert evidence["registrations_before"] == evidence["registrations_after"] == 71
    assert evidence["badges_before"] == 6 and evidence["badges_after"] == 7
    assert evidence["secret_key_earned"] and evidence["blaine_reward_received"]
    assert evidence["master_ball_present"] and evidence["original_six_restored"]
    assert evidence["whole_party_restored"] and evidence["worker_stopped"]
    assert evidence["released"] and evidence["field_ready"]
    assert evidence["copied_progress_imported"] is False
    assert evidence["manual_actual_goal_substitutions"] == 0
    assert evidence["actual_model_comparative_choices"] == 7
    assert evidence["automatic_singleton_support"] == 28
    assert evidence["mandatory_wild_escape_prefaces"] == 1
    assert evidence["flat_outcomes"] == 35 and evidence["metered_units"] == 36
    assert evidence["new_actual_costs"]["decisions"] == 36
    assert evidence["cash_after"] == evidence["cash_before"] + evidence["cash_rewards"] == 5113
    assert evidence["new_actual_costs"]["cash_debits"] == 0
    assert evidence["training_rows_added"] == evidence["fits"] == evidence["parameter_updates"] == 0
    assert evidence["runtime_llm_calls"] == 0 and evidence["preparation_goals"] == 0
    assert len(evidence["native_execution_errors"]) == 2
    assert evidence["earlier_menu_unavailable_retained"]
    assert evidence["post_final_repair_native_errors"] == 0
    assert evidence["cold_proof"]["inputs"] == evidence["cold_proof"]["frames"] == 0
    assert evidence["final_fresh_exit_gates"] == {"completed": 0, "total": 5}
    (battle,) = evidence["story_battles"]
    assert battle["won"] and battle["decisions"] == 8
    assert battle["action_counts"] == {
        "attack": 4, "forced_switch": 0, "switch_prompt": 3, "voluntary_switch": 1
    }
    assert battle["metrics"]["party_hp_lost"] == battle["metrics"]["party_faints"] == 0
    assert battle["metrics"]["teacher_interventions"] == battle["teacher_queries"] == 0
    assert battle["memory_writes"] == 0
    assert not any(value in text for value in ("/Users/", "/Volumes/", "peterandrews"))
