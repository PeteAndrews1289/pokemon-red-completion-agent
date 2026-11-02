from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_acquisition import MapObject
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS
from pokemon_red_completion.observation import CurrentMapObject, RawGameState
from pokemon_red_completion.red_npc_item_gift import (
    RedNPCItemGift,
    _decode_gift,
    collect_npc_item_gift,
)


def cartridge():
    rom = bytearray(0x10000)
    rom[MAP_HEADER_BANKS + 52] = 3
    rom[MAP_HEADER_POINTERS + 104 : MAP_HEADER_POINTERS + 106] = b"\x00\x41"
    rom[0xC105:0xC107] = b"\x00\x42"
    rom[0xC204:0xC206] = b"\x00\x43"
    # Independent event bit2 atD800; four synthetic text addresses in this bank.
    body = bytes.fromhex(
        "08 fa 00 d8 cb 57 20 27 21 10 44 cd 49 3c 01 01 1f "
        "cd 2e 3e 30 14 21 00 d8 cb d6 3e 34 ea 4d cc 3e 11 cd 6d 3e "
        "21 20 44 18 08 21 30 44 18 03 21 40 44 cd 49 3c c3 d7 24"
    )
    rom[0xC300:0xC338] = body
    return rom, MapObject(52, 32, 2, 15, 255, 208, 3)


def test_decoder_follows_npc_text_and_derives_item_quantity_and_event():
    rom, obj = cartridge()
    result = _decode_gift(bytes(rom), obj, 3, 5)
    assert result == RedNPCItemGift(52, 3, 32, (2, 15), 31, 1, 1482, 5, 52)
    rom[0xC310] = 42
    rom[0xC30F] = 2
    changed = _decode_gift(bytes(rom), obj, 3, 5)
    assert (changed.item_id, changed.quantity) == (42, 2)


@pytest.mark.parametrize(
    "offset,value",
    [
        (0, 0),
        (1, 0),
        (3, 0xC0),
        (4, 0),
        (5, 0x4E),
        (7, 0),
        (8, 0),
        (11, 0),
        (14, 0),
        (15, 0),
        (16, 0),
        (19, 0),
        (21, 0),
        (23, 1),
        (26, 0),
        (33, 0),
        (35, 0),
        (41, 0),
        (46, 0),
        (53, 0),
        (10, 0x80),
    ],
)
def test_decoder_refuses_mutated_script_instead_of_guessing(offset, value):
    rom, obj = cartridge()
    rom[0xC300 + offset] = value
    with pytest.raises(CartridgeReadError):
        _decode_gift(bytes(rom), obj, 3, 5)


@pytest.mark.parametrize("kind", [0, 0x43, 0x83])
def test_non_npc_text_rejected(kind):
    rom, obj = cartridge()
    with pytest.raises(CartridgeReadError):
        _decode_gift(bytes(rom), replace(obj, text_and_kind=kind), 3, 5)


GIFT = RedNPCItemGift(52, 3, 32, (2, 15), 31, 1, 105, 5, 52)


