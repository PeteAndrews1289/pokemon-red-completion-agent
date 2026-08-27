from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_living_dex_provider_curriculum import (
    RedEncounterSourceTarget,
)
from pokemon_red_completion.red_living_dex_wild_corridor import (
    RedLivingDexWildCorridorError,
    derive_red_living_dex_wild_corridor,
)


def _terrain() -> Terrain:
    grass = [[False] * 6 for _ in range(6)]
    for y, x in ((2, 1), (3, 1), (2, 4), (3, 4)):
        grass[y][x] = True
    return Terrain(
        map_id=int(MapId.ROUTE_2),
        tileset=0,
        walkable=tuple(tuple(True for _ in range(6)) for _ in range(6)),
        grass=tuple(tuple(row) for row in grass),
        water=tuple(tuple(False for _ in range(6)) for _ in range(6)),
        tiles=tuple(tuple(0 for _ in range(6)) for _ in range(6)),
    )


def _graph(*, one_way: bool = False) -> LocalGraph:
    edges: dict[tuple[int, int], tuple[LocalEdge, ...]] = {}
    for x in (1, 4):
        south = (3, x)
        north = (2, x)
        edges[south] = (
            LocalEdge(
                north,
                "up",
                required_mode="land",
                action_kind=MacroActionKind.MOVE,
            ),
        )
        if not one_way:
            edges[north] = (
                LocalEdge(
                    south,
                    "down",
                    required_mode="land",
                    action_kind=MacroActionKind.MOVE,
                ),
            )
    return LocalGraph(edges)


def test_derives_a_reversible_grass_pair_without_a_teacher_route() -> None:
    target = RedEncounterSourceTarget("wild:Route2:grass")
    corridor = derive_red_living_dex_wild_corridor(
        target,
        _terrain(),
        _graph(),
    )

    assert corridor.origin_at == (3, 1)
    assert corridor.terminal_at == (2, 1)
    assert corridor.profile_parameters() == {
        "source_id": "wild:Route2:grass",
        "label": "cartridge-derived reversible encounter corridor",
        "map_id": int(MapId.ROUTE_2),
        "player_x": 1,
        "player_y": 3,
        "forward_directions": ["up"],
        "starting_endpoint": "south",
        "maximum_legs": 64,
        "maximum_seek_steps": 256,
        "maximum_encounters": 32,
    }
    assert corridor.public_dict() == {
        "bidirectional_walk_edges": 2,
        "cartridge_derived": True,
        "encounter_tiles": 2,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "provider_local_direction_steps": 1,
        "raw_teacher_direction_steps": 0,
        "schema": "pokemon.red.private-living-dex-wild-corridor.v1",
        "teacher_route": False,
    }


def test_exclusions_change_the_pair_without_becoming_family_identity() -> None:
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"),
        _terrain(),
        _graph(),
        excluded={(3, 1)},
    )

    assert corridor.origin_at == (3, 4)
    assert corridor.terminal_at == (2, 4)
    assert "excluded" not in corridor.private_dict()


def test_rejects_a_one_way_or_non_grass_corridor() -> None:
    with pytest.raises(RedLivingDexWildCorridorError, match="no unobstructed"):
        derive_red_living_dex_wild_corridor(
            RedEncounterSourceTarget("wild:Route2:grass"),
            _terrain(),
            _graph(one_way=True),
        )

    with pytest.raises(RedLivingDexWildCorridorError, match="terrain differs"):
        derive_red_living_dex_wild_corridor(
            RedEncounterSourceTarget("wild:Route2:grass"),
            replace(_terrain(), map_id=int(MapId.ROUTE_3)),
            _graph(),
        )


def test_derived_parameters_build_the_existing_real_provider_profile() -> None:
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"),
        _terrain(),
        _graph(),
    )
    profile = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id="derived-wild-corridor",
            providers=(
                (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
                (
                    GoalKind.ACQUIRE_SPECIES,
                    RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
                    corridor.profile_parameters(),
                ),
                (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
            ),
        )
    )

    acquisition = next(
        provider
        for provider in profile.providers
        if provider.kind is GoalKind.ACQUIRE_SPECIES
    )
    assert acquisition.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE
    assert acquisition.parameters["source_id"] == "wild:Route2:grass"
