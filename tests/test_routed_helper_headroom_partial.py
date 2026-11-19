"""Preserve a native helper stop through routing without granting evolution."""
from types import SimpleNamespace as N
import pytest
from test_helper_headroom_partial import nested
from test_routed_semantic_goal import _composer
from test_productive_venue_stop import boundary_and_report,ordinary
from pokemon_red_completion.red_evolution_helper_xp import EvolutionHelperXPExhausted
from pokemon_red_completion.goal_manager import GoalKind,GoalFailureReason
from pokemon_red_completion.goal_manager_runtime import GoalVerification
from pokemon_red_completion.red_integrated_play import settled_evolution_partial
from pokemon_red_completion.routed_semantic_goal import _evolution_progress,RoutedSemanticGoalError

def test_actual_native_pause_survives_routed_report_and_remains_a_failed_goal():
    native=nested("partial_report",spec=N(parameters={"source_species_ref":"pokemon:national:021","target_species_ref":"pokemon:national:022"}))(
        EvolutionHelperXPExhausted(24,8,frozenset({179}),trainee_initial_xp=812,trainee_terminal_xp=2390,trainee_xp_gained=1578))
    _,binding,meter,_=_composer(offered_kind=GoalKind.EVOLVE_SPECIES,destination_kind=GoalKind.EVOLVE_SPECIES,
        evolution_evidence={**native.evidence,"retained_active_roster_restored":True},
        destination_verification=GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED))
    report=binding.execute()
    assert report.evidence["helper_xp_headroom_exhausted"] is True
    assert report.evidence["trainee_xp_gained"]==1578
    assert settled_evolution_partial(binding,report)
    assert binding.verify(report).status.value=="failed"
    assert report.actions_executed==meter.actions

@pytest.mark.parametrize("fault",[None,"missing_xp","zero_xp","inconsistent_xp","bool_xp","bool_stop","no_roster","no_battles","negative_heals","unsettled","lost_specimen","exception"])
def test_productive_helper_stop_keeps_cost_custody_and_positive_target_requirements(fault):
    before,after,e=boundary_and_report()
    for key in ("training_venue_exhausted","no_verified_win_in_quantum","no_verified_win"):e.pop(key)
    e.update(helper_xp_headroom_exhausted=True,trainee_initial_xp=100,trainee_terminal_xp=150,trainee_xp_gained=50)
    if fault=="missing_xp":e.pop("trainee_xp_gained")
    elif fault=="zero_xp":e.update(trainee_terminal_xp=100,trainee_xp_gained=0)
    elif fault=="inconsistent_xp":e["trainee_xp_gained"]=49
    elif fault=="bool_xp":e["trainee_xp_gained"]=True
    elif fault=="bool_stop":e["helper_xp_headroom_exhausted"]=1
    elif fault=="no_roster":e["retained_active_roster_restored"]=False
    elif fault=="no_battles":e["completed_training_battles"]=0
    elif fault=="negative_heals":e["healing_trips"]=-1
    elif fault=="unsettled":after["input_ready"]=False
    elif fault=="lost_specimen":after["specimen_counts"]={"other":1}
    assert ordinary(before,after,e,RuntimeError("unknown")if fault=="exception"else None)is(fault is None)

def test_forwarding_rejects_coerced_helper_stop():
    with pytest.raises(RoutedSemanticGoalError,match="typed costs"):
        _evolution_progress({"helper_xp_headroom_exhausted":1})
