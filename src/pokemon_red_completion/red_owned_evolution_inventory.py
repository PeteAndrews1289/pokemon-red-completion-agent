"""Action-free living-collection prerequisites from cartridge evolution rules.

This is an inventory, not a gameplay permission or a learned selection. Surplus
ownership does not prove navigation, storage access, battle safety or affordability.
Exact specimen identities remain on the executor side of the policy boundary.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.red_collection import red_species_number, red_species_ref


@dataclass(frozen=True, slots=True)
class RedOwnedEvolutionPrerequisite:
    source_species_ref: str
    target_species_ref: str
    evolution_level: int
    retained_source_copies: int
    duplicate_acquisitions_needed: int
    party_or_box_precursors: tuple[LivingSpecimen, ...]

    @property
    def has_owned_surplus(self) -> bool:
        return self.duplicate_acquisitions_needed == 0


def inventory_red_owned_level_evolutions(
    observation: CollectionObservation,
    graph: Mapping[int, tuple[Evolution, ...]],
    *,
    target_species: frozenset[str],
) -> tuple[RedOwnedEvolutionPrerequisite, ...]:
    """One row per missing target reachable from a currently owned precursor.

    Registered-but-no-longer-living targets are still missing. Keep one source
    copy; expose duplicate-acquisition deficits instead of hiding them. Two
    interchangeable specimens are one objective, not two strategic alternatives.
    Daycare specimens count toward retention but are not directly controllable.
    Branches share their precursor stock: this is not a simultaneous allocation.
    """
    counts = Counter(specimen.species_ref for specimen in observation.specimens)
    rows = []
    seen: set[tuple[int, int]] = set()
    for source in sorted(counts):
        number = red_species_number(source)
        for step in graph.get(number, ()):
            if step.from_species != number:
                raise ValueError("evolution graph source differs from its key")
            if step.method is not EvolutionMethod.LEVEL:
                continue
            if (
                type(step.requirement) is not int
                or not 1 <= step.requirement <= 100
                or type(step.to_species) is not int
                or not 1 <= step.to_species <= 151
                or step.to_species == number
            ):
                raise ValueError("level evolution rule is invalid")
            key = number, step.to_species
            if key in seen:
                raise ValueError("duplicate level evolution rule")
            seen.add(key)
            target = red_species_ref(step.to_species)
            if target not in target_species or counts[target]:
                continue
            precursors = tuple(sorted(
                (
                    specimen for specimen in observation.specimens
                    if specimen.species_ref == source
                    and specimen.location in {CollectionLocation.PARTY, CollectionLocation.BOX}
                ),
                key=lambda specimen: (
                    specimen.location.value, specimen.container_index, specimen.slot_index,
                ),
            ))
            rows.append(RedOwnedEvolutionPrerequisite(
                source, target, step.requirement, counts[source],
                max(0, 2 - counts[source]), precursors,
            ))
    return tuple(sorted(rows, key=lambda row: (
        row.target_species_ref, row.source_species_ref,
    )))
