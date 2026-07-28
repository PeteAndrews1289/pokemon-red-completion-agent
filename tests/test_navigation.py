from __future__ import annotations

import pytest

from pokemon_red_completion.navigation import (
    Coordinate,
    Direction,
    GridMap,
    NoPathError,
    path_to_directions,
    shortest_path,
)


def test_shortest_path_uses_cardinal_steps_and_includes_endpoints() -> None:
    grid = GridMap(width=5, height=4)

    path = shortest_path(grid, Coordinate(0, 0), Coordinate(3, 2))

    assert path[0] == Coordinate(0, 0)
    assert path[-1] == Coordinate(3, 2)
    assert len(path) == 6
    assert len(path_to_directions(path)) == 5


def test_obstacle_is_avoided() -> None:
    wall = frozenset({Coordinate(1, 0), Coordinate(1, 1), Coordinate(1, 2)})
    grid = GridMap(width=4, height=4, blocked=wall)

    path = shortest_path(grid, Coordinate(0, 0), Coordinate(2, 0))

    assert all(point not in wall for point in path)
    assert path[-1] == Coordinate(2, 0)


def test_tie_breaking_is_stable() -> None:
    grid = GridMap(width=3, height=3)
    start = Coordinate(0, 0)
    goal = Coordinate(2, 2)

    paths = {shortest_path(grid, start, goal) for _ in range(10)}

    assert len(paths) == 1


def test_start_equal_to_goal_has_no_movement() -> None:
    start = Coordinate(1, 1)

    path = shortest_path(GridMap(width=3, height=3), start, start)

    assert path == (start,)
    assert path_to_directions(path) == ()


def test_blocked_interaction_target_can_be_allowed_explicitly() -> None:
    goal = Coordinate(1, 0)
    grid = GridMap(width=2, height=1, blocked=frozenset({goal}))

    with pytest.raises(NoPathError, match="Goal coordinate is blocked"):
        shortest_path(grid, Coordinate(0, 0), goal)

    assert shortest_path(
        grid,
        Coordinate(0, 0),
        goal,
        allow_blocked_goal=True,
    ) == (Coordinate(0, 0), goal)


def test_unreachable_and_invalid_coordinates_fail_clearly() -> None:
    grid = GridMap(
        width=3,
        height=3,
        blocked=frozenset({Coordinate(1, 0), Coordinate(1, 1), Coordinate(1, 2)}),
    )

    with pytest.raises(NoPathError, match="No path"):
        shortest_path(grid, Coordinate(0, 1), Coordinate(2, 1))
    with pytest.raises(ValueError, match="outside the grid"):
        shortest_path(grid, Coordinate(-1, 0), Coordinate(2, 1))


def test_path_to_directions_rejects_invalid_jump() -> None:
    with pytest.raises(ValueError, match="non-cardinal"):
        path_to_directions((Coordinate(0, 0), Coordinate(2, 0)))

    assert path_to_directions(
        (Coordinate(1, 1), Coordinate(1, 0), Coordinate(2, 0))
    ) == (Direction.UP, Direction.RIGHT)
