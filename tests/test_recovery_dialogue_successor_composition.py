"""Exercise the full route, recovery custody guard and dialogue/battle handoff."""

from dataclasses import replace

import pytest
from test_scripted_dialogue_battle_successor import prepared

from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.red_routed_recovery import (
    RecoveryRouteInterruptionHandler, RedRoutedRecoveryError,
)
from pokemon_red_completion.route_executor import (
    InterruptionReceipt, RouteExecutionLimits, _wait_until_ready,
)


def guarded():
    reader, actions, inner, snapshot = prepared()
    reader.raw = replace(reader.raw, party_count=1, party_species_ids=(165,),
                         party_hp=(30,), player_money=100)
    outer = RecoveryRouteInterruptionHandler(
        actions, reader, post_prep_species=(165,), post_prep_living_slots=(0,), inner=inner,
    )
    return reader, actions, outer, snapshot


def test_full_route_uses_both_handlers_and_preserves_custody(monkeypatch):
    reader, actions, handler, snapshot = guarded()
    calls = []

    def finish(*_args, **_kwargs):
        calls.append("separate_existing_battle_executor")
        reader.raw = replace(reader.raw, battle_state=0)
        reader.ready = True
        return reader.raw

    monkeypatch.setattr("pokemon_red_completion.gen1_route_runtime.run_adaptive_trainer_battle", finish)
    terminal, receipts, _ = _wait_until_ready(
        snapshot, actions, Gen1TraversalObserver(reader), handler,
        RouteExecutionLimits(max_interruptions=2), used_interruptions=0,
    )
    assert terminal.ready and calls == ["separate_existing_battle_executor"]
    assert [r.kind for r in receipts] == ["scripted_dialogue", "trainer_engagement"]
    assert reader.raw.party_species_ids == (165,) and reader.raw.party_hp == (30,)
    assert reader.raw.player_money == 100 and handler.verified_trainer_income == 0


@pytest.mark.parametrize("fault", ["missing", "wrong_kind", "unverified", "unhandled", "relocated",
                                  "species", "faint", "cash"])
def test_pending_claim_cannot_bypass_field_or_resource_guards(fault):
    reader, actions, handler, snapshot = guarded()
    kinds = frozenset() if fault == "unhandled" else frozenset({"battle:2"})

    class ClaimedSuccessor:
        handled_interruption_kinds = kinds

        def handle(self, _snapshot):
            reader.raw = replace(reader.raw, battle_state=2,
                                 player_y=7 if fault == "relocated" else 8,
                                 party_species_ids=(166,) if fault == "species" else (165,),
                                 party_hp=(0,) if fault == "faint" else (30,),
                                 player_money=101 if fault == "cash" else 100)
            details = dict(verified=fault != "unverified")
            if fault != "missing":
                details["pending_interruption_kind"] = "wild_battle" if fault == "wrong_kind" else "battle:2"
            return InterruptionReceipt(kind="scripted_dialogue", resumed_map=snapshot.map_id,
                                       resumed_at=snapshot.at, details=details)

    handler.inner = ClaimedSuccessor()
    with pytest.raises(RedRoutedRecoveryError):
        handler.handle(snapshot)
    assert handler.verified_trainer_income == 0
    assert actions.actions == []
