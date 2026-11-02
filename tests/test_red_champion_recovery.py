from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_faint_recovery import raw_party

from pokemon_red_completion import red_champion_recovery as gate


def test_owned_revive_one_item_budget():
    raw = raw_party(bag=((53, 1),))
    choice = gate.owned_champion_revive(raw)
    assert (int(choice.item), choice.party_index, choice.expected_hp) == (53, 1, 50)


@pytest.mark.parametrize("used", [1, 2, -1, True, None])
def test_repeated_or_invalid_revive_budget_rejected(used):
    with pytest.raises(ValueError):
        gate.owned_champion_revive(raw_party(bag=((53, 1),)), items_used=used)


@pytest.mark.parametrize("bag,hp", [(((53, 2),), (100, 0)), ((), (100, 0)),
                                   (((18, 1),), (100, 1)), (((53, 1),), (100, 1))])
def test_other_preparation_resources_rejected(bag, hp):
    with pytest.raises(ValueError):
        gate.owned_champion_revive(raw_party(bag=bag, hp=hp))


@pytest.mark.parametrize("battle_result", [0, 1])
@pytest.mark.parametrize("fault", [None, "win", "unresolved", "not_ready", "cash",
                                   "cost", "battle", "map", "event", "resources", "missing"])
def test_only_settled_authentic_loss_enters_recovery(monkeypatch, fault, battle_result):
    raw = replace(raw_party(hp=(180, 101)), map_id=9, player_money=11921,
                  event_flags=bytes(320), battle_state=0, battle_result=battle_result)
    completion = NS(outcome="lost", field_ready=True, money_delta=-11922,
                    episode=NS(battle_won=False, stop_reason="party_defeated"))
    monkeypatch.setattr(gate, "_raw_party_fully_restored", lambda _: fault != "resources")
    if fault in {"win", "unresolved"}:
        completion.outcome = "won" if fault == "win" else "unresolved"
    if fault == "cash":
        raw = replace(raw, player_money=23843)
    if fault == "cost":
        completion.money_delta = 0
    if fault == "battle":
        raw = replace(raw, battle_state=2)
    if fault == "map":
        raw = replace(raw, map_id=120)
    if fault == "event":
        flags = bytearray(320)
        flags[2305 // 8] |= 1 << (2305 % 8)
        raw = replace(raw, event_flags=bytes(flags))
    if fault == "missing":
        completion = None
    kwargs = dict(starting_money=23843, input_ready=fault != "not_ready")
    if fault:
        with pytest.raises(ValueError):
            gate.require_champion_loss_recovery(completion, raw, **kwargs)
    else:
        gate.require_champion_loss_recovery(completion, raw, **kwargs)
