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
from dataclasses import dataclass, replace
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
    MacroTransition,
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
SCRIPT_POINTER_OFFSET = 7
LOAD_IMMEDIATE_A_OPCODE = 0x3E
STORE_A_ABSOLUTE_OPCODE = 0xEA
CALL_OPCODE = 0xCD
WLASTMAP_ADDRESS = 0xD365

#: A warp whose destination is this returns to whichever map warped in. Shops
#: and Pokémon Centres use it because one interior serves many towns, so the
#: back edge is only knowable from the maps that point at it.
RETURN_TO_LAST_MAP = 0xFF

#: Where a run begins, and the root every reachability check is measured from.
STARTING_MAP = 0

#: The engine retains ``wLastMap`` before a warp only for maps using one of
#: these two tilesets. The second is Indigo Plateau; treating every map entered
#: from outdoors as "outside" breaks nested buildings and underground paths.
OUTSIDE_TILESETS = frozenset({0, 23})


class Heading(StrEnum):
    """Which edge of a map a connection leaves by."""

    NORTH = "north"
    SOUTH = "south"
    WEST = "west"
    EAST = "east"

    @property
    def opposite(self) -> Heading:
        return _OPPOSITE[self]

    @property
    def action(self) -> str:
        return {
            Heading.NORTH: "up",
            Heading.SOUTH: "down",
            Heading.WEST: "left",
            Heading.EAST: "right",
        }[self]


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
    RETURN = "return"
    SCRIPTED = "scripted"


