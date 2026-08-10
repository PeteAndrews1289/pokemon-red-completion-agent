"""The map header decoder, exercised against bytes laid out by hand.

``test_gen1_maps`` checks what the real cartridge contains, by comparing a
recorded read against structures maintained independently. It cannot check the
*decoder*: mutate the connection stride or swap two headings and the recorded
file still says what it always said, so those tests stay green while the parser
is broken. That is the failure this repository keeps rediscovering, and the
answer is a cartridge small enough to write out and assert against.

Every map below is fictional. The point is the layout, not Kanto.
"""

from __future__ import annotations

import pytest

from pokemon_red_completion.gen1_cartridge import CartridgeReadError, bank_offset
from pokemon_red_completion.gen1_maps import (
    MAP_HEADER_BANKS,
    MAP_HEADER_POINTERS,
    RETURN_TO_LAST_MAP,
    ConnectionGeometry,
    Heading,
    PassageKind,
    read_map_graph,
    routes_between,
    verify_against_encounter_reads,
)

ROM_BYTES = 0x10000
BANK = 1  # in bank 1 a banked address equals its flat offset, which keeps the
# fixtures readable: a header written at $4100 is at byte 0x4100.

#: The layout, stated here independently of the module under test.
#:
#: Deliberately not imported. A fixture that lays out bytes using the same
#: constants the decoder reads them back with cannot fail: swap two headings in
#: the module and the fixture swaps with it, and the test stays green while the
#: game gets a wrong map. These four lines are a second opinion, and they are
#: the only reason the heading and stride assertions below mean anything.
WRITE_ORDER = (Heading.NORTH, Heading.SOUTH, Heading.WEST, Heading.EAST)
BIT_FOR = {Heading.NORTH: 3, Heading.SOUTH: 2, Heading.WEST: 1, Heading.EAST: 0}
CONNECTION_WIDTH = 11
WARP_WIDTH = 4


class Cartridge:
    """A ROM with nothing in it but the map tables under test."""

    def __init__(self) -> None:
        self.data = bytearray(ROM_BYTES)
        self.next_free = 0x4100

    def add(
        self,
        map_id: int,
        *,
        size: tuple[int, int] = (4, 5),
        tileset: int = 0,
        connections: dict[Heading, int] | None = None,
        warps: tuple[tuple[int, int, int, int], ...] = (),
    ) -> None:
        """Write one map: its header, its connections and its warps."""

        connections = connections or {}
        header = self.next_free
        flags = 0
        for heading in connections:
            flags |= 1 << BIT_FOR[heading]

        body = bytearray()
        body.append(tileset)
        body.append(size[0])
        body.append(size[1])
        body.extend(b"\x00" * 6)  # block, text and script pointers
        body.append(flags)
        # Positional: the structs carry no heading of their own, so which one
        # is north is decided entirely by the order they are written in.
        for heading in WRITE_ORDER:
            if heading in connections:
                destination = connections[heading]
                destination_width = size[1]
                if heading is Heading.NORTH:
                    geometry = (size[1], destination_width, size[0] * 2 - 1, 0)
                elif heading is Heading.SOUTH:
                    geometry = (size[1], destination_width, 0, 0)
                elif heading is Heading.WEST:
                    geometry = (size[0], destination_width, 0, size[1] * 2 - 1)
                else:
                    geometry = (size[0], destination_width, 0, 0)
                # The pointer bytes are distinctive noise. Geometry begins at
                # byte five, so a decoder using the wrong eleven-byte stride
                # will not accidentally read another plausible destination.
                body.extend(
                    bytes(
                        (
                            destination,
                            0x11,
                            0x22,
                            0x33,
                            0x44,
                            *geometry,
                            0x55,
                            0x66,
                        )
                    )
                )
                assert len(body) >= CONNECTION_WIDTH

        objects = header + len(body) + 2
        body.extend(objects.to_bytes(2, "little"))
        self.data[header : header + len(body)] = body

        doors = bytearray([0, len(warps)])
        for y, x, destination_warp, destination in warps:
            doors.extend([y, x, destination_warp, destination])
            assert len(doors) % WARP_WIDTH == 2, "a warp is four bytes wide"
        self.data[objects : objects + len(doors)] = doors

        self.data[MAP_HEADER_BANKS + map_id] = BANK
        at = MAP_HEADER_POINTERS + 2 * map_id
        self.data[at : at + 2] = header.to_bytes(2, "little")
        self.next_free = objects + len(doors) + 1

    def bytes(self) -> bytes:
        # Every slot not written above must decode as unused, or the reader
        # would treat a run of zeroes as map 0 repeated 248 times.
        for map_id in range(248):
            at = MAP_HEADER_POINTERS + 2 * map_id
            if self.data[at : at + 2] == b"\x00\x00":
                self.data[at : at + 2] = (0x7FF0).to_bytes(2, "little")
                self.data[MAP_HEADER_BANKS + map_id] = BANK
                self.data[bank_offset(BANK, 0x7FF0) + 9] = 0xFF  # not a header
        return bytes(self.data)


