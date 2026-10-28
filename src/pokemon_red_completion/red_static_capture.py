"""Cartridge-bound one-off encounter observation, not a route or actor.

The event is decoded through the object's text thunk. Trainer header byte zero
is an event offset, NOT necessarily the object's index (Articuno is the trap).
No inputs, state edits, inferred visibility or species-specific movement.
"""

from __future__ import annotations

from dataclasses import dataclass

from .gen1_acquisition import STATIC_ENCOUNTER_SPRITES
from .gen1_cartridge import CartridgeReadError, bank_offset, internal_to_dex
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS
from .gen1_trainer_sight import EVENT_FLAGS_END, EVENT_FLAGS_START
from .gen1_traversal import MapObjectEvent, map_object_events
from .observation import PokemonRedStateReader, event_flag_is_set
from .rom import verify_rom_bytes


@dataclass(frozen=True, slots=True)
class RedStaticCaptureTarget:
    species_number: int
    internal_species: int
    level: int
    map_id: int
    object_index: int
    sprite_id: int
    at: tuple[int, int]
    event_flag: int

    def __post_init__(self) -> None:
        from .red_collection import red_internal_species_number

        for name, upper in (
            ("species_number", 151),
            ("internal_species", 190),
            ("level", 100),
            ("object_index", 15),
            ("sprite_id", 255),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= upper:
                raise ValueError("static capture identity is invalid")
        if red_internal_species_number(self.internal_species) != self.species_number:
            raise ValueError("static capture species representations disagree")
        if (
            type(self.map_id) is not int
            or not 0 <= self.map_id <= 247
            or type(self.event_flag) is not int
            or not 0 <= self.event_flag < 2560
            or not isinstance(self.at, tuple)
            or len(self.at) != 2
            or any(type(x) is not int or not 0 <= x <= 255 for x in self.at)
        ):
            raise ValueError("static capture map/coordinate/event is invalid")


def _decode_static_target(
    rom: bytes,
    event: MapObjectEvent,
    species_number: int,
) -> RedStaticCaptureTarget:
    bank = rom[MAP_HEADER_BANKS + event.map_id]

    def pointer(at: int) -> int:
        if at < 0 or at + 2 > len(rom):
            raise CartridgeReadError("static capture pointer is truncated")
        value = int.from_bytes(rom[at : at + 2], "little")
        if not 0x4000 <= value < 0x8000:
            raise CartridgeReadError("static capture pointer leaves its bank")
        return bank_offset(bank, value)

    def read(at: int, length: int) -> bytes:
        if not bank * 0x4000 <= at < at + length <= min(len(rom), (bank + 1) * 0x4000):
            raise CartridgeReadError("static capture span leaves its bank")
        return rom[at : at + length]

    if (
        not event.is_trainer
        or event.sprite_id not in STATIC_ENCOUNTER_SPRITES
        or event.trainer_class is None
        or event.trainer_set is None
        or not 1 <= event.trainer_set <= 100
    ):
        raise CartridgeReadError("object is not a supported static capture")
    header = pointer(MAP_HEADER_POINTERS + event.map_id * 2)
    read(header, 9)
    texts = pointer(header + 5)
    text_id = event.text_id & 0x3F
    if not text_id:
        raise CartridgeReadError("static capture object has no text")
    read(texts, text_id * 2)
    thunk = pointer(texts + (text_id - 1) * 2)
    if read(thunk, 2) != b"\x08\x21":
        raise CartridgeReadError("static capture text lacks its header load")
    address = pointer(thunk + 2)
    data = read(address, 12)
    event_address = int.from_bytes(data[2:4], "little")
    if (
        data[0] > 15
        or data[1] != 0
        or not EVENT_FLAGS_START <= event_address < EVENT_FLAGS_END
        or any(
            not 0x4000 <= int.from_bytes(data[i : i + 2], "little") < 0x8000
            for i in range(4, 12, 2)
        )
    ):
        raise CartridgeReadError("static capture header is invalid")
    flag = (event_address - EVENT_FLAGS_START) * 8 + data[0]
    if flag >= (EVENT_FLAGS_END - EVENT_FLAGS_START) * 8:
        raise CartridgeReadError("static capture event leaves observed flags")
    return RedStaticCaptureTarget(
        species_number,
        event.trainer_class,
        event.trainer_set,
        event.map_id,
        event.object_index,
        event.sprite_id,
        event.at,
        flag,
    )


def red_static_capture_targets(rom: bytes) -> tuple[RedStaticCaptureTarget, ...]:
    """Decode the four supported unique targets under the pinned revision gate."""
    verify_rom_bytes(rom)
    dex = internal_to_dex(rom)
    # Scope qualification, not policy preferences. Other static encounters need
    # their own access/outcome qualification before broadening this adapter.
    required = frozenset({144, 145, 146, 150})
    events = map_object_events(rom, {83, 162, 194, 227})
    targets = tuple(
        _decode_static_target(rom, event, dex[event.trainer_class])
        for event in events
        if event.is_trainer
        and event.trainer_class is not None
        and dex.get(event.trainer_class) in required
    )
    if len(targets) != 4 or {t.species_number for t in targets} != required:
        raise CartridgeReadError("static capture target set differs")
    return targets


@dataclass(frozen=True, slots=True)
class StaticCaptureAvailability:
    registered: bool
    consumed: bool
    present_here: bool
    ready_to_interact: bool


def observe_static_capture(
    reader: PokemonRedStateReader,
    target: RedStaticCaptureTarget,
) -> StaticCaptureAvailability:
    """Read availability, distinguishing off-map/hidden from event consumption."""
    raw = reader.read()
    if raw.event_flags is None or len(raw.event_flags) * 8 <= target.event_flag:
        raise ValueError("static capture event evidence is missing or truncated")
    registered = target.species_number in reader.read_pokedex_state().owned_species
    consumed = event_flag_is_set(raw.event_flags, target.event_flag)
    present = ready = False
    if raw.map_id == target.map_id and raw.battle_state == 0 and not consumed:
        objects = [
            o for o in reader.read_current_map_objects() if o.sprite_index == target.object_index
        ]
        if len(objects) > 1:
            raise ValueError("static capture has duplicate live objects")
        if objects:
            obj = objects[0]
            if obj.picture_id != target.sprite_id or obj.at != target.at or obj.moving:
                raise ValueError("static capture object drifted")
            present = obj.visible
            delta = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
            facing = reader.read_player_facing()
            if facing not in delta or raw.player_y is None or raw.player_x is None:
                raise ValueError("static capture facing/position is missing")
            dy, dx = delta[facing]
            ready = (
                present
                and not registered
                and reader.read_input_readiness().ready
                and not reader.read_bottom_dialogue_box_visible()
                and (raw.player_y + dy, raw.player_x + dx) == target.at
            )
    return StaticCaptureAvailability(registered, consumed, present, ready)


def require_static_capture_admission(
    reader: PokemonRedStateReader,
    target: RedStaticCaptureTarget,
    *,
    internal_species: int,
    level: int,
    ball_id: int,
    minimum_balls: int,
    allow_facing_preparation: bool = False,
) -> StaticCaptureAvailability:
    """Recheck the live interaction boundary before the executor presses A.

    This is mechanical admission only, not proof of capture policy quality.
    Ball allocation remains a caller/model decision, never an implicit fallback.
    """
    from .observation import ItemId

    if (internal_species, level) != (target.internal_species, target.level):
        raise ValueError("capture request differs from the static source")
    if (
        type(minimum_balls) is not int
        or minimum_balls <= 0
        or type(ball_id) is not int
        or ball_id
        not in {
            int(ItemId.MASTER_BALL),
            int(ItemId.ULTRA_BALL),
            int(ItemId.GREAT_BALL),
            int(ItemId.POKE_BALL),
        }
    ):
        raise ValueError("static capture ball admission is invalid")
    if type(allow_facing_preparation) is not bool:
        raise ValueError("static capture facing preparation must be explicit")
    availability = observe_static_capture(reader, target)
    raw = reader.read()
    adjacent = (
        raw.player_y is not None and raw.player_x is not None
        and abs(raw.player_y - target.at[0]) + abs(raw.player_x - target.at[1]) == 1
    )
    may_face = (
        allow_facing_preparation and adjacent and availability.present_here
        and not availability.registered and not availability.consumed
        and reader.read_input_readiness().ready and not reader.read_bottom_dialogue_box_visible()
    )
    if not availability.ready_to_interact and not may_face:
        raise ValueError("static source is not at a fresh interaction boundary")
    if (
        raw.bag_items is None
        or dict(raw.bag_items).get(ball_id, 0) < minimum_balls
        or raw.party_count is None
        or not 1 <= raw.party_count <= 6
        or raw.party_hp is None
        or len(raw.party_hp) != raw.party_count
        or not any(hp > 0 for hp in raw.party_hp)
    ):
        raise ValueError("static capture resources are not available")
    boxes = reader.read_all_box_states()
    if raw.party_count == 6 and len(boxes.boxes[boxes.current_box_index].species_ids) >= 20:
        raise ValueError("static capture has no party/current-box room")
    return availability
