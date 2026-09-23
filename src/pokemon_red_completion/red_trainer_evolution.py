"""Cartridge-derived level-evolution verification for preparation only.

This observes transformations; it never selects moves, changes a save or allows
an arbitrary new party. Stable OT/DV bindings are private session fingerprints.
"""

from dataclasses import dataclass

from .gen1_cartridge import EvolutionMethod, evolution_graph, internal_to_dex
from .party import PartyObservation
from .red_party import PokemonRedPartyReader


@dataclass(frozen=True)
class RedTrainerEvolutionGuard:
    party_reader: PokemonRedPartyReader
    before: PartyObservation
    specimen_refs: tuple[str, ...]
    level_edges: frozenset[tuple[int, int, int]]

    @classmethod
    def from_rom(cls, rom, emulator):
        dex = internal_to_dex(rom)
        internal = {number: code for code, number in dex.items()}
        edges = frozenset(
            (internal[e.from_species], internal[e.to_species], e.requirement)
            for rows in evolution_graph(rom).values()
            for e in rows
            if e.method == EvolutionMethod.LEVEL
        )
        reader = PokemonRedPartyReader(emulator)
        return cls(reader, reader.read(), reader.preparation_specimen_refs(), edges)

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
        for old, new in zip(self.before.members, after.members, strict=True):
            if (
                old.experience is None
                or new.experience is None
                or new.experience < old.experience
                or new.level < old.level
            ):
                return False
            if new.species_id != old.species_id and not (
                new.level > old.level
                and new.experience > old.experience
                and any(
                    a == old.species_id and b == new.species_id and new.level >= level
                    for a, b, level in self.level_edges
                )
            ):
                return False
        return True
