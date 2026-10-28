"""ROM-free vertical checks for an exhausted, incomplete preparation endpoint."""
from dataclasses import replace
from types import SimpleNamespace as N
import ast
from pathlib import Path

import pytest

from test_preparation_ready_endpoint import ready_fixture
from pokemon_red_completion import red_player_field_goals as field
from pokemon_red_completion import red_player_preparation_binding as p
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason
from pokemon_red_completion.party import MoveObservation


def exhausted_fixture(monkeypatch, *, progress=10, ready=False, corrupt=None,
                      maximum_recoveries=1, stop_reason="encounter_limit"):
    rt, actions, kw, mon, health, nursing, records = ready_fixture(
        monkeypatch, completed=False, worn=not ready, corrupt=corrupt)
    kw.update(maximum_battles=3, maximum_recoveries=maximum_recoveries)
    allowances = []

    def dose(**kwargs):
        allowances.append(kwargs["maximum_battles"])
        assert len(allowances) == 1
        assert kwargs["restore_on_return"] is False
        mon.experience += progress
        health["ready"] = ready
        actions.actions_executed += 5
        rt.emulator.frame_count += 200
        return dict(battles=3, encounters=3, xp_gained=progress,
                    health_limited_return=stop_reason != "encounter_limit",
                    stop_reason=stop_reason)

    monkeypatch.setattr(p, "execute_wild_preparation", dose)
    return rt, actions, kw, mon, health, nursing, records, allowances


@pytest.mark.parametrize("recoveries", [0, 1, 63])
def test_exhausted_partial_restores_once_keeps_failed_target_and_full_cost(monkeypatch, recoveries):
    rt, actions, kw, mon, health, nursing, records, allowances = exhausted_fixture(
        monkeypatch, maximum_recoveries=recoveries)
    binding = p.preparation_binding(rt, actions, restore_exhausted_partial=True, **kw)
    report = binding.execute()
    verdict = binding.verify(report)
    assert verdict.status is GoalDecisionOutcome.FAILED
    assert verdict.failure_reason is GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
    assert allowances == [3] and len(nursing) == 1 and health["ready"]
    assert (mon.level, mon.experience) == (5, 145)
    assert (report.actions_executed, report.frames_executed) == (8, 260)
    endpoint = report.evidence["bounded_partial_preparation"]
    assert endpoint["target_level"] == 6 and endpoint["target_reached"] is False
    assert endpoint["stop_reason"] == "encounter_limit" and endpoint["encounters"] == 3
    assert endpoint["restoration"] == dict(actions=3, frames=60, evidence={"restoration": "metered"})
    assert endpoint["support_authority"] == "selected_preparation_final_restoration"
    assert report.evidence["trainee_xp_gained_across_doses"] == 10
    assert report.evidence["party_xp_gained_across_doses"] == 10
    assert "completed_target_endpoint" not in report.evidence
    if recoveries:
        dose = report.evidence["retained_doses"][-1]
        assert dose["verification"] == "failed" and dose["target_reached"] is False
        assert dose["remaining_battles"] == 0
        assert dose["terminal_sha256"] != endpoint["terminal_sha256"]
        assert report.evidence["xp_gained_across_doses"] == 10
    assert binding.verify(replace(report, actions_executed=5)).failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED
    assert binding.verify(replace(report, evidence={})).failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


def test_default_partial_keeps_recovery_as_next_goal_and_unchanged_binding_identity(monkeypatch):
    rt, a, kw, _, health, nursing, _, _ = exhausted_fixture(monkeypatch)
    default = p.preparation_binding(rt, a, **kw)
    explicit = p.preparation_binding(rt, a, restore_exhausted_partial=False, **kw)
    opted = p.preparation_binding(rt, a, restore_exhausted_partial=True, **kw)
    assert default.binding_ref == explicit.binding_ref != opted.binding_ref
    report = default.execute()
    assert default.verify(report).failure_reason is GoalFailureReason.RECOVERY_REQUIRED
    assert not nursing and not health["ready"]
    assert "bounded_partial_preparation" not in report.evidence


