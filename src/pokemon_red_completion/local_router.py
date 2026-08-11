"""Game-neutral routing across one map with explicit action requirements."""

from __future__ import annotations

import heapq
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from pokemon_red_completion.actions import MacroAction, MacroActionKind

Coordinate = tuple[int, int]
TraversalMode = str | None
TraversalState = tuple[Coordinate, TraversalMode]
LocalGoal = tuple[Coordinate, TraversalMode]


@dataclass(frozen=True, slots=True)
class LocalEdge:
    """One executable transition between two coordinates."""

    target: Coordinate
    action: str
    kind: str = "walk"
    requirements: frozenset[str] = frozenset()
    cost: int = 1
    action_kind: MacroActionKind = MacroActionKind.MOVE
    required_mode: str | None = None
    result_mode: str | None = None
    transient: Coordinate | None = None

    def __post_init__(self) -> None:
        if not self.action:
            raise ValueError("a local edge needs an action")
        if not self.kind:
            raise ValueError("a local edge needs a transition kind")
        if self.cost <= 0:
            raise ValueError("a local edge must cost something to cross")
        if not isinstance(self.action_kind, MacroActionKind):
            raise TypeError("a local edge action kind must be a MacroActionKind")
        for label, mode in (
            ("required_mode", self.required_mode),
            ("result_mode", self.result_mode),
        ):
            if mode is not None and not mode:
                raise ValueError(f"{label} cannot be empty")
        if self.transient == self.target:
            raise ValueError("a local edge transient cannot equal its target")

    @property
    def macro_action(self) -> MacroAction:
        return MacroAction(self.action_kind, self.action)

    def permits_mode(self, mode: TraversalMode) -> bool:
        return self.required_mode is None or self.required_mode == mode

    def next_mode(self, mode: TraversalMode) -> TraversalMode:
        return self.result_mode if self.result_mode is not None else mode


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
    modes: tuple[TraversalMode, ...]

    def __post_init__(self) -> None:
        if len(self.coordinates) != len(self.edges) + 1:
            raise ValueError("a local path needs exactly one edge between each coordinate")
        if len(self.modes) != len(self.coordinates):
            raise ValueError("a local path needs one movement mode at every coordinate")


class LocalRouterError(RuntimeError):
    """Raised when no permitted local route can be found."""


@dataclass(frozen=True, slots=True)
class PlannedTransition:
    """A path to the nearest requested transition and that exact transition."""

    approach: LocalPath
    transition: LocalEdge


def without_coordinates(
    graph: LocalGraph,
    blocked: Collection[Coordinate],
) -> LocalGraph:
    """Return a graph that neither enters nor leaves currently blocked squares."""

    unavailable = frozenset(blocked)
    if not unavailable:
        return graph
    return LocalGraph(
        {
            source: tuple(edge for edge in outgoing if edge.target not in unavailable)
            for source, outgoing in graph.edges.items()
            if source not in unavailable
        }
    )


def find_local_path(
    graph: LocalGraph,
    start: Coordinate,
    goal: Coordinate,
    *,
    capabilities: frozenset[str] = frozenset(),
    start_mode: TraversalMode = None,
    goal_mode: TraversalMode = None,
) -> LocalPath:
    """Find the cheapest path whose edge requirements are all available."""

    if start == goal and (goal_mode is None or start_mode == goal_mode):
        return LocalPath(coordinates=(start,), edges=(), modes=(start_mode,))

    initial = (start, start_mode)
    frontier: list[tuple[int, int, Coordinate, TraversalMode]] = [(0, 0, start, start_mode)]
    came_from: dict[TraversalState, tuple[TraversalState, LocalEdge]] = {}
    best_cost = {initial: 0}
    sequence = 1

    while frontier:
        cost, _, current, current_mode = heapq.heappop(frontier)
        current_state = (current, current_mode)
        if cost != best_cost.get(current_state):
            continue
        if current == goal and (goal_mode is None or current_mode == goal_mode):
            return _reconstruct(came_from, initial, current_state)

        for edge in graph.neighbors(current):
            if not edge.requirements.issubset(capabilities) or not edge.permits_mode(current_mode):
                continue
            candidate_cost = cost + edge.cost
            following = (edge.target, edge.next_mode(current_mode))
            if candidate_cost >= best_cost.get(following, candidate_cost + 1):
                continue
            came_from[following] = (current_state, edge)
            best_cost[following] = candidate_cost
            heapq.heappush(
                frontier,
                (candidate_cost, sequence, following[0], following[1]),
            )
            sequence += 1

    raise LocalRouterError(f"no permitted local route from {start} to {goal}")


