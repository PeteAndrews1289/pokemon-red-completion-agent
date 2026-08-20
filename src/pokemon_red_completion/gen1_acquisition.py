"""Scripted Generation I acquisition routes decoded from the cartridge.

Grass, water and fishing are not the whole Pokédex.  A cartridge also yields
Pokémon through one-of choices, gifts, fossil restoration, Game Corner prizes
and fixed encounters.  Those routes are especially important to a transferable
teacher: treating them as names in a Red-only catalog would make the next title
another transcription project.

This module keeps the choices visible.  Three starters are individually
obtainable from a cartridge, but only one is available in one save; the Fighting
Dojo and the two Mt. Moon fossils have the same shape.  Game Corner prizes are
repeatable.  Gifts and fixed encounters are not.  A collection planner can
therefore ask either the existential question ("can this cartridge ever yield
species X?") or the resource question ("can this save still yield it?") without
silently confusing the two.

Offsets below were located against the pinned pret/pokered source revision by
following the instructions that consume each table.  Every reader validates the
surrounding opcodes, terminators, counts and cross-table identities.  A moved or
different structure is refused rather than decoded as plausible data.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.gen1_cartridge import (
    MAP_ID_LIMIT,
    MAXIMUM_LEVEL,
    CartridgeReadError,
    bank_offset,
    internal_to_dex,
)
from pokemon_red_completion.gen1_maps import (
    CONNECTION_FLAG_LIMIT,
    CONNECTION_FLAGS_OFFSET,
    CONNECTION_STRUCT_BYTES,
    MAP_HEADER_BANKS,
    MAP_HEADER_POINTERS,
    WARP_COUNT_LIMIT,
    read_map_graph,
)

GAME_CORNER_BANK = 20
GAME_CORNER_POINTER_TABLE = 0x52843
GAME_CORNER_MENU_COUNT = 2
GAME_CORNER_ENTRIES_PER_MENU = 3
GAME_CORNER_LEVEL_POINTER_INSTRUCTION = 0x5297B
GAME_CORNER_PRIZE_COUNT = 6

STARTER_SCRIPT = 0x1D103
STARTER_SCRIPT_BYTES = 49
STARTER_LEVEL = 5

DIRECT_GIFT_SCRIPTS = (0x1DD47, 0x51DAB)
DIRECT_GIFT_COUNT = 2

DOJO_GIFT_SCRIPTS = (0x5CF16, 0x5CF5E)
DOJO_LEVEL = 30

FOSSIL_CHOICE_SCRIPT = 0x6105B
FOSSIL_LEVEL = 30

TEXT_TERMINATOR = 0x50
LOAD_BC_IMMEDIATE = 0x01
LOAD_A_IMMEDIATE = 0x3E
LOAD_B_IMMEDIATE = 0x06
LOAD_C_IMMEDIATE = 0x0E
LOAD_HL_IMMEDIATE = 0x21
CALL = 0xCD
STORE_A_ABSOLUTE = 0xEA
LOAD_A_ABSOLUTE = 0xFA
COPY_A_TO_B = 0x47
COMPARE_IMMEDIATE = 0xFE
JUMP_RELATIVE_IF_ZERO = 0x28

OBJECT_TRAINER_FLAG = 0x40
OBJECT_ITEM_FLAG = 0x80
OBJECT_BASE_BYTES = 6
OBJECT_TRAINER_EXTRA_BYTES = 2
OBJECT_ITEM_EXTRA_BYTES = 1
BG_EVENT_BYTES = 3
WARP_EVENT_BYTES = 4
OBJECT_COUNT_LIMIT = 32
BG_EVENT_COUNT_LIMIT = 32

# Pokémon-shaped overworld sprites that also carry the trainer flag are fixed
# encounters.  Human trainer objects carry the same flag but never these
# sprites.  The supported cartridges contain exactly the twelve encounters
# asserted below; plain decorative Pokémon sprites do not carry the flag.
MONSTER_SPRITE = 0x05
BIRD_SPRITE = 0x09
POKE_BALL_SPRITE = 0x3D
SNORLAX_SPRITE = 0x43
STATIC_ENCOUNTER_SPRITES = frozenset({MONSTER_SPRITE, BIRD_SPRITE, POKE_BALL_SPRITE})

# Snorlax is exceptional: its object has no trainer payload.  The map script
# writes species and level directly into battle RAM.  The addresses are decoded
# from the first matching instruction sequence and must agree in both copies.
SCRIPTED_BATTLE_BYTES = 10
SNORLAX_INTERNAL_INDEX = 0x84
SNORLAX_EXPECTED_LEVEL = 30
SNORLAX_MAP_IDS = frozenset({0x17, 0x1B})

EXPECTED_OBJECT_STATIC_COUNTS = {
    100: 6,  # Voltorb disguised as item balls
    101: 2,  # Electrode disguised as item balls
    144: 1,
    145: 1,
    146: 1,
    150: 1,
}


class AcquisitionSource(StrEnum):
    """How a scripted route yields a Pokémon."""

    STARTER = "starter"
    GIFT = "gift"
    DOJO_GIFT = "dojo_gift"
    FOSSIL = "fossil"
    GAME_CORNER = "game_corner"
    STATIC = "static"


@dataclass(frozen=True, slots=True)
class ScriptedAcquisition:
    """One direct Pokémon source decoded from a cartridge."""

    species: int
    level: int
    source: AcquisitionSource
    choice_group: str | None = None
    repeatable: bool = False
    cost: int | None = None
    map_id: int | None = None
    at: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.species <= 151:
            raise ValueError("scripted acquisition species must be a Pokédex number")
        if not 1 <= self.level <= MAXIMUM_LEVEL:
            raise ValueError("scripted acquisition level must be between 1 and 100")
        if self.cost is not None and self.cost <= 0:
            raise ValueError("scripted acquisition cost must be positive")
        if (self.map_id is None) != (self.at is None):
            raise ValueError("a mapped acquisition needs both map id and coordinate")


@dataclass(frozen=True, slots=True)
class MapObject:
    """One variable-width object record from a map's object block."""

    map_id: int
    sprite: int
    y: int
    x: int
    movement: int
    facing_or_range: int
    text_and_kind: int
    extra: tuple[int, ...] = ()

    @property
    def is_trainer(self) -> bool:
        return bool(self.text_and_kind & OBJECT_TRAINER_FLAG)

    @property
    def is_item(self) -> bool:
        return bool(self.text_and_kind & OBJECT_ITEM_FLAG)


