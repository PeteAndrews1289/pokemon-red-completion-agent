"""Shortest routes across a map graph, without knowing which game it came from.

This module used to carry a hand-written five-node sketch of Kanto and a test
asserting that Saffron City was unreachable -- true of the sketch, false of the
game. That is the shape of the problem the whole repository is trying to leave
behind: a hand-written world model can only ever be as complete as the last
person to type into it, and its gaps become requirements the moment a test
asserts them.

So the world model is gone from here. This is the routing, and nothing else:
nodes are opaque integers, edges say how they are joined, and where the graph
comes from is somebody else's problem.
:func:`pokemon_red_completion.gen1_maps.macro_graph` supplies one read from a
Generation I cartridge; a later title supplies its own, and this code does not
change.

**What a route here does and does not promise.** It promises that the maps are
joined -- that a player standing on one can, by some means, reach the next. It
does not promise the way is open *now*. Crossing to Cinnabar means surfing,
Saffron's gates want a drink, and neither the header data nor this module knows
it. Traversal requirements are a separate read, and until they exist a route is
a candidate to be checked rather than a plan to be executed.
"""

from __future__ import annotations

import heapq
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MacroEdge:
    """One way to get from the map holding this edge to another.

    ``kind`` and ``at`` are carried rather than collapsed because the caller
    needs them to act: leaving by a connection means walking off an edge, and
    leaving by a warp means standing on one particular block first.
    """

    target_map: int
    kind: str = "connection"
    #: The ``(y, x)`` block to stand on, when the edge is a warp.
    at: tuple[int, int] | None = None
    #: How expensive this transition is. Uniform by default, because header
    #: data does not say how far apart two doors are.
    cost: int = 1

    def __post_init__(self) -> None:
        if self.cost <= 0:
            raise ValueError("a macro edge must cost something to cross")


@dataclass(frozen=True)
class MacroGraph:
    """Maps joined by edges, keyed by whatever identifier the title uses."""

    edges: Mapping[int, tuple[MacroEdge, ...]]

    def neighbors(self, node: int) -> tuple[MacroEdge, ...]:
        return tuple(self.edges.get(node, ()))

    def __len__(self) -> int:
        return len(self.edges)


class GlobalRouterError(RuntimeError):
    """Raised when no macro route can be found."""


def find_macro_route(graph: MacroGraph, start: int, goal: int) -> tuple[int, ...]:
    """The cheapest sequence of maps joining two points.

    Dijkstra rather than breadth-first so that an edge can cost more than one
    once traversal requirements exist -- surfing is not free, and a route that
    prefers a longer walk to a shorter swim is often the right one.
    """

    if start == goal:
        return (start,)

    frontier: list[tuple[int, int, int]] = [(0, 0, start)]
    came_from: dict[int, int] = {}
    best_cost: dict[int, int] = {start: 0}
    sequence = 1

    while frontier:
        cost, _, current = heapq.heappop(frontier)
        if cost != best_cost.get(current):
            continue
        if current == goal:
            return _reconstruct_path(came_from, start, goal)

        for edge in graph.neighbors(current):
            neighbor = edge.target_map
            candidate_cost = cost + edge.cost
            if candidate_cost >= best_cost.get(neighbor, candidate_cost + 1):
                continue
            came_from[neighbor] = current
            best_cost[neighbor] = candidate_cost
            heapq.heappush(frontier, (candidate_cost, sequence, neighbor))
            sequence += 1

    raise GlobalRouterError(f"no macro route from map {start} to map {goal}")


def _reconstruct_path(came_from: Mapping[int, int], start: int, goal: int) -> tuple[int, ...]:
    reversed_path = [goal]
    current = goal
    while current != start:
        current = came_from[current]
        reversed_path.append(current)
    return tuple(reversed(reversed_path))
