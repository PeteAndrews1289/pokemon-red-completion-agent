"""Pokémon Red binding for the game-neutral Pokédex contract.

Two things live here and nowhere else: where Red keeps its registration
bitfields, and which species a single Red cartridge cannot reach.

**Identifier space.** These flags are indexed by *Pokédex ordinal* (Bulbasaur is
1, Mew is 151), which is a different numbering system from the internal species
indices used by :mod:`pokemon_red_completion.red_party` (Blastoise is ``0x1C``
there, but ordinal 9 here).  Mixing the two produces a plausible and meaningless
completion percentage, so the two adapters deliberately do not share constants.

**Address derivation.** ``PARTY_MON_2_NICKNAME`` and ``PARTY_MON_3_NICKNAME``
are already-verified symbols eleven bytes apart, so the six-entry nickname block
starts at ``0xD2B5`` and ends at ``0xD2B5 + 6 * 11 = 0xD2F7``.  The owned
bitfield begins exactly there, and the seen bitfield exactly nineteen bytes
later—nineteen being ``ceil(151 / 8)``.  Both offsets are re-derived from those
committed symbols below, and :mod:`tests.test_red_pokedex` asserts the
arithmetic, so a future edit cannot silently drift.
"""

from __future__ import annotations

from dataclasses import dataclass

from .observation import RamAddress, ReadOnlyMemory
from .pokedex import (
    ExclusionReason,
    PokedexObservation,
    declare_target,
    registration_from_flags,
)

RED_TOTAL_SPECIES = 151
NICKNAME_LENGTH = 11
PARTY_NICKNAME_COUNT = 6
#: Nickname block start, derived from the two committed nickname symbols.
PARTY_NICKNAMES_BASE = int(RamAddress.PARTY_MON_2_NICKNAME) - NICKNAME_LENGTH
POKEDEX_FLAG_BYTES = (RED_TOTAL_SPECIES + 7) // 8
POKEDEX_OWNED = PARTY_NICKNAMES_BASE + PARTY_NICKNAME_COUNT * NICKNAME_LENGTH
POKEDEX_SEEN = POKEDEX_OWNED + POKEDEX_FLAG_BYTES

#: Species a single Red cartridge cannot register, and why.
#:
#: Stating the unreachable set rather than the reachable one keeps the
#: declaration short enough to review.  "100% of the Pokédex" is not a coherent
#: target for one cartridge, and pinning that here stops the number drifting
#: into something that merely sounds complete.
RED_EXCLUSIONS: dict[int, ExclusionReason] = {
    # Blue-exclusive lines.
    27: ExclusionReason.VERSION_EXCLUSIVE,  # Sandshrew
    28: ExclusionReason.VERSION_EXCLUSIVE,  # Sandslash
    37: ExclusionReason.VERSION_EXCLUSIVE,  # Vulpix
    38: ExclusionReason.VERSION_EXCLUSIVE,  # Ninetales
    52: ExclusionReason.VERSION_EXCLUSIVE,  # Meowth
    53: ExclusionReason.VERSION_EXCLUSIVE,  # Persian
    69: ExclusionReason.VERSION_EXCLUSIVE,  # Bellsprout
    70: ExclusionReason.VERSION_EXCLUSIVE,  # Weepinbell
    71: ExclusionReason.VERSION_EXCLUSIVE,  # Victreebel
    126: ExclusionReason.VERSION_EXCLUSIVE,  # Magmar
    # Evolutions that only occur on trade.
    65: ExclusionReason.REQUIRES_TRADE,  # Alakazam
    68: ExclusionReason.REQUIRES_TRADE,  # Machamp
    76: ExclusionReason.REQUIRES_TRADE,  # Golem
    94: ExclusionReason.REQUIRES_TRADE,  # Gengar
    # Never distributed in normal play.
    151: ExclusionReason.EVENT_DISTRIBUTION,  # Mew
    # Forfeited by a choice this route makes.  These are not properties of the
    # cartridge: a different starter, fossil, Dojo prize, or evolution stone
    # moves them into the obtainable set and moves others out.  They belong in
    # the declaration because the denominator is route-specific, and a target
    # that ignores that reports completion against a set the run could never
    # have reached.
    1: ExclusionReason.MUTUALLY_EXCLUSIVE_CHOICE,  # Bulbasaur, taken by the rival
    2: ExclusionReason.MUTUALLY_EXCLUSIVE_CHOICE,  # Ivysaur
    3: ExclusionReason.MUTUALLY_EXCLUSIVE_CHOICE,  # Venusaur
    4: ExclusionReason.MUTUALLY_EXCLUSIVE_CHOICE,  # Charmander, chosen by neither
    5: ExclusionReason.MUTUALLY_EXCLUSIVE_CHOICE,  # Charmeleon
    6: ExclusionReason.MUTUALLY_EXCLUSIVE_CHOICE,  # Charizard
    107: ExclusionReason.MUTUALLY_EXCLUSIVE_CHOICE,  # Hitmonchan, Hitmonlee taken
    134: ExclusionReason.MUTUALLY_EXCLUSIVE_CHOICE,  # Vaporeon, Jolteon taken
    136: ExclusionReason.MUTUALLY_EXCLUSIVE_CHOICE,  # Flareon, Jolteon taken
    140: ExclusionReason.MUTUALLY_EXCLUSIVE_CHOICE,  # Kabuto, Helix Fossil taken
    141: ExclusionReason.MUTUALLY_EXCLUSIVE_CHOICE,  # Kabutops
}

#: The auditable completion target for one Red cartridge.
RED_POKEDEX_TARGET = declare_target(RED_TOTAL_SPECIES, RED_EXCLUSIONS)


@dataclass(frozen=True, slots=True)
class PokemonRedPokedexReader:
    """Projects Red's registration bitfields into the neutral contract."""

    memory: ReadOnlyMemory

    def _flags(self, base: int) -> tuple[int, ...]:
        return tuple(self.memory.read_u8(base + offset) for offset in range(POKEDEX_FLAG_BYTES))

    def read(self) -> PokedexObservation:
        """Read the seen and owned registers.

        An owned species is always also seen in normal play, but a partially
        written save can violate that.  The union keeps the observation
        internally consistent rather than raising on a state the game itself
        can transiently produce.
        """

        owned = registration_from_flags(self._flags(POKEDEX_OWNED), RED_TOTAL_SPECIES)
        seen = registration_from_flags(self._flags(POKEDEX_SEEN), RED_TOTAL_SPECIES)
        return PokedexObservation(seen=seen | owned, owned=owned)
