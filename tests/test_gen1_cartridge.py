"""Game facts derived from the cartridge rather than typed into a file.

A teacher that knows a game because somebody typed its facts in does not
transfer: every title costs another person-week, and each typed fact is an
assertion nothing can falsify. That is how eleven version exclusives were
recorded as ten, and how a Mansion band of 30-32 outlived the 155 encounters
saying 28-39.

These tests need no ROM. The reads are the measurement and live in
``docs/evidence/evolution-graph-2026-08-10.json``; this is the accounting that
holds the hand-written declarations against them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_red_completion.gen1_cartridge import (
    CartridgeReadError,
    Evolution,
    EvolutionMethod,
    internal_to_dex,
    trade_evolutions,
    verify_evolution_graph,
)
from pokemon_red_completion.generation_one import GENERATION_ONE_TRADE_EVOLUTIONS

RECORD = Path("docs/evidence/evolution-graph-2026-08-10.json")


@pytest.fixture(scope="module")
def record() -> dict:
    if not RECORD.exists():  # pragma: no cover - the record is committed
        pytest.skip(f"{RECORD} has not been produced")
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_the_declared_trade_evolutions_are_what_the_cartridge_says(record: dict) -> None:
    """The hand-written table is now confirmed rather than asserted."""

    derived = {int(k): v for k, v in record["trade_evolutions"].items()}

    assert derived == GENERATION_ONE_TRADE_EVOLUTIONS


def test_both_cartridges_carry_the_same_evolution_graph(record: dict) -> None:
    """Red and Blue differ in encounters and trades, not in how things evolve.

    If this ever fails the campaign model needs a per-title graph, because a
    trade evolution reachable on one cartridge and not the other changes what a
    plan can obtain.
    """

    assert record["cartridges_agree"] is True


def test_only_four_evolutions_need_a_second_save(record: dict) -> None:
    """The number that decides how many concurrent saves a campaign needs."""

    assert record["totals_by_method"]["trade"] == 4
    assert record["species_with_evolutions"] == 70


def test_a_trade_evolution_announces_that_it_needs_a_partner() -> None:
    """The property the campaign model consumes, kept on the type itself."""

    trade = Evolution(from_species=64, to_species=65, method=EvolutionMethod.TRADE)
    level = Evolution(from_species=50, to_species=51, method=EvolutionMethod.LEVEL, requirement=26)

    assert trade.needs_a_trade_partner
    assert not level.needs_a_trade_partner


def test_trade_evolutions_are_derived_from_a_graph_not_a_list() -> None:
    """Given a graph, the campaign's input falls out rather than being restated."""

    graph = {
        50: (Evolution(50, 51, EvolutionMethod.LEVEL, 26),),
        64: (Evolution(64, 65, EvolutionMethod.TRADE),),
        133: (Evolution(133, 134, EvolutionMethod.STONE, 34),),
    }

    assert trade_evolutions(graph) == {65: 64}


def test_a_cartridge_that_does_not_match_is_refused() -> None:
    """The offsets were located against one revision and say so.

    A different revision must fail loudly rather than return plausible nonsense,
    because a table read at the wrong address still returns bytes.
    """

    with pytest.raises(CartridgeReadError, match="not the cartridge"):
        internal_to_dex(bytes(0x50000))


def test_four_valid_anchors_are_not_mistaken_for_a_complete_species_table() -> None:
    """The anchors locate a table; they do not prove all 151 entries survived."""

    rom = bytearray(0x100000)
    for internal, expected in {0x1C: 9, 0x3B: 50, 0x76: 51, 0x84: 143}.items():
        rom[0x41024 + internal - 1] = expected

    with pytest.raises(CartridgeReadError, match="4 valid entries"):
        internal_to_dex(bytes(rom))


def test_the_complete_evolution_guard_checks_both_anchors_and_totals(record: dict) -> None:
    graph = {
        int(species): [
            Evolution(
                from_species=int(species),
                to_species=step["to"],
                method=EvolutionMethod(step["method"]),
                requirement=step["requirement"],
            )
            for step in steps
        ]
        for species, steps in record["graph"].items()
    }

    verify_evolution_graph(graph)

    without_kadabra = {species: list(steps) for species, steps in graph.items()}
    without_kadabra.pop(64)
    with pytest.raises(CartridgeReadError, match="Kadabra"):
        verify_evolution_graph(without_kadabra)


def test_the_stone_evolutions_include_the_eevee_branch(record: dict) -> None:
    """The mutually exclusive choice a run makes, derived rather than typed.

    Eevee's three stones are the reason a Pokedex target is a function of a
    run's choices, and they are now read from the cartridge.
    """

    eevee = record["graph"]["133"]

    assert len(eevee) == 3
    assert {step["to"] for step in eevee} == {134, 135, 136}
    assert all(step["method"] == "stone" for step in eevee)
