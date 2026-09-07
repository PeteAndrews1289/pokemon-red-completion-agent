from types import SimpleNamespace

import pytest

from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_routed_recovery import (
    RecoveryRouteInterruptionHandler,
    RedRoutedRecoveryError,
)
from pokemon_red_completion.route_executor import InterruptionReceipt, TraversalSnapshot


class FakeInner:
    def __init__(self, receipt=None, exc=None):
        self.calls = 0
        self.receipt = receipt or InterruptionReceipt("wild_battle", 1, (0, 0))
        self.exc = exc

    def handle(self, snapshot: TraversalSnapshot) -> InterruptionReceipt:
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.receipt


def make_handler(raw, ready=True, exc=None):
    inner = FakeInner(exc=exc)
    reader = SimpleNamespace(
        read=lambda: raw,
        read_input_readiness=lambda: SimpleNamespace(ready=ready),
    )
    handler = RecoveryRouteInterruptionHandler(
        executor=SimpleNamespace(execute=lambda a: None),
        reader=reader,
        post_prep_species=(25, 15),
        post_prep_living_slots=(1,),
        inner=inner,
    )
    return handler, inner


SNAP = TraversalSnapshot(1, (0, 0), True, interruption="wild_battle")
RAW_BASE = dict(game_started=True, map_id=1, player_x=0, player_y=0, party_count=2)


def test_originally_fainted_member_survives_and_returns_receipt():
    raw = RawGameState(**RAW_BASE, battle_state=0, party_species_ids=(25, 15), party_hp=(0, 10))
    handler, inner = make_handler(raw)
    receipt = handler.handle(SNAP)
    assert receipt == inner.receipt
    assert inner.calls == 1


def test_newly_fainted_living_member_rejected():
    raw = RawGameState(**RAW_BASE, battle_state=0, party_species_ids=(25, 15), party_hp=(0, 0))
    handler, inner = make_handler(raw)
    with pytest.raises(RedRoutedRecoveryError, match="slot 1 fainted"):
        handler.handle(SNAP)
    assert inner.calls == 1


@pytest.mark.parametrize("species,hp", [((25,), (0,)), ((25, 15), (10,))])
def test_missing_roster_or_hp_slot_rejected(species, hp):
    raw = RawGameState(**RAW_BASE, battle_state=0, party_species_ids=species, party_hp=hp)
    handler, inner = make_handler(raw)
    with pytest.raises(RedRoutedRecoveryError, match="party roster truncated or changed"):
        handler.handle(SNAP)
    assert inner.calls == 1


def test_species_reorder_rejected():
    raw = RawGameState(**RAW_BASE, battle_state=0, party_species_ids=(15, 25), party_hp=(0, 10))
    handler, inner = make_handler(raw)
    with pytest.raises(RedRoutedRecoveryError, match="party species changed"):
        handler.handle(SNAP)
    assert inner.calls == 1


@pytest.mark.parametrize("battle_state,ready", [(1, True), (0, False)])
def test_unsettled_field_or_battle_ongoing_rejected(battle_state, ready):
    raw = RawGameState(
        **RAW_BASE, battle_state=battle_state, party_species_ids=(25, 15), party_hp=(0, 10),
    )
    handler, inner = make_handler(raw, ready=ready)
    with pytest.raises(RedRoutedRecoveryError, match="field not settled"):
        handler.handle(SNAP)
    assert inner.calls == 1


def test_inner_exception_propagates():
    raw = RawGameState(**RAW_BASE, battle_state=0, party_species_ids=(25, 15), party_hp=(0, 10))
    handler, inner = make_handler(raw, exc=RuntimeError("inner failure"))
    with pytest.raises(RuntimeError, match="inner failure"):
        handler.handle(SNAP)
    assert inner.calls == 1
