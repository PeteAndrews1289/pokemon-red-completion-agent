"""Compulsory trainer source is allowed only for proved settled native loss."""
from copy import deepcopy
from dataclasses import replace

import pytest
from test_red_integrated_play import _facts
from test_red_live_option_menu import _binding
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot
from pokemon_red_completion.red_integrated_play import ordinary_player_setback


def case():
    before_facts = dict(_facts(), completed_objectives=["earned"], cash=11269,
                        battle_state=2, compulsory_battle_control=True)
    after_facts = dict(_facts(), completed_objectives=["earned"], cash=5634,
                       actions=236, completed_actions=236, frames=23160)
    before = AutonomousSnapshot(b"exact compulsory trainer", before_facts, True)
    after = AutonomousSnapshot(b"settled native blackout", after_facts, True)
    binding = _binding(GoalKind.RECOVER_CONTROL, calls=[],
        binding_ref="pokemon.red:retained-engagement:" + before.sha256)
    evidence = dict(support="already_engaged_native_trainer", source_sha256=before.sha256,
        terminal_sha256=after.sha256, objective_completed=False, reward=None,
        battle=dict(schema="pokemon.red.learned-trainer-completion.v1", outcome="lost",
                    field_ready=True, money_delta=-5635))
    report = GoalExecutionReport(236, 23160, evidence)
    verdict = GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
    return binding, before, after, report, verdict


def test_real_compulsory_trainer_boundary_accepts_only_ordinary_native_loss():
    binding, before, after, report, verdict = case()
    facts_before, facts_after, evidence = deepcopy(before.facts), deepcopy(after.facts), deepcopy(dict(report.evidence))
    assert ordinary_player_setback(binding, before, after, report, verdict, None)
    assert before.facts == facts_before and after.facts == facts_after and report.evidence == evidence
    assert verdict.failure_reason is GoalFailureReason.RESOURCE_LOST
    assert report.evidence["objective_completed"] is False
    assert report.evidence["battle"]["outcome"] == "lost"


@pytest.mark.parametrize("fault", ["unsafe_before", "before_buttons", "unmarked", "truthy_marker",
    "wild_battle", "unknown_battle", "unsettled_field", "source_progress_missing", "source_stock_missing",
    "ref", "support", "source", "terminal", "objective_success", "reward", "battle_schema", "battle_won",
    "battle_unresolved", "battle_unready", "halfcash", "wrong_delta", "float_delta", "error", "verification",
    "partial_actions", "wrong_report_actions", "wrong_report_frames", "terminal_unready", "terminal_buttons",
    "terminal_battle", "terminal_unsafe", "owned_lost", "story_lost", "stock_lost"])
def test_compulsory_source_does_not_bypass_existing_native_loss_guards(fault):
    binding, before, after, report, verdict = case()
    bf, af, e = before.facts, after.facts, deepcopy(dict(report.evidence))
    error = None
    if fault == "unsafe_before": before = replace(before, safe=False)
    elif fault == "before_buttons": bf["buttons_released"] = False
    elif fault == "unmarked": bf.pop("compulsory_battle_control")
    elif fault == "truthy_marker": bf["compulsory_battle_control"] = 1
    elif fault == "wild_battle": bf["battle_state"] = 1
    elif fault == "unknown_battle": bf["battle_state"] = 3
    elif fault == "unsettled_field": bf.update(battle_state=0, input_ready=False)
    elif fault == "source_progress_missing": bf.pop("completed_objectives")
    elif fault == "source_stock_missing": bf["specimen_counts"] = {}
    elif fault == "ref": binding = replace(binding, binding_ref="unrelated")
    elif fault == "support": e["support"] = "unknown"
    elif fault == "source": e["source_sha256"] = "0" * 64
    elif fault == "terminal": e["terminal_sha256"] = "0" * 64
    elif fault == "objective_success": e["objective_completed"] = True
    elif fault == "reward": e["reward"] = {}
    elif fault == "battle_schema": e["battle"]["schema"] = "unknown"
    elif fault == "battle_won": e["battle"]["outcome"] = "won"
    elif fault == "battle_unresolved": e["battle"]["outcome"] = "unresolved"
    elif fault == "battle_unready": e["battle"]["field_ready"] = False
    elif fault == "halfcash": af["cash"] = 5635
    elif fault == "wrong_delta": e["battle"]["money_delta"] = -5634
    elif fault == "float_delta": e["battle"]["money_delta"] = -5635.0
    elif fault == "error": error = RuntimeError("unhandled native fault")
    elif fault == "verification": verdict = GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
    elif fault == "partial_actions": af["completed_actions"] = 235
    elif fault == "wrong_report_actions": report = GoalExecutionReport(235, 23160, e)
    elif fault == "wrong_report_frames": report = GoalExecutionReport(236, 23159, e)
    elif fault == "terminal_unready": af["input_ready"] = False
    elif fault == "terminal_buttons": af["buttons_released"] = False
    elif fault == "terminal_battle": af["battle_state"] = 2; af["compulsory_battle_control"] = True
    elif fault == "terminal_unsafe": after = replace(after, safe=False)
    elif fault == "owned_lost": af["owned_species"] = []
    elif fault == "story_lost": af["completed_objectives"] = []
    elif fault == "stock_lost": af["specimen_counts"] = {"other": 1}
    report = GoalExecutionReport(report.actions_executed, report.frames_executed, e)
    assert not ordinary_player_setback(binding, before, after, report, verdict, error)


@pytest.mark.parametrize("kind", [kind for kind in GoalKind if kind is not GoalKind.RECOVER_CONTROL])
def test_compulsory_before_boundary_is_not_admitted_for_other_goal_kinds(kind):
    binding, before, after, report, verdict = case()
    assert not ordinary_player_setback(replace(binding, kind=kind), before, after, report, verdict, None)


def test_existing_settled_field_source_retains_its_old_behavior():
    binding, before, after, report, verdict = case()
    before.facts.update(battle_state=0, input_ready=True)
    before.facts.pop("compulsory_battle_control")
    assert ordinary_player_setback(binding, before, after, report, verdict, None)