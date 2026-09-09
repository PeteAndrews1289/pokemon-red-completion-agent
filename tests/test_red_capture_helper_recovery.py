from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_capture_party import fixture

import pokemon_red_completion.red_capture_helper_recovery as recovery
import pokemon_red_completion.red_capture_party as support
from pokemon_red_completion.goal_manager_runtime import GoalVerification
from pokemon_red_completion.party import StatusCondition


@pytest.mark.parametrize("mutation", [None, "still_asleep", "money", "lost_specimen"])
def test_withdraw_then_explicit_restore_rechecks_readiness_and_resources(monkeypatch, mutation):
    plan, state, reader, healthy = fixture(monkeypatch)
    asleep = replace(
        healthy,
        members=(*healthy.members[:-1], replace(healthy.members[-1], status=StatusCondition.SLEEP)),
    )
    current = [asleep]
    calls = []

    def restore():
        calls.append("restore")
        if mutation != "still_asleep":
            current[0] = healthy
        if mutation == "money":
            state.raw = replace(state.raw, player_money=1)
        if mutation == "lost_specimen":
            state.box = replace(state.box, species_ids=(185,), levels=(13,))
        return {"capture_helper_restoration": {"verified": True, "setup_training_rows": 0}}

    def execute():
        return support.execute_capture_party_at_pc(
            plan,
            object(),
            reader,
            pc_map_id=64,
            read_party=lambda: current[0],
            restore_helper=restore,
        )

    if mutation:
        with pytest.raises(support.RedCapturePartyError):
            execute()
    else:
        result = execute()
        assert result["capture_helper_restoration"]["verified"] is True
        assert result["specimens_preserved"] == 8
        assert result["setup_training_rows"] == 0
    assert calls == ["restore"]


def test_ready_withdrawal_does_not_trigger_an_extra_center_visit(monkeypatch):
    plan, _, reader, healthy = fixture(monkeypatch)
    support.execute_capture_party_at_pc(
        plan,
        object(),
        reader,
        pc_map_id=64,
        read_party=lambda: healthy,
        restore_helper=lambda: pytest.fail("unnecessary healing"),
    )


@pytest.mark.parametrize("mode", ["success", "unverified", "still_asleep", "unavailable"])
def test_recovery_uses_existing_verified_skill_and_actual_readiness(monkeypatch, mode):
    from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind

    _, _, _, healthy = fixture(monkeypatch)
    asleep = replace(
        healthy,
        members=(*healthy.members[:-1], replace(healthy.members[-1], status=StatusCondition.SLEEP)),
    )
    current = [
        SimpleNamespace(
            party=asleep, input_ready=True, raw=SimpleNamespace(map_id=64, battle_state=0)
        )
    ]
    actions = SimpleNamespace(actions_executed=5)
    emulator = SimpleNamespace(frame_count=20)
    local = object()
    router = SimpleNamespace(
        routed_recovery=True,
        actions=actions,
        runtime=SimpleNamespace(
            emulator=emulator,
            enumerator=lambda _: SimpleNamespace(enumerate=lambda _: local),
            adapter=SimpleNamespace(observe=lambda: current[0]),
        ),
    )
    calls = []

    def execute():
        calls.append("execute")
        actions.actions_executed += 11
        emulator.frame_count += 120
        if mode != "still_asleep":
            current[0].party = healthy
        return object()

    def verify(report):
        calls.append("verify")
        return (
            GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if mode == "unverified"
            else GoalVerification.succeeded()
        )

    def bind(r, bindings, observed, *, prepare_escort, require_pp_restore):
        assert r is router and require_pp_restore is True
        assert bindings is local
        calls.append("bind")
        return SimpleNamespace(
            bindings=()
            if mode == "unavailable"
            else (SimpleNamespace(kind=GoalKind.RESTORE_TEAM, execute=execute, verify=verify),)
        )

    monkeypatch.setattr(recovery, "bind_routed_center_recovery", bind)
    if mode != "success":
        with pytest.raises(support.RedCapturePartyError):
            recovery.restore_capture_helper(router)
    else:
        result = recovery.restore_capture_helper(router)
        assert result == {
            "capture_helper_restoration": {
                "verified": True,
                "actions": 11,
                "frames": 120,
                "setup_training_rows": 0,
            }
        }
    assert calls == (["bind"] if mode == "unavailable" else ["bind", "execute", "verify"])
