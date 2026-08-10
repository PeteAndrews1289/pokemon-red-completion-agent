"""Read Generation I game data out of a cartridge instead of hand-writing it.

A teacher that knows a game because somebody typed its facts into a Python file
does not transfer. Every new title costs another person-week of typing, and each
typed fact is an assertion nothing can falsify — which is how eleven version
exclusives were recorded as ten, and how a Mansion band of 30-32 outlived the
155 encounters that said 28-39.

The tables are in the cartridge. Reading them makes the same facts *derived*,
checkable, and free for the next cartridge.

**Nothing here is transcribed, and nothing is trusted.** Every structure was
located by searching a ROM for a shape this repository had already measured, and
every read re-derives those measurements and refuses to continue if they no
longer hold. A cartridge revision that moves a table fails loudly rather than
returning plausible nonsense.

How each offset was found:

``INTERNAL_TO_DEX_TABLE``
    Anchored on the four internal indices the party adapter already asserts --
    Blastoise 0x1C, Diglett 0x3B, Dugtrio 0x76, Snorlax 0x84. Exactly one table
    in the ROM satisfies all four, and all 151 indices map to valid dex numbers.

``WILD_POINTER_ARRAY``
    Diglett's Cave was measured over 29 live encounters to hold only Diglett and
    Dugtrio. Exactly one structure matches that shape. The array indexing it puts
    the cave at index 197, which is its map id, and index 165 then gives the
    Mansion at levels 28-39 -- the band measured over 164 live encounters.

``EVOLUTION_POINTER_ARRAY``
    Anchored on two facts already declared here: Diglett evolves at level 26 into
    Dugtrio, and Kadabra evolves by trade into Alakazam. Each byte pattern occurs
    exactly once in the ROM.

The fishing anchors
    Found by following code rather than by scanning for data. The Old Rod's only
    bite is not in a table at all -- it is an immediate operand -- so the search
    started from the one pair every rod shares, ``(level 5, Magikarp)``, and the
    single occurrence that reads as a ``ld bc`` immediate turned out to sit in
    bank 3 beside the wild data. The Good Rod and Super Rod tables are named by
    ``ld hl`` instructions a few bytes away.

    So these offsets point at *instructions*, and the table addresses are read
    from their operands. A revision that moves the tables but keeps the code
    still reads correctly, and one that moves the code fails on the opcode check
    rather than silently decoding whatever now lives there.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

SPECIES_COUNT = 151
INTERNAL_INDEX_LIMIT = 190
MAP_ID_LIMIT = 248
SLOTS_PER_TABLE = 10

INTERNAL_TO_DEX_TABLE = 0x41024
WILD_DATA_BANK = 3
WILD_POINTER_ARRAY = 0x0CEEB
EVOLUTION_DATA_BANK = 14
EVOLUTION_POINTER_ARRAY = 0x3B05C

#: Fishing lives in the same bank as the wild data, and is reached through
#: instructions rather than through a pointer array. Each address below is an
#: opcode; the operand that follows it names the data.
FISHING_BANK = 3
OLD_ROD_ENCOUNTER = 0x6252  # ld bc, nn -- the only bite the Old Rod has
GOOD_ROD_SLOT_COUNT = 0x6268  # cp n     -- how many slots the Good Rod rolls over
GOOD_ROD_TABLE_POINTER = 0x626C  # ld hl, nn
SUPER_ROD_TABLE_POINTER = 0x68F0  # ld hl, nn
LOAD_BC_IMMEDIATE = 0x01
LOAD_HL_IMMEDIATE = 0x21
COMPARE_IMMEDIATE = 0xFE
SUPER_ROD_ENTRY_STRIDE = 3
SUPER_ROD_GROUP_LIMIT = 8
MAXIMUM_LEVEL = 100

#: The ten people who will swap a Pokémon for one of yours.
#:
#: Found by the shape only this table has: a stride carrying two species indices,
#: a small dialog selector, and eleven bytes of name text. Exactly one place in
#: the ROM holds ten of those in a row, and no place holds twelve.
IN_GAME_TRADE_TABLE = 0x71B7B
IN_GAME_TRADE_STRIDE = 14
IN_GAME_TRADE_COUNT = 10
IN_GAME_TRADE_NICKNAME_BYTES = 11
DIALOG_SELECTOR_LIMIT = 4
TEXT_TERMINATOR = 0x50
UPPERCASE_A = 0x80
LOWERCASE_A = 0xA0
LETTERS = 26

#: Facts re-derived on every read. If any fails, the cartridge is not the one
#: these offsets were located against and the read is refused.
DEX_ANCHORS = {0x1C: 9, 0x3B: 50, 0x76: 51, 0x84: 143}
DIGLETTS_CAVE_MAP_ID = 197
DIGLETTS_CAVE_SPECIES = frozenset({0x3B, 0x76})
MANSION_MAP_ID = 165
MANSION_MEASURED_BAND = (28, 39)


class CartridgeReadError(RuntimeError):
    """Raised when a cartridge does not match the located structures."""


class EvolutionMethod(StrEnum):
    """How one species becomes another.

    Game-neutral by intent: later titles add methods, and a title that has none
    of these simply reports none rather than being forced into Gen 1's shape.
    """

    LEVEL = "level"
    STONE = "stone"
    TRADE = "trade"


@dataclass(frozen=True, slots=True)
class Evolution:
    """One way a species can become another, read from the cartridge."""

    from_species: int
    to_species: int
    method: EvolutionMethod
    #: The level for a level evolution, the item identifier for a stone, and
    #: ``None`` for a trade, which has no threshold.
    requirement: int | None = None

    @property
    def needs_a_trade_partner(self) -> bool:
        """Whether a second concurrent save is required.

        This is the property the campaign model needs: it is what separates a
        species one cartridge can reach alone from one that needs a partner.
        """

        return self.method is EvolutionMethod.TRADE


def internal_to_dex(rom: bytes) -> dict[int, int]:
    """Map internal species indices to Pokédex numbers.

    The two spaces are not interchangeable and confusing them is silent:
    Blastoise is 0x1C internally and 9 in the dex, and a table indexed by one
    and read by the other returns a different species entirely.
    """

    for internal, expected in DEX_ANCHORS.items():
        actual = rom[INTERNAL_TO_DEX_TABLE + internal - 1]
        if actual != expected:
            raise CartridgeReadError(
                f"internal index {internal:#04x} maps to {actual}, not the {expected} "
                "the party adapter asserts; this is not the cartridge these offsets "
                "were located against"
            )
    mapping = {
        index + 1: rom[INTERNAL_TO_DEX_TABLE + index] for index in range(INTERNAL_INDEX_LIMIT)
    }
    return {internal: dex for internal, dex in mapping.items() if 1 <= dex <= SPECIES_COUNT}


def bank_offset(bank: int, address: int) -> int:
    """Where a banked address lands in the flat ROM image.

    Public because every structure in a Generation I cartridge is addressed this
    way, and a second copy of this arithmetic in a sibling module is exactly the
    kind of drift this repository has already paid for three times.
    """

    return bank * 0x4000 + (address - 0x4000)


def wild_tables(rom: bytes) -> dict[int, list[tuple[int, int]]]:
    """Every ``(level, internal species)`` slot each map can field.

    Grass and water only. Fishing, Game Corner prizes, gifts, fossils, in-game
    trades and evolution are separate routes stored elsewhere, so absence here
    is not unobtainability.
    """

    tables: dict[int, list[tuple[int, int]]] = {}
    for map_id in range(MAP_ID_LIMIT):
        at = WILD_POINTER_ARRAY + 2 * map_id
        address = int.from_bytes(rom[at : at + 2], "little")
        if not 0x4000 <= address <= 0x7FFF:
            continue
        cursor = bank_offset(WILD_DATA_BANK, address)
        slots: list[tuple[int, int]] = []
        for _ in range(2):
            rate = rom[cursor]
            cursor += 1
            if rate == 0:
                continue
            slots.extend(
                (rom[cursor + 2 * slot], rom[cursor + 2 * slot + 1])
                for slot in range(SLOTS_PER_TABLE)
            )
            cursor += 2 * SLOTS_PER_TABLE
        if slots:
            tables[map_id] = slots
    _verify_wild_tables(tables)
    return tables


def _verify_wild_tables(tables: Mapping[int, list[tuple[int, int]]]) -> None:
    cave = tables.get(DIGLETTS_CAVE_MAP_ID)
    if not cave or {species for _, species in cave} != set(DIGLETTS_CAVE_SPECIES):
        raise CartridgeReadError(
            "Diglett's Cave does not hold exactly Diglett and Dugtrio; the wild "
            "pointer array is not where it was located"
        )
    mansion = tables.get(MANSION_MAP_ID)
    if not mansion:
        raise CartridgeReadError("no Mansion table; the map index is wrong")
    levels = [level for level, _ in mansion]
    if (min(levels), max(levels)) != MANSION_MEASURED_BAND:
        raise CartridgeReadError(
            f"Mansion band {min(levels)}-{max(levels)} contradicts the measured "
            f"{MANSION_MEASURED_BAND[0]}-{MANSION_MEASURED_BAND[1]}"
        )


def evolution_graph(rom: bytes) -> dict[int, tuple[Evolution, ...]]:
    """Every evolution each species has, keyed and valued by Pokédex number.

    A living Pokédex needs this: how a species enters the collection is as much
    a part of the plan as where it is found, and three of Gen 1's methods have
    different costs -- a level is time, a stone is a finite item, and a trade
    needs a second concurrent save.
    """

    dex = internal_to_dex(rom)
    graph: dict[int, list[Evolution]] = {}
    for internal, species in dex.items():
        at = EVOLUTION_POINTER_ARRAY + 2 * (internal - 1)
        address = int.from_bytes(rom[at : at + 2], "little")
        if not 0x4000 <= address <= 0x7FFF:
            continue
        cursor = bank_offset(EVOLUTION_DATA_BANK, address)
        found: list[Evolution] = []
        while rom[cursor] != 0:
            kind = rom[cursor]
            if kind == 1:
                level, target = rom[cursor + 1], rom[cursor + 2]
                step, method, requirement = 3, EvolutionMethod.LEVEL, level
            elif kind == 2:
                item, target = rom[cursor + 1], rom[cursor + 3]
                step, method, requirement = 4, EvolutionMethod.STONE, item
            elif kind == 3:
                target = rom[cursor + 2]
                step, method, requirement = 3, EvolutionMethod.TRADE, None
            else:
                raise CartridgeReadError(
                    f"unknown evolution kind {kind} for species {species}; the "
                    "evolution pointer array is not where it was located"
                )
            if target in dex:
                found.append(
                    Evolution(
                        from_species=species,
                        to_species=dex[target],
                        method=method,
                        requirement=requirement,
                    )
                )
            cursor += step
        if found:
            graph[species] = found
    _verify_evolution_graph(graph)
    return {species: tuple(items) for species, items in graph.items()}


def _verify_evolution_graph(graph: Mapping[int, list[Evolution]]) -> None:
    diglett = graph.get(50, [])
    if not any(
        step.method is EvolutionMethod.LEVEL
        and step.requirement == 26
        and step.to_species == 51
        for step in diglett
    ):
        raise CartridgeReadError(
            "Diglett does not evolve at level 26 into Dugtrio; the evolution "
            "pointer array is not where it was located"
        )


class RodKind(StrEnum):
    """Which rod produces a bite.

    They differ in more than quality: the first two carry their own fixed slots
    and work wherever fishing works at all, while the third is the only one that
    varies by map. A planner that wants a particular species needs to know which
    of those two shapes it is dealing with.
    """

    OLD = "old"
    GOOD = "good"
    SUPER = "super"


@dataclass(frozen=True, slots=True)
class FishingSlot:
    """One ``(level, species)`` a rod can produce, keyed by Pokédex number."""

    level: int
    species: int
    rod: RodKind


@dataclass(frozen=True, slots=True)
class FishingTables:
    """What each rod can produce, read from the cartridge.

    Split by shape rather than by rod. ``anywhere`` holds the slots that do not
    depend on position, and ``by_map`` holds the Super Rod's per-map groups. A
    map absent from ``by_map`` is one where the Super Rod never bites -- which
    is not the same as a map where fishing is impossible, since the other two
    rods still work there.
    """

    anywhere: tuple[FishingSlot, ...]
    by_map: Mapping[int, tuple[FishingSlot, ...]]

    def at(self, map_id: int) -> tuple[FishingSlot, ...]:
        """Everything any rod can produce on one map."""

        return self.anywhere + tuple(self.by_map.get(map_id, ()))

    def species(self) -> frozenset[int]:
        """Every species reachable with a rod, anywhere."""

        found = {slot.species for slot in self.anywhere}
        for slots in self.by_map.values():
            found |= {slot.species for slot in slots}
        return frozenset(found)


def _fishing_offset(address: int) -> int:
    return bank_offset(FISHING_BANK, address)


def _operand_address(rom: bytes, at: int, opcode: int, what: str) -> int:
    """Read the address an instruction names, refusing if it is not that instruction."""

    offset = _fishing_offset(at)
    if rom[offset] != opcode:
        raise CartridgeReadError(
            f"{what} at {at:#06x} is {rom[offset]:#04x}, not the {opcode:#04x} it was "
            "located against; this cartridge's fishing code is not where it was found"
        )
    address = int.from_bytes(rom[offset + 1 : offset + 3], "little")
    if not 0x4000 <= address <= 0x7FFF:
        raise CartridgeReadError(f"{what} names {address:#06x}, which is outside its bank")
    return address


def fishing_tables(rom: bytes) -> FishingTables:
    """Every bite each rod can produce.

    Fishing is a separate acquisition route from walking in grass, and the
    difference is load-bearing for a living Pokédex: the wild tables alone make
    four species look version-exclusive that are not, because both cartridges
    offer them on a rod.
    """

    dex = internal_to_dex(rom)

    old_rod_at = _fishing_offset(OLD_ROD_ENCOUNTER)
    if rom[old_rod_at] != LOAD_BC_IMMEDIATE:
        raise CartridgeReadError(
            f"the Old Rod encounter at {OLD_ROD_ENCOUNTER:#06x} is "
            f"{rom[old_rod_at]:#04x}, not the {LOAD_BC_IMMEDIATE:#04x} immediate load it "
            "was located against"
        )
    anywhere = [_slot(dex, rom[old_rod_at + 2], rom[old_rod_at + 1], RodKind.OLD)]

    count_at = _fishing_offset(GOOD_ROD_SLOT_COUNT)
    if rom[count_at] != COMPARE_IMMEDIATE:
        raise CartridgeReadError(
            f"the Good Rod slot count at {GOOD_ROD_SLOT_COUNT:#06x} is not a compare"
        )
    good_rod_slots = rom[count_at + 1]
    good_rod = _fishing_offset(
        _operand_address(rom, GOOD_ROD_TABLE_POINTER, LOAD_HL_IMMEDIATE, "the Good Rod table")
    )
    anywhere.extend(
        _slot(dex, rom[good_rod + 2 * slot], rom[good_rod + 2 * slot + 1], RodKind.GOOD)
        for slot in range(good_rod_slots)
    )

    at = _fishing_offset(
        _operand_address(rom, SUPER_ROD_TABLE_POINTER, LOAD_HL_IMMEDIATE, "the Super Rod table")
    )
    by_map: dict[int, tuple[FishingSlot, ...]] = {}
    order: list[int] = []
    while rom[at] != 0xFF:
        map_id = rom[at]
        group = int.from_bytes(rom[at + 1 : at + 3], "little")
        if not 0x4000 <= group <= 0x7FFF:
            raise CartridgeReadError(
                f"Super Rod group for map {map_id} points at {group:#06x}, outside its bank"
            )
        cursor = _fishing_offset(group)
        size = rom[cursor]
        if not 1 <= size <= SUPER_ROD_GROUP_LIMIT:
            raise CartridgeReadError(
                f"Super Rod group for map {map_id} claims {size} slots; the table is "
                "not where it was located"
            )
        by_map[map_id] = tuple(
            _slot(dex, rom[cursor + 1 + 2 * slot], rom[cursor + 2 + 2 * slot], RodKind.SUPER)
            for slot in range(size)
        )
        order.append(map_id)
        at += SUPER_ROD_ENTRY_STRIDE

    tables = FishingTables(anywhere=tuple(anywhere), by_map=by_map)
    _verify_fishing(rom, tables, order)
    return tables


def _slot(dex: Mapping[int, int], level: int, internal: int, rod: RodKind) -> FishingSlot:
    if internal not in dex:
        raise CartridgeReadError(
            f"the {rod.value} rod offers internal index {internal:#04x}, which is not a "
            "species; the fishing tables are not where they were located"
        )
    if not 1 <= level <= MAXIMUM_LEVEL:
        raise CartridgeReadError(f"the {rod.value} rod offers level {level}, which is not a level")
    return FishingSlot(level=level, species=dex[internal], rod=rod)


def _verify_fishing(rom: bytes, tables: FishingTables, order: list[int]) -> None:
    """Re-derive what the located structure must satisfy, or refuse.

    The strong check is the last one, and it is a cross-check rather than a
    restatement: every map the *wild* tables give a water encounter rate must be
    a map the Super Rod list names. Those water tables are verified separately
    against bands measured from live play, so this ties the fishing read to a
    measurement instead of to another read.
    """

    if len(set(order)) != len(order):
        raise CartridgeReadError("the Super Rod table names a map twice")
    if order != sorted(order):
        raise CartridgeReadError(
            "the Super Rod map ids are not ascending; the table is searched linearly "
            "over sorted data, so this is not that table"
        )
    if not order:
        raise CartridgeReadError("the Super Rod table is empty")

    unfishable = sorted(_maps_with_water(rom) - set(order))
    if unfishable:
        raise CartridgeReadError(
            f"maps {unfishable} carry a water encounter table but are absent from the "
            "Super Rod list; the two structures disagree, so one was read wrongly"
        )


def _maps_with_water(rom: bytes) -> set[int]:
    """Maps whose wild data carries a second table -- the ones you can surf."""

    found: set[int] = set()
    for map_id in range(MAP_ID_LIMIT):
        at = WILD_POINTER_ARRAY + 2 * map_id
        address = int.from_bytes(rom[at : at + 2], "little")
        if not 0x4000 <= address <= 0x7FFF:
            continue
        cursor = bank_offset(WILD_DATA_BANK, address)
        grass_rate = rom[cursor]
        cursor += 1
        if grass_rate:
            cursor += 2 * SLOTS_PER_TABLE
        if rom[cursor]:
            found.add(map_id)
    return found


def trade_evolutions(graph: Mapping[int, tuple[Evolution, ...]]) -> dict[int, int]:
    """Evolved species mapped to the precursor that must be traded for it.

    This is the shape :mod:`pokemon_red_completion.campaign` consumes, so a
    campaign's trade lifting can be derived from the cartridge rather than
    declared beside it.
    """

    return {
        step.to_species: step.from_species
        for steps in graph.values()
        for step in steps
        if step.needs_a_trade_partner
    }


@dataclass(frozen=True, slots=True)
class InGameTrade:
    """A swap an in-game character will make, keyed by Pokédex number.

    The cost is the point. Unlike catching, a trade *spends* a specimen, so a
    living collection needs two of the given species -- one to keep and one to
    hand over -- or has to go and catch another afterwards.
    """

    give_species: int
    get_species: int
    nickname: str


def _decode_text(raw: bytes) -> str:
    """Read a cartridge string, which is not ASCII."""

    letters: list[str] = []
    for value in raw:
        if value == TEXT_TERMINATOR:
            break
        if UPPERCASE_A <= value < UPPERCASE_A + LETTERS:
            letters.append(chr(ord("A") + value - UPPERCASE_A))
        elif LOWERCASE_A <= value < LOWERCASE_A + LETTERS:
            letters.append(chr(ord("a") + value - LOWERCASE_A))
        else:
            letters.append("?")
    return "".join(letters)


def in_game_trades(rom: bytes) -> tuple[InGameTrade, ...]:
    """Every swap a character in the world will make.

    A separate acquisition route from catching, and not a minor one: four
    species in Generation I -- Farfetch'd, Lickitung, Mr. Mime and Jynx --
    appear in no wild table, on no rod, and at the end of no evolution. The only
    way a cartridge produces them alone is by trading with somebody who lives
    there.
    """

    dex = internal_to_dex(rom)
    trades: list[InGameTrade] = []
    for index in range(IN_GAME_TRADE_COUNT):
        at = IN_GAME_TRADE_TABLE + IN_GAME_TRADE_STRIDE * index
        give, get, dialog = rom[at], rom[at + 1], rom[at + 2]
        if give not in dex or get not in dex:
            raise CartridgeReadError(
                f"trade {index} offers internal indices {give:#04x} and {get:#04x}, at least "
                "one of which is not a species; the trade table is not where it was located"
            )
        if dialog > DIALOG_SELECTOR_LIMIT:
            raise CartridgeReadError(f"trade {index} names dialog {dialog}, which is not one")
        if give == get:
            raise CartridgeReadError(f"trade {index} swaps a species for itself")
        nickname = _decode_text(rom[at + 3 : at + 3 + IN_GAME_TRADE_NICKNAME_BYTES])
        if not nickname or "?" in nickname:
            raise CartridgeReadError(
                f"trade {index} has no readable nickname; the stride is wrong"
            )
        trades.append(
            InGameTrade(
                give_species=dex[give], get_species=dex[get], nickname=nickname
            )
        )
    _verify_the_trade_table_ends(rom, dex)
    return tuple(trades)


def _verify_the_trade_table_ends(rom: bytes, dex: Mapping[int, int]) -> None:
    """The count has to be right, not merely survivable.

    Reading ten entries from a longer table would parse cleanly and quietly drop
    the rest, so the eleventh position must *fail* to look like a trade.
    """

    at = IN_GAME_TRADE_TABLE + IN_GAME_TRADE_STRIDE * IN_GAME_TRADE_COUNT
    give, get = rom[at], rom[at + 1]
    nickname = _decode_text(rom[at + 3 : at + 3 + IN_GAME_TRADE_NICKNAME_BYTES])
    if give in dex and get in dex and nickname and "?" not in nickname:
        raise CartridgeReadError(
            f"an eleventh entry reads as a trade, so there are more than {IN_GAME_TRADE_COUNT}; "
            "the count is wrong and trades are being dropped"
        )


def catchable_species(rom: bytes) -> frozenset[int]:
    """Every species this cartridge yields directly, by grass, surf or rod.

    Directly is the operative word: no evolution, no trade, no gift, no fossil,
    no Game Corner. This is the seed set the other routes grow from.
    """

    dex = internal_to_dex(rom)
    wild = {
        dex[species]
        for slots in wild_tables(rom).values()
        for _, species in slots
        if species in dex
    }
    return frozenset(wild | fishing_tables(rom).species())


def reachable_species(rom: bytes, *, with_trade_partner: bool = False) -> frozenset[int]:
    """What the catchable set grows into once every other route is applied.

    Three routes compound, so they are applied until nothing more falls out
    rather than once each: evolving something you caught, swapping something you
    caught with a character in the world, and evolving what they gave you.

    ``with_trade_partner`` decides whether *trade evolutions* count -- those need
    a second concurrent save, which the in-game swaps do not. A lone cartridge
    cannot perform them, so the default answers the single-save question.
    """

    return grow_collection(
        catchable_species(rom),
        evolutions=evolution_graph(rom),
        swaps={trade.get_species: trade.give_species for trade in in_game_trades(rom)},
        with_trade_partner=with_trade_partner,
    )


def grow_collection(
    seed: Iterable[int],
    *,
    evolutions: Mapping[int, tuple[Evolution, ...]],
    swaps: Mapping[int, int],
    with_trade_partner: bool = False,
) -> frozenset[int]:
    """Apply evolution and in-game trading until nothing more falls out.

    The two routes compound, which is why this loops rather than doing each once:
    a species you were given can evolve, and what it evolves into can be the
    price of another swap.

    Takes plain tables rather than a ROM so the closure can be exercised on its
    own. Reached through a whole-cartridge read, its only possible test is one
    that recomputes it, and a test that reimplements the thing it is checking
    agrees with any bug in either copy.
    """

    reached = set(seed)
    growing = True
    while growing:
        growing = False
        frontier = list(reached)
        while frontier:
            species = frontier.pop()
            for step in evolutions.get(species, ()):
                if step.needs_a_trade_partner and not with_trade_partner:
                    continue
                if step.to_species not in reached:
                    reached.add(step.to_species)
                    frontier.append(step.to_species)
                    growing = True
        for reward, price in swaps.items():
            # You have to have something to hand over.
            if price in reached and reward not in reached:
                reached.add(reward)
                growing = True
    return frozenset(reached)


def version_exclusives(
    first_rom: bytes, second_rom: bytes
) -> tuple[frozenset[int], frozenset[int]]:
    """What each of two cartridges can reach and the other cannot.

    This is the whole reason a living Pokédex needs more than one cartridge, and
    it used to be a typed table. Deriving it is what caught the difference
    between the two questions "which species appear in a cartridge's wild
    tables" and "which species can a cartridge reach": four species differ in
    the wild tables and are *not* exclusive, because both cartridges offer them
    on a rod, and six more are exclusive without appearing in any wild table at
    all, because they are only ever reached by evolving something that does.

    Trade evolutions are included on both sides. Exclusivity is a property of
    what a cartridge contains, not of how many saves are run beside it, and the
    two cartridges carry the same evolution graph so the choice cancels.
    """

    first = reachable_species(first_rom, with_trade_partner=True)
    second = reachable_species(second_rom, with_trade_partner=True)
    return first - second, second - first