def _bcd2(raw: bytes) -> int:
    """Decode the two packed-decimal bytes used for Game Corner prices."""

    if len(raw) != 2:
        raise CartridgeReadError("a Game Corner price is not two bytes")
    digits: list[int] = []
    for value in raw:
        high, low = value >> 4, value & 0x0F
        if high > 9 or low > 9:
            raise CartridgeReadError("a Game Corner price is not packed decimal")
        digits.extend((high, low))
    return 1000 * digits[0] + 100 * digits[1] + 10 * digits[2] + digits[3]


def _decode_game_corner_tables(
    rom: bytes,
    *,
    entry_offsets: Sequence[int],
    cost_offsets: Sequence[int],
    levels_offset: int,
    dex: Mapping[int, int],
) -> tuple[ScriptedAcquisition, ...]:
    """Decode prize tables; offsets are injectable for an independent fixture."""

    if len(entry_offsets) != GAME_CORNER_MENU_COUNT or len(cost_offsets) != len(
        entry_offsets
    ):
        raise CartridgeReadError("the Game Corner does not name two Pokémon menus")

    offered: list[tuple[int, int]] = []
    for entries_at, costs_at in zip(entry_offsets, cost_offsets, strict=True):
        species = tuple(
            rom[entries_at + index] for index in range(GAME_CORNER_ENTRIES_PER_MENU)
        )
        if rom[entries_at + GAME_CORNER_ENTRIES_PER_MENU] != TEXT_TERMINATOR:
            raise CartridgeReadError("a Game Corner Pokémon menu does not end after three prizes")
        if rom[costs_at + 2 * GAME_CORNER_ENTRIES_PER_MENU] != TEXT_TERMINATOR:
            raise CartridgeReadError("a Game Corner price menu does not end after three prices")
        offered.extend(
            (internal, _bcd2(rom[costs_at + 2 * index : costs_at + 2 * index + 2]))
            for index, internal in enumerate(species)
        )

    if len(offered) != GAME_CORNER_PRIZE_COUNT or len({item[0] for item in offered}) != len(
        offered
    ):
        raise CartridgeReadError("the Game Corner Pokémon prize list is incomplete or duplicated")
    if any(internal not in dex for internal, _ in offered):
        raise CartridgeReadError("the Game Corner offers an invalid internal species index")

    levels: dict[int, int] = {}
    for index in range(GAME_CORNER_PRIZE_COUNT):
        internal = rom[levels_offset + 2 * index]
        level = rom[levels_offset + 2 * index + 1]
        if internal in levels:
            raise CartridgeReadError("the Game Corner level dictionary repeats a species")
        if internal not in dex or not 1 <= level <= MAXIMUM_LEVEL:
            raise CartridgeReadError("the Game Corner level dictionary contains invalid data")
        levels[internal] = level
    if set(levels) != {internal for internal, _ in offered}:
        raise CartridgeReadError(
            "the Game Corner menus and level dictionary name different species"
        )

    return tuple(
        ScriptedAcquisition(
            species=dex[internal],
            level=levels[internal],
            source=AcquisitionSource.GAME_CORNER,
            repeatable=True,
            cost=cost,
        )
        for internal, cost in offered
    )


