from __future__ import annotations

import heapq
from dataclasses import dataclass
from enum import StrEnum
from itertools import count


@dataclass(frozen=True, order=True, slots=True)
class Coordinate:
    x: int
    y: int

    def manhattan_distance(self, other: Coordinate) -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)


class Direction(StrEnum):
    UP = "up"
    RIGHT = "right"
    DOWN = "down"
    LEFT = "left"

    @property
    def delta(self) -> tuple[int, int]:
        return {
            Direction.UP: (0, -1),
            Direction.RIGHT: (1, 0),
            Direction.DOWN: (0, 1),
            Direction.LEFT: (-1, 0),
        }[self]


@dataclass(frozen=True, slots=True)
class GridMap:
    width: int
    height: int
    blocked: frozenset[Coordinate] = frozenset()
    blocked_transitions: frozenset[tuple[Coordinate, Coordinate]] = frozenset()

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Grid dimensions must be positive.")
        outside = sorted(point for point in self.blocked if not self.contains(point))
        if outside:
            raise ValueError(f"Blocked coordinates outside the grid: {outside!r}")
        invalid_transitions = sorted(
            (start, end)
            for start, end in self.blocked_transitions
            if (
                not self.contains(start)
                or not self.contains(end)
                or start.manhattan_distance(end) != 1
            )
        )
        if invalid_transitions:
            raise ValueError(
                "Blocked transitions must connect adjacent in-bounds coordinates: "
                f"{invalid_transitions!r}"
            )

    def contains(self, point: Coordinate) -> bool:
        return 0 <= point.x < self.width and 0 <= point.y < self.height

    def is_walkable(
        self,
        point: Coordinate,
        *,
        goal: Coordinate | None = None,
        allow_blocked_goal: bool = False,
    ) -> bool:
        if not self.contains(point):
            return False
        if allow_blocked_goal and point == goal:
            return True
        return point not in self.blocked

    def neighbors(
        self,
        point: Coordinate,
        *,
        goal: Coordinate,
        allow_blocked_goal: bool = False,
    ) -> tuple[Coordinate, ...]:
        neighbors: list[Coordinate] = []
        for direction in Direction:
            dx, dy = direction.delta
            candidate = Coordinate(point.x + dx, point.y + dy)
            if (point, candidate) in self.blocked_transitions:
                continue
            if self.is_walkable(
                candidate,
                goal=goal,
                allow_blocked_goal=allow_blocked_goal,
            ):
                neighbors.append(candidate)
        return tuple(neighbors)


class NoPathError(RuntimeError):
    """Raised when deterministic navigation cannot connect two valid coordinates."""


def shortest_path(
    grid: GridMap,
    start: Coordinate,
    goal: Coordinate,
    *,
    allow_blocked_goal: bool = False,
) -> tuple[Coordinate, ...]:
    """Return an inclusive shortest path using deterministic A* tie-breaking."""
    if not grid.contains(start):
        raise ValueError(f"Start coordinate is outside the grid: {start!r}")
    if not grid.contains(goal):
        raise ValueError(f"Goal coordinate is outside the grid: {goal!r}")
    if start in grid.blocked:
        raise NoPathError(f"Start coordinate is blocked: {start!r}")
    if goal in grid.blocked and not allow_blocked_goal:
        raise NoPathError(f"Goal coordinate is blocked: {goal!r}")
    if start == goal:
        return (start,)

    sequence = count()
    frontier: list[tuple[int, int, int, int, int, Coordinate]] = [
        (start.manhattan_distance(goal), 0, start.y, start.x, next(sequence), start)
    ]
    came_from: dict[Coordinate, Coordinate] = {}
    best_cost: dict[Coordinate, int] = {start: 0}

    while frontier:
        _, cost, _, _, _, current = heapq.heappop(frontier)
        if cost != best_cost.get(current):
            continue
        if current == goal:
            return _reconstruct_path(came_from, start, goal)

        for neighbor in grid.neighbors(
            current,
            goal=goal,
            allow_blocked_goal=allow_blocked_goal,
        ):
            candidate_cost = cost + 1
            if candidate_cost >= best_cost.get(neighbor, candidate_cost + 1):
                continue
            came_from[neighbor] = current
            best_cost[neighbor] = candidate_cost
            priority = candidate_cost + neighbor.manhattan_distance(goal)
            heapq.heappush(
                frontier,
                (
                    priority,
                    candidate_cost,
                    neighbor.y,
                    neighbor.x,
                    next(sequence),
                    neighbor,
                ),
            )

    raise NoPathError(f"No path from {start!r} to {goal!r}.")


def path_to_directions(path: tuple[Coordinate, ...]) -> tuple[Direction, ...]:
    if not path:
        raise ValueError("A path must contain at least one coordinate.")

    directions: list[Direction] = []
    for current, following in zip(path, path[1:], strict=False):
        delta = (following.x - current.x, following.y - current.y)
        try:
            direction = next(direction for direction in Direction if direction.delta == delta)
        except StopIteration as error:
            raise ValueError(
                f"Path contains non-cardinal or non-adjacent step: {current!r} -> {following!r}"
            ) from error
        directions.append(direction)
    return tuple(directions)


def _reconstruct_path(
    came_from: dict[Coordinate, Coordinate],
    start: Coordinate,
    goal: Coordinate,
) -> tuple[Coordinate, ...]:
    reversed_path = [goal]
    current = goal
    while current != start:
        current = came_from[current]
        reversed_path.append(current)
    return tuple(reversed(reversed_path))
