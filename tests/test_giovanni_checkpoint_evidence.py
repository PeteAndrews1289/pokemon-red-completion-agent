"""Closed Giovanni progress must remain separate from support and parameter learning."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/evidence/red-giovanni-continuation-2026-10-13.json"


def evidence():
    return json.loads(PATH.read_text())


def test_native_giovanni_reward_resources_and_originals_are_verified():
    data = evidence()
    assert data["status"] == "closed_all_requested_outcomes_complete"
    assert data["partition"] == "development"
    assert data["badges_before"] == 7 and data["badges_after"] == 8
    assert data["badge_bits"] == 255 and data["giovanni_reward_received"]
    assert data["registrations_before"] == 71 and data["registrations_after"] == 75
    assert data["registrations_added"] == 4
    assert {s for row in data["acquisitions"] for s in row["species"]} == {
        "pokemon:national:079", "pokemon:national:080",
        "pokemon:national:108", "pokemon:national:090",
    }
    assert data["master_ball_present"] and dict(data["bag_stock"])[1] == 1
    assert data["original_six_restored"] and data["whole_party_restored"]
    assert data["party_hp"] == data["party_max_hp"] and not any(data["party_status"])
    assert data["party_pp_current"] == data["party_pp_maximum"]
    assert data["bag_slots_after"] == 14 and data["secret_key_conserved_in_pc"]
    assert all(row["items_conserved"] and row["sales"] == 0 for row in data["storage_receipts"])
    assert any(43 in row["stored_items"] for row in data["storage_receipts"])
    assert data["cash_after"] == 5268
    assert data["cash_after"] == (data["cash_before"] + data["native_gross_cash_rewards"]
                                  - data["new_actual_costs"]["cash_debits"])
    assert data["known_field_moves"] == dict(cut=True, fly=True, surf=True, strength=False)


def test_choice_ownership_and_all_cost_units_are_preserved():
    data = evidence()
    assert data["actual_model_comparative_choices"] == 69
    assert data["automatic_singleton_support"] == 43
    assert data["flat_outcomes"] == 112
    assert data["mandatory_control_preface_units"] == data["mandatory_wild_escape_prefaces"] == 2
    assert data["metered_units"] == data["new_actual_costs"]["decisions"] == 114
    assert data["flat_outcomes"] + data["mandatory_control_preface_units"] == data["metered_units"]
    assert data["manual_actual_goal_substitutions"] == 0 and data["no_opening_restart"]
    assert not data["copied_progress_imported"]
    assert data["preparation_goals"] == 22 and data["optional_grinding_goals"] == 19
    assert len(data["owned_machine_lessons"]) == 3
    assert data["party_total_level_gain"] == 27
    assert data["training_rows_added"] == data["fits"] == data["parameter_updates"] == 0
    assert data["runtime_llm_calls"] == 0 and data["goal_model_unchanged"]
    adjustment = data["selection_adjustment"]
    assert adjustment["default_mix"] == 0.25 and adjustment["declared_mix"] == 0.75
    assert adjustment["forced_goal"] is None and not adjustment["learned_stopping"]
    assert adjustment["model_weights_unchanged"] and adjustment["seed_unchanged"]
    assert adjustment["legal_choices_unchanged"] and data["qualified_exploration_adjustment"]


def test_native_losses_failures_and_correlated_copy_limits_are_not_erased():
    data = evidence()
    assert data["earlier_menu_unavailable_retained"]
    assert {row["error_type"] for row in data["native_execution_errors"]} == {
        "RouteExecutionError", "KeyboardInterrupt",
    }
    assert len(data["native_execution_errors"]) == 3
    assert data["outcome_counts"] == {"succeeded": 88, "failed": 21, "None": 3}
    copy = data["earlier_party_gym_copy"]
    assert copy["passed"] and copy["optional_preparation_goals"] == 0
    assert not copy["copy_back"] and not copy["independent_origin"]
    assert not copy["paired_comparison"] and copy["confounders"]
    assert all(data[key] for key in (
        "qualified_walking_capture_arrival", "qualified_early_safari_departure",
        "qualified_gym_frontier",
    ))
    assert any(not row["passed"] for row in data["diagnostic_results"])
    assert data["separate_diagnostic_costs"]["actions"] == 3587
    assert data["separate_diagnostic_costs"]["cash_debits"] == 500
    assert all(row["inputs"] == 0 for row in [data["cold_proof"]])


def test_final_battle_and_cold_stop_do_not_claim_perfect_or_final_autonomy():
    data = evidence()
    (final,) = [row for row in data["story_battles"] if row["badge_bits_after"] == 255]
    assert final["won"] and final["decisions"] == 28
    assert final["action_counts"] == dict(attack=13, voluntary_switch=11,
                                          forced_switch=0, switch_prompt=4)
    assert final["metrics"]["party_hp_lost"] == 136
    assert final["metrics"]["party_faints"] == final["metrics"]["invalid_action_failures"] == 0
    assert final["teacher_queries"] == final["metrics"]["teacher_interventions"] == 0
    assert data["worker_stopped"] and data["released"] and data["field_ready"]
    assert data["cold_proof"]["inputs"] == data["cold_proof"]["frames"] == 0
    assert data["final_fresh_exit_gates"] == dict(completed=0, total=5)
    assert not data["verification"]["full_suite"] and not data["verification"]["ci"]
    assert not any(value in PATH.read_text() for value in ("/Users/", "/Volumes/", "peterandrews"))
