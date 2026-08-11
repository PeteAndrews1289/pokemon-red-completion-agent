from __future__ import annotations

from typing import cast

import pytest

from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.post_silph_strategic_route import (
    POST_SILPH_CHALLENGE_DESTINATION,
    POST_SILPH_COLLECTION_DESTINATION,
    PostSilphStrategicApproach,
    post_silph_destination_bindings,
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
    return (
        plan_route(macro, {1: graph}, 1, (0, 0), 1, goal_at=(0, 1)),
        plan_route(macro, {1: graph}, 1, (0, 0), 1, goal_at=(0, 2)),
    )


def test_post_silph_bindings_preserve_team_building_before_gym() -> None:
    collection, challenge = _plans()

    bindings = post_silph_destination_bindings(collection, challenge)

    assert tuple(item.destination_ref for item in bindings) == (
        POST_SILPH_COLLECTION_DESTINATION,
        POST_SILPH_CHALLENGE_DESTINATION,
    )
    assert bindings[0].plan is collection
    assert bindings[1].plan is challenge
    assert bindings[0].semantic_tags == (
        StrategicNavigationTag.ACQUIRE_PARTY_MEMBER,
        StrategicNavigationTag.COLLECTION,
        StrategicNavigationTag.IMPROVE_TEAM,
    )


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("maximum_flees", -1),
        ("maximum_trainer_battles", -1),
        ("stabilization_frames", 0),
    ),
)
def test_post_silph_approach_rejects_invalid_runtime_bounds(
    field: str,
    invalid: int,
) -> None:
    with pytest.raises(ValueError):
        PostSilphStrategicApproach(
            rom=b"rom",
            reader=cast(PokemonRedStateReader, object()),
            trajectory=cast(StrategicNavigationTrajectoryObserver, object()),
            **{field: invalid},
        )