def test_already_ready_exhausted_partial_has_no_extra_nurse(monkeypatch):
    rt, a, kw, _, _, nursing, _, _ = exhausted_fixture(monkeypatch, ready=True)
    b = p.preparation_binding(rt, a, restore_exhausted_partial=True, **kw)
    report = b.execute()
    assert b.verify(report).failure_reason is GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
    assert not nursing and report.actions_executed == 5


def test_no_trainee_progress_is_not_healed_or_relabeled_partial(monkeypatch):
    rt, a, kw, _, health, nursing, _, _ = exhausted_fixture(monkeypatch, progress=0)
    b = p.preparation_binding(rt, a, restore_exhausted_partial=True, **kw)
    report = b.execute()
    assert b.verify(report).failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED
    assert not nursing and not health["ready"]
    assert "bounded_partial_preparation" not in report.evidence


def test_non_exhausted_health_return_is_not_granted_final_endpoint_restoration(monkeypatch):
    rt, a, kw, _, health, nursing, _, _ = exhausted_fixture(
        monkeypatch, maximum_recoveries=0, stop_reason="party_hp_below_half")
    b = p.preparation_binding(rt, a, restore_exhausted_partial=True, **kw)
    report = b.execute()
    assert b.verify(report).failure_reason is GoalFailureReason.RECOVERY_REQUIRED
    assert not nursing and not health["ready"]


def test_unavailable_nurse_retains_typed_recovery_required_without_extra_input(monkeypatch):
    rt, a, kw, _, health, nursing, records, _ = exhausted_fixture(monkeypatch)
    monkeypatch.setattr(p, "RedCenterRestoreGoalProvider",
                        lambda *a, **k: N(offer=lambda _: N(binding=None)))
    b = p.preparation_binding(rt, a, restore_exhausted_partial=True, **kw)
    report = b.execute()
    assert b.verify(report).failure_reason is GoalFailureReason.RECOVERY_REQUIRED
    assert not nursing and not health["ready"] and report.actions_executed == 5
    assert records[-1][0] == "bounded-partial-recovery-intent"
    assert "bounded_partial_preparation" not in report.evidence


@pytest.mark.parametrize("fault", ["unhealed", "xp", "level", "species", "moves", "cash", "home"])
def test_final_nursing_cannot_mint_progress_or_hide_preservation_failure(monkeypatch, fault):
    rt, a, kw, _, _, nursing, records, _ = exhausted_fixture(monkeypatch, corrupt=fault)
    b = p.preparation_binding(rt, a, restore_exhausted_partial=True, **kw)
    with pytest.raises(ValueError, match="changed progress or readiness"):
        b.execute()
    assert len(nursing) == 1
    assert records[0][0] == "retained-dose" and records[0][1]["verification"] == "failed"


def test_unknown_nursing_failure_propagates_with_original_dose_retained(monkeypatch):
    rt, a, kw, mon, _, _, records, _ = exhausted_fixture(monkeypatch)
    error = RuntimeError("unknown guard failure")
    def failed_restore(_):
        raise error
    a.execute_restoration = failed_restore
    b = p.preparation_binding(rt, a, restore_exhausted_partial=True, **kw)
    with pytest.raises(RuntimeError) as caught:
        b.execute()
    assert caught.value is error and (mon.level, mon.experience) == (5, 145)
    assert [name for name, _ in records] == ["retained-dose", "bounded-partial-recovery-intent"]


def test_typed_budget_denial_propagates_pre_input_and_retains_original_dose(monkeypatch):
    from pokemon_red_completion.executor import RestorationBudgetExhausted
    rt, a, kw, mon, _, _, records, _ = exhausted_fixture(monkeypatch)
    error = RestorationBudgetExhausted(maximum_heals=2, restoration_attempts=2)
    def denied(_):
        raise error
    a.execute_restoration = denied
    b = p.preparation_binding(rt, a, restore_exhausted_partial=True, **kw)
    with pytest.raises(RestorationBudgetExhausted) as caught:
        b.execute()
    assert caught.value is error
    assert a.actions_executed == 5 and rt.emulator.frame_count == 200
    assert mon.experience == 145 and records[0][1]["remaining_battles"] == 0


