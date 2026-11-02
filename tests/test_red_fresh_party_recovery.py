"""Fresh-party census evidence is scoped to one certified native goal."""

from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding

import pokemon_red_completion.red_native_player as native
from pokemon_red_completion.collection import CollectionLocation, LivingSpecimen
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_integrated_play import ordinary_player_setback
from pokemon_red_completion.red_player_party_guard import RedPlayerPartyGuard


def fresh_session(monkeypatch):
    starter = PartyMemberObservation(1, 179, 16, 30, 40, experience=4000)
    weedle = PartyMemberObservation(2, 112, 6, 18, 20, experience=316)
    kakuna = PartyMemberObservation(3, 113, 4, 5, 18, experience=64)
    state = N(members=(starter, weedle, kakuna), refs=("starter", "caught-a", "caught-b"),
              state=b"before", cash=65, ready=True, dialogue=False, other=(),
              owned={"pokemon:national:008", "pokemon:national:013", "pokemon:national:014"})
    reader = N(read=lambda: PartyObservation(state.members),
               preparation_specimen_refs=lambda: state.refs)
    guard = RedPlayerPartyGuard(reader, PartyObservation((starter,)), ("starter",),
                                frozenset({(112, 113, 7)}))
    session = native.NativePlayerSession.__new__(native.NativePlayerSession)
    session.controller = N(save_state_bytes=lambda: state.state, frames_executed=0,
                           pressed_buttons=())
    session.recorder = N(trace=[], enabled=False)
    session.actions = N(actions_executed=0)
    session.roles = ("starter",)
    session.heals = session.support_restorations = session.training_healing_trips = 0
    session.consequence = session.active_kind = None
    session.runtime = N(adapter=N(party_guard=guard), registration_policy=None,
                        reader=N(read_bottom_dialogue_box_visible=lambda: state.dialogue))
    species = {179: "pokemon:national:008", 112: "pokemon:national:013",
               113: "pokemon:national:014", 165: "pokemon:national:019"}

    def capture(_runtime):
        specimens = tuple(LivingSpecimen(species[m.species_id], m.level,
                          CollectionLocation.PARTY, slot_index=i)
                          for i, m in enumerate(state.members)) + state.other
        return N(raw=N(player_money=state.cash, battle_state=0), input_ready=state.ready,
                 collection_observation=N(specimens=specimens,
                     owned_species=state.owned)), {"completed_objectives": []}

    monkeypatch.setattr(native, "capture_player_lesson_snapshot", capture)
    monkeypatch.setattr(native, "player_diagnostic_state", lambda *args, **kwargs: {})
    return session, state, guard


def earned_trip(session, state):
    state.members = (state.members[0],
                     replace(state.members[1], species_id=113, level=7, experience=370),
                     replace(state.members[2], hp=0))
    state.state, state.cash = b"earned-trip", 345
    session.recorder.trace = [None] * 401
    session.actions.actions_executed = 401
    session.controller.frames_executed = 25548


def report():
    return GoalExecutionReport(401, 25548, dict(
        schema="pokemon.core.routed-semantic-goal-report.v1", budget_reconciled=True,
        destination_bound=True, destination_executed=True, route_verified=True,
        within_budget=True, destination_kind=GoalKind.ACQUIRE_SPECIES.value,
        capture_survey=dict(safety_stopped=True, search_exhausted=False, captures=0,
                            encounters_seen=0, semantic_actions=0, flees=0)))


def setback(before, after, r=None, error=None):
    return ordinary_player_setback(
        _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="retained:route22", calls=[]),
        before, after, report() if r is None else r,
        GoalVerification.failed(GoalFailureReason.RESOURCE_LOST), error)


def test_earned_evolution_and_faint_cover_new_catches_without_refreshing_original(monkeypatch):
    session, state, original = fresh_session(monkeypatch)
    before = session.snapshot()
    assert original.continuation_evidence(
        native.capture_player_lesson_snapshot(session.runtime)[0].collection_observation) is None
    earned_trip(session, state)
    session.recorder.enabled = True  # Nested restoration snapshots retain the same scope.
    after = session.snapshot()
    assert session.snapshot() == after
    a, b = (s.facts["retained_party_continuation"] for s in (before, after))
    assert a["guard_sha256"] == b["guard_sha256"]
    assert a["individuals"].keys() == b["individuals"].keys() == set(state.refs)
    assert b["individuals"]["caught-a"] == dict(
        species_ref="pokemon:national:014", level=7, experience=370)
    assert state.members[2].hp == 0 and setback(before, after)
    assert session.runtime.adapter.party_guard is original
    assert original.refs == ("starter",) and original.before.members[0].level == 16
    assert after.facts["completed_actions"] == 401 and after.facts["cash"] == 345


