"""Composed failures renew only the existing verified evolution dose boundary."""
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.red_integrated_play import settled_evolution_partial

@pytest.mark.parametrize("fault", [None, "kind", "ref", "mechanic", "complete", "missing_verdict", "success", "diverged", "nested_missing", "nested_kind", "route_unverified", "unrestored", "no_battles", "not_bounded"])
def test_composed_partial_does_not_hide_unverified_failures(fault):
    binding=N(kind=GoalKind.ACQUIRE_SPECIES, binding_ref="red-npc-trade-dependency:1:77")
    inner=dict(schema="pokemon.core.routed-semantic-goal-report.v1",
        destination_kind="evolve_species", evolution_partial=True, budget_reconciled=True,
        destination_bound=True, destination_executed=True, route_verified=True,
        within_budget=True, retained_active_roster_restored=True,
        settlement_reserve_reached=True, completed_training_battles=59)
    evidence=dict(mechanic="trade_level_dependency", complete=False, intermediate=inner,
        intermediate_verification=dict(status="failed", failure_reason="outcome_not_verified"))
    if fault=="kind":binding.kind=GoalKind.DEVELOP_TEAM
    elif fault=="ref":binding.binding_ref="another-acquisition"
    elif fault=="mechanic":evidence["mechanic"]="unknown"
    elif fault=="complete":evidence["complete"]=True
    elif fault=="missing_verdict":evidence.pop("intermediate_verification")
    elif fault=="success":evidence["intermediate_verification"]["status"]="succeeded"
    elif fault=="diverged":evidence["intermediate_verification"]["failure_reason"]="world_state_diverged"
    elif fault=="nested_missing":evidence["intermediate"]=None
    elif fault=="nested_kind":inner["destination_kind"]="acquire_species"
    elif fault=="route_unverified":inner["route_verified"]=False
    elif fault=="unrestored":inner["retained_active_roster_restored"]=False
    elif fault=="no_battles":inner["completed_training_battles"]=0
    elif fault=="not_bounded":inner["settlement_reserve_reached"]=False
    assert settled_evolution_partial(binding, GoalExecutionReport(3,30,evidence)) is (fault is None)