def _signed_byte(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


@dataclass(frozen=True, slots=True)
class ConnectionGeometry:
    """The coordinate fields of one eleven-byte connection record.

    Rendering pointers occupy the other bytes. These four fields are the ones
    the engine uses to reposition the player, and therefore the ones route
    composition needs. Alignments are retained as cartridge bytes so the read
    remains inspectable; the axis being adjusted is interpreted as signed.
    """

    strip_length: int
    destination_width: int
    y_alignment: int
    x_alignment: int

    def transitions(
        self,
        heading: Heading,
        *,
        source_size: tuple[int, int],
        destination_size: tuple[int, int],
    ) -> tuple[MacroTransition, ...]:
        """Every exact border coordinate accepted by this connection."""

        source_height, source_width = (dimension * 2 for dimension in source_size)
        destination_height, destination_width = (dimension * 2 for dimension in destination_size)
        if self.destination_width != destination_size[1]:
            raise CartridgeReadError(
                "a connection's destination width disagrees with its target header"
            )

        candidates: list[MacroTransition] = []
        if heading in (Heading.NORTH, Heading.SOUTH):
            source_y = 0 if heading is Heading.NORTH else source_height - 1
            destination_y = self.y_alignment
            x_adjustment = _signed_byte(self.x_alignment)
            for source_x in range(source_width):
                destination_x = source_x + x_adjustment
                if (
                    0 <= destination_y < destination_height
                    and 0 <= destination_x < destination_width
                ):
                    candidates.append(
                        MacroTransition(
                            exit_at=(source_y, source_x),
                            arrival_at=(destination_y, destination_x),
                            action=heading.action,
                        )
                    )
        else:
            source_x = 0 if heading is Heading.WEST else source_width - 1
            destination_x = self.x_alignment
            y_adjustment = _signed_byte(self.y_alignment)
            for source_y in range(source_height):
                destination_y = source_y + y_adjustment
                if (
                    0 <= destination_y < destination_height
                    and 0 <= destination_x < destination_width
                ):
                    candidates.append(
                        MacroTransition(
                            exit_at=(source_y, source_x),
                            arrival_at=(destination_y, destination_x),
                            action=heading.action,
                        )
                    )

        if not candidates:
            raise CartridgeReadError(
                f"a {heading.value} connection exposes no in-bounds coordinates"
            )
        return tuple(candidates)


@dataclass(frozen=True, slots=True)
class _Header:
    tileset: int
    height: int
    width: int
    connections: dict[Heading, tuple[int, ConnectionGeometry]]
    retained_outside_override: int | None = None


@dataclass(frozen=True, slots=True)
class _Warp:
    y: int
    x: int
    destination_warp_index: int
    destination_map: int

    @property
    def at(self) -> tuple[int, int]:
        return self.y, self.x


@dataclass(frozen=True, slots=True)
class Passage:
    """One way out of a map."""

    #: ``None`` for a scripted exit, where the destination is decided in play.
    to_map: int | None
    kind: PassageKind
    #: Set for a connection: which edge to leave by.
    heading: Heading | None = None
    #: Set for a boundary return: which direction walks out after reaching the
    #: warp coordinate. Entering that coordinate alone does not trigger Red.
    exit_action: str | None = None
    #: Set for a warp: the ``(y, x)`` block the player must stand on.
    at: tuple[int, int] | None = None
    #: Exact coordinate reached after an ordinary warp.
    arrival_at: tuple[int, int] | None = None
    #: Zero-based destination warp from the source event. For a return it is
    #: applied after the retained outside map resolves the target.
    destination_warp_index: int | None = None
    #: Raw coordinate-bearing connection record, when this is a connection.
    connection: ConnectionGeometry | None = None
    #: Exact executable border crossings derived from ``connection``.
    coordinate_transitions: tuple[MacroTransition, ...] = ()

    @property
    def is_warp(self) -> bool:
        return self.kind in (PassageKind.WARP, PassageKind.RETURN)

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
    tileset: int = -1
    warp_locations: tuple[tuple[int, int], ...] = ()
    retained_outside_override: int | None = None

    def neighbours(self) -> frozenset[int]:
        return frozenset(passage.to_map for passage in self.passages if passage.to_map is not None)

    @property
    def has_a_scripted_exit(self) -> bool:
        """Whether some way out of here cannot be planned from static data."""

        return any(passage.kind is PassageKind.SCRIPTED for passage in self.passages)

    @property
    def is_outside(self) -> bool:
        return self.tileset in OUTSIDE_TILESETS


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
    _verify_connection_transitions_are_reciprocal(passages)
    reachable = _reachable_from(
        STARTING_MAP,
        passages,
        outside_maps={
            map_id for map_id, header in headers.items() if header.tileset in OUTSIDE_TILESETS
        },
    )
    verify_connections_are_two_sided(reachable, one_sided)
    return {
        map_id: MapNode(
            map_id=map_id,
            height=headers[map_id].height,
            width=headers[map_id].width,
            passages=tuple(passages.get(map_id, ())),
            tileset=headers[map_id].tileset,
            warp_locations=tuple(warp.at for warp in warps.get(map_id, ())),
            retained_outside_override=headers[map_id].retained_outside_override,
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
    # Imported here to keep the low-level map-header and terrain decoders from
    # forming a module import cycle.  The executable graph needs both reads:
    # coordinates say *where* a warp is, while the tileset tables say whether
    # merely entering that coordinate triggers it.
    from pokemon_red_completion.gen1_terrain import (
        automatic_warp_tiles,
        directional_warp_tiles,
        terrain_for,
        tilesets,
    )

    sets = tilesets(rom)
    terrain_tiles = {
        map_id: terrain_for(rom, map_id, sets).tiles
        for map_id in graph
    }
    graph = _with_directional_warp_actions(
        graph,
        terrain_tiles,
        directional_warp_tiles(rom),
    )
    graph = _with_automatic_warp_triggers(
        graph,
        terrain_tiles,
        automatic_warp_tiles(rom),
    )
    graph = _without_inert_directional_warps(
        graph,
        terrain_tiles,
        directional_warp_tiles(rom),
    )
    verify_against_encounter_reads(
        reachable=set(graph),
        named_maps={item.value for item in MapId},
        with_wild_tables=set(wild_tables(rom)),
        fishable=set(fishing_tables(rom).by_map),
    )
    return graph


def _with_directional_warp_actions(
    graph: Mapping[int, MapNode],
    tile_grids: Mapping[int, tuple[tuple[int, ...], ...]],
    directional_tiles: Mapping[str, frozenset[int]],
) -> dict[int, MapNode]:
    """Derive a second input from the outdoor tile immediately beyond a warp."""

    delta = {
        "up": (-1, 0),
        "down": (1, 0),
        "left": (0, -1),
        "right": (0, 1),
    }
    projected: dict[int, MapNode] = {}
    for map_id, node in graph.items():
        tiles = tile_grids[map_id]

        def derive(
            passage: Passage,
            *,
            source_tileset: int = node.tileset,
            source_tiles: tuple[tuple[int, ...], ...] = tiles,
        ) -> Passage:
            if (
                passage.kind is not PassageKind.WARP
                or passage.exit_action is not None
                or passage.at is None
                or source_tileset not in OUTSIDE_TILESETS
            ):
                return passage
            actions = tuple(
                action
                for action, (dy, dx) in delta.items()
                if 0 <= passage.at[0] + dy < len(source_tiles)
                and 0 <= passage.at[1] + dx
                < len(source_tiles[passage.at[0] + dy])
                and source_tiles[passage.at[0] + dy][passage.at[1] + dx]
                in directional_tiles[action]
            )
            return replace(passage, exit_action=actions[0]) if len(actions) == 1 else passage

        projected[map_id] = replace(
            node,
            passages=tuple(derive(passage) for passage in node.passages),
        )
    return projected


def _with_automatic_warp_triggers(
    graph: Mapping[int, MapNode],
    tile_grids: Mapping[int, tuple[tuple[int, ...], ...]],
    automatic_tiles: Mapping[int, frozenset[int]],
) -> dict[int, MapNode]:
    """Clear extra-input actions where cartridge tile tables trigger on entry."""

    projected: dict[int, MapNode] = {}
    for map_id, node in graph.items():
        tiles = tile_grids[map_id]
        triggers = automatic_tiles[node.tileset]
        passages = tuple(
            replace(passage, exit_action=None)
            if passage.at is not None
            and passage.exit_action is not None
            and tiles[passage.at[0]][passage.at[1]] in triggers
            else passage
            for passage in node.passages
        )
        projected[map_id] = replace(node, passages=passages)
    return projected


def _without_inert_directional_warps(
    graph: Mapping[int, MapNode],
    tile_grids: Mapping[int, tuple[tuple[int, ...], ...]],
    directional_tiles: Mapping[str, frozenset[int]],
) -> dict[int, MapNode]:
    """Drop outdoor warp rows whose tile in front fails the engine table.

    Gatehouses expose paired warp records, but only the row facing a listed
    carpet tile is executable.  Keeping both made the joint router prefer an
    inert upper row on Route 7 even though the lower row is the real entrance.
    """

    delta = {
        "up": (-1, 0),
        "down": (1, 0),
        "left": (0, -1),
        "right": (0, 1),
    }
    projected: dict[int, MapNode] = {}
    for map_id, node in graph.items():
        tiles = tile_grids[map_id]

        def executable(
            passage: Passage,
            *,
            source_tileset: int = node.tileset,
            source_tiles: tuple[tuple[int, ...], ...] = tiles,
        ) -> bool:
            if (
                passage.kind is not PassageKind.WARP
                or passage.exit_action is None
                or passage.at is None
                or source_tileset not in OUTSIDE_TILESETS
            ):
                return True
            dy, dx = delta[passage.exit_action]
            y, x = passage.at[0] + dy, passage.at[1] + dx
            return (
                0 <= y < len(source_tiles)
                and 0 <= x < len(source_tiles[y])
                and source_tiles[y][x] in directional_tiles[passage.exit_action]
            )

        projected[map_id] = replace(
            node,
            passages=tuple(passage for passage in node.passages if executable(passage)),
        )
    return projected


def _read_headers(
    rom: bytes,
) -> tuple[
    dict[int, _Header],
    dict[int, list[_Warp]],
    list[tuple[int, Heading, int]],
]:
    """Decode every slot, keeping only connections both endpoints agree on."""

    raw: dict[int, _Header] = {}
    warps: dict[int, list[_Warp]] = {}
    for map_id in range(MAP_ID_LIMIT):
        bank = rom[MAP_HEADER_BANKS + map_id]
        at = MAP_HEADER_POINTERS + 2 * map_id
        address = int.from_bytes(rom[at : at + 2], "little")
        if not 0x4000 <= address <= 0x7FFF or bank * 0x4000 >= len(rom):
            continue
        header_offset = bank_offset(bank, address)
        flags = rom[header_offset + CONNECTION_FLAGS_OFFSET]
        if flags > CONNECTION_FLAG_LIMIT:
            continue  # an unused slot; its bytes are not a header
        cursor = header_offset + CONNECTION_FLAGS_OFFSET + 1
        found: dict[Heading, tuple[int, ConnectionGeometry]] = {}
        for heading, bit in CONNECTION_ORDER:
            if flags & (1 << bit):
                found[heading] = (
                    rom[cursor],
                    ConnectionGeometry(
                        strip_length=rom[cursor + 5],
                        destination_width=rom[cursor + 6],
                        y_alignment=rom[cursor + 7],
                        x_alignment=rom[cursor + 8],
                    ),
                )
                cursor += CONNECTION_STRUCT_BYTES
        raw[map_id] = _Header(
            tileset=rom[header_offset],
            height=rom[header_offset + 1],
            width=rom[header_offset + 2],
            connections=found,
            retained_outside_override=_retained_outside_override(
                rom,
                bank,
                int.from_bytes(
                    rom[
                        header_offset + SCRIPT_POINTER_OFFSET : header_offset
                        + SCRIPT_POINTER_OFFSET
                        + 2
                    ],
                    "little",
                ),
            ),
        )
        warps[map_id] = _read_warps(rom, bank, cursor)

    kept: dict[int, _Header] = {}
    one_sided: list[tuple[int, Heading, int]] = []
    for map_id, header_record in raw.items():
        agreed: dict[Heading, tuple[int, ConnectionGeometry]] = {}
        for heading, (other, geometry) in header_record.connections.items():
            neighbour = raw.get(other)
            reverse = None if neighbour is None else neighbour.connections.get(heading.opposite)
            if reverse is not None and reverse[0] == map_id:
                agreed[heading] = (other, geometry)
            else:
                one_sided.append((map_id, heading, other))
        kept[map_id] = _Header(
            tileset=header_record.tileset,
            height=header_record.height,
            width=header_record.width,
            connections=agreed,
            retained_outside_override=header_record.retained_outside_override,
        )
    for map_id, header in kept.items():
        override = header.retained_outside_override
        if override is None:
            continue
        target = kept.get(override)
        if target is None or target.tileset not in OUTSIDE_TILESETS:
            raise CartridgeReadError(
                f"map {map_id} script sets retained outside map to invalid target {override}"
            )
    return kept, warps, one_sided


def _retained_outside_override(
    rom: bytes,
    bank: int,
    script_address: int,
) -> int | None:
    """Decode the bounded constant ``wLastMap`` initializer used by entrances."""

    if not 0x4000 <= script_address <= 0x7FFF:
        return None
    at = bank_offset(bank, script_address)
    for prefix, required_opcode in ((0, None), (3, CALL_OPCODE)):
        if required_opcode is not None and rom[at] != required_opcode:
            continue
        candidate = rom[at + prefix : at + prefix + 5]
        if len(candidate) != 5:
            continue
        if (
            candidate[0] == LOAD_IMMEDIATE_A_OPCODE
            and candidate[2] == STORE_A_ABSOLUTE_OPCODE
            and int.from_bytes(candidate[3:5], "little") == WLASTMAP_ADDRESS
        ):
            return candidate[1]
    return None


def _read_warps(rom: bytes, bank: int, cursor: int) -> list[_Warp]:
    """Every door, including its destination warp index and map."""

    objects = int.from_bytes(rom[cursor : cursor + 2], "little")
    if not 0x4000 <= objects <= 0x7FFF:
        return []
    at = bank_offset(bank, objects)
    count = rom[at + 1]
    if count > WARP_COUNT_LIMIT:
        return []
    body = at + 2
    return [
        _Warp(
            y=rom[body + WARP_STRUCT_BYTES * index],
            x=rom[body + WARP_STRUCT_BYTES * index + 1],
            destination_warp_index=rom[body + WARP_STRUCT_BYTES * index + 2],
            destination_map=rom[body + WARP_STRUCT_BYTES * index + 3],
        )
        for index in range(count)
    ]


def _assemble(
    headers: Mapping[int, _Header],
    warps: Mapping[int, list[_Warp]],
) -> dict[int, list[Passage]]:
    """Turn agreed connections and warps into one list of exits per map."""

    passages: dict[int, list[Passage]] = {}
    for map_id, header in headers.items():
        for heading, (other, geometry) in header.connections.items():
            target = headers[other]
            passages.setdefault(map_id, []).append(
                Passage(
                    to_map=other,
                    kind=PassageKind.CONNECTION,
                    heading=heading,
                    connection=geometry,
                    coordinate_transitions=geometry.transitions(
                        heading,
                        source_size=(header.height, header.width),
                        destination_size=(target.height, target.width),
                    ),
                )
            )

    for map_id, doors in warps.items():
        for door in doors:
            destination = door.destination_map
            if destination == RETURN_TO_LAST_MAP:
                passages.setdefault(map_id, []).append(
                    Passage(
                        to_map=None,
                        kind=PassageKind.RETURN,
                        at=door.at,
                        exit_action=_boundary_return_action(headers[map_id], door.at),
                        destination_warp_index=door.destination_warp_index,
                    )
                )
                continue

            kind = PassageKind.WARP if destination in headers else PassageKind.SCRIPTED
            arrival_at: tuple[int, int] | None = None
            exit_action: str | None = None
            if kind is PassageKind.WARP:
                destination_warps = warps.get(destination, ())
                if door.destination_warp_index >= len(destination_warps):
                    raise CartridgeReadError(
                        f"map {map_id} warp at {door.at} targets missing warp "
                        f"{door.destination_warp_index} on map {destination}"
                    )
                arrival_at = destination_warps[door.destination_warp_index].at
                # Directional warp behavior belongs to the source trigger,
                # not the destination arrival. Viridian Forest's north edge
                # is the live asymmetric witness: its top warp needs a second
                # UP, while the paired gate's bottom warp fires on entry.
                exit_action = _boundary_warp_action(headers[map_id], door.at)
            passages.setdefault(map_id, []).append(
                Passage(
                    to_map=destination if kind is PassageKind.WARP else None,
                    kind=kind,
                    exit_action=exit_action,
                    at=door.at,
                    arrival_at=arrival_at,
                    destination_warp_index=door.destination_warp_index,
                )
            )
    return passages


def _boundary_return_action(header: _Header, at: tuple[int, int]) -> str | None:
    """Return the outward action for a non-corner map-edge warp."""

    y, x = at
    maximum_y = header.height * 2 - 1
    maximum_x = header.width * 2 - 1
    candidates = tuple(
        action
        for condition, action in (
            (y == 0, "up"),
            (y == maximum_y, "down"),
            (x == 0, "left"),
            (x == maximum_x, "right"),
        )
        if condition
    )
    return candidates[0] if len(candidates) == 1 else None


def _boundary_warp_action(header: _Header, at: tuple[int, int]) -> str | None:
    """Return the extra outward action required by a source boundary warp.

    Top and horizontal boundary triggers require a second outward input after
    Red enters their coordinate. Bottom-boundary triggers fire on entry. The
    cartridge automatic-warp table may subsequently clear any geometric guess.
    """

    y, x = at
    maximum_y = header.height * 2 - 1
    maximum_x = header.width * 2 - 1
    if y in {0, maximum_y} and x in {0, maximum_x}:
        return None
    if y == 0:
        return "up"
    if y == maximum_y:
        return None
    candidates = tuple(
        action
        for condition, action in (
            (x == 0, "left"),
            (x == maximum_x, "right"),
        )
        if condition
    )
    return candidates[0] if len(candidates) == 1 else None


def _verify_connection_transitions_are_reciprocal(
    passages: Mapping[int, list[Passage]],
) -> None:
    """Refuse geometry whose reverse endpoint does not return to its source."""

    for map_id, exits in passages.items():
        for passage in exits:
            if passage.kind is not PassageKind.CONNECTION:
                continue
            assert passage.to_map is not None
            assert passage.heading is not None
            reverse = next(
                (
                    candidate
                    for candidate in passages.get(passage.to_map, ())
                    if candidate.kind is PassageKind.CONNECTION
                    and candidate.to_map == map_id
                    and candidate.heading is passage.heading.opposite
                ),
                None,
            )
            if reverse is None:
                raise CartridgeReadError(
                    f"map {map_id}'s {passage.heading.value} connection has no reverse"
                )
            forward_pairs = {
                (transition.exit_at, transition.arrival_at)
                for transition in passage.coordinate_transitions
            }
            reverse_pairs = {
                (transition.arrival_at, transition.exit_at)
                for transition in reverse.coordinate_transitions
            }
            if forward_pairs != reverse_pairs:
                raise CartridgeReadError(
                    f"map {map_id}'s {passage.heading.value} connection coordinates "
                    "do not agree with the reverse connection"
                )


def _reachable_from(
    start: int,
    passages: Mapping[int, list[Passage]],
    *,
    outside_maps: set[int],
) -> set[int]:
    start_state = (start, None)
    seen_states: set[tuple[int, int | None]] = {start_state}
    seen_maps = {start}
    frontier: list[tuple[int, int | None]] = [start_state]
    while frontier:
        node, last_outside = frontier.pop()
        for passage in passages.get(node, ()):
            destination: int
            following_last_outside: int | None
            if passage.kind is PassageKind.RETURN:
                if last_outside is None:
                    continue
                destination = last_outside
                following_last_outside = last_outside
            else:
                if passage.to_map is None:
                    continue
                destination = passage.to_map
                following_last_outside = last_outside
                if passage.kind is PassageKind.WARP and node in outside_maps:
                    following_last_outside = node
            following = (destination, following_last_outside)
            if following in seen_states:
                continue
            seen_states.add(following)
            seen_maps.add(destination)
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
                    arrival_at=passage.arrival_at,
                    heading=passage.heading.value if passage.heading is not None else None,
                    exit_action=passage.exit_action,
                    coordinate_transitions=passage.coordinate_transitions,
                    destination_warp_index=passage.destination_warp_index,
                )
                for passage in node.passages
                if passage.kind is not PassageKind.SCRIPTED
            )
            for map_id, node in graph.items()
        },
        outside_nodes=frozenset(map_id for map_id, node in graph.items() if node.is_outside),
        warp_locations={map_id: node.warp_locations for map_id, node in graph.items()},
        retained_outside_overrides={
            map_id: node.retained_outside_override
            for map_id, node in graph.items()
            if node.retained_outside_override is not None
        },
    )


def routes_between(
    graph: Mapping[int, MapNode],
    start: int,
    goal: int,
    *,
    last_outside: int | None = None,
) -> tuple[int, ...]:
    """The shortest sequence of maps joining two points, or empty if none.

    Breadth-first because every passage costs the same here: a warp and an edge
    crossing are both one map transition. Weighting them by walking distance
    needs the block data, which is a separate read.
    """

    if start not in graph:
        raise CartridgeReadError(f"map {start} is not in the graph")
    routed = macro_graph_from_nodes(graph)
    try:
        return find_macro_route(routed, start, goal, last_outside=last_outside)
    except GlobalRouterError:
        return ()
