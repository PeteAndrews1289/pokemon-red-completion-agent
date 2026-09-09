"""Qualified auto-trigger trainer text before Red arms its battle identity.

TalkToTrainer prints its introduction before EngageMapTrainer/StartTrainerBattle.
This adapter qualifies that narrow text thunk, not arbitrary dialogue or menus.
Only a fresh bound trigger step or authenticated failed-state recovery may use it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .gen1_cartridge import CartridgeReadError, bank_offset
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS
from .gen1_scripted_arrival import trainer_room_interaction_coordinates
from .gen1_trainer_parties import trainer_party_quote
from .gen1_trainer_sight import TrainerFacing, trainer_headers, trainer_sight_zones
from .gen1_traversal import map_object_events
from .global_router import MacroPath
from .observation import InputReadiness, PokemonRedStateReader, RawGameState, event_flag_is_set
from .red_trainer_funding import TrainerFundingCandidate
from .rom import verify_rom_bytes
from .route_plan import RoutePlan


class TrainerDialogueReader(Protocol):
    def read(self) -> RawGameState: ...
    def read_player_facing(self) -> str: ...
    def read_bottom_dialogue_box_visible(self) -> bool: ...
    def read_trainer_dialogue_context(self) -> tuple[int, int]: ...
    def read_pending_trainer_battle_identity(self) -> tuple[int, int] | None: ...
    def read_input_readiness(self) -> InputReadiness: ...


def _qualified_header(rom: bytes, target: TrainerFundingCandidate) -> int:
    """Decode a target's map/default/text thunk under the public revision gate."""
    map_id = int(target.trainer.map_id)
    triggers = trainer_room_interaction_coordinates(rom, map_id)
    if target.approach.terminal_at not in triggers:
        raise CartridgeReadError("trainer text target is not an automatic trigger")
    headers = [
        h
        for h in trainer_headers(rom, {map_id}, full_event_offsets=True)
        if h.sprite_index == target.trainer.sprite_index
        and h.event_flag == target.trainer.event_flag
    ]
    if len(headers) != 1:
        raise CartridgeReadError("trainer text lacks a unique bound header")
    bank = rom[MAP_HEADER_BANKS + map_id]

    def pointer(at: int) -> int:
        value = int.from_bytes(rom[at : at + 2], "little")
        if not 0x4000 <= value <= 0x7FFF:
            raise CartridgeReadError("trainer text pointer leaves its bank")
        return bank_offset(bank, value)

    def read(at: int, count: int) -> bytes:
        if not bank * 0x4000 <= at < at + count <= min(len(rom), (bank + 1) * 0x4000):
            raise CartridgeReadError("trainer text span leaves its bank")
        return rom[at : at + count]

    header = pointer(MAP_HEADER_POINTERS + 2 * map_id)
    read(header, 9)
    script = pointer(header + 7)
    entry = read(script, 22)
    table = pointer(script + 10)
    read(table, 2)
    default = pointer(table)
    code = read(default, 32)
    # Existing arrival parser qualifies the coordinate branch. Bind its text ID
    # and exact supported DisplayTextID callee as well, not just JP's opcode.
    sprite = target.trainer.sprite_index
    if code[25:32] != bytes((0x3E, sprite, 0xE0, 0x8C, 0xC3, 0x20, 0x29)):
        raise CartridgeReadError("automatic trainer text branch differs")
    text_table = pointer(header + 5)
    read(text_table, 2 * sprite)
    thunk = pointer(text_table + 2 * (sprite - 1))
    expected = (
        b"\x08\x21" + headers[0].address.to_bytes(2, "little") + bytes.fromhex("cd cc 31 c3 d7 24")
    )
    if read(thunk, 10) != expected or int.from_bytes(entry[7:9], "little") != headers[0].address:
        raise CartridgeReadError("trainer text thunk or default header differs")
    return headers[0].address


def bind_scripted_trainer_dialogue(
    rom: bytes,
    reader: TrainerDialogueReader,
    target: TrainerFundingCandidate,
    initial: RawGameState,
    *,
    final_event_flag: int,
) -> Callable[[], None]:
    """Return an explicit validator; creation never sends or authorizes input."""
    verify_rom_bytes(rom)
    header = _qualified_header(rom, target)
    if type(final_event_flag) is not int or not 0 <= final_event_flag < 2560:
        raise ValueError("trainer final event must be a supported event bit")

    def validate() -> None:
        raw = reader.read()
        pending = reader.read_pending_trainer_battle_identity()
        if pending is not None and pending != (
            target.trainer.trainer_class,
            target.trainer.trainer_set,
        ):
            raise CartridgeReadError("automatic text armed another trainer")
        readiness = reader.read_input_readiness()
        if (
            raw.battle_state != 0
            or raw.map_id != target.trainer.map_id
            or (raw.player_y, raw.player_x) != target.approach.terminal_at
            or reader.read_player_facing() != target.interaction_facing.value
            or not reader.read_bottom_dialogue_box_visible()
            or reader.read_trainer_dialogue_context() != (header, target.trainer.sprite_index)
            or readiness.joy_ignore
            or readiness.simulated_joypad_index
            or readiness.npc_movement_script_table
            or raw.event_flags is None
            or event_flag_is_set(raw.event_flags, target.trainer.event_flag)
            or event_flag_is_set(raw.event_flags, final_event_flag)
            or raw.bag_items != initial.bag_items
            or raw.player_money != initial.player_money
            or raw.party_species_ids != initial.party_species_ids
            or raw.party_hp != initial.party_hp
            or raw.party_count != initial.party_count
            or raw.party_hp is None
            or any(hp <= 0 for hp in raw.party_hp)
        ):
            raise CartridgeReadError("automatic trainer dialogue context changed")

    return validate


def retained_scripted_trainer_candidate(
    rom: bytes,
    reader: PokemonRedStateReader,
    *,
    map_id: int,
    trainer_event_flag: int,
    final_event_flag: int,
) -> TrainerFundingCandidate:
    """Bind an observed introduction, never replay its movement or start a goal.

    The recovery driver separately authenticates exact failed-state provenance.
    This adapter only qualifies the current cartridge/mechanical boundary.
    """
    verify_rom_bytes(rom)
    raw = reader.read()
    if (
        raw.map_id != map_id
        or raw.battle_state != 0
        or raw.player_y is None
        or raw.player_x is None
    ):
        raise CartridgeReadError("retained trainer text requires its declared field map")
    at = (raw.player_y, raw.player_x)
    facing = TrainerFacing(reader.read_player_facing())
    dy, dx = facing.delta
    zones = trainer_sight_zones(
        trainer_headers(rom, {map_id}, full_event_offsets=True),
        map_object_events(rom, {map_id}),
        raw,
        reader.read_current_map_objects(),
    )
    matches = [
        z
        for z in zones
        if z.visible
        and not z.defeated
        and z.event_flag == trainer_event_flag
        and z.at == (at[0] + dy, at[1] + dx)
    ]
    if len(matches) != 1:
        raise CartridgeReadError("retained trainer text lacks a unique adjacent target")
    trainer = matches[0]
    target = TrainerFundingCandidate(
        trainer,
        trainer_party_quote(
            rom,
            trainer.trainer_class,
            trainer.trainer_set,
            allow_final_class=trainer.trainer_class == 247,
        ),
        RoutePlan(MacroPath((map_id,), ()), at, None, (), None, at, None),
        facing,
    )
    bind_scripted_trainer_dialogue(rom, reader, target, raw, final_event_flag=final_event_flag)()
    return target