def world(monkeypatch, *, fault=None, stalled=False):
    import pokemon_red_completion.red_npc_item_gift as m
    import pokemon_red_completion.surge as surge

    w = NS(
        raw=RawGameState(
            True,
            52,
            15,
            3,
            1,
            0,
            bag_items=((3, 10),),
            event_flags=bytes(320),
            player_money=1000,
            party_species_ids=(28,),
            party_hp=(100,),
        ),
        pulses=[],
        facing="up",
        given=False,
        settled=False,
        boxes=(),
        dex=(),
        pc=(),
    )
    npc = CurrentMapObject(3, 32, (2, 15), 0, 0)
    display = CurrentMapObject(5, 69, (2, 16), 0, 0)
    w.objects = (npc, display)
    w.read = lambda: w.raw
    w.read_input_readiness = lambda: NS(ready=not w.given or w.settled)
    w.read_bottom_dialogue_box_visible = lambda: w.given and not w.settled
    w.read_player_facing = lambda: w.facing
    w.read_current_map_objects = lambda: w.objects
    w.read_all_box_states = lambda: w.boxes
    w.read_pokedex_state = lambda: w.dex
    w.read_pc_items = lambda: w.pc
    monkeypatch.setattr(m, "old_amber_gift", lambda _: GIFT)

    def pulse(actions, kind, **kwargs):
        w.pulses.append(kind)
        if stalled:
            return
        if not w.given:
            flags = bytearray(w.raw.event_flags)
            flags[105 // 8] |= 1 << (105 % 8)
            w.raw = replace(w.raw, bag_items=(*w.raw.bag_items, (31, 1)), event_flags=bytes(flags))
            w.given = True
            if fault == "money":
                w.raw = replace(w.raw, player_money=0)
            if fault == "party":
                w.raw = replace(w.raw, party_hp=(99,))
            if fault == "bag":
                w.raw = replace(w.raw, bag_items=((31, 1),))
            if fault == "events":
                w.raw = replace(w.raw, event_flags=bytes([1]) + w.raw.event_flags[1:])
            if fault == "boxes":
                w.boxes = (1,)
        else:
            assert kind is MacroActionKind.CANCEL
            w.settled = True
            if fault != "display":
                w.objects = (npc,)

    monkeypatch.setattr(surge, "_pulse", pulse)
    return w


def test_native_gift_declines_after_gain_and_proves_exact_transition(monkeypatch):
    w = world(monkeypatch)
    result = collect_npc_item_gift(w, w, GIFT, rom=b"fixture")
    assert result == dict(
        item_id=31, quantity=1, event_verified=True, source_removed=True, learned=False
    )
    assert w.pulses == [MacroActionKind.INTERACT, MacroActionKind.CANCEL]


@pytest.mark.parametrize("fault", ["money", "party", "bag", "events", "boxes", "display"])
def test_gift_does_not_accept_extra_changes_or_missing_removal(monkeypatch, fault):
    w = world(monkeypatch, fault=fault)
    with pytest.raises(RuntimeError):
        collect_npc_item_gift(w, w, GIFT, rom=b"fixture")
    assert 1 <= len(w.pulses) <= 65


@pytest.mark.parametrize(
    "fault",
    [
        "descriptor",
        "not_started",
        "map",
        "battle",
        "facing",
        "owned",
        "full",
        "event",
        "npc",
        "display",
    ],
)
def test_unavailable_gift_refuses_before_any_input(monkeypatch, fault):
    w = world(monkeypatch)
    gift = GIFT
    if fault == "descriptor":
        gift = replace(gift, item_id=42)
    if fault == "not_started":
        w.raw = replace(w.raw, game_started=False)
    if fault == "map":
        w.raw = replace(w.raw, map_id=51)
    if fault == "battle":
        w.raw = replace(w.raw, battle_state=1)
    if fault == "facing":
        w.facing = "down"
    if fault == "owned":
        w.raw = replace(w.raw, bag_items=((31, 1),))
    if fault == "full":
        w.raw = replace(w.raw, bag_items=tuple((i, 1) for i in range(1, 21)))
    if fault == "event":
        flags = bytearray(320)
        flags[105 // 8] |= 1 << (105 % 8)
        w.raw = replace(w.raw, event_flags=bytes(flags))
    if fault == "npc":
        w.objects = (replace(w.objects[0], at=(2, 14)), w.objects[1])
    if fault == "display":
        w.objects = w.objects[:1]
    with pytest.raises(ValueError):
        collect_npc_item_gift(w, w, gift, rom=b"fixture")
    assert not w.pulses


def test_dialogue_has_finite_bound_and_does_not_reinteract(monkeypatch):
    w = world(monkeypatch, stalled=True)
    with pytest.raises(RuntimeError, match="bound"):
        collect_npc_item_gift(w, w, GIFT, rom=b"fixture")
    assert len(w.pulses) == 65
    assert w.pulses.count(MacroActionKind.INTERACT) == 1
