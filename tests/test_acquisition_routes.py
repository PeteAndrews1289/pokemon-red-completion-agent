"""Every way a cartridge yields a species, and why grass alone is not enough.

A living Pokédex is a question about acquisition, not about encounters. This
repository learned the difference the expensive way: it compared the two
cartridges' wild tables, found ten species on each side, and recorded ten
version exclusives. The real number is eleven, and the wild-table comparison was
wrong in both directions at once -- it counted four species that are not
exclusive and missed six that are.

These tests hold that accounting. They need no ROM: the reads are the
measurement and live in ``docs/evidence/acquisition-routes-2026-08-10.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_red_completion.gen1_cartridge import (
    CartridgeReadError,
    FishingSlot,
    FishingTables,
    RodKind,
    fishing_tables,
)
from pokemon_red_completion.generation_one import UNAVAILABLE_IN_BLUE, UNAVAILABLE_IN_RED

RECORD = Path("docs/evidence/acquisition-routes-2026-08-10.json")


@pytest.fixture(scope="module")
def record() -> dict:
    if not RECORD.exists():  # pragma: no cover - the record is committed
        pytest.skip(f"{RECORD} has not been produced")
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_the_declared_version_exclusives_are_derived_from_the_cartridges(record: dict) -> None:
    """The table that was typed, then corrected, is now computed.

    ``UNAVAILABLE_IN_BLUE`` names what only Red reaches, so it must equal Red's
    derived exclusives -- the naming is mirrored and worth reading twice.
    """

    assert set(record["version_exclusives"]["red"]) == set(UNAVAILABLE_IN_BLUE)
    assert set(record["version_exclusives"]["blue"]) == set(UNAVAILABLE_IN_RED)
    assert len(record["version_exclusives"]["red"]) == 11
    assert len(record["version_exclusives"]["blue"]) == 11


def test_a_wild_table_difference_is_not_version_exclusivity(record: dict) -> None:
    """The four species that made the count come out as ten.

    Horsea and Seadra appear in Red's wild tables and not Blue's; Krabby and
    Kingler the reverse. All four are on a Super Rod in both cartridges, so none
    is exclusive. Comparing encounter tables answers a different question from
    the one a Pokédex asks.
    """

    covered = record["wild_difference_that_is_not_exclusivity"]

    assert covered == [98, 99, 116, 117]
    for species in covered:
        assert species not in UNAVAILABLE_IN_RED
        assert species not in UNAVAILABLE_IN_BLUE
        for title in ("red", "blue"):
            assert species in record["by_title"][title]["rod_species"]


def test_six_exclusives_appear_in_no_wild_table_at_all(record: dict) -> None:
    """The other half of the error: exclusivity that is inherited.

    Vileplume, Primeape and Arcanine are never encountered; nor are Ninetales,
    Persian and Victreebel. Each is reached only by evolving a species that is
    itself exclusive, so a search of encounter tables cannot see them.
    """

    inherited = record["exclusive_but_absent_from_every_wild_table"]

    assert inherited == [38, 45, 53, 57, 59, 71]
    for species in inherited:
        assert species in set(UNAVAILABLE_IN_RED) | set(UNAVAILABLE_IN_BLUE)
        for title in ("red", "blue"):
            assert species not in record["by_title"][title]["wild_table_species"]
            assert species not in record["by_title"][title]["rod_species"]


def test_both_cartridges_fish_identically(record: dict) -> None:
    """Red and Blue differ in grass and in trades, not on a rod.

    If this ever fails, the exclusive lists have to be re-derived: a rod that
    differs between cartridges is another source of exclusivity.
    """

    assert record["fishing_tables_identical_across_cartridges"] is True
    assert record["by_title"]["red"]["anywhere"] == record["by_title"]["blue"]["anywhere"]


def test_a_rod_reaches_species_no_amount_of_walking_does(record: dict) -> None:
    """Fishing is a distinct route, not a convenience.

    Eight species per cartridge are on a rod and in no wild table. A planner
    that only knows how to walk in grass cannot complete a Pokédex.
    """

    for title in ("red", "blue"):
        rod_only = record["by_title"][title]["rod_only_species"]
        assert len(rod_only) == 8
        wild = set(record["by_title"][title]["wild_table_species"])
        assert not wild & set(rod_only)
        assert set(rod_only) <= set(record["by_title"][title]["catchable"])


def test_a_trade_partner_is_worth_exactly_the_trade_evolutions(record: dict) -> None:
    """What a second concurrent save buys, counted rather than assumed."""

    for title in ("red", "blue"):
        alone = set(record["by_title"][title]["reachable_alone"])
        partnered = set(record["by_title"][title]["reachable_with_a_trade_partner"])
        assert partnered - alone == {65, 68, 76, 94}


def test_the_super_rod_is_the_only_rod_that_depends_on_where_you_stand() -> None:
    """The distinction the type exists to hold.

    A map absent from the Super Rod table is not a map where fishing fails --
    the other two rods still bite there. Collapsing the two shapes would make a
    planner believe Pallet Town's pond is empty.
    """

    tables = FishingTables(
        anywhere=(
            FishingSlot(level=5, species=129, rod=RodKind.OLD),
            FishingSlot(level=10, species=118, rod=RodKind.GOOD),
        ),
        by_map={42: (FishingSlot(level=15, species=116, rod=RodKind.SUPER),)},
    )

    assert {slot.species for slot in tables.at(42)} == {129, 118, 116}
    assert {slot.species for slot in tables.at(7)} == {129, 118}
    assert tables.species() == frozenset({129, 118, 116})


def test_a_cartridge_whose_fishing_code_moved_is_refused() -> None:
    """A table read at the wrong address still returns bytes.

    The offsets name instructions, so a cartridge that does not carry those
    instructions must fail by name rather than decode whatever is there.
    """

    with pytest.raises(CartridgeReadError):
        fishing_tables(bytes(0x50000))
