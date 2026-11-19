"""CANDIDATE: bounded exact-cartridge scripted-wild opposition observation.

Mechanic facts only. This neither selects a goal nor starts an encounter. Raw
phase addresses are private to the cartridge/observation adapter; public player
features receive only the existing numeric opposition descriptor. No native
qualification or campaign authority follows from decoding the cartridge.
"""

from dataclasses import dataclass
from hashlib import sha256

from .gen1_cartridge import INTERNAL_INDEX_LIMIT, MAP_ID_LIMIT, CartridgeReadError, bank_offset
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS, SCRIPT_POINTER_OFFSET
from .gen1_trainer_sight import EVENT_FLAGS_END, EVENT_FLAGS_START
from .observation import RamAddress, event_flag_is_set
from .provenance import canonical_sha256
from .rom import RomValidationError, verify_rom_bytes

# Located by following references to the script-decoded source operand and the
# existing ENEMY_LEVEL observation field. It is NOT located with a level/species
# literal. See ENGINE-GUARD-REGIONS.json: LD DE,destination; LD A,[source]; LD [DE],A.
_LEVEL_DE_BRIDGE_OFFSET = 0x3EB38


def _require(value, message):
    if not value:
        raise CartridgeReadError(message)


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


@dataclass(frozen=True)
class ScriptedWildGateScope:
    """The caller's already admitted gate; never a new strategic target."""

    map_id: int
    defeated_event: int
    trigger_at: tuple[int, int]
    required_item_id: int
    required_item_count: int = 1

    def __post_init__(self):
        if not (_integer(self.map_id, 0, MAP_ID_LIMIT - 1)
                and _integer(self.defeated_event, 0, 4095)
                and type(self.trigger_at) is tuple and len(self.trigger_at) == 2
                and all(_integer(x, 0, 254) for x in self.trigger_at)
                and _integer(self.required_item_id, 1, 255)
                and _integer(self.required_item_count, 1, 99)):
            raise ValueError("scripted wild gate scope differs")


@dataclass(frozen=True)
class ScriptedWildOpposition:
    """Semantic, unbound opponent quote; private identity is not a model feature."""

    rom_sha256: str
    layout_sha256: str
    map_id: int
    defeated_event: int
    trigger_coordinates: tuple[tuple[int, int], ...]
    species_id: int
    level: int
    region_pins: tuple[tuple[int, int, str], ...]

    def __post_init__(self):
        hashes = (self.rom_sha256, self.layout_sha256)
        if (any(type(h) is not str or len(h) != 64
                or any(c not in "0123456789abcdef" for c in h) for h in hashes)
                or not _integer(self.map_id, 0, MAP_ID_LIMIT - 1)
                or not _integer(self.defeated_event, 0, 4095)
                or not _integer(self.species_id, 1, INTERNAL_INDEX_LIMIT)
                or not _integer(self.level, 1, 100)
                or type(self.trigger_coordinates) is not tuple
                or not 1 <= len(self.trigger_coordinates) <= 16
                or any(type(at) is not tuple or len(at) != 2
                       or any(not _integer(v, 0, 254) for v in at)
                       for at in self.trigger_coordinates)
                or type(self.region_pins) is not tuple or not self.region_pins):
            raise ValueError("scripted wild opposition evidence differs")

    @property
    def opponent_levels(self):
        return (self.level,)

    def document(self):
        return dict(schema="pokemon.red.scripted-wild-opposition.v1",
                    rom_sha256=self.rom_sha256, layout_sha256=self.layout_sha256,
                    map_id=self.map_id, defeated_event=self.defeated_event,
                    trigger_coordinates=self.trigger_coordinates,
                    species_id=self.species_id, level=self.level,
                    region_pins=self.region_pins,
                    scope="decoded-current-admitted-single-wild-gate", learned=False)


@dataclass(frozen=True)
class BoundScriptedWildOpposition:
    opposition: ScriptedWildOpposition
    source_sha256: str
    binding_ref: str

    def __post_init__(self):
        if (type(self.opposition) is not ScriptedWildOpposition
                or type(self.source_sha256) is not str or len(self.source_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.source_sha256)
                or type(self.binding_ref) is not str or not self.binding_ref):
            raise ValueError("scripted wild binding witness differs")

    def document(self):
        return dict(schema="pokemon.red.bound-scripted-wild-opposition.v1",
                    source_sha256=self.source_sha256, binding_ref=self.binding_ref,
                    opposition=self.opposition.document())


@dataclass(frozen=True)
class _WildScriptLayout:
    opposition: ScriptedWildOpposition
    local_script_address: int
    current_script_address: int
    override_address: int
    override_mask: int


