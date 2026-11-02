"""Read-only early exclusion of a cartridge-proven closed regional entrance.

This Red-specific gate removes no destination once its native guard is hidden.
Already-local cave exploration always retains the ordinary route checks.
"""
from functools import lru_cache

from .gen1_acquisition import map_objects
from .gen1_maps import map_graph
from .gen1_terrain import walkable_world
from .gen1_traversal import surf_local_graph, traversal_rules
from .red_field_item import _field_item_toggle_indices
from .rom import verify_rom_bytes

_CAVE_MAPS = frozenset({0xE2, 0xE3, 0xE4})
_CITY = 3


@lru_cache(maxsize=2)
def _cave_guard_toggle(rom: bytes) -> int:
    """Authenticate the only outside entrance and its mandatory standing guard."""
    verify_rom_bytes(rom)
    maps = map_graph(rom)
    entries = [(mid, p) for mid, node in maps.items() if mid not in _CAVE_MAPS
               for p in node.passages if p.to_map in _CAVE_MAPS]
    if len(entries) != 1 or entries[0][0] != _CITY:
        raise ValueError("cave region does not have one authenticated outside entrance")
    entry = entries[0][1]
    if entry.to_map != 0xE4 or entry.at is None:
        raise ValueError("cave entry differs from the pinned cartridge")
    approach = (entry.at[0] + 1, entry.at[1])
    guards = [(i, obj) for i, obj in enumerate(map_objects(rom)[_CITY], 1)
              if (obj.y, obj.x) == approach and obj.movement == 0xFF
              and not obj.is_item and not obj.is_trainer]
    if len(guards) != 1:
        raise ValueError("cave entry lacks one stationary native guard")
    # Geometry, including water/ledge actions, must provide no alternate approach.
    terrain = walkable_world(rom)[_CITY]
    graph = surf_local_graph(terrain, traversal_rules(rom, maps))
    incoming = {at for at, edges in graph.edges.items()
                if any(edge.target == entry.at for edge in edges)}
    if incoming != {approach}:
        raise ValueError("cave entrance has an alternate native approach")
    index = _field_item_toggle_indices(rom).get((_CITY, guards[0][0]))
    if index is None:
        raise ValueError("cave guard has no native visibility flag")
    return index


def closed_remote_cave_entry(rom, reader, *, current_map, target_map) -> bool:
    """Exclude only a proven closed remote entrance; unknown stays ordinary."""
    if target_map not in _CAVE_MAPS or current_map in _CAVE_MAPS:
        return False
    read_hidden = getattr(reader, "read_toggleable_object_hidden", None)
    if not callable(read_hidden):
        return False
    hidden = read_hidden(_cave_guard_toggle(rom))
    if type(hidden) is not bool:
        raise ValueError("native cave guard visibility must be boolean")
    return not hidden


def observed_cave_guard_world(world, reader):
    """Remove only the cartridge-bound guard whose native hidden bit is true.

    Center return quotes must not keep a permanently hidden outside guard as a
    wall. All other occupancy, field requirements and trainer masks survive.
    This reads the same global flag as closed_remote_cave_entry; no story or
    registration history substitutes for native visibility.
    """
    from dataclasses import replace

    read_hidden = getattr(reader, "read_toggleable_object_hidden", None)
    if (not callable(read_hidden) or not hasattr(world, "object_blockers")
            or _CITY not in world.object_blockers):
        return world
    index = _cave_guard_toggle(world.rom)
    hidden = read_hidden(index)
    if type(hidden) is not bool:
        raise ValueError("native cave guard visibility must be boolean")
    if not hidden:
        return world
    keys = [key for key, value in _field_item_toggle_indices(world.rom).items()
            if value == index]
    if len(keys) != 1 or keys[0][0] != _CITY:
        raise ValueError("authenticated cave guard toggle identity changed")
    obj = map_objects(world.rom)[_CITY][keys[0][1] - 1]
    at = obj.y, obj.x
    if at not in world.object_blockers[_CITY]:
        return world
    observed = replace(world, object_blockers={
        **world.object_blockers, _CITY: world.object_blockers[_CITY] - {at},
    })
    result = replace(observed, local_graphs={
        **observed.local_graphs,
        _CITY: observed._graph_for_terrain(observed.terrain[_CITY]),
    })
    if read_hidden(index) is not True:
        raise ValueError("native cave guard visibility changed during projection")
    return result
