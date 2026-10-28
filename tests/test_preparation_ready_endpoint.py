from dataclasses import replace
from types import SimpleNamespace as N
import pytest

from test_red_player_preparation_binding import setup
from pokemon_red_completion import red_player_preparation_binding as p
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.party import MoveObservation


def ready_fixture(monkeypatch, *, completed=True, worn=True, corrupt=None):
    rt, actions, kwargs, mon = setup(monkeypatch)
    # Native RawGameState is immutable; keep mutations in the fake backing
    # state while each read supplies an independent observed snapshot.
    raw = rt.reader.read()
    rt.reader.read = lambda: N(**vars(raw))
    rt.adapter.observe = lambda: N(raw=rt.reader.read(), input_ready=True, game_state=None)
    monkeypatch.setattr(p, "level_evolution_edges", lambda _: ())
    health = dict(ready=True)
    calls, records = [], []
    rt.emulator.save_state_bytes = lambda: repr((mon.level, mon.experience,
        tuple(m.move_id for m in mon.known_moves), health, rt.reader.read().player_money)).encode()
    monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: health["ready"])
    kwargs["record"] = lambda name, value: records.append((name, value))
    original = p.execute_wild_preparation
    def run(**kw):
        result = original(**kw)
        health["ready"] = not worn
        if not completed:
            mon.level = 5
            result.update(health_limited_return=True)
        return result
    monkeypatch.setattr(p, "execute_wild_preparation", run)
    offer_binding = object()
    def provider(*args, **kw):
        assert kw["require_full_pp_restore"] is True
        return N(offer=lambda _: N(binding=offer_binding))
    monkeypatch.setattr(p, "RedCenterRestoreGoalProvider", provider)
    def restore(binding):
        assert binding is offer_binding
        calls.append(binding)
        actions.actions_executed += 3
        rt.emulator.frame_count += 60
        health["ready"] = corrupt != "unhealed"
        if corrupt == "xp": mon.experience += 1
        if corrupt == "level": mon.level += 1
        if corrupt == "species": mon.species_id = 180
        if corrupt == "moves": mon.known_moves = (MoveObservation(45, 40),)
        if corrupt == "cash": raw.player_money -= 1
        if corrupt == "home": raw.map_id = 42
        return GoalExecutionReport(3, 60, {"restoration": "metered"})
    actions.execute_restoration = restore
    return rt, actions, kwargs, mon, health, calls, records


def test_completed_endpoint_includes_final_metered_recovery_and_preserves_xp(monkeypatch):
    rt, a, kw, mon, health, calls, records = ready_fixture(monkeypatch)
    original = p.preparation_binding(rt, a, **kw)
    b = p.preparation_binding(rt, a, restore_completed_target=True, **kw)
    assert b.binding_ref != original.binding_ref and not calls
    r = b.execute()
    assert (r.actions_executed, r.frames_executed) == (8, 260)
    assert len(calls) == 1 and health["ready"] and mon.experience == 180
    assert b.verify(r).status is GoalDecisionOutcome.SUCCEEDED
    endpoint = r.evidence["completed_target_endpoint"]
    assert endpoint["target_reached"] and endpoint["fully_restored"]
    assert endpoint["restoration"]["actions"] == 3
    assert [n for n, _ in records] == ["completed-target-recovery-intent", "completed-target-ready-endpoint"]
    with pytest.raises(ValueError, match="consumed"): b.execute()
    assert b.verify(replace(r, actions_executed=5)).status is GoalDecisionOutcome.FAILED
    assert b.verify(replace(r, evidence={})).status is GoalDecisionOutcome.FAILED
    mon.experience += 1
    assert b.verify(r).status is GoalDecisionOutcome.FAILED


def test_legacy_endpoint_leaves_recovery_to_next_goal(monkeypatch):
    rt, a, kw, _, health, calls, records = ready_fixture(monkeypatch)
    b = p.preparation_binding(rt, a, **kw)
    r = b.execute()
    assert b.verify(r).status is GoalDecisionOutcome.SUCCEEDED
    assert not calls and not records and not health["ready"]
    assert "completed_target_endpoint" not in r.evidence


def test_already_ready_completed_endpoint_does_not_charge_unneeded_nurse(monkeypatch):
    rt, a, kw, _, _, calls, _ = ready_fixture(monkeypatch, worn=False)
    b = p.preparation_binding(rt, a, restore_completed_target=True, **kw)
    r = b.execute()
    assert b.verify(r).status is GoalDecisionOutcome.SUCCEEDED
    assert not calls and r.actions_executed == 5
    assert r.evidence["completed_target_endpoint"]["restoration"] is None


def test_partial_target_is_not_healed_or_relabelled_complete(monkeypatch):
    rt, a, kw, _, health, calls, _ = ready_fixture(monkeypatch, completed=False)
    b = p.preparation_binding(rt, a, restore_completed_target=True, **kw)
    r = b.execute()
    assert b.verify(r).failure_reason is GoalFailureReason.RECOVERY_REQUIRED
    assert not calls and not health["ready"]
    assert "completed_target_endpoint" not in r.evidence


@pytest.mark.parametrize("fault", ["unhealed", "xp", "level", "species", "moves", "cash", "home"])
def test_nurse_cannot_mint_progress_or_claim_an_unrestored_endpoint(monkeypatch, fault):
    rt, a, kw, _, _, _, _ = ready_fixture(monkeypatch, corrupt=fault)
    b = p.preparation_binding(rt, a, restore_completed_target=True, **kw)
    with pytest.raises(ValueError, match="changed progress or readiness"):
        b.execute()


@pytest.mark.parametrize("value", [None, 0, 1, "true"])
def test_endpoint_requires_explicit_boolean(monkeypatch, value):
    rt, a, kw, _, _, _, _ = ready_fixture(monkeypatch)
    with pytest.raises(ValueError, match="explicit boolean"):
        p.preparation_binding(rt, a, restore_completed_target=value, **kw)


def test_endpoint_requires_shared_metered_recovery_port(monkeypatch):
    rt, a, kw, _, _, _, _ = ready_fixture(monkeypatch)
    del a.execute_restoration
    with pytest.raises(ValueError, match="shared metered"):
        p.preparation_binding(rt, a, restore_completed_target=True, **kw)


def test_missing_nurse_preserves_failure_after_target_attainment(monkeypatch):
    rt, a, kw, mon, _, calls, _ = ready_fixture(monkeypatch)
    monkeypatch.setattr(p, "RedCenterRestoreGoalProvider", lambda *a, **k: N(offer=lambda _: N(binding=None)))
    b = p.preparation_binding(rt, a, restore_completed_target=True, **kw)
    with pytest.raises(RuntimeError, match="restoration unavailable"): b.execute()
    assert mon.level == 6 and mon.experience == 180 and not calls