def game_corner_prizes(rom: bytes) -> tuple[ScriptedAcquisition, ...]:
    """All six repeatable Pokémon prizes, including cartridge-specific prices."""

    dex = internal_to_dex(rom)
    entry_offsets: list[int] = []
    cost_offsets: list[int] = []
    for menu in range(GAME_CORNER_MENU_COUNT):
        at = GAME_CORNER_POINTER_TABLE + 4 * menu
        entries_address = int.from_bytes(rom[at : at + 2], "little")
        costs_address = int.from_bytes(rom[at + 2 : at + 4], "little")
        if not 0x4000 <= entries_address <= 0x7FFF or not 0x4000 <= costs_address <= 0x7FFF:
            raise CartridgeReadError("a Game Corner menu pointer is outside its bank")
        entry_offsets.append(bank_offset(GAME_CORNER_BANK, entries_address))
        cost_offsets.append(bank_offset(GAME_CORNER_BANK, costs_address))

    at = GAME_CORNER_LEVEL_POINTER_INSTRUCTION
    if rom[at] != LOAD_HL_IMMEDIATE:
        raise CartridgeReadError("the Game Corner level dictionary is no longer loaded here")
    level_address = int.from_bytes(rom[at + 1 : at + 3], "little")
    if not 0x4000 <= level_address <= 0x7FFF:
        raise CartridgeReadError("the Game Corner level dictionary points outside its bank")
    return _decode_game_corner_tables(
        rom,
        entry_offsets=entry_offsets,
        cost_offsets=cost_offsets,
        levels_offset=bank_offset(GAME_CORNER_BANK, level_address),
        dex=dex,
    )


def _decode_starter_script(
    block: bytes, dex: Mapping[int, int]
) -> tuple[ScriptedAcquisition, ...]:
    """Decode the three selected-species immediates in Oak's ball scripts."""

    # Each arm first stores the rival's counter-pick, then the rival's ball
    # object, then loads the species the player's ball yields.  The offsets are
    # deliberately asserted rather than merely indexed: shifting an arm must
    # fail instead of returning three unrelated bytes.
    expected_opcodes = {
        0: LOAD_A_IMMEDIATE,
        2: STORE_A_ABSOLUTE,
        5: LOAD_A_IMMEDIATE,
        7: STORE_A_ABSOLUTE,
        10: LOAD_A_IMMEDIATE,
        12: LOAD_B_IMMEDIATE,
        17: LOAD_A_IMMEDIATE,
        19: STORE_A_ABSOLUTE,
        22: LOAD_A_IMMEDIATE,
        24: STORE_A_ABSOLUTE,
        27: LOAD_A_IMMEDIATE,
        29: LOAD_B_IMMEDIATE,
        34: LOAD_A_IMMEDIATE,
        36: STORE_A_ABSOLUTE,
        39: LOAD_A_IMMEDIATE,
        41: STORE_A_ABSOLUTE,
        44: LOAD_A_IMMEDIATE,
        46: LOAD_B_IMMEDIATE,
        48: STORE_A_ABSOLUTE,
    }
    if len(block) < STARTER_SCRIPT_BYTES or any(
        block[offset] != opcode for offset, opcode in expected_opcodes.items()
    ):
        raise CartridgeReadError("Oak's three starter arms are not where they were located")
    if block[3:5] != block[20:22] or block[3:5] != block[37:39]:
        raise CartridgeReadError("Oak's starter arms do not share one rival-species destination")
    if block[8:10] != block[25:27] or block[8:10] != block[42:44]:
        raise CartridgeReadError("Oak's starter arms do not share one rival-ball destination")

    internal = (block[11], block[28], block[45])
    if len(set(internal)) != 3 or any(species not in dex for species in internal):
        raise CartridgeReadError("Oak's starter arms do not yield three distinct species")
    return tuple(
        ScriptedAcquisition(
            species=dex[species],
            level=STARTER_LEVEL,
            source=AcquisitionSource.STARTER,
            choice_group="oak_starter",
        )
        for species in internal
    )


