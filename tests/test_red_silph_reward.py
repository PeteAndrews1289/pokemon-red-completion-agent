from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_silph_reward as reward
from pokemon_red_completion.observation import EventFlag, ItemId, RawGameState


@pytest.mark.parametrize("fault", [None, "unearned", "claimed", "full", "cash", "timeout"])
def test_reward_requires_earned_boundary_and_exact_inventory(monkeypatch, fault):
    events = bytearray(256)
    if fault != "unearned":
        events[int(EventFlag.BEAT_SILPH_CO_GIOVANNI) // 8] |= (
            1 << (int(EventFlag.BEAT_SILPH_CO_GIOVANNI) % 8))
    if fault == "claimed":
        events[int(EventFlag.GOT_MASTER_BALL) // 8] |= (
            1 << (int(EventFlag.GOT_MASTER_BALL) % 8))
    bag = tuple((i, 1) for i in range(2, 22)) if fault == "full" else ((4, 1),)
    state = [RawGameState(True, 235, 12, 7, 2, 0, event_flags=bytes(events),
                          bag_items=bag, player_money=1000)]
    calls = []

    monkeypatch.setattr(reward, "approach_npc", lambda *a, **kw: calls.append("route"))

    def interact(*args):
        if fault == "timeout":
            return
        updated = bytearray(state[0].event_flags)
        updated[int(EventFlag.GOT_MASTER_BALL) // 8] |= (
            1 << (int(EventFlag.GOT_MASTER_BALL) % 8))
        state[0] = replace(state[0], event_flags=bytes(updated),
                           bag_items=(*bag, (int(ItemId.MASTER_BALL), 1)),
                           player_money=999 if fault == "cash" else 1000)

    monkeypatch.setattr(reward.silph, "_interact", interact)
    monkeypatch.setattr(reward.silph, "_confirm_many", lambda *a: None)
    reader = NS(read=lambda: state[0], read_input_readiness=lambda: NS(ready=True),
                read_bottom_dialogue_box_visible=lambda: False)
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            reward.collect_silph_reward(NS(), reader, NS(), rom=b"rom")
        if fault in {"unearned", "claimed", "full"}:
            assert not calls
    else:
        assert reward.collect_silph_reward(NS(), reader, NS(), rom=b"rom")[
            "master_balls_received"] == 1
