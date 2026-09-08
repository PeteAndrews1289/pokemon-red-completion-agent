"""Cartridge-authenticated level edges for prospective acquisition planning."""

from __future__ import annotations

from collections.abc import Mapping

from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod, evolution_graph
from pokemon_red_completion.red_collection import RED_SOLO_COLLECTION_CONTRACT, red_species_ref


def level_acquisition_edges(
    graph: Mapping[int, tuple[Evolution, ...]],
) -> tuple[tuple[str, str], ...]:
    """Project ordinary level evolutions only; no invented item/trade rules."""
    targets = RED_SOLO_COLLECTION_CONTRACT.target_species
    edges = set()
    for source, evolutions in graph.items():
        for rule in evolutions:
            if rule.from_species != source:
                raise ValueError("cartridge evolution source differs from graph key")
            if rule.method is not EvolutionMethod.LEVEL:
                continue
            if type(rule.requirement) is not int or not 1 <= rule.requirement <= 100:
                raise ValueError("level evolution threshold must be a cartridge level")
            pair = red_species_ref(source), red_species_ref(rule.to_species)
            if pair[0] == pair[1]:
                raise ValueError("level evolution must change species")
            if all(s in targets for s in pair):
                edges.add(pair)
    return tuple(sorted(edges))


def cartridge_level_acquisition_edges(rom: bytes) -> tuple[tuple[str, str], ...]:
    return level_acquisition_edges(evolution_graph(rom))