def starter_choices(rom: bytes) -> tuple[ScriptedAcquisition, ...]:
    """The three mutually exclusive level-five starters."""

    return _decode_starter_script(
        rom[STARTER_SCRIPT : STARTER_SCRIPT + STARTER_SCRIPT_BYTES], internal_to_dex(rom)
    )


def _decode_direct_gift(
    block: bytes, dex: Mapping[int, int]
) -> tuple[int, int, int]:
    """Return ``(dex species, level, GivePokemon target)`` from ``lb bc``."""

    if len(block) < 6 or block[0] != LOAD_BC_IMMEDIATE or block[3] != CALL:
        raise CartridgeReadError("a direct gift is no longer an immediate pair followed by a call")
    level, internal = block[1], block[2]
    if internal not in dex or not 1 <= level <= MAXIMUM_LEVEL:
        raise CartridgeReadError("a direct gift contains an invalid species or level")
    return dex[internal], level, int.from_bytes(block[4:6], "little")


def direct_gifts(rom: bytes) -> tuple[ScriptedAcquisition, ...]:
    """Eevee and Lapras, read from their ``GivePokemon`` call sites."""

    dex = internal_to_dex(rom)
    decoded = [_decode_direct_gift(rom[at : at + 6], dex) for at in DIRECT_GIFT_SCRIPTS]
    if len(decoded) != DIRECT_GIFT_COUNT or len({species for species, _, _ in decoded}) != len(
        decoded
    ):
        raise CartridgeReadError("the direct gift sites are incomplete or duplicated")
    if len({target for _, _, target in decoded}) != 1:
        raise CartridgeReadError("the direct gifts no longer call the same GivePokemon routine")
    return tuple(
        ScriptedAcquisition(species=species, level=level, source=AcquisitionSource.GIFT)
        for species, level, _ in decoded
    )


def _decode_dojo_gift(
    block: bytes, dex: Mapping[int, int]
) -> tuple[int, int, int, int]:
    """Return species, level and the two shared call targets from one dojo arm."""

    if len(block) < 29 or block[0] != LOAD_A_IMMEDIATE or block[2] != CALL:
        raise CartridgeReadError("a Fighting Dojo gift no longer begins by displaying one species")
    suffix = block[20:29]
    if (
        suffix[0] != LOAD_A_ABSOLUTE
        or suffix[3] != COPY_A_TO_B
        or suffix[4] != LOAD_C_IMMEDIATE
        or suffix[6] != CALL
    ):
        raise CartridgeReadError("a Fighting Dojo gift no longer gives the displayed species")
    internal, level = block[1], suffix[5]
    if internal not in dex or not 1 <= level <= MAXIMUM_LEVEL:
        raise CartridgeReadError("a Fighting Dojo gift contains an invalid species or level")
    return (
        dex[internal],
        level,
        int.from_bytes(block[3:5], "little"),
        int.from_bytes(suffix[7:9], "little"),
    )


