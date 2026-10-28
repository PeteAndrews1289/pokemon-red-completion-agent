"""One-time NPC item gifts with cartridge script and native outcome proof.

The first qualified script is Museum1F's fossil ingredient. This is a parameter
adapter, not a movement recipe or an autonomous decision to collect that item.
Grammar reference: pret/pokered 1e96034092686d006e863cace09e87273051a3d8,
scripts/Museum1F.asm, Museum1FScientist2Text. Other scripts are not implied supported.
"""

from dataclasses import dataclass

from .actions import MacroActionKind
from .gen1_acquisition import map_objects
from .gen1_cartridge import CartridgeReadError, bank_offset
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS
from .gen1_trainer_sight import EVENT_FLAGS_END, EVENT_FLAGS_START
from .observation import MAX_BAG_ITEMS, event_flag_is_set
from .rom import verify_rom_bytes


@dataclass(frozen=True, slots=True)
class RedNPCItemGift:
    map_id: int
    object_index: int
    sprite_id: int
    at: tuple[int, int]
    item_id: int
    quantity: int
    event_flag: int
    removed_object_index: int
    toggle_index: int


def _decode_gift(rom, obj, object_index, removed_object_index):
    bank = rom[MAP_HEADER_BANKS + obj.map_id]

    def pointer(at):
        if not 0 <= at < at + 2 <= len(rom):
            raise CartridgeReadError("item gift pointer is truncated")
        value = int.from_bytes(rom[at : at + 2], "little")
        if not 0x4000 <= value < 0x8000:
            raise CartridgeReadError("item gift pointer leaves bank")
        return bank_offset(bank, value)

    header = pointer(MAP_HEADER_POINTERS + obj.map_id * 2)
    texts = pointer(header + 5)
    if obj.is_item or obj.is_trainer or not 1 <= obj.text_and_kind <= 63:
        raise CartridgeReadError("item gift needs an ordinary text NPC")
    script = pointer(texts + (obj.text_and_kind - 1) * 2)
    if script + 56 > min(len(rom), (bank + 1) * 0x4000):
        raise CartridgeReadError("item gift script is truncated")
    b = rom[script : script + 56]
    address = int.from_bytes(b[2:4], "little")
    bit = (b[5] - 0x47) // 8
    if (
        b[:2] != bytes.fromhex("08 fa")
        or b[4] != 0xCB
        or not 0 <= bit <= 7
        or b[5] != 0x47 + 8 * bit
        or not EVENT_FLAGS_START <= address < EVENT_FLAGS_END
        or b[6:9] != bytes.fromhex("20 27 21")
        or b[11:15] != bytes.fromhex("cd 49 3c 01")
        or not 1 <= b[15] <= 99
        or not 1 <= b[16] <= 250
        or b[17:23] != bytes.fromhex("cd 2e 3e 30 14 21")
        or b[23:25] != b[2:4]
        or b[25:28] != bytes((0xCB, 0xC6 + 8 * bit, 0x3E))
        or b[29:38] != bytes.fromhex("ea 4d cc 3e 11 cd 6d 3e 21")
        or b[40:43] != bytes.fromhex("18 08 21")
        or b[45:48] != bytes.fromhex("18 03 21")
        or b[50:] != bytes.fromhex("cd 49 3c c3 d7 24")
    ):
        raise CartridgeReadError("unsupported one-time item gift grammar")
    for offset in (9, 38, 43, 48):
        pointer(script + offset)
    return RedNPCItemGift(
        obj.map_id,
        object_index,
        obj.sprite,
        (obj.y, obj.x),
        b[16],
        b[15],
        (address - EVENT_FLAGS_START) * 8 + bit,
        removed_object_index,
        b[28],
    )


def old_amber_gift(rom: bytes) -> RedNPCItemGift:
    """Authenticate the qualified item/NPC/display contract, never its route."""
    verify_rom_bytes(rom)
    objects = map_objects(rom)[52]
    if len(objects) != 5 or objects[2].movement != 0xFF or objects[4].sprite != 0x45:
        raise CartridgeReadError("fossil ingredient object table differs")
    gift = _decode_gift(rom, objects[2], 3, 5)
    if (gift.item_id, gift.quantity, gift.toggle_index, gift.sprite_id) != (31, 1, 52, 32):
        raise CartridgeReadError("fossil ingredient script identity differs")
    return gift