def test_a_connection_is_decoded_with_its_heading() -> None:
    """North must come out north. The structs are positional, so an order
    mistake silently pairs a map with the wrong neighbour."""

    cartridge = Cartridge()
    cartridge.add(0, connections={Heading.NORTH: 1})
    cartridge.add(1, connections={Heading.SOUTH: 0})

    graph = read_map_graph(cartridge.bytes())

    assert set(graph) == {0, 1}
    (north,) = graph[0].passages
    assert north.heading is Heading.NORTH
    assert north.to_map == 1
    assert north.kind is PassageKind.CONNECTION
    assert north.connection == ConnectionGeometry(
        strip_length=5,
        destination_width=5,
        y_alignment=7,
        x_alignment=0,
    )
    assert north.coordinate_transitions[0].exit_at == (0, 0)
    assert north.coordinate_transitions[0].arrival_at == (7, 0)
    assert north.coordinate_transitions[-1].exit_at == (0, 9)
    assert north.coordinate_transitions[-1].arrival_at == (7, 9)
    (south,) = graph[1].passages
    assert south.heading is Heading.SOUTH
    assert south.to_map == 0


def test_all_four_headings_survive_together() -> None:
    """With several connections the struct stride decides which is which.

    A stride that is off by one still yields four plausible neighbours, so this
    is the assertion that catches it.
    """

    cartridge = Cartridge()
    cartridge.add(
        0,
        connections={
            Heading.NORTH: 1,
            Heading.SOUTH: 2,
            Heading.WEST: 3,
            Heading.EAST: 4,
        },
    )
    cartridge.add(1, connections={Heading.SOUTH: 0})
    cartridge.add(2, connections={Heading.NORTH: 0})
    cartridge.add(3, connections={Heading.EAST: 0})
    cartridge.add(4, connections={Heading.WEST: 0})

    graph = read_map_graph(cartridge.bytes())

    assert {p.heading: p.to_map for p in graph[0].passages} == {
        Heading.NORTH: 1,
        Heading.SOUTH: 2,
        Heading.WEST: 3,
        Heading.EAST: 4,
    }


def test_a_warp_carries_the_block_it_is_stood_on() -> None:
    """Its coordinates are what makes a warp actionable rather than notional."""

    cartridge = Cartridge()
    cartridge.add(0, warps=((5, 13, 0, 1),))
    cartridge.add(1, warps=((7, 2, 0, 0),))

    graph = read_map_graph(cartridge.bytes())

    (door,) = graph[0].passages
    assert door.kind is PassageKind.WARP
    assert door.to_map == 1
    assert door.at == (5, 13)
    assert door.arrival_at == (7, 2)
    assert door.destination_warp_index == 0


def test_a_warp_arrival_uses_its_destination_index() -> None:
    """The third byte selects a target event; it is not padding."""

    cartridge = Cartridge()
    cartridge.add(0, warps=((5, 13, 1, 1),))
    cartridge.add(
        1,
        tileset=1,
        warps=((1, 2, 0, 200), (7, 8, 0, 201)),
    )

    graph = read_map_graph(cartridge.bytes())

    (door,) = graph[0].passages
    assert door.destination_warp_index == 1
    assert door.arrival_at == (7, 8)


def test_several_doors_on_one_map_are_kept_apart() -> None:
    """The stride only matters past the first door.

    With a single warp per map the four-byte spacing is never exercised: index
    zero reads the same bytes whatever the stride is. A town with three
    buildings is the smallest fixture that can tell a correct stride from a
    wrong one, and the first draft of this file did not have one.
    """

    cartridge = Cartridge()
    cartridge.add(0, warps=((2, 3, 0, 1), (4, 5, 0, 2), (6, 7, 0, 3)))
    for interior in (1, 2, 3):
        cartridge.add(interior, tileset=1, warps=((0, 0, 0, RETURN_TO_LAST_MAP),))

    graph = read_map_graph(cartridge.bytes())

    assert {(p.at, p.to_map) for p in graph[0].passages} == {
        ((2, 3), 1),
        ((4, 5), 2),
        ((6, 7), 3),
    }


def test_an_interior_returns_to_whichever_map_led_in() -> None:
    """Two towns, one shop. The way out names no destination at all.

    Read literally the shop is a trap with no exit; the back edges exist only
    in the maps that point at it.
    """

    cartridge = Cartridge()
    cartridge.add(0, connections={Heading.NORTH: 1}, warps=((1, 1, 0, 2),))
    cartridge.add(1, connections={Heading.SOUTH: 0}, warps=((2, 2, 0, 2),))
    cartridge.add(2, tileset=1, warps=((3, 3, 0, RETURN_TO_LAST_MAP),))

    graph = read_map_graph(cartridge.bytes())

    assert graph[2].neighbours() == frozenset()
    (return_warp,) = graph[2].passages
    assert return_warp.kind is PassageKind.RETURN
    assert return_warp.at == (3, 3)
    assert return_warp.to_map is None
    assert return_warp.destination_warp_index == 0