def uncaptured_health_stop_report():
    events = [
        dict(kind="survey_action_returned", operation="seek_encounter", returned=None),
        dict(kind="survey_action_returned", operation="capture_encounter", returned=False),
        dict(kind="capture_not_retained"),
        dict(kind="survey_action_returned", operation="seek_encounter", returned=None),
        dict(kind="survey_stopped", reason="safety_check_failed", semantic_actions=3),
    ]
    events = [dict(event, event_ordinal=i, source_id="wild:test:grass",
                   selection_authority="deterministic_capture_support")
              for i, event in enumerate(events)]
    return replace(report(), evidence={**report().evidence,
        "capture_survey": dict(safety_stopped=True, search_exhausted=False, captures=0,
                               encounters_seen=1, semantic_actions=3, flees=1),
        "capture_diagnostics": dict(schema="pokemon.red.capture-survey-diagnostics.v1",
                                    diagnostic_only=True, capture_attempts=1,
                                    failed_capture_attempts=1, direct_flees=0, events=events)})


def test_completed_uncaptured_search_keeps_earned_evolution_as_failed_goal(monkeypatch):
    session, state, _ = fresh_session(monkeypatch)
    before = session.snapshot()
    earned_trip(session, state)
    after = session.snapshot()
    assert setback(before, after, uncaptured_health_stop_report())
    assert GoalVerification.failed(GoalFailureReason.RESOURCE_LOST).status.value == "failed"
    assert after.facts["specimen_counts"] != before.facts["specimen_counts"]


@pytest.mark.parametrize("fault", ["missing", "failed_action", "false_capture",
    "wrong_return", "ordinal", "source", "authority", "action_count", "encounters",
    "failed_count", "boolean_count", "stop_reason", "unready", "extra_registration"])
def test_uncaptured_search_requires_complete_action_and_native_census_proof(monkeypatch, fault):
    from copy import deepcopy

    session, state, _ = fresh_session(monkeypatch)
    before = session.snapshot()
    earned_trip(session, state)
    if fault == "unready":
        state.ready = False
    if fault == "extra_registration":
        state.owned.add("pokemon:national:021")
    after = session.snapshot()
    receipt = uncaptured_health_stop_report()
    evidence = deepcopy(dict(receipt.evidence))
    diagnostics = evidence["capture_diagnostics"]
    event = diagnostics["events"][1]
    if fault == "missing":
        evidence.pop("capture_diagnostics")
    elif fault in {"failed_action", "false_capture"}:
        event["kind"] = "survey_action_failed" if fault == "failed_action" else "capture_verified"
    elif fault == "wrong_return":
        event["returned"] = True
    elif fault == "ordinal":
        event["event_ordinal"] = 0
    elif fault == "source":
        event["source_id"] = "another:source"
    elif fault == "authority":
        event["selection_authority"] = "operator"
    elif fault in {"action_count", "encounters"}:
        evidence["capture_survey"]["semantic_actions" if fault == "action_count"
                                    else "encounters_seen"] += 1
    elif fault in {"failed_count", "boolean_count"}:
        diagnostics["failed_capture_attempts"] = 2 if fault == "failed_count" else True
    elif fault == "stop_reason":
        diagnostics["events"][-1]["reason"] = "unknown"
    assert not setback(before, after, replace(receipt, evidence=evidence))


@pytest.mark.parametrize("fault", ["missing", "fingerprint", "duplicate", "illegal",
                                  "unearned", "xp_regression", "level_regression"])
