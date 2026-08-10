"""Game-neutral routing across one map with explicit action requirements."""

from __future__ import annotations

import heapq
from collections.abc import Mapping
from dataclasses import dataclass

Coordinate = tuple[int, int]


@dataclass(frozen=True, slots=True)
class LocalEdge:
    """One executable transition between two coordinates."""

    target: Coordinate
    action: str
    kind: str = "walk"
    requirements: frozenset[str] = frozenset()
    cost: int = 1

    def __post_init__(self) -> None:
        if not self.action:
            raise ValueError("a local edge needs an action")
        if not self.kind:
            raise ValueError("a local edge needs a transition kind")
        if self.cost <= 0:
            raise ValueError("a local edge must cost something to cross")


@dataclass(frozen=True)
class LocalGraph:
    """Directed coordinate transitions supplied by a game adapter."""

    edges: Mapping[Coordinate, tuple[LocalEdge, ...]]

    def neighbors(self, coordinate: Coordinate) -> tuple[LocalEdge, ...]:
        return tuple(self.edges.get(coordinate, ()))


@dataclass(frozen=True, slots=True)
class LocalPath:
    """A coordinate route retaining the exact actions needed to execute it."""

    coordinates: tuple[Coordinate, ...]
    edges: tuple[LocalEdge, ...]

    def __post_init__(self) -> None:
        if len(self.coordinates) != len(self.edges) + 1:
            raise ValueError("a local path needs exactly one edge between each coordinate")


class LocalRouterError(RuntimeError):
    """Raised when no permitted local route can be found."""


@dataclass(frozen=True, slots=True)
class PlannedTransition:
    """A path to the nearest requested transition and that exact transition."""

    approach: LocalPath
    transition: LocalEdge


def find_local_path(
    graph: LocalGraph,
    start: Coordinate,
    goal: Coordinate,
    *,
    capabilities: frozenset[str] = frozenset(),
) -> LocalPath:
    """Find the cheapest path whose edge requirements are all available."""

    if start == goal:
        return LocalPath(coordinates=(start,), edges=())

    frontier: list[tuple[int, int, Coordinate]] = [(0, 0, start)]
    came_from: dict[Coordinate, tuple[Coordinate, LocalEdge]] = {}
    best_cost = {start: 0}
    sequence = 1

    while frontier:
        cost, _, current = heapq.heappop(frontier)
        if cost != best_cost.get(current):
            continue
        if current == goal:
            return _reconstruct(came_from, start, goal)

        for edge in graph.neighbors(current):
            if not edge.requirements.issubset(capabilities):
                continue
            candidate_cost = cost + edge.cost
            if candidate_cost >= best_cost.get(edge.target, candidate_cost + 1):
                continue
            came_from[edge.target] = (current, edge)
            best_cost[edge.target] = candidate_cost
            heapq.heappush(frontier, (candidate_cost, sequence, edge.target))
            sequence += 1

    raise LocalRouterError(f"no permitted local route from {start} to {goal}")


def find_nearest_transition(
    graph: LocalGraph,
    start: Coordinate,
    kind: str,
    *,
    capabilities: frozenset[str] = frozenset(),
) -> PlannedTransition:
    """Find the cheapest reachable source of an eligible transition kind."""

    if not kind:
        raise ValueError("a requested transition kind cannot be empty")
    frontier: list[tuple[int, int, Coordinate]] = [(0, 0, start)]
    came_from: dict[Coordinate, tuple[Coordinate, LocalEdge]] = {}
    best_cost = {start: 0}
    sequence = 1
    while frontier:
        cost, _, current = heapq.heappop(frontier)
        if cost != best_cost.get(current):
            continue
        for edge in graph.neighbors(current):
            if edge.kind == kind and edge.requirements.issubset(capabilities):
                return PlannedTransition(
                    approach=_reconstruct(came_from, start, current),
                    transition=edge,
                )
        for edge in graph.neighbors(current):
            if not edge.requirements.issubset(capabilities):
                continue
            candidate_cost = cost + edge.cost
            if candidate_cost >= best_cost.get(edge.target, candidate_cost + 1):
                continue
            came_from[edge.target] = (current, edge)
            best_cost[edge.target] = candidate_cost
            heapq.heappush(frontier, (candidate_cost, sequence, edge.target))
            sequence += 1
    raise LocalRouterError(f"no permitted {kind} transition is reachable from {start}")


def _reconstruct(
    came_from: Mapping[Coordinate, tuple[Coordinate, LocalEdge]],
    start: Coordinate,
    goal: Coordinate,
) -> LocalPath:
    coordinates = [goal]
    edges: list[LocalEdge] = []
    current = goal
    while current != start:
        previous, edge = came_from[current]
        coordinates.append(previous)
        edges.append(edge)
        current = previous
    return LocalPath(
        coordinates=tuple(reversed(coordinates)),
        edges=tuple(reversed(edges)),
    )
