"""Canonical Generation I cartridge facts shared by completion contracts.

These are cartridge facts, not route choices or memory layouts. Keeping the
National Pokédex sets here prevents the lightweight registration target and
the stricter living-collection contract from drifting apart.
"""

from __future__ import annotations

GENERATION_ONE_SPECIES_COUNT = 151

# Species unavailable on Red without trading from Blue. Pinsir is deliberately
# present: the living-collection contract included it while a later target did
# not, producing two contradictory one-save denominators.
UNAVAILABLE_IN_RED = frozenset(
    {
        27,  # Sandshrew
        28,  # Sandslash
        37,  # Vulpix
        38,  # Ninetales
        52,  # Meowth
        53,  # Persian
        69,  # Bellsprout
        70,  # Weepinbell
        71,  # Victreebel
        126,  # Magmar
        127,  # Pinsir
    }
)

# Species unavailable on Blue without trading from Red. Scyther is the
# reciprocal Safari Zone / Game Corner exclusive to Pinsir.
UNAVAILABLE_IN_BLUE = frozenset(
    {
        23,  # Ekans
        24,  # Arbok
        43,  # Oddish
        44,  # Gloom
        45,  # Vileplume
        56,  # Mankey
        57,  # Primeape
        58,  # Growlithe
        59,  # Arcanine
        123,  # Scyther
        125,  # Electabuzz
    }
)

# Evolved species mapped to the precursor that evolves when traded.
#
# Confirmed against both cartridges on 2026-08-09 by reading the evolution
# pointer array directly -- see docs/evidence/evolution-graph-2026-08-09.json and
# pokemon_red_completion.gen1_cartridge.trade_evolutions, which derives exactly
# this mapping from the 72-evolution graph. The declaration is kept because the
# planner must work without a ROM present; it is no longer the only statement of
# the fact, and test_gen1_cartridge holds the two together.
GENERATION_ONE_TRADE_EVOLUTIONS = {
    65: 64,  # Kadabra -> Alakazam
    68: 67,  # Machoke -> Machamp
    76: 75,  # Graveler -> Golem
    94: 93,  # Haunter -> Gengar
}

GENERATION_ONE_EVENT_ONLY = frozenset({151})

if len(UNAVAILABLE_IN_RED) != 11 or len(UNAVAILABLE_IN_BLUE) != 11:
    raise AssertionError("each Generation I cartridge must declare eleven paired-version gaps")
if UNAVAILABLE_IN_RED & UNAVAILABLE_IN_BLUE:
    raise AssertionError("Red and Blue paired-version gaps must be reciprocal")

__all__ = [
    "GENERATION_ONE_EVENT_ONLY",
    "GENERATION_ONE_SPECIES_COUNT",
    "GENERATION_ONE_TRADE_EVOLUTIONS",
    "UNAVAILABLE_IN_BLUE",
    "UNAVAILABLE_IN_RED",
]
