import copy
from collections import Counter
from dataclasses import replace

import pytest
from test_red_live_option_menu import _binding
from test_routed_semantic_goal import _composer

from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot
from pokemon_red_completion.red_integrated_play import ordinary_player_setback
from pokemon_red_completion.routed_semantic_goal import RoutedSemanticGoalError, _evolution_progress


def partial_case():
    individuals = {
        f"individual-{i}": dict(species_ref=f"pokemon:national:{species:03d}",
                                level=30, experience=22000)
        for i, species in enumerate((8, 20, 22, 22, 24, 44))
    }
    other = {"pokemon:national:017": 1}
    counts = Counter(other)
    counts.update(m["species_ref"] for m in individuals.values())
    facts = dict(
        actions=0, completed_actions=0, frames=0, cash=100,
        owned_species=sorted(counts), specimen_counts=dict(counts), completed_objectives=["begin"],
        battle_state=0, input_ready=True, buttons_released=True,
        retained_party_continuation=dict(
            schema="pokemon.red.retained-party-continuation.v1",
            guard_sha256="a" * 64, native_identity_verified=True,
            individuals=individuals, other_specimen_counts=other,
        ),
    )
    after = copy.deepcopy(facts)
    after.update(actions=2, completed_actions=2, frames=20)
    after["retained_party_continuation"]["individuals"]["individual-0"]["experience"] += 100
    evidence = dict(
        schema="pokemon.core.routed-semantic-goal-report.v1",
        destination_kind="evolve_species", budget_reconciled=True, destination_bound=True,
        destination_executed=True, route_verified=True, within_budget=True,
        evolution_partial=True, settlement_reserve_reached=True, wall_limit_reached=False,
        retained_active_roster_restored=False, field_carrier_custody_retained=True,
        completed_training_battles=1, healing_trips=0,
    )
    binding = _binding(GoalKind.EVOLVE_SPECIES, binding_ref="evolution", calls=[])
    report = GoalExecutionReport(2, 20, evidence)
    verdict = GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
    return binding, facts, after, report, verdict


@pytest.mark.parametrize("fault", [
    None, "no_flag", "unverified_identity", "missing_census", "guard", "missing_individual",
    "xp_regression", "other_stock", "no_xp", "unready", "unpaid_cost", "unknown_stop",
    "zero_battles", "five_individuals", "wrong_reason", "exception",
])
def test_active_custody_partial_requires_exact_paid_positive_census(fault):
    binding, before, after, report, verdict = partial_case()
    proof = after["retained_party_continuation"]
    evidence = dict(report.evidence)
    error = None
    if fault == "no_flag":
        evidence.pop("field_carrier_custody_retained")
    elif fault == "unverified_identity":
        proof["native_identity_verified"] = False
    elif fault == "missing_census":
        after.pop("retained_party_continuation")
    elif fault == "guard":
        proof["guard_sha256"] = "b" * 64
    elif fault == "missing_individual":
        proof["individuals"].pop("individual-5")
    elif fault == "xp_regression":
        proof["individuals"]["individual-1"]["experience"] -= 1
    elif fault == "other_stock":
        proof["other_specimen_counts"] = {"pokemon:national:016": 1}
        after["specimen_counts"].pop("pokemon:national:017")
        after["specimen_counts"]["pokemon:national:016"] = 1
    elif fault == "no_xp":
        proof["individuals"]["individual-0"]["experience"] = 22000
    elif fault == "unready":
        after["input_ready"] = False
    elif fault == "unpaid_cost":
        report = GoalExecutionReport(1, 20, report.evidence)
    elif fault == "unknown_stop":
        evidence["settlement_reserve_reached"] = False
    elif fault == "zero_battles":
        evidence["completed_training_battles"] = 0
    elif fault == "five_individuals":
        for f in (before, after):
            f["retained_party_continuation"]["individuals"].pop("individual-5")
            f["specimen_counts"].pop("pokemon:national:044")
    elif fault == "wrong_reason":
        verdict = GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
    elif fault == "exception":
        error = RuntimeError("Unknown native fault")
    report = replace(report, evidence=evidence)
    result = ordinary_player_setback(
        binding, AutonomousSnapshot(b"before", before, True),
        AutonomousSnapshot(b"after", after, True), report, verdict, error,
    )
    assert result is (fault is None)
    assert verdict.status is GoalDecisionOutcome.FAILED


def test_routing_retains_verified_custody_flag_without_original_roster_claim():
    _, _, _, partial, verdict = partial_case()
    _, binding, meter, _ = _composer(
        offered_kind=GoalKind.EVOLVE_SPECIES, destination_kind=GoalKind.EVOLVE_SPECIES,
        evolution_evidence=partial.evidence, destination_verification=verdict,
    )
    report = binding.execute()
    assert report.evidence["field_carrier_custody_retained"] is True
    assert report.evidence["retained_active_roster_restored"] is False
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED
    assert report.actions_executed == meter.actions == 5


@pytest.mark.parametrize("value", [1, "true", None])
def test_routing_rejects_untyped_active_custody_flag(value):
    with pytest.raises(RoutedSemanticGoalError):
        _evolution_progress(dict(field_carrier_custody_retained=value))

