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
"""

from __future__ import annotations

from collections.abc import Mapping
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


def _bank_offset(bank: int, address: int) -> int:
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
        cursor = _bank_offset(WILD_DATA_BANK, address)
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
        cursor = _bank_offset(EVOLUTION_DATA_BANK, address)
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
