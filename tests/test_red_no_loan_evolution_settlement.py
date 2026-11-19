"""E2: a declared no-loan configuration settles evolution as a verified no-op."""

from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_goal_context as context
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_native_boxed_evolution import settle_native_evolution
from pokemon_red_completion.red_player_party_guard import RedPlayerPartyGuard


def _runtime(*, active_refs=("a", "b"), battle=0, input_ready=True, field_carrier=None, loanable=frozenset()):
    a = PartyMemberObservation(1, 177, 15, 30, 40, experience=3000)
    b = PartyMemberObservation(2, 165, 7, 20, 25, experience=350)
    members = {"a": a, "b": b, "c": PartyMemberObservation(3, 13, 9, 20, 22, experience=500)}
    reader = N(read=lambda: PartyObservation(tuple(members[r] for r in active_refs)),
               preparation_specimen_refs=lambda: active_refs)
    guard = RedPlayerPartyGuard(reader, PartyObservation((a, b)), ("a", "b"), frozenset(),
                                N(read_box_specimen_identities=lambda: ()) if loanable else None, loanable)
    if field_carrier is not None:
        object.__setattr__(guard, "field_carrier", field_carrier)
    calls = []
    adapter = N(party_guard=guard, observe=lambda: N(raw=N(battle_state=battle), input_ready=input_ready))
    return N(evolution_settlement=lambda port: calls.append(port), adapter=adapter), calls


def test_restored_roster_is_a_verified_noop_without_calling_the_loan_callback():
    runtime, calls = _runtime()
    assert settle_native_evolution(runtime, "port") == {"no_loan_active_roster_verified": True}
    assert calls == []


def test_extra_withdrawn_member_is_allowed_but_original_members_must_remain_active():
    runtime, calls = _runtime(active_refs=("a", "b", "c"))
    assert settle_native_evolution(runtime, "port") == {"no_loan_active_roster_verified": True}
    runtime, calls = _runtime(active_refs=("a", "c"))
    with pytest.raises(context.RedGoalContextError, match="unrestored active roster"):
        settle_native_evolution(runtime, "port")
    assert calls == []


def test_unsettled_battle_requires_the_original_training_error_to_defer():
    runtime, calls = _runtime(battle=1)
    with pytest.raises(context.RedGoalContextError, match="settled field control"):
        settle_native_evolution(runtime, "port")
    assert settle_native_evolution(runtime, "port", training_error=RuntimeError("x")) == {
        "retained_active_roster_restoration_deferred": True
    }
    runtime, _ = _runtime(input_ready=False)
    with pytest.raises(context.RedGoalContextError):
        settle_native_evolution(runtime, "port")
    assert calls == []


def test_loan_configurations_and_field_carriers_keep_the_existing_contract():
    runtime, calls = _runtime(field_carrier=N(phase="pending"))
    with pytest.raises(context.RedGoalContextError, match="explicit guarded PC loan"):
        settle_native_evolution(runtime, "port")
    runtime, calls = _runtime(loanable=frozenset({"b"}))
    try:  # the existing loan path still runs its callback, then its own stock checks
        settle_native_evolution(runtime, "port")
    except Exception:  # noqa: BLE001 - this stub lacks a collection observation
        pass
    assert calls == ["port"]
