from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_gym_reward as gym


@pytest.mark.parametrize(
    "fault", [None, "identity", "set", "consumed", "consumed_event", "missing"]
)
@pytest.mark.parametrize("spec", [gym.KOGA_REWARD, gym.BLAINE_REWARD, gym.GIOVANNI_REWARD])
def test_leader_contract(monkeypatch, fault, spec):
    monkeypatch.setattr(gym, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        gym,
        "map_object_events",
        lambda *a: (
            NS(
                object_index=1,
                trainer_class=240 if fault == "identity" else spec.trainer_class,
                trainer_set=spec.trainer_set + (1 if fault == "set" else 0),
            ),
        ),
    )
    monkeypatch.setattr(gym, "trainer_party_quote", lambda *a: NS(expected_victory_money=4257))
    events = bytearray(256)
    if fault == "consumed_event":
        events[spec.defeated_event // 8] |= 1 << (spec.defeated_event % 8)
    raw = NS(
        event_flags=None if fault == "missing" else bytes(events),
        badge_bits=spec.badge if fault == "consumed" else 0,
    )
    if fault:
        with pytest.raises(ValueError):
            spec.contract(b"rom", raw)
    else:
        contract = spec.contract(b"rom", raw)
        assert contract.trainer_identity == (
            spec.trainer_class,
            spec.trainer_class - 200,
            spec.trainer_set,
        )
        assert contract.victory_items == ((spec.item, 1),)
        assert contract.victory_badge_bits == spec.badge


@pytest.mark.parametrize("fault", [None, "no_win", "cash", "item", "badge", "map"])
@pytest.mark.parametrize("spec", [gym.KOGA_REWARD, gym.BLAINE_REWARD, gym.GIOVANNI_REWARD])
def test_native_reward_reconciliation(monkeypatch, fault, spec):
    events = bytearray(256)
    for e in (spec.defeated_event, spec.reward_event):
        events[e // 8] |= 1 << (e % 8)
    if fault == "no_win":
        events[spec.defeated_event // 8] = 0
    raw = NS(
        event_flags=bytes(events),
        battle_state=0,
        map_id=0 if fault == "map" else spec.map_id,
        player_money=5256 if fault == "cash" else 5257,
        bag_items=((4, 1),) if fault == "item" else ((4, 1), (spec.item, 1)),
        badge_bits=(15 | spec.badge) ^ (1 if fault == "badge" else 0),
    )
    reader = NS(
        read=lambda: raw,
        read_input_readiness=lambda: NS(ready=True),
        read_bottom_dialogue_box_visible=lambda: False,
    )
    monkeypatch.setattr(gym.silph, "_interact", lambda *a: None)
    before = NS(player_money=1000, bag_items=((4, 1),), badge_bits=15)
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            spec.settle(reader, NS(), before=before, victory_money=4257)
    else:
        assert spec.settle(reader, NS(), before=before, victory_money=4257)["item"] == spec.item
