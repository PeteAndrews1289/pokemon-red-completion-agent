from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_acquisition import MapObject
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS
from pokemon_red_completion.observation import (
    CurrentMapObject, MenuCursorState, PokemonRedStateReader, RawGameState,
)
from pokemon_red_completion.red_npc_item_gift import (
    RedDrinkItemGift, collect_drink_item_gift, fresh_water_machine_gift,
)


def cartridge(monkeypatch):
    import pokemon_red_completion.red_npc_item_gift as m
    rom = bytearray(0x4C000)
    rom[MAP_HEADER_BANKS + 126] = 18
    rom[MAP_HEADER_POINTERS + 252:MAP_HEADER_POINTERS + 254] = bytes.fromhex('c943')
    rom[0x483CE:0x483D0] = bytes.fromhex('5b45')
    rom[0x4855D:0x4855F] = bytes.fromhex('6c45')
    rom[0x4856C:0x48574] = bytes.fromhex('08cdd843fa37cda7')
    rom[0x48581:0x48584] = bytes.fromhex('cdec35')
    rom[0x4858A:0x4858D] = bytes.fromhex('cd0c44')
    body = bytes.fromhex(
        'fa78d7cb67202321f344cd493ccde6440101d5cd2e3e300c21f944cd493c2178d7cbe6c9'
    )
    rom[0x4840C:0x4840C+len(body)] = body
    objects = (MapObject(126, 12, 4, 10, 255, 210, 1), MapObject(126, 8, 5, 5, 254, 0, 2))
    monkeypatch.setattr(m, 'verify_rom_bytes', lambda _: None)
    monkeypatch.setattr(m, 'map_objects', lambda _: {126: objects})
    return rom


def test_cartridge_contract_decodes_consumable_tm_and_event(monkeypatch):
    assert fresh_water_machine_gift(bytes(cartridge(monkeypatch))) == RedDrinkItemGift(126, 2, 8, 60, 213, 396)


@pytest.mark.parametrize('offset', [0x4856C, 0x48581, 0x4858A, 0x4840C, 0x48410, 0x4841E, 0x48421, 0x4842E])
def test_script_or_resource_mutation_is_not_silently_generalized(monkeypatch, offset):
    rom = cartridge(monkeypatch)
    rom[offset] ^= 1
    with pytest.raises(CartridgeReadError):
        fresh_water_machine_gift(bytes(rom))


GIFT = RedDrinkItemGift(126, 2, 8, 60, 213, 396)


