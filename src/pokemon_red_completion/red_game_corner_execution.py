"""Legal native Game Corner transactions, not a funding or gambling policy.

Targets, prices and menu ownership are cartridge-authenticated. These bounded
executors translate an already selected transaction into observed inputs and
verify exact currency/inventory changes. They never edit money or registration.
"""

from collections import Counter

from .actions import MacroAction, MacroActionKind
from .gen1_acquisition import game_corner_prizes, map_objects
from .gen1_cartridge import CartridgeReadError, bank_offset, internal_to_dex
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS
from .observation import MAX_BAG_ITEMS, event_flag_is_set
from .red_game_corner_resources import authenticate_coin_vendor
from .surge import _pulse

GAME_CORNER = 0x87
PRIZE_ROOM = 0x89
DINER = 0x8A
COIN_CASE = 0x45
_PARTY = ("party_count", "party_species_ids", "party_levels", "party_hp",
    "party_max_hp", "party_moves", "party_pp", "party_status", "party_stats")
_FIELD = ("map_id", "player_x", "player_y", "badge_bits", "battle_state")


def _boundary(reader, map_id, at, facing):
    raw = reader.read()
    if (raw.map_id != map_id or (raw.player_y, raw.player_x) != at
        or raw.battle_state != 0 or not reader.read_input_readiness().ready
        or reader.read_bottom_dialogue_box_visible()
        or reader.read_player_facing() != facing):
        raise ValueError("Game Corner transaction needs its observed field stance")
    if raw.bag_items is None or raw.player_money is None:
        raise ValueError("Game Corner resource observation unavailable")
    return raw


def _same(before, after, fields):
    if any(getattr(before, field) != getattr(after, field) for field in fields):
        raise RuntimeError("Game Corner changed protected field or party resources")


def _yes_no(reader):
    rows = " ".join(reader.read_screen_text_rows()).upper()
    if "YES" not in rows or "NO" not in rows:
        return False
    cursor = reader.read_menu_cursor_state()
    return cursor.maximum_visible_index == 1


def _select(actions, reader, index):
    for _ in range(8):
        cursor = reader.read_menu_cursor_state()
        if cursor.scroll_offset or index > cursor.maximum_visible_index:
            raise ValueError("transaction menu geometry differs")
        if cursor.selected_visible_index == index:
            _pulse(actions, MacroActionKind.CONFIRM, frames=120)
            return
        actions.execute(MacroAction(MacroActionKind.MOVE,
            "down" if cursor.selected_visible_index < index else "up"))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
    raise RuntimeError("transaction menu selection did not converge")


def coin_case_gift_contract(rom):
    obj = map_objects(rom)[DINER][4]
    if (obj.sprite, obj.y, obj.x, obj.movement, obj.text_and_kind) != (36, 1, 0, 255, 5):
        raise CartridgeReadError("Coin Case donor object differs")
    bank = rom[MAP_HEADER_BANKS + DINER]
    at = MAP_HEADER_POINTERS + 2 * DINER
    header = bank_offset(bank, int.from_bytes(rom[at:at+2], "little"))
    texts = bank_offset(bank, int.from_bytes(rom[header+5:header+7], "little"))
    script = bank_offset(bank, int.from_bytes(rom[texts+8:texts+10], "little"))
    expected = bytes.fromhex("08fa83d7cb47202321a751cd493c010145cd2e3e300d"
        "2183d7cbc621ac51cd493c180e21b251cd493c180621b751cd493cc3d724")
    if rom[script:script+len(expected)] != expected:
        raise CartridgeReadError("Coin Case native gift script differs")
    return (0xD783 - 0xD747) * 8