def test_missing_duplicate_or_unearned_individual_cannot_continue(monkeypatch, fault):
    session, state, original = fresh_session(monkeypatch)
    before = session.snapshot()
    earned_trip(session, state)
    if fault == "missing":
        state.members, state.refs = state.members[:-1], state.refs[:-1]
    elif fault == "fingerprint":
        state.refs = (state.refs[0], "replacement", state.refs[2])
    elif fault == "duplicate":
        state.refs = (state.refs[0], state.refs[1], state.refs[1])
    elif fault == "illegal":
        state.members = (state.members[0], replace(state.members[1], species_id=165),
                         state.members[2])
    elif fault == "unearned":
        state.members = (state.members[0], replace(state.members[1], experience=316),
                         state.members[2])
    elif fault == "xp_regression":
        state.members = (state.members[0], replace(state.members[1], experience=315),
                         state.members[2])
    elif fault == "level_regression":
        state.members = (state.members[0], replace(state.members[1], level=5), state.members[2])
    if fault in {"missing", "fingerprint"}:
        after = session.snapshot()
        assert "retained_party_continuation" not in after.facts
        assert not setback(before, after)
    else:
        with pytest.raises(ValueError):
            session.snapshot()
    assert original.refs == ("starter",)


@pytest.mark.parametrize("fault", ["missing_proof", "changed_guard", "unready", "dialogue",
    "unsafe", "route", "destination", "budget", "survey_input", "exception", "cost"])
def test_certificate_does_not_waive_route_control_or_cost_checks(monkeypatch, fault):
    session, state, _ = fresh_session(monkeypatch)
    before = session.snapshot()
    earned_trip(session, state)
    state.ready = fault != "unready"
    state.dialogue = fault == "dialogue"
    after, receipt, error = session.snapshot(), report(), None
    if fault == "missing_proof":
        facts = dict(after.facts)
        facts.pop("retained_party_continuation")
        after = replace(after, facts=facts)
    elif fault == "changed_guard":
        proof = {**after.facts["retained_party_continuation"], "guard_sha256": "f" * 64}
        after = replace(after, facts={**after.facts, "retained_party_continuation": proof})
    elif fault == "unsafe":
        after = replace(after, safe=False)
    elif fault in {"route", "destination", "budget"}:
        key = {"route": "route_verified", "destination": "destination_executed",
               "budget": "within_budget"}[fault]
        receipt = replace(receipt, evidence={**receipt.evidence, key: False})
    elif fault == "survey_input":
        survey = {**receipt.evidence["capture_survey"], "semantic_actions": 1}
        receipt = replace(receipt, evidence={**receipt.evidence, "capture_survey": survey})
    elif fault == "exception":
        error = RuntimeError("retained partial input")
    elif fault == "cost":
        receipt = replace(receipt, actions_executed=400)
    assert not setback(before, after, receipt, error)


def test_new_catch_receives_next_goal_scope_only_after_completed_boundary(monkeypatch):
    session, state, original = fresh_session(monkeypatch)
    before = session.snapshot()
    state.members += (PartyMemberObservation(4, 165, 4, 20, 20, experience=64),)
    state.refs += ("new-catch",)
    during = session.snapshot()
    proof = during.facts["retained_party_continuation"]
    assert "new-catch" not in proof["individuals"]
    assert proof["other_specimen_counts"] == {"pokemon:national:019": 1}
    assert proof["guard_sha256"] == before.facts["retained_party_continuation"]["guard_sha256"]
    assert session._decision_party_guard.refs == ("starter", "caught-a", "caught-b")
    assert not session.finish_decision()
    following = session.snapshot()
    assert "new-catch" in following.facts["retained_party_continuation"]["individuals"]
    assert following.facts["retained_party_continuation"]["guard_sha256"] != (
        before.facts["retained_party_continuation"]["guard_sha256"])
    assert original.refs == ("starter",)
    assert following.state == during.state and following.facts["actions"] == 0


@pytest.mark.parametrize("active", ["recorder", "goal"])
def test_scope_cannot_change_while_native_execution_is_active(monkeypatch, active):
    session, _, _ = fresh_session(monkeypatch)
    session.snapshot()
    if active == "recorder":
        session.recorder.enabled = True
    else:
        session.active_kind = GoalKind.ACQUIRE_SPECIES
    with pytest.raises(ValueError, match="during native execution"):
        session.finish_decision()
    assert not session._decision_party_guard_pending


def test_scope_callback_preserves_existing_consequence_stop(monkeypatch):
    session, _, _ = fresh_session(monkeypatch)
    session.snapshot()
    session.consequence = N(done=True)
    assert session.finish_decision()
    assert session._decision_party_guard_pending