def dojo_choices(rom: bytes) -> tuple[ScriptedAcquisition, ...]:
    """The two mutually exclusive Fighting Dojo gifts."""

    dex = internal_to_dex(rom)
    decoded = [_decode_dojo_gift(rom[at : at + 29], dex) for at in DOJO_GIFT_SCRIPTS]
    if len({species for species, _, _, _ in decoded}) != 2:
        raise CartridgeReadError("the Fighting Dojo does not offer two distinct species")
    if {level for _, level, _, _ in decoded} != {DOJO_LEVEL}:
        raise CartridgeReadError("the Fighting Dojo gift levels disagree")
    if len({display for _, _, display, _ in decoded}) != 1 or len(
        {give for _, _, _, give in decoded}
    ) != 1:
        raise CartridgeReadError("the two Fighting Dojo arms do not share their routines")
    return tuple(
        ScriptedAcquisition(
            species=species,
            level=level,
            source=AcquisitionSource.DOJO_GIFT,
            choice_group="fighting_dojo",
        )
        for species, level, _, _ in decoded
    )


def _decode_fossil_choices(
    block: bytes, dex: Mapping[int, int]
) -> tuple[tuple[int, int], tuple[int, int], tuple[None, int]]:
    """Decode ``(item, species)`` branches; amber is the unqualified fallback."""

    expected = {
        0: COMPARE_IMMEDIATE,
        2: JUMP_RELATIVE_IF_ZERO,
        4: COMPARE_IMMEDIATE,
        6: JUMP_RELATIVE_IF_ZERO,
        8: LOAD_B_IMMEDIATE,
        12: LOAD_B_IMMEDIATE,
        16: LOAD_B_IMMEDIATE,
    }
    if len(block) < 18 or any(block[offset] != opcode for offset, opcode in expected.items()):
        raise CartridgeReadError("the fossil selection branches are not where they were located")
    dome_item, helix_item = block[1], block[5]
    aerodactyl, omanyte, kabuto = block[9], block[13], block[17]
    internal = (aerodactyl, omanyte, kabuto)
    if dome_item == helix_item or len(set(internal)) != 3 or any(
        species not in dex for species in internal
    ):
        raise CartridgeReadError("the fossil selection branches are incomplete or invalid")
    return (dome_item, dex[kabuto]), (helix_item, dex[omanyte]), (None, dex[aerodactyl])


def fossil_choices(rom: bytes) -> tuple[ScriptedAcquisition, ...]:
    """Kabuto/Omanyte's one-of choice plus independently obtainable Aerodactyl."""

    dex = internal_to_dex(rom)
    choice_block = rom[FOSSIL_CHOICE_SCRIPT : FOSSIL_CHOICE_SCRIPT + 25]
    decoded = _decode_fossil_choices(choice_block[:18], dex)
    if (
        len(choice_block) < 25
        or choice_block[18] != STORE_A_ABSOLUTE
        or choice_block[21] != 0x78  # ld a, b
        or choice_block[22] != STORE_A_ABSOLUTE
    ):
        raise CartridgeReadError("the fossil selection no longer stores its chosen species")
    fossil_species_address = choice_block[23:25]
    level_blocks = [
        rom[at : at + 9]
        for at in range(len(rom) - 8)
        if rom[at] == LOAD_A_ABSOLUTE
        and rom[at + 1 : at + 3] == fossil_species_address
        and rom[at + 3] == COPY_A_TO_B
        and rom[at + 4] == LOAD_C_IMMEDIATE
        and rom[at + 6] == CALL
    ]
    if len(level_blocks) != 1:
        raise CartridgeReadError(
            f"the cartridge contains {len(level_blocks)} fossil restoration call sites, not 1"
        )
    level_block = level_blocks[0]
    if (
        len(level_block) < 9
        or level_block[0] != LOAD_A_ABSOLUTE
        or level_block[3] != COPY_A_TO_B
        or level_block[4] != LOAD_C_IMMEDIATE
        or level_block[6] != CALL
    ):
        raise CartridgeReadError("the fossil restoration level is not where it was located")
    level = level_block[5]
    if level != FOSSIL_LEVEL:
        raise CartridgeReadError(
            f"the fossil lab now restores at level {level}, not {FOSSIL_LEVEL}"
        )
    return tuple(
        ScriptedAcquisition(
            species=species,
            level=level,
            source=AcquisitionSource.FOSSIL,
            choice_group="mt_moon_fossil" if item is not None else None,
        )
        for item, species in decoded
    )


