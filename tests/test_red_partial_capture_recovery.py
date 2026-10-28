"""Partial earned captures remain failed goals, with exact census reconciliation."""

from copy import deepcopy
from dataclasses import replace

import pytest
from test_red_fresh_party_recovery import earned_trip, fresh_session, report
from test_red_live_option_menu import _binding

from pokemon_red_completion.collection import CollectionLocation, LivingSpecimen
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalVerification
from pokemon_red_completion.party import PartyMemberObservation
from pokemon_red_completion.red_integrated_play import ordinary_player_setback

CAUGHT = "pokemon:national:019"


def partial_capture(monkeypatch, *, in_party=False, captures=1, evolve=True):
    session, state, permanent = fresh_session(monkeypatch)
    before = session.snapshot()
    earned_trip(session, state)
    if not evolve:
        state.members = (state.members[0],
                         replace(state.members[1], species_id=112, level=6, experience=316),
                         state.members[2])
    state.owned = state.owned | {CAUGHT}
    if in_party:
        state.members += tuple(PartyMemberObservation(4 + i, 165, 4, 20, 20, experience=64)
                               for i in range(captures))
        state.refs += tuple(f"new-catch-{i}" for i in range(captures))
    else:
        state.other = tuple(LivingSpecimen(CAUGHT, 4, CollectionLocation.BOX,
                           slot_index=i) for i in range(captures))
    after = session.snapshot()
    events = [dict(kind="capture_verified", event_ordinal=i, source_id="wild:test:grass",
                   selection_authority="deterministic_capture_support", species_ref=CAUGHT,
                   specimen_count_before=i, specimen_count_after=i + 1,
                   new_owned_species=[CAUGHT] if i == 0 else []) for i in range(captures)]
    receipt = replace(report(), evidence={**report().evidence,
        "capture_survey": dict(captures=captures, encounters_seen=captures,
                               semantic_actions=captures + 1, flees=0,
                               safety_stopped=True, search_exhausted=False),
        "capture_diagnostics": dict(schema="pokemon.red.capture-survey-diagnostics.v1",
                                    diagnostic_only=True, events=events)})
    return session, permanent, before, after, receipt


def accepted(before, after, receipt, *, reason=GoalFailureReason.RESOURCE_LOST, error=None):
    return ordinary_player_setback(
        _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="partial:capture", calls=[]),
        before, after, receipt, GoalVerification.failed(reason), error)


@pytest.mark.parametrize("in_party", [False, True])
@pytest.mark.parametrize("captures", [1, 2])
@pytest.mark.parametrize("evolve", [False, True])
def test_partial_capture_preserves_old_individuals_and_exact_new_stock(
        monkeypatch, in_party, captures, evolve):
    session, permanent, before, after, receipt = partial_capture(
        monkeypatch, in_party=in_party, captures=captures, evolve=evolve)
    assert accepted(before, after, receipt)
    proof = after.facts["retained_party_continuation"]
    assert (
        proof["individuals"].keys()
        == before.facts["retained_party_continuation"]["individuals"].keys()
    )
    assert proof["other_specimen_counts"] == {CAUGHT: captures}
    assert after.facts["owned_species"] == sorted(set(before.facts["owned_species"]) | {CAUGHT})
    assert permanent.refs == ("starter",)
    assert session.runtime.adapter.party_guard is permanent
    if in_party:
        assert not any(ref.startswith("new-catch") for ref in proof["individuals"])
        session.finish_decision()
        assert any(ref.startswith("new-catch") for ref in
                   session.snapshot().facts["retained_party_continuation"]["individuals"])


@pytest.mark.parametrize("reason", [GoalFailureReason.SEARCH_EXHAUSTED,
                                     GoalFailureReason.CAPTURE_ITEMS_EXHAUSTED])
def test_bounded_partial_search_can_return_to_model_without_a_success_label(monkeypatch, reason):
    _, _, before, after, receipt = partial_capture(monkeypatch)
    evidence = deepcopy(dict(receipt.evidence))
    evidence["capture_survey"].update(safety_stopped=False, search_exhausted=True)
    receipt = replace(receipt, evidence=evidence)
    assert accepted(before, after, receipt, reason=reason)
    assert GoalVerification.failed(reason).status.value == "failed"


