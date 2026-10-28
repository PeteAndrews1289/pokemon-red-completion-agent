"""A safe productive dose stays incomplete, but need not end the player."""
import copy
from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding
from test_red_player_preparation_binding import setup

from pokemon_red_completion import red_player_preparation_binding as p
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot
from pokemon_red_completion.red_integrated_play import ordinary_player_setback


def partial_dose(monkeypatch, *, retained=True, progress=True):
    rt, actions, kwargs, mon = setup(monkeypatch)
    raw = rt.reader.read()
    rt.reader.read = lambda: N(**vars(raw))
    healthy, calls = [True], []
    monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: healthy[0])
    rt.emulator.save_state_bytes = lambda: repr(
        (mon.experience, actions.actions_executed, healthy[0])
    ).encode()
    kwargs["plan"].budget = N(max_no_progress=3)
    kwargs.update(maximum_battles=3, maximum_recoveries=1 if retained else 0,
                  repeat_health_limited_zero_progress=retained)

    def run(**kw):
        calls.append(kw["maximum_battles"])
        first = len(calls) == 1
        if first and progress:
            mon.experience += 10
        healthy[0] = not retained or not first
        actions.actions_executed += 5
        rt.emulator.frame_count += 200
        return dict(battles=int(first and progress),
                    encounters=1 if retained and first else kw["maximum_battles"],
                    xp_gained=10 if first and progress else 0,
                    health_limited_return=not healthy[0],
                    stop_reason="party_status" if not healthy[0] else "encounter_limit")

    def heal(_):
        healthy[0] = True
        actions.actions_executed += 1
        rt.emulator.frame_count += 10

    actions.execute_restoration = heal
    monkeypatch.setattr(p, "execute_wild_preparation", run)
    monkeypatch.setattr(p, "RedCenterRestoreGoalProvider",
                        lambda *a, **k: N(offer=lambda _: N(binding=object())))
    binding = p.preparation_binding(rt, actions, **kwargs)
    report = binding.execute()
    return rt, raw, actions, mon, calls, binding, report


@pytest.mark.parametrize("retained", [False, True])
def test_healthy_productive_partial_dose_retains_failure_and_exact_allowance(monkeypatch, retained):
    rt, _, actions, mon, calls, binding, report = partial_dose(monkeypatch, retained=retained)
    verdict = binding.verify(report)
    assert verdict.status is GoalDecisionOutcome.FAILED
    assert verdict.failure_reason is GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
    receipt = report.evidence["bounded_partial_preparation"]
    assert receipt["target_level"] == 6 and receipt["terminal_level"] == mon.level == 5
    assert receipt["initial_xp"] == 135 and receipt["terminal_xp"] == 145
    assert receipt["encounters"] == receipt["encounter_allowance"] == 3
    assert receipt["terminal_sha256"] == p.sha256(rt.emulator.save_state_bytes()).hexdigest()
    assert calls == ([3, 2] if retained else [3])
    assert report.actions_executed == actions.actions_executed == (11 if retained else 5)
    assert report.frames_executed == (410 if retained else 200)
    if retained:
        assert report.evidence["xp_gained"] == 0
        assert report.evidence["xp_gained_across_doses"] == 10
        assert all(not d["target_reached"] for d in report.evidence["retained_doses"])


@pytest.mark.parametrize("fault", ["no_xp", "cash", "bag", "battle", "coordinate", "pressed",
                                  "input", "dialogue", "species", "xp_loss", "objectives",
                                  "receipt", "actions", "frames"])