def test_observed_trainee_xp_stays_distinct_from_whole_party_gain(monkeypatch):
    rt, a, kw, mon, _, _, _, _ = exhausted_fixture(monkeypatch)
    escort = N(species_id=177, level=7, experience=300,
               known_moves=(MoveObservation(33, 35),))
    original = p.execute_wild_preparation
    def dose(**kwargs):
        result = original(**kwargs)
        escort.experience += 25
        result["xp_gained"] += 25
        return result
    monkeypatch.setattr(p, "execute_wild_preparation", dose)
    monkeypatch.setattr(p, "observe_preparation_members",
                        lambda *args: tuple(N(specimen_ref=ref, observation=N(**vars(value)))
                                           for ref, value in (("starter", mon), ("escort", escort))))
    b = p.preparation_binding(rt, a, restore_exhausted_partial=True, **kw)
    report = b.execute()
    assert report.evidence["trainee_xp_gained_across_doses"] == 10
    assert report.evidence["party_xp_gained_across_doses"] == 35
    assert report.evidence["xp_gained_across_doses"] == 35  # legacy party metric stays compatible
    assert b.verify(report).failure_reason is GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED


@pytest.mark.parametrize("value", [None, 0, 1, "true"])
def test_partial_endpoint_boolean_validated_before_field_work(monkeypatch, value):
    rt, a, kw, _, _, _, _, _ = exhausted_fixture(monkeypatch)
    monkeypatch.setattr(field, "_field_ready", lambda _: pytest.fail("field work before declaration"))
    with pytest.raises(ValueError, match="explicit boolean"):
        field.routed_preparation_binding(rt, a, home_map=41, restore_exhausted_partial=value, **kw)
    with pytest.raises(ValueError, match="explicit boolean"):
        p.preparation_binding(rt, a, restore_exhausted_partial=value, **kw)


def test_partial_endpoint_requires_metered_port_before_field_work(monkeypatch):
    rt, a, kw, _, _, _, _, _ = exhausted_fixture(monkeypatch)
    del a.execute_restoration
    monkeypatch.setattr(field, "_field_ready", lambda _: pytest.fail("field work before port"))
    with pytest.raises(ValueError, match="shared metered"):
        field.routed_preparation_binding(rt, a, home_map=41, restore_exhausted_partial=True, **kw)


def test_configured_global_preparation_constructor_explicitly_enables_partial_support():
    helper = Path(p.__file__).resolve().parents[2] / "runtime_helpers/red_whole_player_inventory_20261006.py"
    tree = ast.parse(helper.read_text())
    configured = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name) and n.func.id == "member_preparation_options"]
    assert len(configured) == 1
    flags = {k.arg: k.value for k in configured[0].keywords}
    assert isinstance(flags["restore_exhausted_partial"], ast.Constant)
    assert flags["restore_exhausted_partial"].value is True
    assert flags["maximum_battles"].value == 64
    assert flags["maximum_recoveries"].value == 63


def test_two_doses_preserve_original_failed_receipts_and_charge_final_nurse_once(monkeypatch):
    rt, a, kw, mon, health, nursing, records = ready_fixture(monkeypatch)
    kw.update(maximum_battles=3, maximum_recoveries=3)
    allowances = []
    def dose(**kwargs):
        assert health["ready"]
        allowances.append(kwargs["maximum_battles"])
        mon.level = 5
        mon.experience += 10
        health["ready"] = False
        a.actions_executed += 5
        rt.emulator.frame_count += 200
        final = len(allowances) == 2
        return dict(battles=2 if final else 1, encounters=2 if final else 1,
                    xp_gained=10, health_limited_return=not final,
                    stop_reason="encounter_limit" if final else "party_hp_below_half")
    monkeypatch.setattr(p, "execute_wild_preparation", dose)
    binding = p.preparation_binding(rt, a, restore_exhausted_partial=True, **kw)
    report = binding.execute()
    assert allowances == [3, 2] and len(nursing) == 2
    assert (report.actions_executed, report.frames_executed) == (16, 520)
    assert binding.verify(report).failure_reason is GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
    assert report.evidence["trainee_xp_gained_across_doses"] == 20
    assert [d["remaining_battles"] for d in report.evidence["retained_doses"]] == [2, 0]
    assert all(d["verification"] == "failed" for d in report.evidence["retained_doses"])
    assert [name for name, _ in records] == [
        "retained-dose", "retained-recovery-intent", "retained-dose",
        "bounded-partial-recovery-intent",
    ]


