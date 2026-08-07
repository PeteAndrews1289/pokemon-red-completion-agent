"""Global pathfinding across Kanto's macro map graph."""

from __future__ import annotations

import heapq
from dataclasses import dataclass

from pokemon_red_completion.observation import MapId


@dataclass(frozen=True, slots=True)
class MacroEdge:
    """A transition from one MapId to another."""

    target_map: MapId
    # Additional fields would go here: e.g., the exact tile coordinate of the warp/transition,
    # whether it requires an HM, or if it's a 'fly' connection.


@dataclass(frozen=True)
class MacroGraph:
    """A graph connecting Pokemon Red maps."""

    edges: dict[MapId, tuple[MacroEdge, ...]]

    def neighbors(self, node: MapId) -> tuple[MacroEdge, ...]:
        return self.edges.get(node, ())


class GlobalRouterError(RuntimeError):
    """Raised when no macro route can be found."""


def find_macro_route(
    graph: MacroGraph,
    start: MapId,
    goal: MapId,
) -> tuple[MapId, ...]:
    """Find the shortest sequence of maps connecting start to goal using Dijkstra's algorithm."""

    if start == goal:
        return (start,)

    frontier: list[tuple[int, int, MapId]] = [(0, 0, start)]
    came_from: dict[MapId, MapId] = {}
    best_cost: dict[MapId, int] = {start: 0}

    # We use a sequence counter for tie-breaking in the heap
    sequence = 1

    while frontier:
        cost, _, current = heapq.heappop(frontier)

        if cost != best_cost.get(current):
            continue

        if current == goal:
            return _reconstruct_path(came_from, start, goal)

        for edge in graph.neighbors(current):
            neighbor = edge.target_map
            candidate_cost = cost + 1  # Assuming uniform cost for now

            if candidate_cost >= best_cost.get(neighbor, candidate_cost + 1):
                continue

            came_from[neighbor] = current
            best_cost[neighbor] = candidate_cost
            heapq.heappush(frontier, (candidate_cost, sequence, neighbor))
            sequence += 1

    raise GlobalRouterError(f"No macro route from {start.name} to {goal.name}.")


def _reconstruct_path(
    came_from: dict[MapId, MapId],
    start: MapId,
    goal: MapId,
) -> tuple[MapId, ...]:
    reversed_path = [goal]
    current = goal
    while current != start:
        current = came_from[current]
        reversed_path.append(current)
    return tuple(reversed(reversed_path))


# A basic hardcoded sub-graph for proof-of-concept testing
BASIC_KANTO_GRAPH = MacroGraph(
    edges={
        MapId.PALLET_TOWN: (
            MacroEdge(MapId.ROUTE_1),
            MacroEdge(MapId.REDS_HOUSE_1F),
            MacroEdge(MapId.OAKS_LAB),
            MacroEdge(MapId.ROUTE_21),
        ),
        MapId.ROUTE_1: (
            MacroEdge(MapId.PALLET_TOWN),
            MacroEdge(MapId.VIRIDIAN_CITY),
        ),
        MapId.VIRIDIAN_CITY: (
            MacroEdge(MapId.ROUTE_1),
            MacroEdge(MapId.ROUTE_2),
            MacroEdge(MapId.ROUTE_22_GATE),
            MacroEdge(MapId.VIRIDIAN_POKECENTER),
            MacroEdge(MapId.VIRIDIAN_MART),
            MacroEdge(MapId.VIRIDIAN_GYM),
        ),
        MapId.VIRIDIAN_POKECENTER: (MacroEdge(MapId.VIRIDIAN_CITY),),
        MapId.ROUTE_2: (
            MacroEdge(MapId.VIRIDIAN_CITY),
            MacroEdge(MapId.VIRIDIAN_FOREST_SOUTH_GATE),
            MacroEdge(MapId.DIGLETTS_CAVE_ROUTE_2),
        ),
    }
)