def test_a_boundary_return_records_the_outward_action() -> None:
    cartridge = Cartridge()
    cartridge.add(0, warps=((1, 1, 0, 2),))
    cartridge.add(
        2,
        size=(4, 5),
        tileset=1,
        warps=((7, 3, 0, RETURN_TO_LAST_MAP),),
    )

    graph = read_map_graph(cartridge.bytes())

    (return_warp,) = graph[2].passages
    assert return_warp.at == (7, 3)
    assert return_warp.exit_action == "down"


def test_a_nested_interior_return_keeps_the_outdoor_map() -> None:
    """The immediate previous map is not what ``LAST_MAP`` means."""

    cartridge = Cartridge()
    cartridge.add(0, warps=((1, 1, 0, 2),))
    cartridge.add(2, tileset=1, warps=((2, 2, 0, 3),))
    cartridge.add(3, tileset=1, warps=((3, 3, 0, RETURN_TO_LAST_MAP),))

    graph = read_map_graph(cartridge.bytes())

    assert routes_between(graph, 2, 0, last_outside=0) == (2, 3, 0)
    assert routes_between(graph, 2, 3, last_outside=0) == (2, 3)


def test_a_warp_to_a_slot_holding_no_map_is_marked_not_dropped() -> None:
    """A lift picks its floor at runtime, so the data cannot name one."""

    cartridge = Cartridge()
    cartridge.add(0, warps=((1, 1, 0, 1),))
    cartridge.add(1, warps=((2, 2, 0, 200),))  # slot 200 was never written

    graph = read_map_graph(cartridge.bytes())

    (exit_,) = graph[1].passages
    assert exit_.kind is PassageKind.SCRIPTED
    assert exit_.to_map is None
    assert exit_.at == (2, 2)
    assert graph[1].has_a_scripted_exit
    assert 200 not in graph


def test_a_connection_only_one_slot_claims_never_enters_the_graph() -> None:
    """Reciprocity is the filter that removes unused slots.

    An unused slot decodes into plausible-looking rubbish, and here that rubbish
    claims map 0 as a northern neighbour. Map 0 says nothing of the kind, so the
    claim is not a connection: the slot stays out of the world and map 0 gains
    no edge to it.
    """

    cartridge = Cartridge()
    cartridge.add(0, warps=((1, 1, 0, 1),))
    cartridge.add(1, warps=((1, 1, 0, 0),))
    cartridge.add(50, connections={Heading.NORTH: 0})

    graph = read_map_graph(cartridge.bytes())

    assert set(graph) == {0, 1}
    assert 50 not in graph[0].neighbours()


def test_a_one_sided_connection_on_a_reachable_map_refuses_the_read() -> None:
    """The same discard, but where it means the decode is wrong.

    Map 1 is reachable through a warp, so it is a real map, and a real map with
    a connection the far side denies means the headers were misread.
    """

    cartridge = Cartridge()
    cartridge.add(0, connections={Heading.NORTH: 1}, warps=((1, 1, 0, 1),))
    cartridge.add(1, connections={Heading.NORTH: 0}, warps=((1, 1, 0, 0),))

    with pytest.raises(CartridgeReadError, match="read wrongly"):
        read_map_graph(cartridge.bytes())


def test_only_maps_reachable_from_the_start_are_in_the_graph() -> None:
    """An island nobody can get to is not part of the world."""

    cartridge = Cartridge()
    cartridge.add(0, warps=((1, 1, 0, 1),))
    cartridge.add(1, warps=((1, 1, 0, 0),))
    cartridge.add(50, warps=((1, 1, 0, 51),))
    cartridge.add(51, warps=((1, 1, 0, 50),))

    graph = read_map_graph(cartridge.bytes())

    assert set(graph) == {0, 1}


def test_a_map_size_is_read_from_its_header() -> None:
    """Height and width sit either side of the tileset byte."""

    cartridge = Cartridge()
    cartridge.add(0, size=(9, 10))

    graph = read_map_graph(cartridge.bytes())

    assert (graph[0].height, graph[0].width) == (9, 10)


def test_an_encounter_map_that_cannot_be_reached_refuses_the_read() -> None:
    """Two independent reads of one cartridge have to agree."""

    verify_against_encounter_reads(
        reachable={0, 1, 2}, named_maps={0}, with_wild_tables={1}, fishable={2}
    )

    with pytest.raises(CartridgeReadError, match="observation contract"):
        verify_against_encounter_reads(
            reachable={0, 1}, named_maps={0, 9}, with_wild_tables=set(), fishable=set()
        )

    with pytest.raises(CartridgeReadError, match="wild encounter tables"):
        verify_against_encounter_reads(
            reachable={0, 1}, with_wild_tables={1, 9}, fishable=set()
        )
    with pytest.raises(CartridgeReadError, match="Super Rod"):
        verify_against_encounter_reads(
            reachable={0, 1}, with_wild_tables=set(), fishable={4}
        )
