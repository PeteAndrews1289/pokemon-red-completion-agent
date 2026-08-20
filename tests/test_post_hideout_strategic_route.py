from __future__ import annotations

from typing import cast

import pytest

from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.post_hideout_strategic_route import (
    POST_HIDEOUT_COLLECTION_DESTINATION,
    POST_HIDEOUT_STORY_DESTINATION,
    PostHideoutStrategicApproach,
    PostHideoutStrategicRouteError,
    post_hideout_destination_bindings,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route
from pokemon_red_completion.strategic_navigation import StrategicNavigationTag
from pokemon_red_completion.strategic_navigation_trajectory import (
    StrategicNavigationTrajectoryObserver,
)


def _plans() -> tuple[RoutePlan, RoutePlan]:
    graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), action="right"),),
            (0, 1): (LocalEdge((0, 2), action="right"),),
            (0, 2): (),
        }
    )
    macro = MacroGraph({1: ()})
    short = plan_route(macro, {1: graph}, 1, (0, 0), 1, goal_at=(0, 1))
    long = plan_route(macro, {1: graph}, 1, (0, 0), 1, goal_at=(0, 2))
    return long, short


def test_post_hideout_bindings_preserve_non_cost_teacher_choice() -> None:
    story, collection = _plans()

    bindings = post_hideout_destination_bindings(story, collection)

    assert tuple(item.destination_ref for item in bindings) == (
        POST_HIDEOUT_STORY_DESTINATION,
        POST_HIDEOUT_COLLECTION_DESTINATION,
    )
    assert bindings[0].plan is story
    assert bindings[1].plan is collection
    assert bindings[0].semantic_tags == (
        StrategicNavigationTag.REMOVE_BLOCKER,
        StrategicNavigationTag.STORY_PROGRESS,
    )


def test_post_hideout_bindings_fail_if_story_stops_rejecting_minimum_cost() -> None:
    story, collection = _plans()

    with pytest.raises(PostHideoutStrategicRouteError, match="cost minimum"):
        post_hideout_destination_bindings(collection, story)


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("maximum_flees", -1),
        ("maximum_trainer_battles", -1),
        ("stabilization_frames", 0),
    ),
)
def test_post_hideout_approach_rejects_invalid_runtime_bounds(
    field: str,
    invalid: int,
) -> None:
    with pytest.raises(ValueError):
        PostHideoutStrategicApproach(
            rom=b"rom",
            reader=cast(PokemonRedStateReader, object()),
            trajectory=cast(StrategicNavigationTrajectoryObserver, object()),
            **{field: invalid},
        )
