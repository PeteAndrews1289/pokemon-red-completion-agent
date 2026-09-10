"""Action-free priority ranking for owned level-evolution prerequisites.

This is shortlist support for native qualification, not a gameplay permission,
an execution-readiness proof, or a learned policy choice. Codex separately
authenticates the actual save and qualifies runtime routes before presenting an
EVOLVE goal alongside ACQUIRE.

Rows needing duplicate acquisitions, rows with no controllable precursor, and
rows with zero retained source copies are rejected. Precursors at
level 100 are ignored because they cannot gain a level to evolve. Required
level gains are computed as max(1, evolution_level - precursor.level).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pokemon_red_completion.collection import (
    CollectionLocation,
    LivingSpecimen,
)
from pokemon_red_completion.red_owned_evolution_inventory import (
    RedOwnedEvolutionPrerequisite,
)

_CONTROLLABLE_LOCATIONS = frozenset(
    {
        CollectionLocation.PARTY,
        CollectionLocation.BOX,
    }
)


@dataclass(frozen=True, slots=True)
class PrioritizedOwnedLevelEvolution:
    """An eligible level-evolution objective with its minimum required level gains."""

    prerequisite: RedOwnedEvolutionPrerequisite
    minimum_level_gains: int

    def __post_init__(self) -> None:
        if not isinstance(self.prerequisite, RedOwnedEvolutionPrerequisite):
            raise TypeError("prerequisite must be a RedOwnedEvolutionPrerequisite")
        if type(self.minimum_level_gains) is not int or self.minimum_level_gains < 1:
            raise ValueError("minimum_level_gains must be an integer >= 1")


def prioritize_owned_level_evolutions(
    rows: Iterable[RedOwnedEvolutionPrerequisite],
) -> tuple[PrioritizedOwnedLevelEvolution, ...]:
    """Prioritize existing RedOwnedEvolutionPrerequisite rows for native qualification.

    Reject rows needing duplicate acquisitions, no controllable precursor, or
    no retained source copies.
    Ignore level-100 precursors because they cannot gain a level.
    Compute cheapest required level gains as max(1, evolution_level - precursor.level).
    Sort eligible objectives ascending by required gains, then target and source
    species references solely as deterministic tie breakers.
    """
    if rows is None:
        raise TypeError("rows must be an iterable of RedOwnedEvolutionPrerequisite")

    # Consume without mutating caller's input
    try:
        row_list = list(rows)
    except TypeError as err:
        raise TypeError("rows must be an iterable of RedOwnedEvolutionPrerequisite") from err

    prioritized: list[PrioritizedOwnedLevelEvolution] = []
    for row in row_list:
        if not isinstance(row, RedOwnedEvolutionPrerequisite):
            raise TypeError("rows must contain only RedOwnedEvolutionPrerequisite instances")
        if type(row.evolution_level) is not int or not 1 <= row.evolution_level <= 100:
            raise ValueError("evolution_level must be an integer between 1 and 100")
        if type(row.retained_source_copies) is not int or row.retained_source_copies < 0:
            raise ValueError("retained_source_copies must be a nonnegative integer")
        if (
            type(row.duplicate_acquisitions_needed) is not int
            or row.duplicate_acquisitions_needed < 0
        ):
            raise ValueError("duplicate_acquisitions_needed must be a nonnegative integer")
        if not isinstance(row.party_or_box_precursors, tuple):
            raise TypeError("party_or_box_precursors must be a tuple")

        # Reject rows needing duplicate acquisitions
        if row.duplicate_acquisitions_needed != 0:
            continue

        # Reject rows with no retained source copies
        if row.retained_source_copies < 1:
            continue

        # Filter controllable precursors capable of gaining a level (level < 100)
        controllable: list[LivingSpecimen] = []
        for specimen in row.party_or_box_precursors:
            if not isinstance(specimen, LivingSpecimen):
                raise TypeError("precursors must be LivingSpecimen instances")
            if type(specimen.level) is not int or not 1 <= specimen.level <= 100:
                raise ValueError("specimen level must be an integer between 1 and 100")
            if specimen.location in _CONTROLLABLE_LOCATIONS and specimen.level < 100:
                controllable.append(specimen)

        # Reject rows with no controllable precursor
        if not controllable:
            continue

        # Cheapest required level gains: max(1, evolution_level - precursor.level)
        cheapest_gains = min(
            max(1, row.evolution_level - specimen.level) for specimen in controllable
        )

        prioritized.append(
            PrioritizedOwnedLevelEvolution(
                prerequisite=row,
                minimum_level_gains=cheapest_gains,
            )
        )

    # Species references break equal-effort ties; they are not learned features.
    prioritized.sort(
        key=lambda item: (
            item.minimum_level_gains,
            item.prerequisite.target_species_ref,
            item.prerequisite.source_species_ref,
        )
    )

    return tuple(prioritized)
