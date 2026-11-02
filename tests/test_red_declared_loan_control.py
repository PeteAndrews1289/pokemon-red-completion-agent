from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as N

import pytest
from test_red_player_party_loan import setup

from pokemon_red_completion import red_player_lesson_runtime as module
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalVerification,
)


@pytest.mark.parametrize("battle", (0, 1))
@pytest.mark.parametrize("fault", (None, "no_loan", "wrong_kind", "wrong_ref", "extra", "mutated"))
def test_only_exact_compulsory_control_can_defer_boxed_combat_anchor(monkeypatch, battle, fault):
    runtime, _, state, _ = setup(monkeypatch)
    payload = [b"exact-retained-loan"]
    runtime.emulator = N(frame_count=0, save_state_bytes=lambda: payload[0])
    runtime.registration_policy = None
    guard = runtime.adapter.party_guard
    if fault == "no_loan":
        runtime.adapter.party_guard = replace(guard, loanable_refs=frozenset())
    members = dict(zip(state.refs, state.members, strict=True))
    raw = N(battle_state=battle)
    observation = N(raw=raw, input_ready=not battle)
    monkeypatch.setattr(module, "capture_player_lesson_snapshot", lambda _: (observation, {}))
    monkeypatch.setattr(
        module, "project_registered_observation", lambda *a: N(public_dict=lambda: {})
    )
    monkeypatch.setattr(module, "validate_snapshot", lambda *a: members)
    events = []
    actions = N(record_diagnostic_event=lambda *a: events.append(a))
    prefix = "pokemon.red:interrupted-wild:" if battle else "pokemon.red:retained-loan-return:"

    def inventory(*args):
        if fault == "mutated":
            payload[0] = b"changed"
        binding = ExecutableGoalBinding(("wrong:" if fault == "wrong_ref" else prefix)
            + sha256(b"exact-retained-loan").hexdigest(),
            GoalKind.EXPLORE if fault == "wrong_kind" else GoalKind.RECOVER_CONTROL,
            0.0, 0.0, lambda: pytest.fail("discovery cannot execute"),
            lambda _: GoalVerification.succeeded())
        bindings = (binding,)
        if fault == "extra":
            bindings += (ExecutableGoalBinding("other", GoalKind.EXPLORE, 0.0, 0.0,
                lambda: pytest.fail("discovery cannot execute"),
                lambda _: GoalVerification.succeeded()),)
        blocked = GoalOpportunity("blocked", GoalKind.ADVANCE_STORY, GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED)
        return GoalBindingSet(tuple(b.opportunity for b in bindings) + (blocked,), bindings)

    def observe():
        return module._declared_loan_control_support(runtime, actions,
            combat_specimen_refs=("loan",), remaining_budget=(1.0,) * 5,
            enumerate_bindings=inventory, include_live_pp_readiness=False)

    if fault == "no_loan":
        assert observe() is None
    elif fault:
        with pytest.raises(ValueError):
            observe()
    else:
        result = observe()
        assert result.binding.kind is GoalKind.RECOVER_CONTROL
        assert result.public_dict()["model_queries"] == 0
        assert not result.readiness.history_observed
        assert events[0][1]["guest_promoted_to_combat"] is False
        assert set(guard.refs) - set(state.refs) == {"loan"}
        assert state.cash == 100


def test_ordinary_boundary_does_not_receive_a_loan_control_exception(monkeypatch):
    runtime, _, _, _ = setup(monkeypatch, already_restored=True)
    assert module._declared_loan_control_support(runtime, None,
        combat_specimen_refs=("loan",), remaining_budget=(1.0,) * 5,
        enumerate_bindings=lambda *a: pytest.fail("ordinary boundary must keep normal inventory"),
        include_live_pp_readiness=False) is None
