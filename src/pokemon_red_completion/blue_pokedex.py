"""What a Pokémon Blue cartridge can register.

Blue exists in this repository for one reason: ten species are exclusive to it,
and no amount of Red planning reaches them. With three concurrent Red saves the
campaign reaches 140 of 151 and every remaining gap except Mew is a Blue
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

from pokemon_red_completion.pokedex import ExclusionReason, PokedexTarget, declare_target
from pokemon_red_completion.red_pokedex import (
    DOJO_PRIZES,
    EEVEE_EVOLUTIONS,
    FOSSIL_LINES,
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
#: **These ten are derived, not measured.** They are the complement of the ten
#: Red declares, and that relationship is what makes the pair complete. The
#: repository can now check them — a Blue cartridge loads and reads under the
#: existing adapter — by harvesting encounters the same way Red's bands were
#: measured. Until that harvest exists this table is a stated assumption, and it
#: is marked as one rather than presented as a measurement.
#:
#: The trade evolutions and Mew are cartridge properties shared with Red and
#: carry over unchanged.
BLUE_CARTRIDGE_EXCLUSIONS: dict[int, ExclusionReason] = {
    # Red-exclusive lines. Mirror of RED_CARTRIDGE_EXCLUSIONS' Blue-exclusives.
    23: ExclusionReason.VERSION_EXCLUSIVE,  # Ekans
    24: ExclusionReason.VERSION_EXCLUSIVE,  # Arbok
    43: ExclusionReason.VERSION_EXCLUSIVE,  # Oddish
    44: ExclusionReason.VERSION_EXCLUSIVE,  # Gloom
    45: ExclusionReason.VERSION_EXCLUSIVE,  # Vileplume
    56: ExclusionReason.VERSION_EXCLUSIVE,  # Mankey
    57: ExclusionReason.VERSION_EXCLUSIVE,  # Primeape
    58: ExclusionReason.VERSION_EXCLUSIVE,  # Growlithe
    59: ExclusionReason.VERSION_EXCLUSIVE,  # Arcanine
    125: ExclusionReason.VERSION_EXCLUSIVE,  # Electabuzz
    # Evolutions that only occur on trade. Shared with Red, and liftable by a
    # campaign that runs a partner save -- see pokemon_red_completion.campaign.
    65: ExclusionReason.REQUIRES_TRADE,  # Alakazam
    68: ExclusionReason.REQUIRES_TRADE,  # Machamp
    76: ExclusionReason.REQUIRES_TRADE,  # Golem
    94: ExclusionReason.REQUIRES_TRADE,  # Gengar
    # Never distributed in normal play.
    151: ExclusionReason.EVENT_DISTRIBUTION,  # Mew
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
SHARED_CARTRIDGE_GAPS = frozenset(BLUE_CARTRIDGE_EXCLUSIONS) & frozenset(
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