def test_live_failed_partial_flows_to_next_choice_and_current_continuation_capture(monkeypatch):
    from dataclasses import asdict
    from copy import deepcopy
    from test_party_preparation import enemies, team
    from pokemon_red_completion import red_player_continuation as continuation
    from pokemon_red_completion.party_preparation import build_preparation_plan
    from pokemon_red_completion.post_battle_strategy import BattleAftermath, BattleResult
    from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot
    from pokemon_red_completion.red_integrated_play import ordinary_player_setback

    rt, a, kw, mon, _, nursing, _, allowances = exhausted_fixture(monkeypatch)
    original_member = replace(team(5)[0], specimen_ref="starter",
                              observation=replace(team(5)[0].observation, experience=135))
    original_plan = replace(build_preparation_plan((original_member,), enemies(10)),
                            targets=(("starter", 6),))
    kw["plan"] = original_plan
    def facts(xp, actions, frames):
        return dict(actions=actions, completed_actions=actions, frames=frames, cash=3000,
                    battle_state=0, input_ready=True, buttons_released=True,
                    owned_species=["pokemon:national:007"],
                    specimen_counts={"pokemon:national:007": 1},
                    completed_objectives=["starter"], player_lesson=dict(
                        schema="pokemon.red.player-lesson-snapshot.v1",
                        party=[dict(specimen_ref="starter", level=5, experience=xp)]))
    before = AutonomousSnapshot(rt.emulator.save_state_bytes(), facts(135, 0, 0), True)
    b = p.preparation_binding(rt, a, restore_exhausted_partial=True, **kw)
    report = b.execute()
    verdict = b.verify(report)
    after = AutonomousSnapshot(rt.emulator.save_state_bytes(),
                               facts(mon.experience, a.actions_executed, rt.emulator.frame_count), True)
    assert ordinary_player_setback(b, before, after, report, verdict, None)
    # No automatic retry, post-hoc trainee substitution or new encounter allowance.
    assert allowances == [3] and len(nursing) == 1
    assert verdict.status is GoalDecisionOutcome.FAILED
    assert report.evidence["bounded_partial_preparation"]["terminal_sha256"] == after.sha256
    battle = BattleAftermath(BattleResult.WON, (3,), 1, 1, (5,), 1, 0, 1.0, .01, 0., 0., 0., 0.)
    previous = dict(decisions=9, actions=1000, frames=9000, seconds=50., heals=2, cash_debits=100)
    saved_previous = deepcopy(previous)
    spent = continuation.accumulate_player_costs(
        previous, decisions=1, actions=report.actions_executed, frames=report.frames_executed,
        seconds=2., heals=1, cash_deltas=())
    monkeypatch.setattr(continuation, "capture_player_lesson_snapshot",
                        lambda _: (N(raw=rt.reader.read()), after.facts["player_lesson"]))
    state_before_export = rt.emulator.save_state_bytes()
    context = continuation.capture_player_continuation(
        rt, preparation=original_plan, battle=battle, spent=spent)
    assert rt.emulator.save_state_bytes() == state_before_export
    assert context["state_sha256"] == after.sha256
    assert context["preparation"] == asdict(original_plan)
    assert context["preparation"]["roster"][0]["observation"]["experience"] == 135
    assert context["lesson"]["party"][0]["experience"] == 145
    assert context["battle"] == asdict(battle)
    assert context["spent"]["actions"] == 1008 and context["spent"]["frames"] == 9260
    assert context["spent"]["heals"] == 3 and context["spent"]["cash_debits"] == 100
    assert previous == saved_previous and context["grants_new_budget"] is False
    assert context["fit_allowed"] is False
