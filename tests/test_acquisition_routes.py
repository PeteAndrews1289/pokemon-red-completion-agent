"""Every way a cartridge yields a species, and why grass alone is not enough.

A living Pokédex is a question about acquisition, not about encounters. This
repository learned the difference the expensive way: it compared the two
cartridges' wild tables, found ten species on each side, and recorded ten
version exclusives. The real number is eleven, and the wild-table comparison was
wrong in both directions at once -- it counted four species that are not
exclusive and missed six that are.

These tests hold that accounting. They need no ROM: the reads are the
measurement and live in ``docs/evidence/acquisition-routes-2026-08-11.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_red_completion.gen1_cartridge import (
    IN_GAME_TRADE_COUNT,
    IN_GAME_TRADE_TABLE,
    INTERNAL_TO_DEX_TABLE,
    CartridgeReadError,
    Evolution,
    EvolutionMethod,
    FishingSlot,
    FishingTables,
    RodKind,
    fishing_tables,
    grow_collection,
    in_game_trades,
)
from pokemon_red_completion.generation_one import UNAVAILABLE_IN_BLUE, UNAVAILABLE_IN_RED

RECORD = Path("docs/evidence/acquisition-routes-2026-08-11.json")


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
        alone = set(record["by_title"][title]["reachable_through_parsed_routes_alone"])
        partnered = set(
            record["by_title"][title][
                "reachable_through_parsed_routes_with_a_trade_partner"
            ]
        )
        assert partnered - alone == {65, 68, 76, 94}


def test_parsed_route_reach_states_its_exact_choice_boundary(record: dict) -> None:
    assert "every ordinary retail-cartridge species route" in record["interpretation"]
    assert "not which mutually exclusive choices coexist" in record["interpretation"]
    assert "Mew remains absent" in record["interpretation"]
    assert "every decoded rod" in record["interpretation"]


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


def test_four_species_come_only_from_a_person_in_the_world(record: dict) -> None:
    """Farfetch'd, Lickitung, Mr. Mime and Jynx.

    None appears in a wild table, on a rod, or at the end of any evolution. A
    planner that knows every encounter table in the game and nothing else will
    never obtain them, and a Pokédex counted without them is short by four.
    """

    for title in ("red", "blue"):
        found = record["by_title"][title]
        assert found["species_only_an_in_game_trade_supplies"] == [83, 108, 122, 124]
        for species in (83, 108, 122, 124):
            assert species not in found["wild_table_species"]
            assert species not in found["rod_species"]
            assert species not in found["catchable"]
            assert species in found["reachable_through_parsed_routes_alone"]


def test_a_trade_reward_that_can_be_caught_anyway_is_not_trade_only(record: dict) -> None:
    """Beedrill is a trade reward and is not on that list.

    It is what a caught Weedle grows into, so the trade is a convenience. The
    first version of this accounting called it trade-only, which would have
    made a planner spend a Butterfree it did not need to.
    """

    trades = record["by_title"]["red"]["in_game_trades"]
    rewards = {trade["get"] for trade in trades}

    assert 15 in rewards
    assert 15 not in record["by_title"]["red"]["species_only_an_in_game_trade_supplies"]
    assert 15 in record["by_title"]["red"]["reachable_through_parsed_routes_alone"]


def test_a_trade_costs_a_specimen(record: dict) -> None:
    """Every swap names what it takes as well as what it gives.

    A living collection has to keep one of everything, so a trade that spends
    its only specimen of the given species is a step backwards unless a second
    can be caught. Recording both halves is what lets a plan notice.
    """

    trades = record["by_title"]["red"]["in_game_trades"]

    assert len(trades) == 10
    assert all(trade["give"] != trade["get"] for trade in trades)
    assert all(trade["nickname"] for trade in trades)
    assert {t["nickname"] for t in trades if t["get"] == 83} == {"DUX"}


def test_both_cartridges_offer_the_same_trades(record: dict) -> None:
    assert (
        record["by_title"]["red"]["in_game_trades"]
        == record["by_title"]["blue"]["in_game_trades"]
    )


def test_a_cartridge_whose_trade_table_moved_is_refused() -> None:
    """Ten entries read from a blank cartridge must fail, not return ten blanks."""

    with pytest.raises(CartridgeReadError):
        in_game_trades(bytes(0x80000))


# --------------------------------------------------------------------------
# The decoder itself, against bytes laid out by hand.
#
# Everything above reads the committed record, and a record compared against
# itself agrees with any bug: swap give and get in the reader, or shorten the
# stride, and every assertion above stays green. This repository has now found
# that same hole in three separate readers, so the decoding gets its own
# cartridge, small enough to write out and assert against.
# --------------------------------------------------------------------------

ROM_BYTES = 0x80000
UPPERCASE_A = 0x80
TEXT_END = 0x50

#: The entry layout, stated here rather than imported.
#:
#: A fixture that writes bytes with the same stride the decoder reads them back
#: with cannot fail -- change the module constant and the fixture changes with
#: it. These two lines are the second opinion that makes the stride assertions
#: mean something.
STRIDE = 14
NICKNAME_BYTES = 11


def encoded(name: str) -> bytes:
    """A nickname the way the cartridge stores it, which is not ASCII."""

    return bytes(UPPERCASE_A + ord(letter) - ord("A") for letter in name) + bytes(
        [TEXT_END] * (NICKNAME_BYTES - len(name))
    )


def trade_cartridge(
    entries: list[tuple[int, int, str]], *, eleventh: tuple[int, int, str] | None = None
) -> bytes:
    """A ROM holding a species table and a trade table, and nothing else."""

    data = bytearray(ROM_BYTES)
    # A complete one-to-one species map with the four independently stated
    # anchors. Start from identity and swap values rather than overwriting them:
    # overwriting creates a duplicate and silently drops one Pokédex number.
    mapping = [*range(1, 152), *([0] * 39)]
    for internal, expected in {0x1C: 9, 0x3B: 50, 0x76: 51, 0x84: 143}.items():
        previous = mapping[internal - 1]
        owner = mapping.index(expected)
        mapping[owner] = previous
        mapping[internal - 1] = expected
    data[INTERNAL_TO_DEX_TABLE : INTERNAL_TO_DEX_TABLE + len(mapping)] = bytes(mapping)

    written = list(entries)
    if eleventh is not None:
        written.append(eleventh)
    for index, (give, get, nickname) in enumerate(written):
        at = IN_GAME_TRADE_TABLE + STRIDE * index
        data[at] = give
        data[at + 1] = get
        data[at + 2] = 0
        data[at + 3 : at + 3 + NICKNAME_BYTES] = encoded(nickname)
    return bytes(data)


TEN = [(0x0F + n, 0x40 + n, f"NAME{chr(ord('A') + n)}") for n in range(IN_GAME_TRADE_COUNT)]


def test_the_reader_keeps_what_is_given_apart_from_what_is_got() -> None:
    """The two are adjacent bytes, and swapping them reverses every trade.

    A planner working from a reversed table would hand over the species it was
    trying to collect.
    """

    trades = in_game_trades(trade_cartridge(TEN))

    assert len(trades) == IN_GAME_TRADE_COUNT
    assert trades[0].give_species == 0x0F
    assert trades[0].get_species == 0x40
    assert trades[0].nickname == "NAMEA"


def test_every_trade_is_read_from_its_own_fourteen_bytes() -> None:
    """A stride mistake makes later trades drift into their neighbours."""

    trades = in_game_trades(trade_cartridge(TEN))

    assert [t.give_species for t in trades] == [0x0F + n for n in range(10)]
    assert [t.get_species for t in trades] == [0x40 + n for n in range(10)]
    assert [t.nickname for t in trades] == [f"NAME{chr(ord('A') + n)}" for n in range(10)]


def test_an_eleventh_trade_means_the_count_is_wrong() -> None:
    """Reading ten from a longer table would parse cleanly and drop the rest."""

    with pytest.raises(CartridgeReadError, match="more than 10"):
        in_game_trades(trade_cartridge(TEN, eleventh=(0x05, 0x40, "EXTRA")))


def test_a_swap_of_a_species_for_itself_is_not_a_trade() -> None:
    with pytest.raises(CartridgeReadError, match="for itself"):
        in_game_trades(trade_cartridge([(0x02, 0x02, "SAME"), *TEN[1:]]))


def test_an_unreadable_nickname_means_the_stride_is_wrong() -> None:
    rom = bytearray(trade_cartridge(TEN))
    rom[IN_GAME_TRADE_TABLE + 3] = 0x00  # not a letter and not a terminator

    with pytest.raises(CartridgeReadError, match="nickname"):
        in_game_trades(bytes(rom))


def test_a_trade_is_only_worth_something_if_its_price_can_be_paid() -> None:
    """Reachability must not grant a reward nobody can hand anything over for.

    Same conditional the campaign model applies to trade evolutions, and for the
    same reason: a plan that cannot produce the price cannot produce the reward.
    """

    swaps = {30: 20, 40: 99}

    grown = grow_collection({20}, evolutions={}, swaps=swaps)

    assert grown == {20, 30}, "the swap whose price is missing pays out nothing"


def test_evolution_and_trading_compound() -> None:
    """Why the closure loops instead of applying each route once.

    Catch 1, evolve it into 2, swap 2 for 3, evolve 3 into 4. A single pass in
    either order stops early and undercounts what a cartridge can reach.
    """

    evolutions = {
        1: (Evolution(1, 2, EvolutionMethod.LEVEL, 16),),
        3: (Evolution(3, 4, EvolutionMethod.LEVEL, 32),),
    }

    grown = grow_collection({1}, evolutions=evolutions, swaps={3: 2})

    assert grown == {1, 2, 3, 4}


def test_a_trade_evolution_needs_a_second_save_but_an_in_game_swap_does_not() -> None:
    """The two are different costs and must not be collapsed.

    A person in the world will swap with one cartridge. Making a Machamp needs
    two running at once.
    """

    evolutions = {1: (Evolution(1, 2, EvolutionMethod.TRADE),)}

    alone = grow_collection({1}, evolutions=evolutions, swaps={9: 1})
    partnered = grow_collection({1}, evolutions=evolutions, swaps={9: 1}, with_trade_partner=True)

    assert alone == {1, 9}, "the swap happens, the trade evolution does not"
    assert partnered == {1, 2, 9}


def test_a_cartridge_whose_fishing_code_moved_is_refused() -> None:
    """A table read at the wrong address still returns bytes.

    The offsets name instructions, so a cartridge that does not carry those
    instructions must fail by name rather than decode whatever is there.
    """

    with pytest.raises(CartridgeReadError):
        fishing_tables(bytes(0x50000))
