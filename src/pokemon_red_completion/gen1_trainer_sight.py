"""Cartridge-derived Generation I trainer sight constraints.

Trainer objects and trainer headers are deliberately separate structures in
Red and Blue.  The object block supplies sprite identity, position and facing;
the map script points at twelve-byte headers that supply the defeated event and
engage distance.  Joining both by sprite index produces the squares an
undefeated trainer can see without mistaking the trainer for a permanent wall.

The projected lane is conservative with respect to the viewport: the engine
can engage only while the trainer is rendered, but reserving the complete
bounded lane prevents a route from making the trainer visible and entering the
lane in the same step.  Live engagement remains a typed runtime interruption.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from enum import StrEnum

from pokemon_red_completion.gen1_cartridge import MAP_ID_LIMIT, CartridgeReadError, bank_offset
from pokemon_red_completion.gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS
from pokemon_red_completion.gen1_traversal import MapObjectEvent, map_object_events
from pokemon_red_completion.observation import (
    CurrentMapObject,
    PokemonRedStateReader,
    RawGameState,
    event_flag_is_set,
)
from pokemon_red_completion.route_executor import TraversalHazard

MAP_SCRIPT_POINTER_OFFSET = 7
TRAINER_HEADER_BYTES = 12
TRAINER_SCRIPT_SCAN_BYTES = 96
EVENT_FLAGS_START = 0xD747
EVENT_FLAGS_END = 0xD886
LOAD_HL_OPCODE = 0x21
TRAINER_HEADER_SENTINEL = 0xFF


class TrainerFacing(StrEnum):
    DOWN = "down"
    UP = "up"
    LEFT = "left"
    RIGHT = "right"

    @property
    def delta(self) -> tuple[int, int]:
        return {
            TrainerFacing.DOWN: (1, 0),
            TrainerFacing.UP: (-1, 0),
            TrainerFacing.LEFT: (0, -1),
            TrainerFacing.RIGHT: (0, 1),
        }[self]


_OBJECT_FACING = {
    0xD0: TrainerFacing.DOWN,
    0xD1: TrainerFacing.UP,
    0xD2: TrainerFacing.LEFT,
    0xD3: TrainerFacing.RIGHT,
}
_LIVE_FACING = {
    0x00: TrainerFacing.DOWN,
    0x04: TrainerFacing.UP,
    0x08: TrainerFacing.LEFT,
    0x0C: TrainerFacing.RIGHT,
}


@dataclass(frozen=True, slots=True)
class TrainerHeader:
    map_id: int
    sprite_index: int
    engage_distance: int
    event_flag: int
    address: int

    def __post_init__(self) -> None:
        if not 1 <= self.sprite_index <= 15:
            raise ValueError("a trainer header needs a map sprite index")
        if not 0 <= self.engage_distance <= 15:
            raise ValueError("trainer engage distance must fit one tile nybble")
        if self.event_flag < 0:
            raise ValueError("trainer event flag cannot be negative")


@dataclass(frozen=True, slots=True)
class TrainerSightZone:
    map_id: int
    sprite_index: int
    trainer_class: int
    trainer_set: int
    at: tuple[int, int]
    facing: TrainerFacing
    engage_distance: int
    event_flag: int
    defeated: bool
    visible: bool

    @property
    def active(self) -> bool:
        return not self.defeated and self.engage_distance > 0

    @property
    def lane(self) -> tuple[tuple[int, int], ...]:
        if not self.active:
            return ()
        dy, dx = self.facing.delta
        return tuple(
            (self.at[0] + distance * dy, self.at[1] + distance * dx)
            for distance in range(1, self.engage_distance + 1)
        )


def trainer_headers(rom: bytes, map_ids: Collection[int]) -> tuple[TrainerHeader, ...]:
    """Decode map trainer headers through each map script's loaded pointer."""

    found: list[TrainerHeader] = []
    for map_id in sorted(set(map_ids)):
        # The trainer bit also marks scripted encounters such as the Cerulean
        # rival.  Those objects use a special movement/facing byte and are
        # engaged by map script, not by an ordinary line-of-sight header.
        # Only cartridge facings understood by the sight engine can therefore
        # require a trainer-header table.
        events = tuple(
            event
            for event in map_object_events(rom, {map_id})
            if event.is_trainer and event.direction_or_range in _OBJECT_FACING
        )
        if not events:
            continue
        found.extend(_trainer_headers_for_map(rom, map_id, events))
    return tuple(found)


def _trainer_headers_for_map(
    rom: bytes,
    map_id: int,
    trainer_events: tuple[MapObjectEvent, ...],
) -> tuple[TrainerHeader, ...]:
    if not 0 <= map_id < MAP_ID_LIMIT:
        raise CartridgeReadError(f"map id {map_id} is outside the header table")
    bank = rom[MAP_HEADER_BANKS + map_id]
    pointer_at = MAP_HEADER_POINTERS + 2 * map_id
    header_address = int.from_bytes(rom[pointer_at : pointer_at + 2], "little")
    if not 0x4000 <= header_address <= 0x7FFF:
        raise CartridgeReadError(f"map {map_id} has no readable header")
    header = bank_offset(bank, header_address)
    script_address = int.from_bytes(
        rom[header + MAP_SCRIPT_POINTER_OFFSET : header + MAP_SCRIPT_POINTER_OFFSET + 2],
        "little",
    )
    if not 0x4000 <= script_address <= 0x7FFF:
        raise CartridgeReadError(f"map {map_id} has no readable script")
    script = bank_offset(bank, script_address)
    candidates: list[tuple[TrainerHeader, ...]] = []
    limit = min(len(rom) - 2, script + TRAINER_SCRIPT_SCAN_BYTES)
    for cursor in range(script, limit):
        if rom[cursor] != LOAD_HL_OPCODE:
            continue
        address = int.from_bytes(rom[cursor + 1 : cursor + 3], "little")
        if not 0x4000 <= address <= 0x7FFF:
            continue
        candidate = _decode_header_candidate(
            rom,
            bank,
            map_id,
            address,
            trainer_events,
        )
        if candidate is not None and candidate not in candidates:
            candidates.append(candidate)
    if candidates:
        longest = max(len(candidate) for candidate in candidates)
        candidates = [candidate for candidate in candidates if len(candidate) == longest]
    if len(candidates) != 1:
        raise CartridgeReadError(
            f"map {map_id} exposes {len(candidates)} validated trainer-header tables"
        )
    return candidates[0]


