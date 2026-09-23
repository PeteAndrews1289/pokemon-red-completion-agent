"""Bounded, observed stationary-NPC exchanges, not link trades or evolution.

Cartridge tables and text scripts identify offers; fresh observations prove the
physical exchange. No registered training-admission rule is relaxed here.
Pinned semantics: pret/pokered 1e96034092686d006e863cace09e87273051a3d8,
engine/events/in_game_trades.asm. The native flag is set BEFORE the exchange,
so that flag alone is never success evidence.
"""

from collections import Counter
from dataclasses import dataclass, replace

from .actions import MacroAction, MacroActionKind
from .gen1_acquisition import map_objects
from .gen1_cartridge import CartridgeReadError, bank_offset, in_game_trades
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS
from .red_collection import red_species_ref


class RedNPCTradeError(RuntimeError):
    """An admitted trade missed its observed input or exact exchange boundary."""


@dataclass(frozen=True, slots=True)
class RedNPCTrade:
    index: int
    give: int
    receive: int
    map_id: int
    sprite_index: int
    picture_id: int
    at: tuple[int, int]
    town: int
    center: int


def stationary_npc_trades(rom: bytes) -> tuple[RedNPCTrade, ...]:
    """Two supported stationary scripts; roaming traders remain unavailable."""
    offers, objects = in_game_trades(rom), map_objects(rom)
    result = []
    # Script locations, not transcribed species, levels or walking directions.
    for map_id, index, town, center in ((0x30, 1, 2, 0x3A), (0x3F, 6, 3, 0x40)):
        bank = rom[MAP_HEADER_BANKS + map_id]
        pointer = MAP_HEADER_POINTERS + 2 * map_id
        header = bank_offset(bank, int.from_bytes(rom[pointer : pointer + 2], "little"))
        texts = bank_offset(bank, int.from_bytes(rom[header + 5 : header + 7], "little"))
        script = bank_offset(bank, int.from_bytes(rom[texts + 2 : texts + 4], "little"))
        expected = bytes((0x08, 0x3E, index)) + bytes.fromhex("ea3dcd3e54cd6d3ec3d724")
        if rom[script : script + len(expected)] != expected:
            raise CartridgeReadError("stationary NPC trade script differs")
        matches = [
            (i + 1, obj)
            for i, obj in enumerate(objects[map_id])
            if obj.text_and_kind == 2 and obj.movement == 0xFF
        ]
        if len(matches) != 1:
            raise CartridgeReadError("stationary NPC trade object differs")
        sprite, obj = matches[0]
        offer = offers[index]
        result.append(
            RedNPCTrade(
                index,
                offer.give_species,
                offer.get_species,
                map_id,
                sprite,
                obj.sprite,
                (obj.y, obj.x),
                town,
                center,
            )
        )
    return tuple(result)


def exchange_allowed(collection, trade, protected, registered) -> bool:
    """Only an unprotected physical source may buy a missing registration."""
    source, target = red_species_ref(trade.give), red_species_ref(trade.receive)
    counts = Counter(s.species_ref for s in collection.specimens)
    return target not in registered and counts[source] > protected.get(source, 0)


def verify_npc_exchange(before, after, trade, *, level, flags_before, flags_after, protected):
    """Preserve every other species/level, all credit and protected quantities.

    Containers may change during the declared PC preparation. The local party
    receipt separately proves exact preservation of non-exchanged party records.
    """
    old, new = before.collection_observation, after.collection_observation
    source, target = red_species_ref(trade.give), red_species_ref(trade.receive)
    expected = Counter((s.species_ref, s.level) for s in old.specimens)
    if expected[(source, level)] < 1 or not exchange_allowed(
        old, trade, protected, old.owned_species
    ):
        return False
    expected[(source, level)] -= 1
    expected[(target, level)] += 1
    counts = Counter(s.species_ref for s in new.specimens)
    return bool(
        trade.index not in flags_before
        and flags_after == flags_before | {trade.index}
        and Counter((s.species_ref, s.level) for s in new.specimens) == +expected
        and new.owned_species == old.owned_species | {target}
        and all(counts[s] >= n for s, n in protected.items())
        and before.raw.player_money == after.raw.player_money
        and before.raw.bag_items == after.raw.bag_items
        and after.raw.map_id == trade.map_id
        and after.raw.battle_state == 0
        and after.input_ready
    )