def test_partial_admission_does_not_bypass_native_or_report_checks(monkeypatch, fault):
    rt, raw, _, mon, _, binding, report = partial_dose(monkeypatch, progress=fault != "no_xp")
    if fault == "cash":
        raw.player_money -= 1
    elif fault == "bag":
        raw.bag_items = ((4, 1),)
    elif fault == "battle":
        raw.battle_state = 1
    elif fault == "coordinate":
        raw.player_x += 1
    elif fault == "pressed":
        rt.emulator.pressed_buttons = ("a",)
    elif fault == "input":
        rt.adapter.observe().input_ready = False
    elif fault == "dialogue":
        rt.reader.read_bottom_dialogue_box_visible = lambda: True
    elif fault == "species":
        mon.species_id = 1
        monkeypatch.setattr(p, "level_evolution_edges", lambda _: frozenset())
    elif fault == "xp_loss":
        mon.experience = 134
    elif fault == "objectives":
        rt.adapter.graph.completed_ids = lambda _: frozenset({"unearned"})
    elif fault == "receipt":
        evidence = copy.deepcopy(dict(report.evidence))
        evidence["bounded_partial_preparation"]["target_level"] = 7
        report = replace(report, evidence=evidence)
    elif fault in {"actions", "frames"}:
        name = fault + "_executed"
        report = replace(report, **{name: getattr(report, name) + 1})
    assert binding.verify(report).failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED


@pytest.mark.parametrize("binding_type", ["bounded", "routed", "member"])
@pytest.mark.parametrize("fault", [None, "schema", "terminal", "target", "xp", "count", "bool",
                                  "ref", "reason", "error", "battle", "input", "pressed",
                                  "lost_specimen", "lost_objective", "cost", "unknown_trainee"])
def test_only_certified_incomplete_preparation_permits_next_choice(binding_type, fault):
    def facts(xp, n):
        return dict(actions=n, completed_actions=n, frames=10*n, cash=235,
                    battle_state=0, input_ready=True, buttons_released=True,
                    owned_species=["pokemon:national:007"],
                    specimen_counts={"pokemon:national:007": 1},
                    completed_objectives=["begin"], player_lesson=dict(
                        schema="pokemon.red.player-lesson-snapshot.v1",
                        party=[dict(specimen_ref="one", level=32, experience=xp)]))
    before = AutonomousSnapshot(b"before", facts(100, 0), True)
    after = AutonomousSnapshot(b"after", facts(110, 2), True)
    receipt = dict(schema="pokemon.red.preparation-partial.v1", trainee_ref="one",
                   target_level=34, initial_level=32, terminal_level=32,
                   initial_xp=100, terminal_xp=110, encounter_allowance=3, encounters=3,
                   target_reached=False, fully_restored=True, stop_reason="encounter_limit",
                   terminal_sha256=after.sha256)
    binding = _binding(GoalKind.DEVELOP_TEAM,
                       binding_ref=f"pokemon.red:{binding_type}-preparation:abc", calls=[])
    error, reason = None, GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
    if fault == "schema":
        receipt["schema"] = "unknown"
    elif fault == "terminal":
        receipt["terminal_sha256"] = "0" * 64
    elif fault == "target":
        receipt["target_level"] = 32
    elif fault == "xp":
        receipt["terminal_xp"] = 100
    elif fault == "count":
        receipt["encounters"] = 2
    elif fault == "bool":
        receipt["encounters"] = True
    elif fault == "ref":
        binding = replace(binding, binding_ref="unknown")
    elif fault == "reason":
        reason = GoalFailureReason.OUTCOME_NOT_VERIFIED
    elif fault == "error":
        error = RuntimeError("unrecognized")
    elif fault == "battle":
        after.facts["battle_state"] = 1
    elif fault in {"input", "pressed"}:
        after.facts["input_ready" if fault == "input" else "buttons_released"] = False
    elif fault == "lost_specimen":
        after.facts["specimen_counts"] = {}
    elif fault == "lost_objective":
        after.facts["completed_objectives"] = []
    elif fault == "cost":
        after.facts["completed_actions"] = 1
    elif fault == "unknown_trainee":
        receipt["trainee_ref"] = "another"
    evidence = dict(bounded_partial_preparation=receipt)
    if binding_type != "bounded":
        evidence = dict(mechanic="routed_preparation", support="cartridge_route_then_fresh_binding",
                        preparation=evidence)
    report = GoalExecutionReport(2, 20, evidence)
    verdict = GoalVerification.failed(reason)
    admitted = ordinary_player_setback(binding, before, after, report, verdict, error)
    assert admitted is (fault is None)