def world(monkeypatch, fault=None):
    import pokemon_red_completion.red_npc_item_gift as m
    import pokemon_red_completion.surge as surge
    w = NS(raw=RawGameState(True,126,5,6,1,0,bag_items=((3,4),(60,1)),
        event_flags=bytes(320),player_money=20000,party_species_ids=(28,),party_hp=(100,)),
        phase=0,pulses=[],settled=False,boxes=(),dex=(),pc=())
    w.read=lambda:w.raw
    w.read_input_readiness=lambda:NS(ready=w.phase==0 or w.settled)
    w.read_bottom_dialogue_box_visible=lambda:w.phase>0 and not w.settled
    w.read_current_map_objects=lambda:(CurrentMapObject(2,8,(5,5),0,0),)
    w.read_player_facing=lambda:'up'
    w.read_all_box_states=lambda:w.boxes
    w.read_pokedex_state=lambda:w.dex
    w.read_pc_items=lambda:w.pc
    def prompt(count):
        assert count==1
        if fault=='unknown':return 'unrecognized',0
        return ('offer',int(fault=='cursor'))if w.phase==1 else ('drink',0)if w.phase==2 else None
    w.read_drink_gift_input=prompt
    monkeypatch.setattr(m,'fresh_water_machine_gift',lambda _:GIFT)
    def pulse(actions,kind,**kwargs):
        w.pulses.append(kind)
        if fault=='stalled':return
        if w.phase==0:w.phase=1
        elif w.phase==1:
            assert kind is MacroActionKind.CONFIRM
            w.phase=2
        elif w.phase==2:
            assert kind is MacroActionKind.CONFIRM
            flags=bytearray(w.raw.event_flags);flags[396//8]|=1<<(396%8)
            w.raw=replace(w.raw,bag_items=((3,4),(213,1)),event_flags=bytes(flags));w.phase=3
            if fault=='money':w.raw=replace(w.raw,player_money=0)
            if fault=='party':w.raw=replace(w.raw,party_hp=(99,))
            if fault=='bag':w.raw=replace(w.raw,bag_items=((213,1),))
            if fault=='event':w.raw=replace(w.raw,event_flags=bytes([1])+w.raw.event_flags[1:])
            if fault=='boxes':w.boxes=(1,)
            if fault=='pc':w.pc=(1,)
            if fault=='dex':w.dex=(1,)
        else:
            assert kind is MacroActionKind.CANCEL
            w.settled=True
    monkeypatch.setattr(surge,'_pulse',pulse)
    return w


def test_native_exchange_uses_visible_choices_and_exact_custody(monkeypatch):
    w=world(monkeypatch)
    x=collect_drink_item_gift(w,w,GIFT,rom=b'fixture')
    assert x['item_id']==213 and x['drink_consumed'] and x['event_verified'] and not x['learned']
    assert w.pulses==[MacroActionKind.INTERACT,MacroActionKind.CONFIRM,MacroActionKind.CONFIRM,MacroActionKind.CANCEL]
    assert w.raw.player_money==20000


@pytest.mark.parametrize('fault',['money','party','bag','event','boxes','pc','dex','cursor','unknown'])
def test_unknown_choice_or_extra_state_changes_stop_instead_of_counting_success(monkeypatch,fault):
    w=world(monkeypatch,fault)
    with pytest.raises(RuntimeError):collect_drink_item_gift(w,w,GIFT,rom=b'fixture')
    if fault in('cursor','unknown'):assert len(w.pulses)==1


@pytest.mark.parametrize('fault',['flag','drink_missing','drink_multiple','owned','full','battle','map','facing','descriptor'])
def test_unavailable_exchange_sends_no_input(monkeypatch,fault):
    w=world(monkeypatch);gift=GIFT
    if fault=='flag':
        flags=bytearray(w.raw.event_flags);flags[396//8]|=1<<(396%8);w.raw=replace(w.raw,event_flags=bytes(flags))
    if fault=='drink_missing':w.raw=replace(w.raw,bag_items=((3,4),))
    if fault=='drink_multiple':w.raw=replace(w.raw,bag_items=((3,4),(60,2)))
    if fault=='owned':w.raw=replace(w.raw,bag_items=(*w.raw.bag_items,(213,1)))
    if fault=='full':w.raw=replace(w.raw,bag_items=tuple((i,1)for i in range(1,20))+((60,1),))
    if fault=='battle':w.raw=replace(w.raw,battle_state=2)
    if fault=='map':w.raw=replace(w.raw,map_id=125)
    if fault=='facing':w.read_player_facing=lambda:'down'
    if fault=='descriptor':gift=replace(GIFT,item_id=214)
    with pytest.raises(ValueError):collect_drink_item_gift(w,w,gift,rom=b'fixture')
    assert not w.pulses


def test_finite_dialogue_bound_does_not_reinteract_or_reset_resources(monkeypatch):
    w=world(monkeypatch,'stalled')
    with pytest.raises(RuntimeError,match='bound'):collect_drink_item_gift(w,w,GIFT,rom=b'fixture')
    assert len(w.pulses)==97 and w.pulses.count(MacroActionKind.INTERACT)==1


class Memory:
    def read_u8(self,at):return 0


@pytest.mark.parametrize('signature,text,live,expected',[
    ((8,15,1),'Give her a DRINK? YES NO',True,('offer',0)),
    ((2,1,0),'FRESH WATER',True,('drink',0)),
    ((2,1,0),'FRESH WATER',False,None),
    ((8,15,1),'Teach this move? YES NO',True,('unrecognized',0)),
    ((8,15,1),'Give her a DRINK? YES',True,('unrecognized',0)),
    ((2,1,0),'SODA POP',True,('unrecognized',0)),
])
def test_semantic_prompt_requires_rendered_cursor_layout_and_resource_label(monkeypatch,signature,text,live,expected):
    reader=PokemonRedStateReader(Memory())
    monkeypatch.setattr(reader,'_active_menu_cursor',lambda:live)
    monkeypatch.setattr(reader,'read_menu_cursor_state',lambda:MenuCursorState(0,0,signature[2],signature[1],signature[0]))
    monkeypatch.setattr(reader,'read_screen_text_rows',lambda:(text,))
    assert reader.read_drink_gift_input(1)==expected


@pytest.mark.parametrize('count',[0,4,True,1.0,None])
def test_invalid_drink_counts_are_rejected(count):
    with pytest.raises(ValueError):PokemonRedStateReader(Memory()).read_drink_gift_input(count)


@pytest.mark.parametrize("retained_phase", [1, 2])
def test_selected_cursor_can_remain_visible_during_owned_acknowledgement_text(monkeypatch, retained_phase):
    import pokemon_red_completion.surge as surge
    w = world(monkeypatch)
    original_pulse = surge._pulse
    repeated = []
    def pulse(actions, kind, **kwargs):
        if w.phase == retained_phase and kind is MacroActionKind.CONFIRM and not repeated:
            w.pulses.append(kind)
            repeated.append(True)
            return  # Native text wait preserves the old cursor and inventory.
        original_pulse(actions, kind, **kwargs)
    monkeypatch.setattr(surge, "_pulse", pulse)
    result = collect_drink_item_gift(w, w, GIFT, rom=b"fixture")
    assert result["drink_consumed"] and result["event_verified"]
    assert len(w.pulses) == 5 and w.pulses.count(MacroActionKind.INTERACT) == 1


def test_received_item_text_waits_for_event_commit_with_stale_bag_cursor(monkeypatch):
    import pokemon_red_completion.surge as surge
    w = world(monkeypatch)
    original_prompt = w.read_drink_gift_input
    original_pulse = surge._pulse
    pending = []
    def prompt(count):
        return ("received", 0) if pending else original_prompt(count)
    def pulse(actions, kind, **kwargs):
        if w.phase == 2:
            original_pulse(actions, kind, **kwargs)
            w.raw = replace(w.raw, event_flags=bytes(320))
            pending.append(True)
        elif pending:
            assert kind is MacroActionKind.CONFIRM
            w.pulses.append(kind)
            flags = bytearray(w.raw.event_flags)
            flags[396 // 8] |= 1 << (396 % 8)
            w.raw = replace(w.raw, event_flags=bytes(flags))
            pending.clear()
        else:
            original_pulse(actions, kind, **kwargs)
    w.read_drink_gift_input = prompt
    monkeypatch.setattr(surge, "_pulse", pulse)
    receipt = collect_drink_item_gift(w, w, GIFT, rom=b"fixture")
    assert receipt["event_verified"] and len(w.pulses) == 5
    assert w.pulses.count(MacroActionKind.INTERACT) == 1


def test_received_text_without_owned_exchange_does_not_authorize_confirmation(monkeypatch):
    w = world(monkeypatch)
    w.read_drink_gift_input = lambda _: ("received", 0)
    with pytest.raises(RuntimeError, match="phase"):
        collect_drink_item_gift(w, w, GIFT, rom=b"fixture")
    assert w.pulses == [MacroActionKind.INTERACT]


@pytest.mark.parametrize("text,expected", [
    ("FRESH WATER RED received TM13", ("received", 0)),
    ("FRESH WATER RED received TM14", ("unrecognized", 0)),
    ("FRESH WATER RED received TM130", ("unrecognized", 0)),
])
def test_received_gift_text_is_distinct_from_retained_inventory_cursor(monkeypatch, text, expected):
    reader = PokemonRedStateReader(Memory())
    monkeypatch.setattr(reader, "_active_menu_cursor", lambda: True)
    monkeypatch.setattr(reader, "read_menu_cursor_state", lambda: MenuCursorState(0, 0, 15, 1, 2))
    monkeypatch.setattr(reader, "read_screen_text_rows", lambda: (text,))
    assert reader.read_drink_gift_input(1) == expected


@pytest.mark.parametrize("partial", ["drink_removed", "item_given"])
def test_owned_gift_commit_advances_multiple_text_stages_with_stale_cursor(monkeypatch, partial):
    import pokemon_red_completion.surge as surge
    w = world(monkeypatch)
    original_pulse = surge._pulse
    original_prompt = w.read_drink_gift_input
    pending = []
    def prompt(count):
        return ("unrecognized", 0) if pending else original_prompt(count)
    def pulse(actions, kind, **kwargs):
        if w.phase == 2:
            original_pulse(actions, kind, **kwargs)
            items = ((3, 4),) if partial == "drink_removed" else ((3, 4), (213, 1))
            w.raw = replace(w.raw, event_flags=bytes(320), bag_items=items)
            pending.append(0)
        elif pending:
            assert kind is MacroActionKind.CONFIRM
            w.pulses.append(kind)
            pending[0] += 1
            if pending[0] == 3:
                flags = bytearray(w.raw.event_flags)
                flags[396 // 8] |= 1 << (396 % 8)
                w.raw = replace(w.raw, event_flags=bytes(flags), bag_items=((3, 4), (213, 1)))
                pending.clear()
        else:
            original_pulse(actions, kind, **kwargs)
    w.read_drink_gift_input = prompt
    monkeypatch.setattr(surge, "_pulse", pulse)
    receipt = collect_drink_item_gift(w, w, GIFT, rom=b"fixture")
    assert receipt["event_verified"] and receipt["drink_consumed"]
    assert w.settled and w.pulses.count(MacroActionKind.INTERACT) == 1
    assert w.raw.player_money == 20000


def test_owned_but_uncommitted_gift_still_obeys_finite_bound(monkeypatch):
    import pokemon_red_completion.surge as surge
    w = world(monkeypatch)
    original_pulse = surge._pulse
    original_prompt = w.read_drink_gift_input
    def prompt(count):
        return ("unrecognized", 0) if w.phase == 3 else original_prompt(count)
    def pulse(actions, kind, **kwargs):
        if w.phase == 3:
            assert kind is MacroActionKind.CONFIRM
            w.pulses.append(kind)
        else:
            original_pulse(actions, kind, **kwargs)
            if w.phase == 3:
                w.raw = replace(w.raw, event_flags=bytes(320))
    w.read_drink_gift_input = prompt
    monkeypatch.setattr(surge, "_pulse", pulse)
    with pytest.raises(RuntimeError, match="bound"):
        collect_drink_item_gift(w, w, GIFT, rom=b"fixture")
    assert len(w.pulses) == 97 and w.pulses.count(MacroActionKind.INTERACT) == 1
