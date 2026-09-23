from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_story_item_storage as storage
from pokemon_red_completion.observation import EventFlag, ItemId, RawGameState


@pytest.mark.parametrize("fault", [None, "unearned", "pc_full", "pc_stack_full",
                                      "lost", "extra", "cash", "party", "field"])
def test_storage_conserves_items_and_protected_state(monkeypatch, fault):
    events = bytearray(256)
    for event in (EventFlag.GOT_MASTER_BALL, EventFlag.BEAT_SABRINA):
        events[int(event) // 8] |= 1 << (int(event) % 8)
    if fault == "unearned":
        events = bytearray(256)
    bag = ((int(ItemId.SILPH_SCOPE), 1), (int(ItemId.CARD_KEY), 1), (1, 1), (4, 3))
    raw = [RawGameState(True, 182, 3, 3, 2, 0, event_flags=bytes(events),
                        bag_items=bag, player_money=16459)]
    pc = {2: 1}
    if fault == "pc_full":
        pc = {i: 1 for i in range(100, 150)}
    elif fault == "pc_stack_full":
        pc[int(ItemId.CARD_KEY)] = 99
    calls = []

    def store(*args):
        calls.append(True)
        for item in storage.sabrina.PC_DEPOSIT_ITEMS:
            if fault != "lost":
                pc[int(item)] = pc.get(int(item), 0) + 1
        kept = tuple(row for row in bag if row[0] not in storage.sabrina.PC_DEPOSIT_ITEMS)
        raw[0] = replace(raw[0], bag_items=kept)
        if fault == "extra":
            raw[0] = replace(raw[0], bag_items=())
        elif fault == "cash":
            raw[0] = replace(raw[0], player_money=0)
        elif fault == "party":
            raw[0] = replace(raw[0], party_hp=(1,))
        elif fault == "field":
            raw[0] = replace(raw[0], player_x=4)

    monkeypatch.setattr(storage.sabrina, "_store_obsolete_key_items", store)
    reader = NS(read=lambda: raw[0], read_pc_items=lambda: tuple(pc.items()),
                read_input_readiness=lambda: NS(ready=True))
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            storage.archive_completed_story_keys(NS(), reader, NS())
        if fault in {"unearned", "pc_full", "pc_stack_full"}:
            assert not calls
    else:
        result = storage.archive_completed_story_keys(NS(), reader, NS())
        assert result["bag_stacks_after"] == 2
        assert pc[int(ItemId.CARD_KEY)] == pc[int(ItemId.SILPH_SCOPE)] == 1