def collect_coin_case(actions, reader, *, rom):
    flag = coin_case_gift_contract(rom)
    before = _boundary(reader, DINER, (1, 1), "left")
    objects = [o for o in reader.read_current_map_objects() if o.sprite_index == 5]
    if (len(objects) != 1 or not objects[0].visible or objects[0].moving
        or objects[0].picture_id != 36 or objects[0].at != (1, 0)
        or before.event_flags is None or event_flag_is_set(before.event_flags, flag)):
        raise ValueError("Coin Case donor absent or already consumed")
    bag = dict(before.bag_items)
    if COIN_CASE in bag or len(bag) >= MAX_BAG_ITEMS:
        raise ValueError("Coin Case already held or bag full")
    boxes, dex, pc = reader.read_all_box_states(), reader.read_pokedex_state(), reader.read_pc_items()
    expected = {**bag, COIN_CASE: 1}
    flags = bytearray(before.event_flags)
    flags[flag // 8] |= 1 << (flag % 8)
    _pulse(actions, MacroActionKind.INTERACT, frames=120)
    for _ in range(32):
        after = reader.read()
        _same(before, after, _PARTY + _FIELD + ("player_money",))
        if (dict(after.bag_items) not in (bag, expected)
            or after.event_flags not in (before.event_flags, bytes(flags))
            or reader.read_all_box_states() != boxes or reader.read_pokedex_state() != dex
            or reader.read_pc_items() != pc):
            raise RuntimeError("Coin Case changed unrelated inventory or events")
        if (dict(after.bag_items) == expected and after.event_flags == bytes(flags)
            and reader.read_input_readiness().ready and not reader.read_bottom_dialogue_box_visible()):
            return dict(item_id=COIN_CASE, quantity=1, event_verified=True, learned=False)
        _pulse(actions, MacroActionKind.CANCEL, frames=120)
    raise RuntimeError("Coin Case gift did not settle")


def buy_coin_lot(actions, reader, *, rom):
    case, lot, price, refusal, capacity = authenticate_coin_vendor(rom)
    # The clerk is one tile behind the native counter, not adjacent floor.
    before = _boundary(reader, GAME_CORNER, (8, 5), "up")
    coins = reader.read_game_corner_coins()
    if dict(before.bag_items).get(case) != 1 or coins >= refusal or before.player_money < price:
        raise ValueError("Coin lot lacks Coin Case, capacity or cash")
    clerk = [o for o in reader.read_current_map_objects() if o.sprite_index == 2]
    if len(clerk) != 1 or not clerk[0].visible or clerk[0].at != (6, 5) or clerk[0].picture_id != 38:
        raise ValueError("Coin clerk observation differs")
    boxes, dex, pc = reader.read_all_box_states(), reader.read_pokedex_state(), reader.read_pc_items()
    expected = min(capacity, coins + lot)
    _pulse(actions, MacroActionKind.INTERACT, frames=120)
    confirmed = False
    for _ in range(32):
        after = reader.read()
        balance = reader.read_game_corner_coins()
        _same(before, after, _PARTY + _FIELD + ("bag_items", "event_flags"))
        if (after.player_money not in (before.player_money, before.player_money-price)
            or balance not in (coins, expected) or reader.read_all_box_states() != boxes
            or reader.read_pokedex_state() != dex or reader.read_pc_items() != pc):
            raise RuntimeError("Coin vendor changed unexpected resources")
        paid = after.player_money == before.player_money-price and balance == expected
        if paid and reader.read_input_readiness().ready and not reader.read_bottom_dialogue_box_visible():
            if not confirmed:
                raise RuntimeError("Unobserved coin purchase authority")
            return dict(cash_debit=price, coins_before=coins, coins_after=balance,
                coins_added=balance-coins, learned=False)
        if not confirmed and _yes_no(reader):
            _select(actions, reader, 0)
            confirmed = True
        else:
            _pulse(actions, MacroActionKind.CANCEL if confirmed else MacroActionKind.CONFIRM, frames=120)
    raise RuntimeError("Coin lot purchase did not settle")


def _specimens(raw, boxes):
    return Counter([("party", s, level) for s, level in zip(raw.party_species_ids, raw.party_levels, strict=True)]
        + [(box.box_index, s, level) for box in boxes.boxes
            for s, level in zip(box.species_ids, box.levels, strict=True)])


def receive_pokemon_prize(actions, reader, *, rom, species):
    prizes = game_corner_prizes(rom)
    indices = [i for i, p in enumerate(prizes) if p.species == species]
    if len(indices) != 1:
        raise ValueError("No unique cartridge Pokemon prize")
    index = indices[0]
    prize = prizes[index]
    before = _boundary(reader, PRIZE_ROOM, (3, 2 + 2*(index//3)), "up")
    boxes, dex, pc = reader.read_all_box_states(), reader.read_pokedex_state(), reader.read_pc_items()
    coins = reader.read_game_corner_coins()
    if (dict(before.bag_items).get(COIN_CASE) != 1 or coins < prize.cost
        or (before.party_count >= 6 and len(boxes.boxes[boxes.current_box_index].species_ids) >= 20)):
        raise ValueError("Prize lacks Coin Case, coins or immediate storage")
    internal = [s for s, n in internal_to_dex(rom).items() if n == species]
    if len(internal) != 1:
        raise CartridgeReadError("Prize internal species is ambiguous")
    destination = "party" if before.party_count < 6 else boxes.current_box_index
    expected_specimens = _specimens(before, boxes) + Counter({(destination, internal[0], prize.level): 1})
    _pulse(actions, MacroActionKind.INTERACT, frames=120)
    selected = confirmed = False
    for _ in range(80):
        after = reader.read()
        _same(before, after, _FIELD + ("player_money", "bag_items", "event_flags"))
        if reader.read_pc_items() != pc or reader.read_game_corner_coins() not in (coins, coins-prize.cost):
            raise RuntimeError("Prize changed unrelated currency or PC items")
        # GivePokemon writes owned/seen and party/box bytes in separate native
        # steps. Match the gift executor: read coherent collection only after
        # the receipt dialogue settles, not between those cartridge writes.
        if confirmed and (not reader.read_input_readiness().ready or reader.read_bottom_dialogue_box_visible()):
            _pulse(actions, MacroActionKind.CANCEL, frames=180)
            continue
        new_boxes = reader.read_all_box_states()
        specimens = _specimens(after, new_boxes)
        if specimens not in (_specimens(before, boxes), expected_specimens):
            raise RuntimeError("Prize changed an unexpected specimen")
        if before.party_count == 6:
            _same(before, after, _PARTY)
        else:
            for field in _PARTY[1:]:
                values, old = getattr(after, field), getattr(before, field)
                if values is not None and old is not None and tuple(values[:len(old)]) != tuple(old):
                    raise RuntimeError("Prize changed an existing party member")
        actual_dex = reader.read_pokedex_state()
        if (not set(dex.owned_species) <= set(actual_dex.owned_species)
            or set(actual_dex.owned_species)-set(dex.owned_species) not in (set(), {species})):
            raise RuntimeError("Prize changed unrelated owned flags")
        if (not set(dex.seen_species) <= set(actual_dex.seen_species)
            or set(actual_dex.seen_species)-set(dex.seen_species) not in (set(), {species})):
            raise RuntimeError("Prize changed unrelated seen flags")
        gained = (specimens == expected_specimens and species in actual_dex.owned_species
            and reader.read_game_corner_coins() == coins-prize.cost)
        if gained and reader.read_input_readiness().ready and not reader.read_bottom_dialogue_box_visible():
            if not selected or not confirmed:
                raise RuntimeError("Unobserved prize selection authority")
            return dict(species=species, level=prize.level, coins_spent=prize.cost,
                coins_before=coins, coins_after=coins-prize.cost,
                local_registration_added=species not in dex.owned_species,
                specimen_added=True, destination=destination, learned=False)
        rows = " ".join(reader.read_screen_text_rows())
        counter = prizes[3*(index//3):3*(index//3)+3]
        menu_visible = not selected and all(str(p.cost) in rows for p in counter)
        cursor = reader.read_menu_cursor_state() if menu_visible else None
        if (cursor is not None and cursor.top_x == 1 and cursor.top_y == 4
            and cursor.maximum_visible_index == 3 and cursor.scroll_offset == 0
            and menu_visible):
            _select(actions, reader, index % 3)
            selected = True
        elif selected and not confirmed and _yes_no(reader):
            _select(actions, reader, 0)
            confirmed = True
        else:
            _pulse(actions, MacroActionKind.CANCEL if confirmed else MacroActionKind.CONFIRM, frames=120)
    raise RuntimeError("Pokemon prize did not settle")
