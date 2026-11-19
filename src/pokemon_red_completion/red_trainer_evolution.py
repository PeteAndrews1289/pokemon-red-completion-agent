"""Cartridge-derived level-evolution verification for preparation only.

This observes transformations; it never selects moves, changes a save or allows
an arbitrary new party. Stable OT/DV bindings are private session fingerprints.
"""

from dataclasses import dataclass

from .gen1_cartridge import EvolutionMethod, evolution_graph, internal_to_dex
from .party import PartyObservation
from .red_party import PokemonRedPartyReader


def level_evolution_edges(rom):
    dex = internal_to_dex(rom)
    internal = {number: code for code, number in dex.items()}
    return frozenset(
        (internal[e.from_species], internal[e.to_species], e.requirement)
        for rows in evolution_graph(rom).values()
        for e in rows
        if e.method == EvolutionMethod.LEVEL
    )


def level_evolution_matches(old, new, edges):
    """One earned cartridge evolution, never a stone, trade or species swap."""
    return (
        new.level > old.level
        and old.experience is not None
        and new.experience is not None
        and new.experience > old.experience
        and any(
            a == old.species_id and b == new.species_id and new.level >= level
            for a, b, level in edges
        )
    )


def retained_level_evolution_matches(origin, entry, new, edges):
    """The level was earned before a verified retained-combat chunk boundary."""
    return (
        origin.species_id == entry.species_id
        and origin.level < entry.level <= new.level
        and origin.experience is not None and entry.experience is not None
        and new.experience is not None and origin.experience < entry.experience <= new.experience
        and level_evolution_matches(origin, new, edges)
    )


@dataclass(frozen=True)
class RedTrainerEvolutionGuard:
    party_reader: PokemonRedPartyReader
    before: PartyObservation
    specimen_refs: tuple[str, ...]
    level_edges: frozenset[tuple[int, int, int]]

    retained_origin: PartyObservation | None = None

    @classmethod
    def from_rom(cls, rom, emulator, *, retained_origin=None):
        edges = level_evolution_edges(rom)
        reader = PokemonRedPartyReader(emulator)
        return cls(reader, reader.read(), reader.preparation_specimen_refs(), edges, retained_origin)

    def matches(self, initial, current):
        """Accept unchanged members or one observed level evolution per specimen."""
        if (
            current.battle_state != 0
            or initial.party_count != self.before.size
            or current.party_count != self.before.size
            or initial.party_species_ids != self.before.species_ids()
            or initial.party_levels != self.before.levels
        ):
            return False
        after = self.party_reader.read()
        if (
            self.party_reader.preparation_specimen_refs() != self.specimen_refs
            or after.size != self.before.size
            or after.species_ids() != current.party_species_ids
            or after.levels != current.party_levels
        ):
            return False
        for index, (old, new) in enumerate(zip(self.before.members, after.members, strict=True)):
            if (
                old.experience is None
                or new.experience is None
                or new.experience < old.experience
                or new.level < old.level
            ):
                return False
            if new.species_id != old.species_id and not (
                level_evolution_matches(old, new, self.level_edges)
                or (
                    isinstance(self.retained_origin, PartyObservation)
                    and self.retained_origin.size == self.before.size
                    and retained_level_evolution_matches(
                        self.retained_origin.members[index], old, new, self.level_edges
                    )
                )
            ):
                return False
        return True