def _decode_layout(rom: bytes, map_id: int):
    """Bounded grammar, with no native memory or expected opponent literal."""
    _require(isinstance(rom, bytes) and _integer(map_id, 0, MAP_ID_LIMIT - 1),
             "scripted wild map/ROM differs")
    pins = []

    def read(at, count):
        _require(0 <= at <= len(rom) - count, "scripted wild ROM region unavailable")
        body = rom[at:at + count]
        pins.append((at, count, sha256(body).hexdigest()))
        return body

    def word(body, at):
        return int.from_bytes(body[at:at + 2], "little")

    bank = read(MAP_HEADER_BANKS + map_id, 1)[0]
    _require(0 < bank < len(rom) // 0x4000, "scripted wild map bank differs")

    def banked(address, count):
        _require(0x4000 <= address and address + count <= 0x8000,
                 "scripted wild bank pointer differs")
        return bank_offset(bank, address)

    header_address = word(read(MAP_HEADER_POINTERS + 2 * map_id, 2), 0)
    header = read(banked(header_address, 10), 10)
    script_address = word(header, SCRIPT_POINTER_OFFSET)
    entry = read(banked(script_address, 19), 19)
    _require(entry[0] == entry[12] == 0xCD and entry[3] == 0x21 and entry[6] == 0x11
             and entry[9] == 0xFA and entry[15] == 0xEA and entry[18] == 0xC9
             and entry[10:12] == entry[16:18], "unsupported scripted wild entry")
    local = word(entry, 10)
    _require(0xC000 <= local <= 0xDFFF, "scripted wild local phase is not work RAM")
    initial_address = word(entry, 1)
    _require(initial_address < 0x4000, "scripted wild entry helper is not fixed-bank")
    initial = read(initial_address, 13)
    _require(initial[:6] == bytes.fromhex("af 18 02 3e 01 ea")
             and initial[8:10] == bytes.fromhex("af ea") and initial[12] == 0xC9,
             "scripted wild entry helper has unsupported effects")
    initial_writes = {word(initial, 6), word(initial, 10)}
    _require(all(0xC000 <= at <= 0xDFFF for at in initial_writes),
             "scripted wild entry helper does not write only work RAM")
    dispatch_address = word(entry, 13)
    _require(dispatch_address < 0x4000, "scripted wild dispatcher is not fixed-bank")
    dispatch = read(dispatch_address, 31)
    _require(dispatch[:2] == bytes.fromhex("f5 d5") and dispatch[2] == 0xCD
             and dispatch[5:9] == bytes.fromhex("e1 f1 e5 21")
             and dispatch[11] == dispatch[13] == 0xCB
             and dispatch[15:18] == bytes.fromhex("28 03 fa")
             and dispatch[20:22] == bytes.fromhex("e1 ea") and dispatch[24] == 0xCD
             and dispatch[27] == 0xFA and dispatch[30] == 0xC9,
             "unsupported scripted wild dispatcher")
    override_address = word(dispatch, 9)
    bit = (dispatch[12] - 0x46) // 8
    current = word(dispatch, 18)
    _require(0 <= bit <= 7 and dispatch[12] == 0x46 + 8 * bit
             and dispatch[14] == 0x86 + 8 * bit
             and 0xC000 <= override_address <= 0xDFFF
             and current == word(dispatch, 22) == word(dispatch, 28)
             == int(RamAddress.CURRENT_MAP_SCRIPT), "scripted wild phase operands differ")
    save = read(word(dispatch, 3), 9)
    _require(save[0:2] == bytes.fromhex("7c ea") and save[4:6] == bytes.fromhex("7d ea")
             and save[8] == 0xC9 and word(save, 6) == word(save, 2) + 1,
             "scripted wild header helper differs")
    indexed_address = word(dispatch, 25)
    indexed = read(indexed_address, 20)
    _require(indexed[:12] == bytes.fromhex("e5 d5 c5 87 16 00 5f 19 2a 66 6f 11")
             and word(indexed, 12) == indexed_address + 16
             and indexed[14:] == bytes.fromhex("d5 e9 c1 d1 e1 c9"),
             "scripted wild indexed dispatch differs")
    table = read(banked(word(entry, 7), 2), 2)
    default = read(banked(word(table, 0), 46), 46)
    _require(default[0] == 0xFA and default[3] == 0xCB and default[5] == 0xC2
             and default[8] == 0x21 and default[11] == 0xCD and default[14] == 0xD2
             and default[17:21] == bytes.fromhex("af e0 b4 3e")
             and default[22:25] == bytes.fromhex("e0 8c cd")
             and default[27] == default[32] == default[37] == 0x3E
             and default[29] == default[34] == default[39] == default[42] == 0xEA
             and default[45] == 0xC9, "unsupported scripted wild default")
    event_bit = (default[4] - 0x47) // 8
    event_address = word(default, 1)
    _require(0 <= event_bit <= 7 and default[4] == 0x47 + 8 * event_bit
             and EVENT_FLAGS_START <= event_address < EVENT_FLAGS_END
             and word(default, 6) == word(default, 15)
             and word(default, 30) == int(RamAddress.CURRENT_OPPONENT)
             and word(default, 40) == local and word(default, 43) == current,
             "scripted wild guard/store operands differ")
    event = (event_address - EVENT_FLAGS_START) * 8 + event_bit
    species, level, level_source = default[28], default[33], word(default, 35)
    _require(1 <= species <= INTERNAL_INDEX_LIMIT and 1 <= level <= 100
             and 0xC000 <= level_source <= 0xDFFF,
             "scripted wild opponent fields differ")
    bridge = bytes([0x11]) + int(RamAddress.ENEMY_LEVEL).to_bytes(2, "little")
    bridge += bytes([0xFA]) + level_source.to_bytes(2, "little") + bytes([0x12])
    _require(read(_LEVEL_DE_BRIDGE_OFFSET, len(bridge)) == bridge,
             "scripted wild level no longer reaches observed enemy level")
    coordinate_address = word(default, 12)
    _require(coordinate_address < 0x4000, "scripted wild coordinate helper is not fixed-bank")
    coordinates_helper = read(coordinate_address, 37)
    expected_coordinates_helper = (bytes([0xFA]) + int(RamAddress.PLAYER_Y).to_bytes(2, "little")
        + bytes([0x47, 0xFA]) + int(RamAddress.PLAYER_X).to_bytes(2, "little")
        + bytes.fromhex("4f af ea") + coordinates_helper[10:12]
        + bytes.fromhex("2a fe ff 28 12 e5 21") + coordinates_helper[10:12]
        + bytes.fromhex("34 e1 b8 28 03 23 18 ef 2a b9 20 eb 37 c9 a7 c9"))
    _require(coordinates_helper == expected_coordinates_helper,
             "scripted wild coordinate helper differs")
    _require(initial_writes.isdisjoint({local, current, override_address, event_address,
                 level_source, int(RamAddress.CURRENT_OPPONENT), int(RamAddress.ENEMY_LEVEL),
                 int(RamAddress.CURRENT_MAP), int(RamAddress.IS_IN_BATTLE),
                 int(RamAddress.PLAYER_Y), int(RamAddress.PLAYER_X), word(coordinates_helper, 10)}),
             "scripted wild entry helper alters a quoted guard/phase/opponent fact")
    coord_address = word(default, 9)
    coords = []
    for index in range(17):
        y = read(banked(coord_address + 2 * index, 1), 1)[0]
        if y == 0xFF:
            break
        _require(index < 16, "scripted wild coordinate table is unbounded")
        x = read(banked(coord_address + 2 * index + 1, 1), 1)[0]
        _require(y < header[1] * 2 and x < header[2] * 2,
                 "scripted wild trigger outside map")
        coords.append((y, x))
    _require(coords and len(set(coords)) == len(coords), "scripted wild trigger inventory differs")
    fields = dict(rom_sha256=sha256(rom).hexdigest(), map_id=map_id,
                  defeated_event=event, trigger_coordinates=tuple(coords),
                  species_id=species, level=level, region_pins=tuple(pins))
    proof = ScriptedWildOpposition(layout_sha256=canonical_sha256(fields), **fields)
    return _WildScriptLayout(proof, local, current, override_address, 1 << bit)


def validate_scripted_wild_opposition(proof, rom, *, scope):
    """Refuse stale/foreign typed evidence before forwarding a known descriptor.

    This performs no native read: the field/phase adapter remains the quote owner.
    Equality includes ROM/layout hashes and every decoded region pin; a valid
    dataclass alone is not evidence that a reader's cached proof is current.
    """
    if type(proof) is not ScriptedWildOpposition or type(scope) is not ScriptedWildGateScope:
        raise ValueError("scripted wild opposition witness has no typed current scope")
    try:
        verify_rom_bytes(rom)
        current = _decode_layout(rom, scope.map_id).opposition
    except (CartridgeReadError, RomValidationError) as error:
        raise ValueError("scripted wild opposition witness has no supported current ROM") from error
    if (proof != current or proof.map_id != scope.map_id
            or proof.defeated_event != scope.defeated_event
            or scope.trigger_at not in proof.trigger_coordinates):
        raise ValueError("scripted wild opposition witness differs from current ROM/scope")


def observe_scripted_wild_opposition(rom, raw, *, scope, read_u8):
    """Called ONLY beneath PokemonRedStateReader; unsupported facts stay unknown."""
    if type(scope) is not ScriptedWildGateScope or not callable(read_u8):
        raise TypeError("scripted wild observation requires a typed scope and adapter reader")
    if getattr(raw, "map_id", None) != scope.map_id or getattr(raw, "battle_state", None) != 0:
        return None
    try:
        verify_rom_bytes(rom)
        layout = _decode_layout(rom, scope.map_id)
    except (CartridgeReadError, RomValidationError):
        return None
    proof = layout.opposition
    events, items = getattr(raw, "event_flags", None), getattr(raw, "bag_items", None)
    if (proof.defeated_event != scope.defeated_event or scope.trigger_at not in proof.trigger_coordinates
            or not isinstance(events, bytes) or len(events) * 8 <= proof.defeated_event
            or event_flag_is_set(events, proof.defeated_event) or items is None
            or dict(items).get(scope.required_item_id) != scope.required_item_count):
        return None
    local, current, override = (read_u8(address) for address in
                               (layout.local_script_address, layout.current_script_address, layout.override_address))
    if not all(_integer(value, 0, 255) for value in (local, current, override)):
        return None
    if local != 0 or current != 0 or override & layout.override_mask:
        return None
    return proof
