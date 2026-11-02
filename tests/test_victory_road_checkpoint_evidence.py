"""Native progression,checkpoint and support must not become a training/autonomy claim."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/evidence/red-victory-road-continuation-2026-10-13.json"


def evidence():
    return json.loads(PATH.read_text())


def test_all_four_native_outcomes_include_actual_indigo_recovery_anchor():
    d = evidence()
    assert d["status"] == "closed_all_requested_outcomes_complete"
    assert d["partition"] == "development"
    assert d["native_route22_rival_defeated"] and d["strength_known"]
    assert d["victory_road_crossed"] and "cross_victory_road" in d["completed"]
    assert d["normal_indigo_nurse_verified"] and d["last_blackout_map"] == 9
    assert d["map_id"] == 174 and d["at"] == [7, 7]
    assert d["initial_exterior_checkpoint_anchor"] == 15
    assert d["original_six_restored"] and d["whole_party_restored"]
    assert d["party_hp"] == d["party_max_hp"] and not any(d["party_status"])
    assert d["party_pp_current"] == d["party_pp_maximum"]
    assert dict(d["bag_stock"])[1] == 1 and d["master_ball_present"]
    assert d["known_field_moves"] == dict(cut=True, fly=True, surf=True, strength=True)


def test_registration_and_money_credits_come_only_from_this_actual_lineage():
    d = evidence()
    assert (d["registrations_before"], d["registrations_after"], d["registrations_added"]) == (
        75, 82, 7,
    )
    assert {s for r in d["acquisitions"] for s in r["species"]} == {
        "pokemon:national:083", "pokemon:national:040", "pokemon:national:091",
        "pokemon:national:133", "pokemon:national:034", "pokemon:national:036",
        "pokemon:national:031",
    }
    assert d["cash_after"] == 113
    assert d["cash_after"] == (d["cash_before"] + d["native_gross_cash_rewards"]
                               - d["new_actual_costs"]["cash_debits"])
    assert d["native_gross_cash_rewards"] == 3445 and d["new_actual_costs"]["cash_debits"] == 8600
    assert d["no_opening_restart"] and not d["copied_progress_imported"]


def test_neural_choices_mechanical_support_and_learning_have_separate_counters():
    d = evidence()
    assert d["actual_model_comparative_choices"] == 48
    assert d["automatic_singleton_support"] == 27 and d["deterministic_safety_support"] == 1
    assert d["flat_outcomes"] == 76
    assert d["flat_outcomes"] + len(d["mandatory_control_prefaces"]) == d["metered_units"] == 78
    assert {r["kind"] for r in d["mandatory_control_prefaces"]} == {
        "supplied_wild_escape_preface", "supplied_indigo_nurse_preface",
    }
    assert all(not r["learned"] and r["model_queries"] == 0
               for r in d["mandatory_control_prefaces"])
    assert (d["training_rows_added"] == d["fits"] == d["parameter_updates"]
            == d["runtime_llm_calls"] == 0)
    assert d["goal_model_unchanged"] and d["selection_support"]["unchanged_this_session"]
    assert d["selection_support"]["inherited_development_mix"] == 0.75
    assert d["party_total_level_gain"] == 3


def test_losses_copy_failures_and_failed_deliveries_stay_failed():
    d = evidence()
    assert len(d["native_execution_errors"]) == 4
    assert {r["error_type"] for r in d["native_execution_errors"]} == {
        "RuntimeError", "KeyboardInterrupt", "VictoryRoadChapterError",
    }
    assert d["outcome_counts"] == {"succeeded": 62, "failed": 10, "None": 4}
    assert len(d["certified_failed_field_deliveries"]) == 9
    assert all(r["verification"] == "failed" and not r["acquired"] and not r["complete"]
               for r in d["certified_failed_field_deliveries"])
    assert any(not r["passed"] for r in d["diagnostic_results"])
    assert d["qualified_hole_wild_repair"]["native_hole_wild_branch_exercised"]
    assert d["qualified_nurse_checkpoint_repair"]["last_blackout_map"] == 9
    assert d["separate_diagnostic_costs"]["cash_debits"] == 0


def test_rival_faints_and_stopped_nurse_are_not_perfect_or_final_autonomy():
    d = evidence()
    rival = next(r for r in d["story_battles"] if r["objective"] == "cross_victory_road")
    assert rival["won"] and rival["decisions"] == 30
    assert rival["metrics"]["party_faints"] == 2
    assert (rival["metrics"]["invalid_action_failures"]
            == rival["metrics"]["teacher_interventions"] == 0)
    assert rival["teacher_queries"] == rival["memory_writes"] == 0
    assert d["worker_stopped"] and d["released"] and d["field_ready"]
    assert d["cold_proof"]["inputs"] == d["cold_proof"]["frames"] == 0
    assert d["final_fresh_exit_gates"] == dict(completed=0, total=5)
    assert not d["verification"]["full_suite"] and not d["verification"]["ci"]
    assert not any(p in PATH.read_text() for p in ("/Users/", "/Volumes/", "peterandrews"))