def _decode_object_block(rom: bytes, *, at: int, map_id: int) -> tuple[MapObject, ...]:
    """Decode a variable-stride object block; ``at`` is injectable for fixtures."""

    if at < 0 or at + 2 > len(rom):
        raise CartridgeReadError("a map object block starts outside the cartridge")
    warp_count = rom[at + 1]
    if warp_count > WARP_COUNT_LIMIT:
        raise CartridgeReadError("a map object block has too many warps")
    cursor = at + 2 + WARP_EVENT_BYTES * warp_count
    if cursor >= len(rom):
        raise CartridgeReadError("a map object block ends inside its warp list")
    bg_count = rom[cursor]
    if bg_count > BG_EVENT_COUNT_LIMIT:
        raise CartridgeReadError("a map object block has too many background events")
    cursor += 1 + BG_EVENT_BYTES * bg_count
    if cursor >= len(rom):
        raise CartridgeReadError("a map object block ends inside its background-event list")
    object_count = rom[cursor]
    if object_count > OBJECT_COUNT_LIMIT:
        raise CartridgeReadError("a map object block has too many objects")
    cursor += 1

    found: list[MapObject] = []
    for _ in range(object_count):
        if cursor + OBJECT_BASE_BYTES > len(rom):
            raise CartridgeReadError("a map object block ends inside an object")
        text_and_kind = rom[cursor + 5]
        if text_and_kind & OBJECT_TRAINER_FLAG:
            extra_bytes = OBJECT_TRAINER_EXTRA_BYTES
        elif text_and_kind & OBJECT_ITEM_FLAG:
            extra_bytes = OBJECT_ITEM_EXTRA_BYTES
        else:
            extra_bytes = 0
        if cursor + OBJECT_BASE_BYTES + extra_bytes > len(rom):
            raise CartridgeReadError("a map object block ends inside an object's payload")
        found.append(
            MapObject(
                map_id=map_id,
                sprite=rom[cursor],
                y=rom[cursor + 1] - 4,
                x=rom[cursor + 2] - 4,
                movement=rom[cursor + 3],
                facing_or_range=rom[cursor + 4],
                text_and_kind=text_and_kind,
                extra=tuple(
                    rom[cursor + OBJECT_BASE_BYTES : cursor + OBJECT_BASE_BYTES + extra_bytes]
                ),
            )
        )
        cursor += OBJECT_BASE_BYTES + extra_bytes
    return tuple(found)


def _map_object_offset(rom: bytes, map_id: int) -> int:
    bank = rom[MAP_HEADER_BANKS + map_id]
    address = int.from_bytes(
        rom[MAP_HEADER_POINTERS + 2 * map_id : MAP_HEADER_POINTERS + 2 * map_id + 2],
        "little",
    )
    if not 0x4000 <= address <= 0x7FFF:
        raise CartridgeReadError(f"map {map_id} has no valid header pointer")
    header = bank_offset(bank, address)
    flags = rom[header + CONNECTION_FLAGS_OFFSET]
    if flags > CONNECTION_FLAG_LIMIT:
        raise CartridgeReadError(f"map {map_id} has invalid connection flags")
    cursor = header + CONNECTION_FLAGS_OFFSET + 1
    cursor += CONNECTION_STRUCT_BYTES * flags.bit_count()
    objects = int.from_bytes(rom[cursor : cursor + 2], "little")
    if not 0x4000 <= objects <= 0x7FFF:
        raise CartridgeReadError(f"map {map_id} has no valid object pointer")
    return bank_offset(bank, objects)


def map_objects(rom: bytes) -> dict[int, tuple[MapObject, ...]]:
    """Every object on every map reachable from Pallet Town."""

    graph = read_map_graph(rom)
    found = {
        map_id: _decode_object_block(rom, at=_map_object_offset(rom, map_id), map_id=map_id)
        for map_id in graph
    }
    if not found or len(found) > MAP_ID_LIMIT:
        raise CartridgeReadError("the cartridge yielded no credible map object blocks")
    return found


