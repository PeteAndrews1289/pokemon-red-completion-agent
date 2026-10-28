"""A changed destination returns a failed evolution to the model with exact custody."""

from copy import deepcopy
from dataclasses import replace

import pytest
from test_red_fresh_party_recovery import earned_trip, fresh_session
from test_red_live_option_menu import _binding

from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.red_integrated_play import ordinary_player_setback


def unavailable_destination(monkeypatch, *, evolution=True):
    session, state, permanent = fresh_session(monkeypatch)
    before = session.snapshot()
    earned_trip(session, state)
    if not evolution:
        state.members = (state.members[0], replace(state.members[1], species_id=112), state.members[2])
    after = session.snapshot()
    evidence = dict(schema="pokemon.core.routed-semantic-goal-report.v1",
        route_verified=True, destination_bound=False, destination_executed=False,
        destination_kind=GoalKind.EVOLVE_SPECIES.value, budget_reconciled=True,
        within_budget=True, route_is_policy_kind=False, private_binding_fields=0,
        private_route_fields=0, destination_unavailable=dict(reason="no_legal_target"))
    report = GoalExecutionReport(401, 25548, evidence)
    binding = _binding(GoalKind.EVOLVE_SPECIES, binding_ref="native:routed-evolution", calls=[])
    return before, after, report, binding, permanent


@pytest.mark.parametrize("evolution", [False, True])
def test_completed_route_without_bindable_target_returns_failure_to_model(monkeypatch, evolution):
    before, after, report, binding, permanent = unavailable_destination(monkeypatch, evolution=evolution)
    failed = GoalVerification.failed(GoalFailureReason.BINDING_FAILED)
    assert ordinary_player_setback(binding, before, after, report, failed, None)
    assert failed.status.value == "failed"
    assert report.evidence["destination_executed"] is False
    assert after.facts["cash"] > before.facts["cash"]
    assert permanent.refs == ("starter",)


@pytest.mark.parametrize("fault", ["unknown_schema", "route_unverified", "bound", "executed",
    "budget", "over_budget", "policy_route", "private_fields", "boolean_private_fields",
    "kind", "missing_reason", "unknown_reason", "other_reason", "private_reason_fields",
    "exception", "wrong_failure", "successful_verdict", "unready", "unsafe", "held_button",
    "partial_input", "meter", "census", "identity", "missing_guard", "changed_guard",
    "xp_regression", "unearned_registration", "lost_registration", "lost_objective"])
def test_refusal_does_not_waive_native_proof_or_change_outcome(monkeypatch, fault):
    before, after, report, binding, _ = unavailable_destination(monkeypatch)
    evidence, facts = deepcopy(dict(report.evidence)), deepcopy(dict(after.facts))
    error, verdict = None, GoalVerification.failed(GoalFailureReason.BINDING_FAILED)
    if fault == "unknown_schema": evidence["schema"] = "unknown"
    elif fault == "route_unverified": evidence["route_verified"] = False
    elif fault == "bound": evidence["destination_bound"] = True
    elif fault == "executed": evidence["destination_executed"] = True
    elif fault == "budget": evidence["budget_reconciled"] = False
    elif fault == "over_budget": evidence["within_budget"] = False
    elif fault == "policy_route": evidence["route_is_policy_kind"] = True
    elif fault == "private_fields": evidence["private_binding_fields"] = 1
    elif fault == "boolean_private_fields": evidence["private_route_fields"] = False
    elif fault == "kind": binding = replace(binding, kind=GoalKind.DEVELOP_TEAM)
    elif fault == "missing_reason": evidence.pop("destination_unavailable")
    elif fault == "unknown_reason": evidence["destination_unavailable"]["reason"] = "unknown"
    elif fault == "other_reason": evidence["destination_unavailable"]["reason"] = "missing_resource"
    elif fault == "private_reason_fields": evidence["destination_unavailable"]["path"] = "private"
    elif fault == "exception": error = RuntimeError("unhandled failure")
    elif fault == "wrong_failure": verdict = GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
    elif fault == "successful_verdict": verdict = GoalVerification.succeeded()
    elif fault == "unready": facts["input_ready"] = False
    elif fault == "held_button": facts["buttons_released"] = False
    elif fault == "partial_input": facts["completed_actions"] -= 1
    elif fault == "meter": report = replace(report, actions_executed=400)
    elif fault == "census": facts["specimen_counts"]["pokemon:national:025"] = 1
    elif fault == "identity": facts["retained_party_continuation"]["individuals"].pop("caught-b")
    elif fault == "missing_guard": facts.pop("retained_party_continuation")
    elif fault == "changed_guard": facts["retained_party_continuation"]["guard_sha256"] = "b" * 64
    elif fault == "xp_regression": facts["retained_party_continuation"]["individuals"]["caught-a"]["experience"] = 315
    elif fault == "unearned_registration": facts["owned_species"] += ["pokemon:national:025"]
    elif fault == "lost_registration": facts["owned_species"].remove("pokemon:national:008")
    elif fault == "lost_objective":
        before = replace(before, facts={**before.facts, "completed_objectives": ["prior-objective"]})
    after = replace(after, facts=facts, safe=fault != "unsafe")
    assert not ordinary_player_setback(binding, before, after, replace(report, evidence=evidence), verdict, error)
