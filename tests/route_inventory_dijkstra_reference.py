"""Pinned pre-change Dijkstra oracle;source SHA8436080a65546154b0c657a95b8d61b9dad23ce0bc879a57eaf292214e86f168."""
from __future__ import annotations
import heapq
from collections.abc import Collection, Mapping
from pokemon_red_completion.local_router import LocalGraph,LocalGoal,LocalPath,LocalEdge,TraversalMode,TraversalState,Coordinate

def reference_paths(
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
