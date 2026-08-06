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
    PokedexTarget,
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

#: Species no Red cartridge can register, whatever choices a run makes.
#:
#: Stating the unreachable set rather than the reachable one keeps the
#: declaration short enough to review.  These are properties of the cartridge:
#: no route recovers them, and only a paired Blue run or a trade will.
RED_CARTRIDGE_EXCLUSIONS: dict[int, ExclusionReason] = {
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
    # Never distributed in normal play. Left open for a later title that
    # actually features it rather than pretended away here.
    151: ExclusionReason.EVENT_DISTRIBUTION,  # Mew
}

#: The four branches a Red run must pick, and the lines each one forecloses.
#:
#: These are not cartridge properties. They are coverage decisions: a second
#: run exists precisely to take the other branch, so the target has to be a
#: function of the choices rather than a constant.
STARTER_LINES: dict[str, tuple[int, ...]] = {
    "squirtle": (7, 8, 9),
    "bulbasaur": (1, 2, 3),
    "charmander": (4, 5, 6),
}
FOSSIL_LINES: dict[str, tuple[int, ...]] = {
    "helix": (138, 139),
    "dome": (140, 141),
}
DOJO_PRIZES: dict[str, tuple[int, ...]] = {
    "hitmonlee": (106,),
    "hitmonchan": (107,),
}
EEVEE_EVOLUTIONS: dict[str, tuple[int, ...]] = {
    "vaporeon": (134,),
    "jolteon": (135,),
    "flareon": (136,),
}


@dataclass(frozen=True, slots=True)
class RedRunChoices:
    """The mutually exclusive branches one Red run commits to.

    The rival always takes the starter strong against the player's, so a single
    run reaches exactly one of the three starter lines.
    """

    starter: str = "squirtle"
    fossil: str = "helix"
    dojo_prize: str = "hitmonlee"
    eevee_evolution: str = "jolteon"

    def __post_init__(self) -> None:
        for field_name, options in (
            ("starter", STARTER_LINES),
            ("fossil", FOSSIL_LINES),
            ("dojo_prize", DOJO_PRIZES),
            ("eevee_evolution", EEVEE_EVOLUTIONS),
        ):
            value = getattr(self, field_name)
            if value not in options:
                raise ValueError(
                    f"{field_name} must be one of {sorted(options)}; got {value!r}"
                )

    def forfeited(self) -> dict[int, ExclusionReason]:
        """Every species this run's choices put out of reach."""

        forfeited: dict[int, ExclusionReason] = {}
        for chosen, options in (
            (self.starter, STARTER_LINES),
            (self.fossil, FOSSIL_LINES),
            (self.dojo_prize, DOJO_PRIZES),
            (self.eevee_evolution, EEVEE_EVOLUTIONS),
        ):
            for name, line in options.items():
                if name == chosen:
                    continue
                for species in line:
                    forfeited[species] = ExclusionReason.MUTUALLY_EXCLUSIVE_CHOICE
        return forfeited


def red_target(choices: RedRunChoices | None = None) -> PokedexTarget:
    """The auditable completion target for one Red run with given choices."""

    selected = choices or RedRunChoices()
    return declare_target(
        RED_TOTAL_SPECIES,
        {**RED_CARTRIDGE_EXCLUSIONS, **selected.forfeited()},
    )


#: The target for the route this repository currently runs.
RED_POKEDEX_TARGET = red_target()


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
