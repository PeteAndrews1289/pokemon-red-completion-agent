"""A failed search remains failed; only authenticated incidental evolution recovers."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_skills import _ActionPort, _AreaExecutor, _graph, _Observer, _raw, _Reader
from test_red_live_option_menu import _binding

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.observation import RedPokedexState
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_acquisition import RedAreaExecutionError
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot
from pokemon_red_completion.red_goal_manager import PokemonRedGoalStateAdapter
from pokemon_red_completion.red_goal_skills import RedAreaSurveyGoalProvider
from pokemon_red_completion.red_integrated_play import ordinary_player_setback
from pokemon_red_completion.red_player_party_guard import (
    RedPlayerPartyGuard,
    RetainedPartyGoalStateAdapter,
)


@pytest.mark.parametrize("fault", [None, "no_guard", "unexplained_flag", "lost_flag", "unready"])
def test_destination_types_only_native_guarded_incidental_evolution(fault):
    reader = _Reader(raw=replace(_raw(poke_balls=6), party_species_ids=(177,),
                                party_levels=(15,)), ready=True)
    reader.pokedex = RedPokedexState(frozenset({7}), frozenset({7}))
    reader.xp = 3000
    party_reader = SimpleNamespace(
        read=lambda: PartyObservation((PartyMemberObservation(
            1, reader.raw.party_species_ids[0], reader.raw.party_levels[0],
            180, 180, experience=reader.xp),)),
        preparation_specimen_refs=lambda: ("retained",),
    )
    guard = RedPlayerPartyGuard(party_reader, party_reader.read(), ("retained",),
                               frozenset({(177, 179, 16)}))
    adapter = (PokemonRedGoalStateAdapter(reader, _Observer(), _graph())
               if fault == "no_guard" else
               RetainedPartyGoalStateAdapter(reader, _Observer(), _graph(), party_guard=guard))
    port = _ActionPort(reader)
    actions = CountingExecutor(port)

    class ExhaustedArea(_AreaExecutor):
        def seek_encounter(self):
            self.actions.execute(MacroAction(MacroActionKind.WAIT))
            reader.raw = replace(reader.raw, party_species_ids=(179,), party_levels=(16,))
            reader.xp = 4000
            owned = (
                {7, 8, 25} if fault == "unexplained_flag"
                else {8} if fault == "lost_flag" else {7, 8}
            )
            reader.pokedex = RedPokedexState(frozenset(owned), frozenset(owned))
            raise RedAreaExecutionError("bounded search", reason_code="survey_leg_limit_exceeded")

    provider = RedAreaSurveyGoalProvider("wild:Route1:grass", ExhaustedArea(reader, actions),
                                        actions, port, adapter)
    offer = provider.offer(adapter.observe())
    report = offer.binding.execute()
    if fault == "unready":
        reader.ready = False
    verdict = offer.binding.verify(report)
    assert verdict.status.value == "failed"
    assert verdict.failure_reason is (
        GoalFailureReason.SEARCH_EXHAUSTED if fault is None
        else GoalFailureReason.OUTCOME_NOT_VERIFIED
    )
    assert report.evidence["captures"] == 0
    assert report.actions_executed == 1 and report.frames_executed > 0
    assert reader.raw.bag_items == _raw(poke_balls=6).bag_items


def capture_miss_fixture():
    old, new = "pokemon:national:007", "pokemon:national:008"
    proof = dict(schema="pokemon.red.retained-party-continuation.v1",
                 native_identity_verified=True, guard_sha256="a" * 64,
                 individuals={"retained": dict(species_ref=old, level=15, experience=3000)},
                 other_specimen_counts={})
    facts = dict(actions=0, completed_actions=0, frames=0, cash=5000,
                 owned_species=[old], specimen_counts={old: 1}, completed_objectives=["begin"],
                 battle_state=0, input_ready=True, buttons_released=True,
                 retained_party_continuation=proof)
    terminal = json.loads(json.dumps(facts))
    terminal.update(actions=1, completed_actions=1, frames=10,
                    owned_species=[old, new], specimen_counts={new: 1})
    terminal["retained_party_continuation"]["individuals"]["retained"].update(
        species_ref=new, level=16, experience=4000)
    events = [
        dict(kind="survey_action_returned", operation="seek_encounter", returned=None),
        dict(kind="survey_action_returned", operation="flee_encounter", returned=None),
        dict(kind="survey_action_failed", operation="seek_encounter",
             error_type="RedAreaExecutionError", reason_code="survey_leg_limit_exceeded",
             diagnostic_review=dict(schema="pokemon.red.survey-operation-diagnostics.v1",
                                    diagnostic_only=True, operation="seek_encounter",
                                    measured=dict(native_actions=0, native_frames=0))),
    ]
    for ordinal, event in enumerate(events):
        event.update(event_ordinal=ordinal, source_id="wild:Route1:grass",
                     selection_authority="deterministic_capture_support")
    evidence = dict(schema="pokemon.core.routed-semantic-goal-report.v1",
                    budget_reconciled=True, destination_bound=True, destination_executed=True,
                    route_verified=True, within_budget=True, destination_kind="acquire_species",
                    capture_survey=dict(captures=0, encounters_seen=1, semantic_actions=3,
                                        flees=1, safety_stopped=False, search_exhausted=True,
                                        search_stop_reason="survey_leg_limit_exceeded"),
                    capture_diagnostics=dict(schema="pokemon.red.capture-survey-diagnostics.v1",
                                             diagnostic_only=True, capture_attempts=0,
                                             failed_capture_attempts=0, direct_flees=1,
                                             events=events))
    return facts, terminal, evidence


@pytest.mark.parametrize("fault", [None, "generic", "budget", "route", "destination",
    "safety_stop", "stop_reason", "summary", "diagnostic_count", "earlier_failure",
    "controller_error", "unordered", "proof", "guard", "identity", "stock",
    "unexplained_flag", "lost_flag", "xp", "level", "unsafe", "unready", "battle",
    "buttons", "partial", "cost", "exception", "terminal_actions", "terminal_frames",
    "terminal_counter_bool", "terminal_diagnostics"])
def test_only_certified_zero_capture_evolution_miss_can_requery(fault):
    before, after, evidence = capture_miss_fixture()
    reason, error, safe = GoalFailureReason.SEARCH_EXHAUSTED, None, True
    if fault == "generic":
        reason = GoalFailureReason.OUTCOME_NOT_VERIFIED
    elif fault in {"budget", "route", "destination"}:
        evidence[{"budget": "within_budget", "route": "route_verified",
                  "destination": "destination_executed"}[fault]] = False
    elif fault == "safety_stop":
        evidence["capture_survey"]["safety_stopped"] = True
    elif fault == "stop_reason":
        evidence["capture_survey"]["search_stop_reason"] = "unknown"
    elif fault == "summary":
        evidence["capture_survey"]["semantic_actions"] = 4
    elif fault == "diagnostic_count":
        evidence["capture_diagnostics"]["direct_flees"] = 2
    elif fault == "earlier_failure":
        evidence["capture_diagnostics"]["events"][0]["kind"] = "survey_action_failed"
    elif fault == "controller_error":
        evidence["capture_diagnostics"]["events"][-1]["error_type"] = "RuntimeError"
    elif fault == "unordered":
        evidence["capture_diagnostics"]["events"][-1]["event_ordinal"] = 0
    elif fault == "proof":
        after.pop("retained_party_continuation")
    elif fault == "guard":
        after["retained_party_continuation"]["guard_sha256"] = "b" * 64
    elif fault == "identity":
        after["retained_party_continuation"]["native_identity_verified"] = False
    elif fault == "stock":
        after["specimen_counts"]["pokemon:national:025"] = 1
    elif fault == "unexplained_flag":
        after["owned_species"].append("pokemon:national:025")
    elif fault == "lost_flag":
        after["owned_species"].remove("pokemon:national:007")
    elif fault in {"xp", "level"}:
        after["retained_party_continuation"]["individuals"]["retained"][
            "experience" if fault == "xp" else "level"] = 3000 if fault == "xp" else 15
    elif fault == "unsafe":
        safe = False
    elif fault == "unready":
        after["input_ready"] = False
    elif fault == "battle":
        after["battle_state"] = 1
    elif fault == "buttons":
        after["buttons_released"] = False
    elif fault == "partial":
        after["completed_actions"] = 0
    elif fault == "cost":
        after["frames"] = 11
    elif fault == "exception":
        error = RuntimeError("unknown error")
    elif fault in {"terminal_actions", "terminal_frames", "terminal_counter_bool"}:
        name = "native_frames" if fault == "terminal_frames" else "native_actions"
        evidence["capture_diagnostics"]["events"][-1]["diagnostic_review"]["measured"][name] = (
            False if fault == "terminal_counter_bool" else 1
        )
    elif fault == "terminal_diagnostics":
        evidence["capture_diagnostics"]["events"][-1].pop("diagnostic_review")
    binding = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="test:capture", calls=[])
    verdict = GoalVerification.failed(reason)
    assert ordinary_player_setback(
        binding, AutonomousSnapshot(b"before", before, True),
        AutonomousSnapshot(b"after", after, safe), GoalExecutionReport(1, 10, evidence),
        verdict, error,
    ) is (fault is None)
    assert verdict.status.value == "failed"
    assert evidence["capture_survey"]["captures"] == 0