def find_local_paths(
    graph: LocalGraph,
    start: Coordinate,
    goals: Collection[LocalGoal],
    *,
    capabilities: frozenset[str] = frozenset(),
    start_mode: TraversalMode = None,
) -> dict[LocalGoal, LocalPath]:
    """Find cheapest paths to many coordinate/mode goals in one search.

    A requested mode of ``None`` accepts the first cheapest mode observed at
    that coordinate. Exact-mode and mode-agnostic requests may coexist. Missing
    keys are unreachable, which lets a caller compare alternate exits without
    turning each rejected candidate into an exception or a fresh Dijkstra run.
    """

    remaining = set(goals)
    if not remaining:
        return {}
    initial = (start, start_mode)
    frontier: list[tuple[int, int, Coordinate, TraversalMode]] = [(0, 0, start, start_mode)]
    came_from: dict[TraversalState, tuple[TraversalState, LocalEdge]] = {}
    best_cost = {initial: 0}
    found: dict[LocalGoal, LocalPath] = {}
    sequence = 1

    while frontier and remaining:
        cost, _, current, current_mode = heapq.heappop(frontier)
        current_state = (current, current_mode)
        if cost != best_cost.get(current_state):
            continue
        matched = remaining.intersection({(current, None), current_state})
        if matched:
            path = _reconstruct(came_from, initial, current_state)
            for goal in matched:
                found[goal] = path
            remaining.difference_update(matched)
            if not remaining:
                break

        for edge in graph.neighbors(current):
            if not edge.requirements.issubset(capabilities) or not edge.permits_mode(current_mode):
                continue
            candidate_cost = cost + edge.cost
            following = (edge.target, edge.next_mode(current_mode))
            if candidate_cost >= best_cost.get(following, candidate_cost + 1):
                continue
            came_from[following] = (current_state, edge)
            best_cost[following] = candidate_cost
            heapq.heappush(
                frontier,
                (candidate_cost, sequence, following[0], following[1]),
            )
            sequence += 1
    return found


def find_nearest_transition(
    graph: LocalGraph,
    start: Coordinate,
    kind: str,
    *,
    capabilities: frozenset[str] = frozenset(),
    start_mode: TraversalMode = None,
) -> PlannedTransition:
    """Find the cheapest reachable source of an eligible transition kind."""

    if not kind:
        raise ValueError("a requested transition kind cannot be empty")
    initial = (start, start_mode)
    frontier: list[tuple[int, int, Coordinate, TraversalMode]] = [(0, 0, start, start_mode)]
    came_from: dict[TraversalState, tuple[TraversalState, LocalEdge]] = {}
    best_cost = {initial: 0}
    sequence = 1
    while frontier:
        cost, _, current, current_mode = heapq.heappop(frontier)
        current_state = (current, current_mode)
        if cost != best_cost.get(current_state):
            continue
        for edge in graph.neighbors(current):
            if (
                edge.kind == kind
                and edge.requirements.issubset(capabilities)
                and edge.permits_mode(current_mode)
            ):
                return PlannedTransition(
                    approach=_reconstruct(came_from, initial, current_state),
                    transition=edge,
                )
        for edge in graph.neighbors(current):
            if not edge.requirements.issubset(capabilities) or not edge.permits_mode(current_mode):
                continue
            candidate_cost = cost + edge.cost
            following = (edge.target, edge.next_mode(current_mode))
            if candidate_cost >= best_cost.get(following, candidate_cost + 1):
                continue
            came_from[following] = (current_state, edge)
            best_cost[following] = candidate_cost
            heapq.heappush(
                frontier,
                (candidate_cost, sequence, following[0], following[1]),
            )
            sequence += 1
    raise LocalRouterError(f"no permitted {kind} transition is reachable from {start}")


def _reconstruct(
    came_from: Mapping[TraversalState, tuple[TraversalState, LocalEdge]],
    start: TraversalState,
    goal: TraversalState,
) -> LocalPath:
    states = [goal]
    edges: list[LocalEdge] = []
    current = goal
    while current != start:
        previous, edge = came_from[current]
        states.append(previous)
        edges.append(edge)
        current = previous
    ordered = tuple(reversed(states))
    return LocalPath(
        coordinates=tuple(state[0] for state in ordered),
        edges=tuple(reversed(edges)),
        modes=tuple(state[1] for state in ordered),
    )
