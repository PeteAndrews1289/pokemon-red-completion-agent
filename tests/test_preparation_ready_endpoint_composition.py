"""ROM-free proposals: constructor gate and retained-dose completed endpoint."""
from dataclasses import replace

import pytest

from test_preparation_ready_endpoint import ready_fixture
from pokemon_red_completion import red_player_field_goals as f
from pokemon_red_completion import red_player_preparation_binding as p
from pokemon_red_completion.goal_manager import GoalDecisionOutcome


@pytest.mark.parametrize("value", [None, 0, 1, "true"])
def test_routed_completed_endpoint_flag_is_validated_before_field_work(monkeypatch, value):
    rt, actions, kwargs, _, _, _, _ = ready_fixture(monkeypatch)
    monkeypatch.setattr(
        f, "_field_ready",
        lambda _: pytest.fail("invalid declaration reached field observation"),
    )
    with pytest.raises(ValueError, match="explicit boolean"):
        f.routed_preparation_binding(
            rt, actions, home_map=41, restore_completed_target=value, **kwargs
        )
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("port", ["missing", "noncallable"])
def test_routed_completed_endpoint_requires_metered_port_before_field_work(monkeypatch, port):
    rt, actions, kwargs, _, _, _, _ = ready_fixture(monkeypatch)
    if port == "missing":
        del actions.execute_restoration
    else:
        actions.execute_restoration = object()
    monkeypatch.setattr(
        f, "_field_ready",
        lambda _: pytest.fail("missing restoration port reached field observation"),
    )
    with pytest.raises(ValueError, match="shared metered"):
        f.routed_preparation_binding(
            rt, actions, home_map=41, restore_completed_target=True, **kwargs
        )
    assert actions.actions_executed == rt.emulator.frame_count == 0


def test_routed_legacy_endpoint_still_needs_no_final_restoration_port(monkeypatch):
    rt, actions, kwargs, _, _, _, _ = ready_fixture(monkeypatch)
    del actions.execute_restoration
    observed = []
    monkeypatch.setattr(f, "_field_ready", lambda _: observed.append(True) or False)
    assert f.routed_preparation_binding(
        rt, actions, home_map=41, restore_completed_target=False, **kwargs
    ) is None
    assert observed == [True]
    assert actions.actions_executed == rt.emulator.frame_count == 0


def test_completed_endpoint_after_retained_doses_counts_both_nursing_calls(monkeypatch):
    rt, actions, kwargs, mon, health, nursing, records = ready_fixture(monkeypatch)
    kwargs.update(maximum_battles=3, maximum_recoveries=1)
    allowances = []

    def dose(**kw):
        assert health["ready"]  # The second dose must follow intermediate nursing.
        assert kw["plan"] is kwargs["plan"]
        assert kw["battler"] is kwargs["battler"]
        assert kw["actions"] is actions and kw["emulator"] is rt.emulator
        assert kw["restore_on_return"] is False
        allowances.append(kw["maximum_battles"])
        assert len(allowances) <= 2
        reached = len(allowances) == 2
        mon.level = 6 if reached else 5
        mon.experience += 30 if reached else 15
        health["ready"] = False  # Earned target still needs final metered nursing.
        actions.actions_executed += 5
        rt.emulator.frame_count += 200
        return dict(
            battles=1, encounters=1, xp_gained=30 if reached else 15,
            health_limited_return=not reached,
            stop_reason="target_reached" if reached else "party_hp_below_half",
        )

    monkeypatch.setattr(p, "execute_wild_preparation", dose)
    binding = p.preparation_binding(rt, actions, restore_completed_target=True, **kwargs)
    assert not nursing and not allowances and not records
    report = binding.execute()
    assert allowances == [3, 2]  # Neither nursing call replenishes encounter allowance.
    assert len(nursing) == 2 and health["ready"]
    assert (mon.level, mon.experience) == (6, 180)
    assert (report.actions_executed, report.frames_executed) == (16, 520)
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED

    evidence = report.evidence
    assert evidence["original_target"] == dict(specimen_ref="starter", level=6)
    assert evidence["total_battle_allowance"] == 3
    assert evidence["maximum_recoveries"] == 1
    assert evidence["encounters_across_doses"] == evidence["completed_battles_across_doses"] == 2
    assert evidence["xp_gained_across_doses"] == 45
    assert [d["target_reached"] for d in evidence["retained_doses"]] == [False, True]
    assert [d["remaining_battles"] for d in evidence["retained_doses"]] == [2, 1]
    assert evidence["completed_target_endpoint"]["restoration"]["actions"] == 3
    assert evidence["completed_target_endpoint"]["restoration"]["frames"] == 60
    assert [name for name, _ in records] == [
        "retained-dose", "retained-recovery-intent", "retained-dose",
        "completed-target-recovery-intent", "completed-target-ready-endpoint",
    ]
    # Omitting either same-cost nurse must fail the actual-counter check.
    assert binding.verify(replace(
        report, actions_executed=13, frames_executed=460
    )).status is GoalDecisionOutcome.FAILED