@pytest.mark.parametrize("fault", [
    "missing_receipts", "unverified_capture", "captures_mismatch", "boolean_count",
    "event_jump", "wrong_before", "wrong_new_flags", "missing_new_flags",
    "duplicate_events", "wrong_source", "mixed_source", "missing_schema",
    "stop_false", "stop_both", "route", "budget", "destination", "unready",
    "battle", "unsafe", "cost", "exception", "unknown_reason", "unaccounted_gain",
    "missing_stock", "changed_guard", "missing_individual", "xp_regression",
    "extra_registration", "no_native_identity", "boolean_stock",
])
def test_partial_capture_rejects_unverified_or_unsafe_work(monkeypatch, fault):
    _, _, before, after, receipt = partial_capture(monkeypatch)
    facts = deepcopy(dict(after.facts))
    evidence = deepcopy(dict(receipt.evidence))
    event, survey = evidence["capture_diagnostics"]["events"][0], evidence["capture_survey"]
    reason, error = GoalFailureReason.RESOURCE_LOST, None
    if fault == "missing_receipts":
        evidence.pop("capture_diagnostics")
    elif fault == "unverified_capture":
        event["kind"] = "capture_not_retained"
    elif fault == "captures_mismatch":
        survey.update(captures=2, encounters_seen=2)
    elif fault == "boolean_count":
        event["specimen_count_before"] = False
    elif fault == "event_jump":
        event["specimen_count_after"] = 2
    elif fault == "wrong_before":
        event.update(specimen_count_before=9, specimen_count_after=10)
    elif fault == "wrong_new_flags":
        event["new_owned_species"] = ["pokemon:national:008"]
    elif fault == "missing_new_flags":
        event["new_owned_species"] = []
    elif fault in {"duplicate_events", "mixed_source"}:
        survey.update(captures=2, encounters_seen=2)
        second = {**event, "event_ordinal": 1, "specimen_count_before": 1,
                  "specimen_count_after": 2, "new_owned_species": []}
        if fault == "duplicate_events":
            second["event_ordinal"] = 0
        else:
            second["source_id"] = "another:source"
        evidence["capture_diagnostics"]["events"].append(second)
    elif fault == "wrong_source":
        event["source_id"] = ""
    elif fault == "missing_schema":
        evidence["capture_diagnostics"].pop("schema")
    elif fault in {"stop_false", "stop_both"}:
        survey.update(safety_stopped=fault == "stop_both", search_exhausted=fault == "stop_both")
    elif fault in {"route", "budget", "destination"}:
        evidence[{"route": "route_verified", "budget": "within_budget",
                  "destination": "destination_executed"}[fault]] = False
    elif fault == "unready":
        facts["input_ready"] = False
    elif fault == "battle":
        facts["battle_state"] = 1
    elif fault == "cost":
        receipt = replace(receipt, actions_executed=400)
    elif fault == "exception":
        error = RuntimeError("incomplete native work")
    elif fault == "unknown_reason":
        reason = GoalFailureReason.OUTCOME_NOT_VERIFIED
    elif fault in {"unaccounted_gain", "missing_stock", "boolean_stock"}:
        if fault == "unaccounted_gain":
            facts["specimen_counts"]["pokemon:national:021"] = 1
        elif fault == "missing_stock":
            facts["specimen_counts"].pop("pokemon:national:008")
        else:
            facts["specimen_counts"][CAUGHT] = True
    elif fault in {"changed_guard", "missing_individual", "xp_regression", "no_native_identity"}:
        proof = facts["retained_party_continuation"]
        if fault == "changed_guard":
            proof["guard_sha256"] = "f" * 64
        elif fault == "missing_individual":
            proof["individuals"].pop("caught-b")
        elif fault == "xp_regression":
            proof["individuals"]["caught-a"]["experience"] = 315
        else:
            proof["native_identity_verified"] = False
    elif fault == "extra_registration":
        facts["owned_species"] += ["pokemon:national:021"]
    after = replace(after, facts=facts, safe=fault != "unsafe")
    assert not accepted(
        before, after, replace(receipt, evidence=evidence), reason=reason, error=error)
