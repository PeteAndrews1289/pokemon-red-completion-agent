from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from pokemon_red_completion.gen1_traversal import MapObjectEvent
from pokemon_red_completion.local_router import LocalEdge, LocalGraph

SCRIPT = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "falsify_cinnabar_visible_object_route.py")
)
select_probe_goal = SCRIPT["select_probe_goal"]


def graph() -> LocalGraph:
    return LocalGraph(
        {
            (0, 0): (
                LocalEdge((0, 1), action="right"),
                LocalEdge((1, 0), action="down"),
            ),
            (0, 1): (LocalEdge((0, 2), action="right"),),
            (1, 0): (LocalEdge((1, 1), action="right"),),
            (1, 1): (LocalEdge((1, 2), action="right"),),
            (1, 2): (LocalEdge((0, 2), action="up"),),
            (0, 2): (),
        }
    )


def event(*, movement: int = 0xFF) -> MapObjectEvent:
    return MapObjectEvent(
        map_id=8,
        sprite_id=11,
        y=0,
        x=1,
        movement=movement,
        direction_or_range=0xFF,
        text_id=2,
    )


def test_selection_proves_the_unblocked_candidate_crosses_an_avoidable_object() -> None:
    selected = select_probe_goal(graph(), (0, 0), (event(),))

    assert selected.blocker.at == (0, 1)
    assert selected.goal == (0, 2)
    assert selected.unblocked_path.coordinates == ((0, 0), (0, 1), (0, 2))
    assert selected.avoiding_path.coordinates == (
        (0, 0),
        (1, 0),
        (1, 1),
        (1, 2),
        (0, 2),
    )


def test_selection_does_not_mislabel_a_moving_object_as_the_fixed_control() -> None:
    with pytest.raises(RuntimeError, match="no stationary Cinnabar object"):
        select_probe_goal(graph(), (0, 0), (event(movement=0xFE),))
