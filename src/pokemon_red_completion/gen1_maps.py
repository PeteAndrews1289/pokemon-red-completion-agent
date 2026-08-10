"""Read Kanto's map graph out of a cartridge instead of hand-writing it.

This is the structure that decides whether "plays every mainline title" is a
finite project. Every chapter module in this repository is hand-written walk
directions -- press UP eleven times, then RIGHT four -- and a route written that
way is worth nothing to the next game. Until a route can be *computed*, each
title costs one hand-authored path per objective and the work never converges.

The cartridge already contains the graph. Each map carries a header naming its
size and its up-to-four edge connections, and an object block listing the warps
-- the doors, stairs and ladders that join interiors to the overworld.

How the offsets were found
==========================

Both tables were located by brute search, not transcription. ``MAP_HEADER_
POINTERS`` is the only place in the ROM where 248 consecutive little-endian
words all fall inside the switchable bank window, other than the wild-encounter
array already known; ``MAP_HEADER_BANKS`` is a run of 248 plausible bank
numbers. The pair was then confirmed by an invariant no wrong offset can meet:
map connections must be **reciprocal**. If Pallet Town leaves north into Route
1, Route 1 must leave south into Pallet Town. Seventy-eight connections satisfy
that on both cartridges, and they are the same seventy-eight.

What is dropped, and why that is safe
=====================================

Not all 248 slots are maps. A handful are unused, and reading a header from one
returns bytes that decode into plausible-looking garbage. Those slots are the
only source of non-reciprocal connections, so reciprocity doubles as the filter.

Silently discarding data is exactly the sort of quiet fudge that hides bugs, so
the discard is checked rather than trusted: every non-reciprocal connection must
belong to a slot that is **unreachable** from Pallet Town. A real map with a
one-sided connection would mean the read is wrong, and raises.

Three further checks tie the graph to structures derived elsewhere: every map
the observation contract names, every map with a wild encounter table, and every
map the Super Rod names must be reachable from Pallet Town. Those come from
independent reads, so agreement between them is evidence rather than restatement.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.gen1_cartridge import (
    MAP_ID_LIMIT,
    CartridgeReadError,
    bank_offset,
    fishing_tables,
    wild_tables,
)
from pokemon_red_completion.global_router import (
    GlobalRouterError,
    MacroEdge,
    MacroGraph,
    find_macro_route,
)
from pokemon_red_completion.observation import MapId

MAP_HEADER_POINTERS = 0x01AE
MAP_HEADER_BANKS = 0xC23D
CONNECTION_FLAGS_OFFSET = 9
CONNECTION_STRUCT_BYTES = 11
CONNECTION_FLAG_LIMIT = 0x0F
WARP_STRUCT_BYTES = 4
WARP_COUNT_LIMIT = 32

#: A warp whose destination is this returns to whichever map warped in. Shops
#: and Pokémon Centres use it because one interior serves many towns, so the
#: back edge is only knowable from the maps that point at it.
RETURN_TO_LAST_MAP = 0xFF

#: Where a run begins, and the root every reachability check is measured from.
STARTING_MAP = 0


class Heading(StrEnum):
    """Which edge of a map a connection leaves by."""

    NORTH = "north"
    SOUTH = "south"
    WEST = "west"
    EAST = "east"

    @property
    def opposite(self) -> Heading:
        return _OPPOSITE[self]


_OPPOSITE = {
    Heading.NORTH: Heading.SOUTH,
    Heading.SOUTH: Heading.NORTH,
    Heading.WEST: Heading.EAST,
    Heading.EAST: Heading.WEST,
}

#: The order the connection structs are written in, with the bit that announces
#: each. Reading them out of order silently pairs a map with the wrong neighbour.
CONNECTION_ORDER = (
    (Heading.NORTH, 3),
    (Heading.SOUTH, 2),
    (Heading.WEST, 1),
    (Heading.EAST, 0),
)


class PassageKind(StrEnum):
    """How one map is left for another.

    The distinction is not cosmetic. Walking off an edge needs no target tile --
    any point along the shared border does -- while a warp is a single square
    that has to be stood on. A router that treats them alike cannot produce
    directions for either.

    ``SCRIPTED`` is an exit whose destination the cartridge does not state: the
    lifts point at a slot that holds no map, because the floor is chosen from a
    menu at runtime. Recording it as its own kind keeps a real exit visible
    instead of quietly discarding it and leaving a lift looking like a dead end.
    """

    CONNECTION = "connection"
    WARP = "warp"
    SCRIPTED = "scripted"


@dataclass(frozen=True, slots=True)
class Passage:
    """One way out of a map."""

    #: ``None`` for a scripted exit, where the destination is decided in play.
    to_map: int | None
    kind: PassageKind
    #: Set for a connection: which edge to leave by.
    heading: Heading | None = None
    #: Set for a warp: the ``(y, x)`` block the player must stand on.
    at: tuple[int, int] | None = None
    #: Set only for ``$FF`` return warps. The passage is legal when the map was
    #: entered from this origin, not merely because that origin can enter it.
    return_origin: int | None = None

    @property
    def is_warp(self) -> bool:
        return self.kind is PassageKind.WARP

    @property
    def leads_somewhere_known(self) -> bool:
        return self.to_map is not None


@dataclass(frozen=True, slots=True)
class MapNode:
    """One map, its size, and everywhere it leads."""

    map_id: int
    height: int
    width: int
    passages: tuple[Passage, ...]

    def neighbours(self) -> frozenset[int]:
        return frozenset(
            passage.to_map for passage in self.passages if passage.to_map is not None
        )

    @property
    def has_a_scripted_exit(self) -> bool:
        """Whether some way out of here cannot be planned from static data."""

        return any(passage.kind is PassageKind.SCRIPTED for passage in self.passages)


def read_map_graph(rom: bytes) -> dict[int, MapNode]:
    """Decode the map headers, keeping only what both endpoints agree on.

    Separate from :func:`map_graph` so that the decoding can be exercised
    against bytes laid out by hand. A parser whose only test compares a recorded
    output against itself is a parser nothing checks: break the struct stride or
    swap two connection headings and such a test stays green, which is the
    defect this repository keeps finding in its own suites.
    """

    headers, warps, one_sided = _read_headers(rom)
    passages = _assemble(headers, warps)
    reachable = _reachable_from(STARTING_MAP, passages)
    verify_connections_are_two_sided(reachable, one_sided)
    return {
        map_id: MapNode(
            map_id=map_id,
            height=headers[map_id][0],
            width=headers[map_id][1],
            passages=tuple(passages.get(map_id, ())),
        )
        for map_id in sorted(reachable)
        if map_id in headers
    }


def map_graph(rom: bytes) -> dict[int, MapNode]:
    """Every map that can be reached from the start, and everywhere it leads.

    Keyed by map id, which is the same identifier the emulator reports in
    ``wCurMap`` -- so a route computed here can be checked against a running
    game without a translation table in between.
    """

    graph = read_map_graph(rom)
    verify_against_encounter_reads(
        reachable=set(graph),
        named_maps={item.value for item in MapId},
        with_wild_tables=set(wild_tables(rom)),
        fishable=set(fishing_tables(rom).by_map),
    )
    return graph


def _read_headers(
    rom: bytes,
) -> tuple[
    dict[int, tuple[int, int, dict[Heading, int]]],
    dict[int, list[tuple[int, int, int]]],
    list[tuple[int, Heading, int]],
]:
    """Decode every slot, keeping only connections both endpoints agree on."""

    raw: dict[int, tuple[int, int, dict[Heading, int]]] = {}
    warps: dict[int, list[tuple[int, int, int]]] = {}
    for map_id in range(MAP_ID_LIMIT):
        bank = rom[MAP_HEADER_BANKS + map_id]
        at = MAP_HEADER_POINTERS + 2 * map_id
        address = int.from_bytes(rom[at : at + 2], "little")
        if not 0x4000 <= address <= 0x7FFF or bank * 0x4000 >= len(rom):
            continue
        header = bank_offset(bank, address)
        flags = rom[header + CONNECTION_FLAGS_OFFSET]
        if flags > CONNECTION_FLAG_LIMIT:
            continue  # an unused slot; its bytes are not a header
        cursor = header + CONNECTION_FLAGS_OFFSET + 1
        found: dict[Heading, int] = {}
        for heading, bit in CONNECTION_ORDER:
            if flags & (1 << bit):
                found[heading] = rom[cursor]
                cursor += CONNECTION_STRUCT_BYTES
        raw[map_id] = (rom[header + 1], rom[header + 2], found)
        warps[map_id] = _read_warps(rom, bank, cursor)

    kept: dict[int, tuple[int, int, dict[Heading, int]]] = {}
    one_sided: list[tuple[int, Heading, int]] = []
    for map_id, (height, width, found) in raw.items():
        agreed: dict[Heading, int] = {}
        for heading, other in found.items():
            neighbour = raw.get(other)
            if neighbour is not None and neighbour[2].get(heading.opposite) == map_id:
                agreed[heading] = other
            else:
                one_sided.append((map_id, heading, other))
        kept[map_id] = (height, width, agreed)
    return kept, warps, one_sided


def _read_warps(rom: bytes, bank: int, cursor: int) -> list[tuple[int, int, int]]:
    """The ``(y, x, destination)`` of each door on one map."""

    objects = int.from_bytes(rom[cursor : cursor + 2], "little")
    if not 0x4000 <= objects <= 0x7FFF:
        return []
    at = bank_offset(bank, objects)
    count = rom[at + 1]
    if count > WARP_COUNT_LIMIT:
        return []
    body = at + 2
    return [
        (
            rom[body + WARP_STRUCT_BYTES * index],
            rom[body + WARP_STRUCT_BYTES * index + 1],
            rom[body + WARP_STRUCT_BYTES * index + 3],
        )
        for index in range(count)
    ]


def _assemble(
    headers: Mapping[int, tuple[int, int, dict[Heading, int]]],
    warps: Mapping[int, list[tuple[int, int, int]]],
) -> dict[int, list[Passage]]:
    """Turn agreed connections and warps into one list of exits per map."""

    passages: dict[int, list[Passage]] = {}
    for map_id, (_, _, found) in headers.items():
        for heading, other in found.items():
            passages.setdefault(map_id, []).append(
                Passage(to_map=other, kind=PassageKind.CONNECTION, heading=heading)
            )

    # Who enters each interior, so a "return to last map" warp can be resolved.
    entered: dict[int, set[int]] = {}
    for map_id, doors in warps.items():
        for _, _, destination in doors:
            if destination != RETURN_TO_LAST_MAP and destination in headers:
                entered.setdefault(destination, set()).add(map_id)

    for map_id, doors in warps.items():
        for y, x, destination in doors:
            if destination != RETURN_TO_LAST_MAP:
                kind = PassageKind.WARP if destination in headers else PassageKind.SCRIPTED
                passages.setdefault(map_id, []).append(
                    Passage(
                        to_map=destination if kind is PassageKind.WARP else None,
                        kind=kind,
                        at=(y, x),
                    )
                )
                continue
            # One interior can serve many towns, so the way out is every map
            # that leads in. Dropping these would strand every Pokémon Centre.
            for origin in sorted(entered.get(map_id, ())):
                passages.setdefault(map_id, []).append(
                    Passage(
                        to_map=origin,
                        kind=PassageKind.WARP,
                        at=(y, x),
                        return_origin=origin,
                    )
                )
    return passages


def _reachable_from(start: int, passages: Mapping[int, list[Passage]]) -> set[int]:
    start_state = (start, None)
    seen_states: set[tuple[int, int | None]] = {start_state}
    seen_maps = {start}
    frontier: list[tuple[int, int | None]] = [start_state]
    while frontier:
        node, entry_origin = frontier.pop()
        for passage in passages.get(node, ()):
            if passage.to_map is None:
                continue
            if passage.return_origin is not None and passage.return_origin != entry_origin:
                continue
            following = (passage.to_map, node)
            if following in seen_states:
                continue
            seen_states.add(following)
            seen_maps.add(passage.to_map)
            frontier.append(following)
    return seen_maps


def verify_connections_are_two_sided(
    reachable: set[int], one_sided: Iterable[tuple[int, Heading, int]]
) -> None:
    """Refuse a read in which a real map has a connection the far side denies.

    Reciprocity is what proves the header offsets, and it doubles as the filter
    that removes unused slots -- so the filter has to be held to account. A
    one-sided connection is only ever allowed to come from a slot no player can
    stand on. One belonging to a reachable map means the headers were read
    wrongly and the graph is fiction.

    Kept public and free of any ROM argument so this can be exercised directly.
    A guard reachable only through a full cartridge read is a guard whose test
    passes for whatever reason the cartridge happens to supply.
    """

    stranded = sorted({map_id for map_id, _, _ in one_sided} & reachable)
    if stranded:
        raise CartridgeReadError(
            f"maps {stranded} are reachable but carry a connection the other side does "
            "not return; one-sided connections are supposed to come only from unused "
            "slots, so the map headers were read wrongly"
        )


def verify_against_encounter_reads(
    *,
    reachable: set[int],
    with_wild_tables: set[int],
    fishable: set[int],
    named_maps: set[int] | None = None,
) -> None:
    """Refuse the read unless two independent reads of the cartridge agree.

    A map you can walk in, or fish on, has to be a map you can get to. Those
    two sets come from the wild-encounter and fishing structures, located and
    verified separately, so agreement is evidence rather than restatement.

    Takes sets rather than a ROM so the check can be exercised on its own.
    """

    for label, expected in (
        ("the observation contract", set() if named_maps is None else named_maps),
        ("wild encounter tables", with_wild_tables),
        ("the Super Rod", fishable),
    ):
        missing = sorted(expected - reachable)
        if missing:
            raise CartridgeReadError(
                f"maps {missing} appear in {label} but cannot be reached from the "
                "starting map; the two reads disagree, so one is wrong"
            )


def macro_graph(rom: bytes) -> MacroGraph:
    """The cartridge's map graph, in the form the game-neutral router consumes.

    This is the adapter seam. Everything Generation I knows about how Kanto is
    joined stops here, and what crosses over is a graph of integers and edges
    that a second title can produce just as well.
    """

    return macro_graph_from_nodes(map_graph(rom))


def macro_graph_from_nodes(graph: Mapping[int, MapNode]) -> MacroGraph:
    """Project decoded nodes without dropping the edge needed to act on a route."""

    return MacroGraph(
        edges={
            map_id: tuple(
                MacroEdge(
                    target_map=passage.to_map,
                    kind=passage.kind.value,
                    at=passage.at,
                    heading=passage.heading.value if passage.heading is not None else None,
                    return_origin=passage.return_origin,
                )
                for passage in node.passages
                if passage.to_map is not None
            )
            for map_id, node in graph.items()
        }
    )


def routes_between(graph: Mapping[int, MapNode], start: int, goal: int) -> tuple[int, ...]:
    """The shortest sequence of maps joining two points, or empty if none.

    Breadth-first because every passage costs the same here: a warp and an edge
    crossing are both one map transition. Weighting them by walking distance
    needs the block data, which is a separate read.
    """

    if start not in graph:
        raise CartridgeReadError(f"map {start} is not in the graph")
    routed = macro_graph_from_nodes(graph)
    try:
        return find_macro_route(routed, start, goal)
    except GlobalRouterError:
        return ()