def execute_adjacent_trade(
    actions, reader, party_reader, trade, *, source_slot, source_species_id, target_species_id
):
    """Consume an already selected offer at an authenticated adjacent NPC.

    Source slot is one-based. No retry, species substitution, hidden input or
    battle fallback. Unknown menus time out rather than confirming blindly.
    """
    before = party_reader.read().members
    raw = reader.read()
    flags = reader.read_completed_npc_trades()
    if (
        raw.map_id != trade.map_id
        or raw.battle_state != 0
        or not reader.read_input_readiness().ready
        or reader.read_bottom_dialogue_box_visible()
        or reader.read_pending_trainer_battle_identity() is not None
        or trade.index in flags
        or not 1 <= source_slot <= len(before)
        or before[source_slot - 1].species_id != source_species_id
    ):
        raise RedNPCTradeError("trade boundary or source slot differs")
    objects = [
        o
        for o in reader.read_current_map_objects()
        if o.sprite_index == trade.sprite_index and o.picture_id == trade.picture_id
    ]
    if len(objects) != 1 or objects[0].at != trade.at:
        raise RedNPCTradeError("trade NPC identity or position differs")
    delta = trade.at[0] - raw.player_y, trade.at[1] - raw.player_x
    facing = {(1, 0): "down", (-1, 0): "up", (0, 1): "right", (0, -1): "left"}.get(delta)
    if facing is None:
        raise RedNPCTradeError("trade NPC is not adjacent")

    def pulse(kind, value=None):
        actions.execute(MacroAction(kind, value))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))

    if reader.read_player_facing() != facing:
        pulse(MacroActionKind.MOVE, facing)
    now = reader.read()
    if (now.map_id, now.player_y, now.player_x) != (
        raw.map_id,
        raw.player_y,
        raw.player_x,
    ) or reader.read_player_facing() != facing:
        raise RedNPCTradeError("trade facing did not preserve position")
    pulse(MacroActionKind.INTERACT)
    accepted = selected = False
    for _ in range(120):
        if reader.read().battle_state:
            raise RedNPCTradeError("unexpected trade battle")
        phase = reader.read_npc_trade_input()
        current_flags = reader.read_completed_npc_trades()
        if selected and current_flags == flags | {trade.index}:
            party = party_reader.read().members
            if (
                reader.read_input_readiness().ready
                and not reader.read_bottom_dialogue_box_visible()
                and phase is None
                and len(party) == len(before)
                and party[-1].species_id == target_species_id
                and party[-1].level == before[source_slot - 1].level
            ):
                preserved = before[: source_slot - 1] + before[source_slot:]
                if tuple(replace(m, slot=i + 1) for i, m in enumerate(preserved)) != party[:-1]:
                    raise RedNPCTradeError("trade changed another party member")
                return {
                    "offer_accepted": True,
                    "source_slot": source_slot,
                    "trade_index": trade.index,
                    "received_level": party[-1].level,
                }
        if phase is not None:
            kind, cursor = phase
            if kind == "offer" and not accepted:
                if cursor:
                    pulse(MacroActionKind.MOVE, "up")
                else:
                    pulse(MacroActionKind.CONFIRM)
                    accepted = True
            elif kind == "party" and accepted and not selected:
                if cursor != source_slot - 1:
                    pulse(MacroActionKind.MOVE, "down" if cursor < source_slot - 1 else "up")
                else:
                    pulse(MacroActionKind.CONFIRM)
                    selected = True
            else:
                raise RedNPCTradeError("unexpected repeated trade menu")
        elif reader.read_bottom_dialogue_box_visible():
            # B advances prose but cannot accidentally accept a new offer.
            pulse(MacroActionKind.CANCEL)
        else:
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
    raise RedNPCTradeError("trade dialogue/animation exceeded its budget")