def _decode_header_candidate(
    rom: bytes,
    bank: int,
    map_id: int,
    address: int,
    trainer_events: tuple[MapObjectEvent, ...],
) -> tuple[TrainerHeader, ...] | None:
    start = bank_offset(bank, address)
    event_by_slot = {event.object_index: event for event in trainer_events}
    decoded: list[TrainerHeader] = []
    for ordinal in range(len(trainer_events) + 1):
        cursor = start + ordinal * TRAINER_HEADER_BYTES
        if cursor >= len(rom):
            return None
        if rom[cursor] == TRAINER_HEADER_SENTINEL:
            return tuple(decoded) if decoded else None
        if ordinal == len(trainer_events):
            return None
        sprite_index = rom[cursor]
        event = event_by_slot.get(sprite_index)
        distance_byte = rom[cursor + 1]
        event_address = int.from_bytes(rom[cursor + 2 : cursor + 4], "little")
        text_pointers = tuple(
            int.from_bytes(rom[offset : offset + 2], "little")
            for offset in range(cursor + 4, cursor + TRAINER_HEADER_BYTES, 2)
        )
        if (
            event is None
            or (decoded and sprite_index != decoded[-1].sprite_index + 1)
            or distance_byte & 0x0F
            or not EVENT_FLAGS_START <= event_address < EVENT_FLAGS_END
            or any(not 0x4000 <= pointer <= 0x7FFF for pointer in text_pointers)
        ):
            return None
        event_flag = (event_address - EVENT_FLAGS_START) * 8 + sprite_index % 8
        decoded.append(
            TrainerHeader(
                map_id=map_id,
                sprite_index=sprite_index,
                engage_distance=distance_byte >> 4,
                event_flag=event_flag,
                address=address + ordinal * TRAINER_HEADER_BYTES,
            )
        )
    return None


def trainer_sight_zones(
    headers: Collection[TrainerHeader],
    events: Collection[MapObjectEvent],
    raw: RawGameState,
    current_objects: Collection[CurrentMapObject],
) -> tuple[TrainerSightZone, ...]:
    """Join cartridge identities to live coordinates, facing and event state."""

    if raw.map_id is None:
        return ()
    event_by_slot = {
        event.object_index: event
        for event in events
        if event.map_id == raw.map_id and event.is_trainer
    }
    current_by_slot = {item.sprite_index: item for item in current_objects}
    zones: list[TrainerSightZone] = []
    for header in headers:
        if header.map_id != raw.map_id:
            continue
        event = event_by_slot.get(header.sprite_index)
        current = current_by_slot.get(header.sprite_index)
        if (
            event is None
            or current is None
            or event.trainer_class is None
            or event.trainer_set is None
        ):
            continue
        # Off-screen slots retain a map coordinate but can expose a stale or
        # default facing byte.  The cartridge object's facing remains the
        # authority until the engine renders the trainer; only then can live
        # state truthfully report a changed direction.
        facing = _LIVE_FACING.get(current.facing_direction) if current.visible else None
        if facing is None:
            facing = _OBJECT_FACING.get(event.direction_or_range)
        if facing is None:
            raise CartridgeReadError(
                f"trainer sprite {header.sprite_index} has unsupported facing state"
            )
        zones.append(
            TrainerSightZone(
                map_id=raw.map_id,
                sprite_index=header.sprite_index,
                trainer_class=event.trainer_class,
                trainer_set=event.trainer_set,
                at=current.at,
                facing=facing,
                engage_distance=header.engage_distance,
                event_flag=header.event_flag,
                defeated=event_flag_is_set(raw.event_flags, header.event_flag),
                visible=current.visible,
            )
        )
    return tuple(zones)


@dataclass(slots=True)
class Gen1TrainerSightProjector:
    """Project active trainer lanes into the game-neutral route snapshot."""

    rom: bytes
    reader: PokemonRedStateReader
    _events: dict[int, tuple[MapObjectEvent, ...]] = field(default_factory=dict, init=False)
    _headers: dict[int, tuple[TrainerHeader, ...]] = field(default_factory=dict, init=False)

    def observe_hazards(self, raw: RawGameState) -> tuple[TraversalHazard, ...]:
        if raw.map_id is None or raw.battle_state != 0:
            return ()
        if raw.map_id not in self._events:
            self._events[raw.map_id] = map_object_events(self.rom, {raw.map_id})
            self._headers[raw.map_id] = trainer_headers(self.rom, {raw.map_id})
        events = self._events[raw.map_id]
        headers = self._headers[raw.map_id]
        zones = trainer_sight_zones(
            headers,
            events,
            raw,
            self.reader.read_current_map_objects(),
        )
        return tuple(
            TraversalHazard(at=at, kind="trainer_sight")
            for zone in zones
            for at in zone.lane
        )