def _scripted_snorlax_pairs(rom: bytes) -> tuple[tuple[int, int], ...]:
    """Find direct ``opponent, level`` writes used by the two Snorlax scripts."""

    found: list[tuple[int, int, bytes, bytes]] = []
    for at in range(len(rom) - SCRIPTED_BATTLE_BYTES + 1):
        block = rom[at : at + SCRIPTED_BATTLE_BYTES]
        if (
            block[0] == LOAD_A_IMMEDIATE
            and block[1] == SNORLAX_INTERNAL_INDEX
            and block[2] == STORE_A_ABSOLUTE
            and block[5] == LOAD_A_IMMEDIATE
            and block[7] == STORE_A_ABSOLUTE
        ):
            found.append((block[1], block[6], block[3:5], block[8:10]))
    if len(found) != 2:
        raise CartridgeReadError(
            f"the cartridge contains {len(found)} Snorlax battle writes, not 2"
        )
    if len({(opponent_ram, level_ram) for _, _, opponent_ram, level_ram in found}) != 1:
        raise CartridgeReadError("the two Snorlax scripts write different battle fields")
    return tuple((internal, level) for internal, level, _, _ in found)


def static_encounters(rom: bytes) -> tuple[ScriptedAcquisition, ...]:
    """Fixed catchable encounters, including item mimics and both Snorlax."""

    dex = internal_to_dex(rom)
    objects = map_objects(rom)
    found: list[ScriptedAcquisition] = []
    snorlax_objects: list[MapObject] = []
    for entries in objects.values():
        for item in entries:
            if item.sprite == SNORLAX_SPRITE:
                snorlax_objects.append(item)
            if not item.is_trainer or item.sprite not in STATIC_ENCOUNTER_SPRITES:
                continue
            if len(item.extra) != 2:
                raise CartridgeReadError("a fixed encounter has no species/level payload")
            internal, level = item.extra
            if internal not in dex or not 1 <= level <= MAXIMUM_LEVEL:
                raise CartridgeReadError("a fixed encounter has an invalid species or level")
            found.append(
                ScriptedAcquisition(
                    species=dex[internal],
                    level=level,
                    source=AcquisitionSource.STATIC,
                    map_id=item.map_id,
                    at=(item.y, item.x),
                )
            )

    counts = Counter(item.species for item in found)
    if counts != Counter(EXPECTED_OBJECT_STATIC_COUNTS):
        raise CartridgeReadError(
            f"the object blocks contain fixed encounters {dict(sorted(counts.items()))}, not "
            f"{EXPECTED_OBJECT_STATIC_COUNTS}"
        )
    if len(snorlax_objects) != 2 or {item.map_id for item in snorlax_objects} != set(
        SNORLAX_MAP_IDS
    ):
        raise CartridgeReadError("the two Snorlax objects are missing or on the wrong maps")

    scripted = _scripted_snorlax_pairs(rom)
    if any(
        internal != SNORLAX_INTERNAL_INDEX or level != SNORLAX_EXPECTED_LEVEL
        for internal, level in scripted
    ):
        raise CartridgeReadError("the two Snorlax scripts disagree on species or level")
    for item, (_, level) in zip(
        sorted(snorlax_objects, key=lambda value: value.map_id), scripted, strict=True
    ):
        found.append(
            ScriptedAcquisition(
                species=dex[SNORLAX_INTERNAL_INDEX],
                level=level,
                source=AcquisitionSource.STATIC,
                map_id=item.map_id,
                at=(item.y, item.x),
            )
        )
    return tuple(sorted(found, key=lambda item: (item.map_id or -1, item.at or (-1, -1))))


def scripted_acquisitions(rom: bytes) -> tuple[ScriptedAcquisition, ...]:
    """Every non-wild, non-fishing, non-trade direct source parsed so far."""

    result = (
        starter_choices(rom)
        + direct_gifts(rom)
        + dojo_choices(rom)
        + fossil_choices(rom)
        + game_corner_prizes(rom)
        + static_encounters(rom)
    )
    by_source = Counter(item.source for item in result)
    expected = {
        AcquisitionSource.STARTER: 3,
        AcquisitionSource.GIFT: 2,
        AcquisitionSource.DOJO_GIFT: 2,
        AcquisitionSource.FOSSIL: 3,
        AcquisitionSource.GAME_CORNER: 6,
        AcquisitionSource.STATIC: 14,
    }
    if by_source != Counter(expected):
        rendered = {source.value: by_source[source] for source in AcquisitionSource}
        raise CartridgeReadError(f"the scripted acquisition ledger is incomplete: {rendered}")
    return result


def scripted_species(rom: bytes) -> frozenset[int]:
    """Every species a parsed scripted route directly yields."""

    return frozenset(item.species for item in scripted_acquisitions(rom))