def collect_npc_item_gift(actions, reader, gift: RedNPCItemGift, *, rom: bytes) -> dict:
    """Interact once from an admitted stance; retain errors rather than retry."""
    from .surge import _pulse

    if gift != old_amber_gift(rom):
        raise ValueError("item gift differs from authenticated cartridge source")
    before = reader.read()
    if (
        not before.game_started
        or before.map_id != gift.map_id
        or before.battle_state != 0
        or not reader.read_input_readiness().ready
        or reader.read_bottom_dialogue_box_visible()
        or before.event_flags is None
        or len(before.event_flags) * 8 <= gift.event_flag
        or event_flag_is_set(before.event_flags, gift.event_flag)
        or before.bag_items is None
    ):
        raise ValueError("item gift requires an unconsumed field boundary")
    objects = reader.read_current_map_objects()
    npcs = [o for o in objects if o.sprite_index == gift.object_index]
    direction = reader.read_player_facing()
    delta = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
    if (
        len(npcs) != 1
        or not npcs[0].visible
        or npcs[0].moving
        or (npcs[0].picture_id, npcs[0].at) != (gift.sprite_id, gift.at)
        or before.player_y is None
        or before.player_x is None
        or direction not in delta
        or (before.player_y + delta[direction][0], before.player_x + delta[direction][1]) != gift.at
        or not any(o.sprite_index == gift.removed_object_index for o in objects)
    ):
        raise ValueError("item gift NPC/display/adjacent-facing evidence differs")
    bag = dict(before.bag_items)
    if bag.get(gift.item_id, 0) or len(bag) >= MAX_BAG_ITEMS:
        raise ValueError("one-time gift already held or bag full")
    expected = {**bag, gift.item_id: gift.quantity}
    flags = bytearray(before.event_flags)
    flags[gift.event_flag // 8] |= 1 << (gift.event_flag % 8)
    expected_flags = bytes(flags)
    boxes, dex, pc = (
        reader.read_all_box_states(),
        reader.read_pokedex_state(),
        reader.read_pc_items(),
    )
    _pulse(actions, MacroActionKind.INTERACT, frames=120)
    for _ in range(64):
        after = reader.read()
        for name in (
            "map_id",
            "player_y",
            "player_x",
            "player_money",
            "battle_state",
            "badge_bits",
            "party_count",
            "party_species_ids",
            "party_levels",
            "party_hp",
            "party_max_hp",
            "party_moves",
            "party_pp",
            "party_status",
            "party_stats",
        ):
            if getattr(after, name) != getattr(before, name):
                raise RuntimeError("item gift changed protected " + name)
        if (
            after.bag_items is None
            or dict(after.bag_items) not in (bag, expected)
            or after.event_flags not in (before.event_flags, expected_flags)
            or reader.read_all_box_states() != boxes
            or reader.read_pokedex_state() != dex
            or reader.read_pc_items() != pc
        ):
            raise RuntimeError("item gift changed protected inventory, events or collection")
        gained = dict(after.bag_items) == expected and after.event_flags == expected_flags
        if (
            gained
            and reader.read_input_readiness().ready
            and not reader.read_bottom_dialogue_box_visible()
            and not any(
                o.sprite_index == gift.removed_object_index
                for o in reader.read_current_map_objects()
            )
        ):
            return dict(
                item_id=gift.item_id,
                quantity=gift.quantity,
                event_verified=True,
                source_removed=True,
                learned=False,
            )
        _pulse(actions, MacroActionKind.CANCEL if gained else MacroActionKind.CONFIRM, frames=120)
    raise RuntimeError("item gift did not settle within its native bound")


@dataclass(frozen=True, slots=True)
class RedDrinkItemGift:
    map_id: int
    object_index: int
    sprite_id: int
    drink_item_id: int
    item_id: int
    event_flag: int


def fresh_water_machine_gift(rom: bytes) -> RedDrinkItemGift:
    """Decode the qualified roof exchange; no recommendation or route is implied.

    Grammar: the same pinned pret/pokered revision, CeladonMartRoof.asm.
    The current adapter qualifies Fresh Water only. The other drink branches
    remain unsupported even though their text shares the same NPC.
    """
    from .observation import EventFlag, ItemId, MapId

    verify_rom_bytes(rom)
    mid = int(MapId.CELADON_MART_ROOF)
    objects = map_objects(rom)[mid]
    if len(objects) != 2 or (objects[1].sprite, objects[1].text_and_kind) != (8, 2):
        raise CartridgeReadError("drink gift object differs")
    bank = rom[MAP_HEADER_BANKS + mid]

    def pointer(at):
        if not 0 <= at < at + 2 <= len(rom):
            raise CartridgeReadError("drink gift pointer is truncated")
        value = int.from_bytes(rom[at : at + 2], "little")
        if not 0x4000 <= value < 0x8000:
            raise CartridgeReadError("drink gift pointer leaves bank")
        return bank_offset(bank, value)

    header = pointer(MAP_HEADER_POINTERS + mid * 2)
    texts = pointer(header + 5)
    script = pointer(texts + 2)
    # The girl's prompt calls the verified filtered-drink helper, YesNoChoice
    # and the gift dispatcher. This rejects another ordinary text NPC.
    if (rom[script : script + 8] != bytes.fromhex("08 cd d8 43 fa 37 cd a7")
            or rom[script + 21 : script + 24] != bytes.fromhex("cd ec 35")
            or rom[script + 30 : script + 33] != bytes.fromhex("cd 0c 44")):
        raise CartridgeReadError("drink gift prompt grammar differs")
    dispatcher = pointer(script + 31)
    body = rom[dispatcher : dispatcher + 220]
    signature = bytes.fromhex(
        "fa 78 d7 cb 67 20 23 21 f3 44 cd 49 3c cd e6 44 "
        "01 01 d5 cd 2e 3e 30 0c 21 f9 44 cd 49 3c 21 78 d7 cb e6 c9"
    )
    if body.count(signature) != 1:
        raise CartridgeReadError("Fresh Water gift consume/give/event grammar differs")
    at = body.index(signature)
    address = int.from_bytes(body[at + 1 : at + 3], "little")
    bit = (body[at + 4] - 0x47) // 8
    event = (address - EVENT_FLAGS_START) * 8 + bit
    if not EVENT_FLAGS_START <= address < EVENT_FLAGS_END or event != int(EventFlag.GOT_TM13):
        raise CartridgeReadError("drink gift event differs")
    return RedDrinkItemGift(mid, 2, objects[1].sprite, int(ItemId.FRESH_WATER), body[at + 18], event)


def collect_drink_item_gift(actions, reader, gift: RedDrinkItemGift, *, rom: bytes) -> dict:
    """One admitted exchange, bounded by visible menus and exact custody.

    The caller already approached the current NPC. No item is seeded, no cash
    is created and no missing resource is supplied by this executor.
    """
    from .surge import _pulse

    if gift != fresh_water_machine_gift(rom):
        raise ValueError("drink gift descriptor differs")
    before = reader.read()
    bag = dict(before.bag_items or ())
    flags = before.event_flags
    if (
        not before.game_started or before.map_id != gift.map_id or before.battle_state
        or not reader.read_input_readiness().ready or reader.read_bottom_dialogue_box_visible()
        or flags is None or len(flags) * 8 <= gift.event_flag
        or event_flag_is_set(flags, gift.event_flag) or bag.get(gift.item_id, 0)
        or bag.get(gift.drink_item_id, 0) != 1 or len(bag) >= MAX_BAG_ITEMS
    ):
        raise ValueError("drink gift requires an unconsumed field/resource boundary")
    npcs = [o for o in reader.read_current_map_objects() if o.sprite_index == gift.object_index]
    direction = reader.read_player_facing()
    delta = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
    if (
        len(npcs) != 1 or not npcs[0].visible or npcs[0].moving
        or npcs[0].picture_id != gift.sprite_id or direction not in delta
        or before.player_y is None or before.player_x is None
        or (before.player_y + delta[direction][0], before.player_x + delta[direction][1]) != npcs[0].at
    ):
        raise ValueError("drink gift requires the observed adjacent-facing NPC")
    # Keep the contract conservative: one drink leaves one slot for the TM.
    expected_bag = dict(bag)
    del expected_bag[gift.drink_item_id]
    expected_bag[gift.item_id] = 1
    expected_flags = bytearray(flags)
    expected_flags[gift.event_flag // 8] |= 1 << (gift.event_flag % 8)
    expected_flags = bytes(expected_flags)
    custody = (reader.read_all_box_states(), reader.read_pokedex_state(), reader.read_pc_items())
    drink_count = sum(bool(bag.get(i)) for i in (60, 61, 62))
    confirmed_offer = False
    confirmed_drink = False
    _pulse(actions, MacroActionKind.INTERACT, frames=120)
    for _ in range(96):
        after = reader.read()
        for name in (
            "map_id", "player_y", "player_x", "player_money", "battle_state", "badge_bits",
            "party_count", "party_species_ids", "party_levels", "party_hp", "party_max_hp",
            "party_moves", "party_pp", "party_status", "party_stats",
        ):
            if getattr(after, name) != getattr(before, name):
                raise RuntimeError("drink gift changed protected " + name)
        current = dict(after.bag_items or ())
        removed = {k: v for k, v in bag.items() if k != gift.drink_item_id}
        if (after.bag_items is None or current not in (bag, removed, expected_bag)
                or after.event_flags not in (flags, expected_flags)
                or custody != (reader.read_all_box_states(), reader.read_pokedex_state(), reader.read_pc_items())):
            raise RuntimeError("drink gift changed protected inventory, events or collection")
        gained = current == expected_bag and after.event_flags == expected_flags
        if (gained and confirmed_offer and confirmed_drink
                and reader.read_input_readiness().ready
                and not reader.read_bottom_dialogue_box_visible()):
            return dict(drink_item_id=gift.drink_item_id, item_id=gift.item_id, quantity=1,
                        drink_consumed=True, event_verified=True, learned=False,
                        normal_controller_inputs=True, cash_debit=0)
        if gained:
            _pulse(actions, MacroActionKind.CANCEL, frames=120)
            continue
        if (confirmed_offer and confirmed_drink
                and current in (removed, expected_bag)):
            # Exact chosen-drink consumption owns the rest of this cartridge
            # transaction. Red gives the TM, prints several acknowledgement
            # pages, then sets the event flag. Its old bag cursor can persist
            # throughout; it no longer denotes an undecided resource choice.
            if not reader.read_bottom_dialogue_box_visible():
                raise RuntimeError("drink gift commit lost its owned dialogue")
            _pulse(actions, MacroActionKind.CONFIRM, frames=120)
            continue
        prompt = reader.read_drink_gift_input(drink_count)
        if prompt is not None:
            phase, selected = prompt
            if phase == "offer" and not confirmed_drink:
                if selected != 0:
                    raise RuntimeError("drink gift offer cursor differs")
                confirmed_offer = True
            elif phase == "drink" and confirmed_offer:
                if selected != 0:  # Fresh Water is first in the cartridge's filtered list.
                    raise RuntimeError("drink gift resource cursor differs")
                confirmed_drink = True
            else:
                raise RuntimeError("drink gift unexpected or repeated input phase")
            # Red can retain the selected cursor while printing acknowledgement
            # text before consuming the drink. Repeated same-phase confirms
            # advance that owned text; they never re-interact with the NPC.
            _pulse(actions, MacroActionKind.CONFIRM, frames=120)
        else:
            # The observation adapter rejects an unknown active cursor below;
            # this branch can advance ordinary text only.
            _pulse(actions, MacroActionKind.CONFIRM, frames=120)
    raise RuntimeError("drink gift did not settle within its native bound")
