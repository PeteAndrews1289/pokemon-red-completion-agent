from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_gym_reward as gym


@pytest.mark.parametrize(
    "stacks,held,expected",
    [
        (19, None, True),
        (20, None, False),
        (20, 1, True),
        (20, 99, False),
    ],
)
def test_native_tm_capacity_is_a_real_slot_or_nonfull_existing_stack(stacks, held, expected):
    bag = {i: 1 for i in range(stacks)}
    if held is not None:
        bag.pop(0)
        bag[gym.GIOVANNI_REWARD.item] = held
    assert gym.GIOVANNI_REWARD.capacity_available(NS(bag_items=tuple(bag.items()))) is expected


@pytest.mark.parametrize("fault", [None, "defeat", "reward", "badge", "map", "battle"])
def test_pending_reward_requires_a_real_local_earned_badge(fault):
    reward = gym.GIOVANNI_REWARD
    events = bytearray(256)
    if fault != "defeat":
        events[reward.defeated_event // 8] |= 1 << (reward.defeated_event % 8)
    if fault == "reward":
        events[reward.reward_event // 8] |= 1 << (reward.reward_event % 8)
    raw = NS(
        map_id=0 if fault == "map" else reward.map_id,
        battle_state=1 if fault == "battle" else 0,
        event_flags=bytes(events),
        badge_bits=0 if fault == "badge" else reward.badge,
    )
    assert reward.pending(raw) is (fault is None)


@pytest.mark.parametrize(
    "spec",
    [
        gym.BROCK_REWARD,
        gym.MISTY_REWARD,
        gym.SURGE_REWARD,
        gym.ERIKA_REWARD,
        gym.SABRINA_REWARD,
        gym.KOGA_REWARD,
        gym.BLAINE_REWARD,
        gym.GIOVANNI_REWARD,
    ],
)
@pytest.mark.parametrize("fault", [None, "defeat", "reward", "badge", "events", "badges"])
def test_permanent_reward_proof_does_not_require_unconsumed_tm(spec, fault):
    events = bytearray(256)
    for event in (spec.defeated_event, spec.reward_event):
        if fault != ("defeat" if event == spec.defeated_event else "reward"):
            events[event // 8] |= 1 << (event % 8)
    raw = NS(
        event_flags=None if fault == "events" else bytes(events),
        badge_bits=None if fault == "badges" else (0 if fault == "badge" else spec.badge),
        bag_items=(),
    )
    assert spec.received(raw) == (fault is None)


@pytest.mark.parametrize(
    "fault", [None, "identity", "set", "consumed", "consumed_event", "missing"]
)
@pytest.mark.parametrize(
    "spec",
    [
        gym.BROCK_REWARD,
        gym.MISTY_REWARD,
        gym.SURGE_REWARD,
        gym.ERIKA_REWARD,
        gym.SABRINA_REWARD,
        gym.KOGA_REWARD,
        gym.BLAINE_REWARD,
        gym.GIOVANNI_REWARD,
    ],
)
def test_leader_contract(monkeypatch, fault, spec):
    monkeypatch.setattr(gym, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        gym,
        "map_object_events",
        lambda *a: (
            NS(
                object_index=1,
                trainer_class=spec.trainer_class + (1 if fault == "identity" else 0),
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
        assert contract.battle_plan_id == (
            "sabrina" if spec == gym.SABRINA_REWARD else spec.objective_id
        )
        assert contract.trainer_identity == (
            spec.trainer_class,
            spec.trainer_class - 200,
            spec.trainer_set,
        )
        assert contract.victory_items == ((spec.item, 1),)
        assert contract.victory_badge_bits == spec.badge


@pytest.mark.parametrize("fault", [None, "no_win", "cash", "item", "badge", "map"])
@pytest.mark.parametrize(
    "spec",
    [
        gym.BROCK_REWARD,
        gym.MISTY_REWARD,
        gym.SURGE_REWARD,
        gym.ERIKA_REWARD,
        gym.SABRINA_REWARD,
        gym.KOGA_REWARD,
        gym.BLAINE_REWARD,
        gym.GIOVANNI_REWARD,
    ],
)
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
