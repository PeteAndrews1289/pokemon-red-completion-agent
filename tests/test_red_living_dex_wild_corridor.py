from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_living_dex_provider_curriculum import (
    RedEncounterSourceTarget,
)
from pokemon_red_completion.red_living_dex_wild_corridor import (
    RedLivingDexWildCorridorError,
    bind_red_local_discovery_profile,
    derive_red_living_dex_wild_corridor,
    retarget_red_wild_profile,
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


def test_regional_retargeting_moves_both_surveys_not_other_skills_or_budgets():
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"), _terrain(), _graph(),
    )
    old = {**corridor.profile_parameters(), "source_id": "wild:Route11:grass",
           "map_id": int(MapId.ROUTE_11), "player_x": 17, "player_y": 8,
           "maximum_encounters": 3, "maximum_legs": 12, "maximum_seek_steps": 20}
    profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id="regional-test", providers=(
            (GoalKind.ACQUIRE_SPECIES, RedGoalMechanic.WILD_CORRIDOR_CAPTURE, old),
            (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
            (GoalKind.EXPLORE, RedGoalMechanic.WILD_CORRIDOR_DISCOVERY, old),
        ),
    ))
    moved = retarget_red_wild_profile(profile, corridor)
    assert moved.profile_sha256 != profile.profile_sha256
    assert moved.profile_id == profile.profile_id
    assert moved.providers[1] == profile.providers[1]
    assert profile.providers[0].parameters["source_id"] == "wild:Route11:grass"
    for spec in (moved.providers[0], moved.providers[2]):
        assert spec.parameters["source_id"] == "wild:Route2:grass"
        assert (spec.parameters["map_id"], spec.parameters["player_y"],
                spec.parameters["player_x"]) == (int(MapId.ROUTE_2), 3, 1)
        assert spec.parameters["maximum_encounters"] == 3
        assert spec.parameters["maximum_legs"] == 12
        assert spec.parameters["maximum_seek_steps"] == 20
    assert retarget_red_wild_profile(moved, corridor) == moved


def _local_discovery_profile(numbers=None):
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"), _terrain(), _graph(),
    )
    params = corridor.profile_parameters()
    if numbers is not None:
        params["source_species_numbers"] = numbers
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id="local-discovery", providers=(
            (GoalKind.ACQUIRE_SPECIES, RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
             corridor.profile_parameters()),
            (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
            (GoalKind.EXPLORE, RedGoalMechanic.WILD_CORRIDOR_DISCOVERY, params),
        ),
    ))


def test_local_discovery_uses_cartridge_slots_not_canonical_acquisition(monkeypatch):
    from pokemon_red_completion import gen1_cartridge as cartridge
    monkeypatch.setattr(cartridge, "internal_to_dex", lambda _: {90: 16, 91: 13, 92: 16})
    def tables(_, *, medium):
        assert medium == "grass"
        return {int(MapId.ROUTE_2): [(2, 90), (3, 91), (4, 92)],
                int(MapId.ROUTE_11): [(9, 92)]}
    monkeypatch.setattr(cartridge, "wild_tables", tables)
    original = _local_discovery_profile()
    bound = bind_red_local_discovery_profile(original, "wild:Route2:grass", b"fixture")
    assert bound.providers[:2] == original.providers[:2]
    assert bound.providers[2].parameters["source_species_numbers"] == (13, 16)
    assert "source_species_numbers" not in original.providers[2].parameters
    assert bound.profile_sha256 != original.profile_sha256
    with pytest.raises(RedLivingDexWildCorridorError, match="source differs"):
        bind_red_local_discovery_profile(original, "wild:Route11:grass", b"fixture")
    # A regional retarget cannot carry stale sighting facts from its old source.
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"), _terrain(), _graph(),
    )
    assert "source_species_numbers" not in retarget_red_wild_profile(
        bound, corridor,
    ).providers[2].parameters


@pytest.mark.parametrize("numbers", [[], [True], [0], [152], [9, 9], [16, 9]])
def test_profile_rejects_invalid_local_discovery_species(numbers):
    with pytest.raises(RedGoalContextProfileError, match="local discovery species"):
        _local_discovery_profile(numbers)


def test_regional_retargeting_rejects_missing_survey():
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"), _terrain(), _graph(),
    )
    profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id="no-capture", providers=(
            (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
            (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
            (GoalKind.EXPLORE, RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
             corridor.profile_parameters()),
        ),
    ))
    with pytest.raises(RedLivingDexWildCorridorError, match="capture and discovery"):
        retarget_red_wild_profile(profile, corridor)


def test_regional_retargeting_does_not_move_mansion_only_battle_dose():
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"), _terrain(), _graph(),
    )
    parameters = corridor.profile_parameters()
    development = {**parameters, "map_id": int(MapId.POKEMON_MANSION_1F),
                   "source_id": "wild:PokemonMansion1F:grass", "completed_battles": 4}
    profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id="venue-bound", providers=(
            (GoalKind.ACQUIRE_SPECIES, RedGoalMechanic.WILD_CORRIDOR_CAPTURE, parameters),
            (GoalKind.DEVELOP_TEAM, RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT, development),
            (GoalKind.EXPLORE, RedGoalMechanic.WILD_CORRIDOR_DISCOVERY, parameters),
        ),
    ))
    with pytest.raises(RedLivingDexWildCorridorError, match="venue-bound development"):
        retarget_red_wild_profile(profile, corridor)


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
