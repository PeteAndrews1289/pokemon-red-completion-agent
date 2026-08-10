"""What a Pokémon Blue cartridge can register.

Blue exists in this repository for one reason: eleven species are exclusive to it,
and no amount of Red planning reaches them. With three concurrent Red saves the
campaign reaches 139 of 151 and every remaining gap except Mew is a Blue
exclusive.

Blue and Red are the same game with a different pair of encounter tables and a
different set of in-game trades. Everything that is a *choice* rather than a
cartridge property — starter, fossil, Dojo prize, Eevee stone — is identical, so
those tables are reused from :mod:`pokemon_red_completion.red_pokedex` rather
than copied. A copy would drift, and this repository has paid for drifting
copies three times already.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.generation_one import (
    GENERATION_ONE_EVENT_ONLY,
    GENERATION_ONE_TRADE_EVOLUTIONS,
    UNAVAILABLE_IN_BLUE,
)
from pokemon_red_completion.pokedex import ExclusionReason, PokedexTarget, declare_target
from pokemon_red_completion.red_pokedex import (
    DOJO_PRIZES,
    EEVEE_EVOLUTIONS,
    FOSSIL_LINES,
    RED_CARTRIDGE_EXCLUSIONS,
    RED_TOTAL_SPECIES,
    STARTER_LINES,
    RedRunChoices,
)

BLUE_TOTAL_SPECIES = RED_TOTAL_SPECIES

#: Species a Blue cartridge cannot register on its own.
#:
#: The version-exclusive half is the mirror of Red's: each game's exclusives are
#: the other's gap, which is the entire reason a living Pokédex needs both.
#:
#: **These eleven are derived from both cartridges, not assumed.** They are
#: reciprocal to Red's eleven paired-version gaps, and on 2026-08-10 the
#: reciprocity stopped being a claim: reading each cartridge's wild tables,
#: rods and evolution graph and differencing the two reachable sets returns
#: exactly these eleven and exactly Red's eleven. See
#: docs/evidence/acquisition-routes-2026-08-10.json.
#:
#: No encounter harvest was needed, and one would not have settled it anyway.
#: Sampling shows what is *present*; proving Ekans absent from Blue would mean
#: walking every area and then arguing about how much walking is enough. The
#: tables are static data, so reading them settles presence and absence at once.
#:
#: The trade evolutions and Mew are cartridge properties shared with Red and
#: carry over unchanged.
BLUE_CARTRIDGE_EXCLUSIONS: dict[int, ExclusionReason] = {
    **{species: ExclusionReason.VERSION_EXCLUSIVE for species in UNAVAILABLE_IN_BLUE},
    **{species: ExclusionReason.REQUIRES_TRADE for species in GENERATION_ONE_TRADE_EVOLUTIONS},
    **{species: ExclusionReason.EVENT_DISTRIBUTION for species in GENERATION_ONE_EVENT_ONLY},
}


@dataclass(frozen=True, slots=True)
class BlueRunChoices(RedRunChoices):
    """The branches a Blue run must pick.

    Identical to Red's: the starter, fossil, Dojo prize and Eevee stone are the
    same decisions with the same forfeits. Subclassing states that they are the
    same decision rather than two that happen to agree today.
    """


def blue_target(choices: RedRunChoices | None = None) -> PokedexTarget:
    """The auditable completion target for one Blue run with given choices."""

    selected = choices or BlueRunChoices()
    return declare_target(
        BLUE_TOTAL_SPECIES,
        {**BLUE_CARTRIDGE_EXCLUSIONS, **selected.forfeited()},
    )


#: What the two cartridges between them cannot reach, ignoring choices.
#:
#: Computed rather than written down, so it cannot disagree with the tables
#: above. If it is ever anything but Mew, one of the two exclusion sets is
#: wrong.
SHARED_CARTRIDGE_GAPS = frozenset(RED_CARTRIDGE_EXCLUSIONS) & frozenset(
    species
    for species, reason in BLUE_CARTRIDGE_EXCLUSIONS.items()
    if reason is ExclusionReason.EVENT_DISTRIBUTION
)

__all__ = [
    "BLUE_CARTRIDGE_EXCLUSIONS",
    "BLUE_TOTAL_SPECIES",
    "BlueRunChoices",
    "DOJO_PRIZES",
    "EEVEE_EVOLUTIONS",
    "FOSSIL_LINES",
    "SHARED_CARTRIDGE_GAPS",
    "STARTER_LINES",
    "blue_target",
]
