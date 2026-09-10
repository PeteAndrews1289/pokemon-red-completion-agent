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
    bind_red_capture_status_profile,
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


def test_search_budget_is_prospective_and_survives_real_source_retargeting():
    from pokemon_red_completion.red_living_dex_wild_corridor import (
        bind_red_capture_search_budget_profile,
    )
    original = _local_discovery_profile()
    original_hash = original.profile_sha256
    bound = bind_red_capture_search_budget_profile(original)
    assert bound.profile_sha256 != original_hash
    assert original == _local_discovery_profile()
    assert original.providers[0].parameters["maximum_legs"] == 64
    assert "capture_search_budget" not in original.providers[0].parameters
    assert bound.providers[1:] == original.providers[1:]
    assert bound.providers[0].parameters["maximum_legs"] == 160
    assert bound.providers[0].parameters["maximum_seek_steps"] == 256
    assert bound.providers[0].parameters["maximum_encounters"] == 32
    assert bind_red_capture_search_budget_profile(bound) == bound
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"), _terrain(), _graph(),
    )
    for source, map_id in (("wild:Route2:grass", MapId.ROUTE_2),
                           ("wild:Route11:grass", MapId.ROUTE_11)):
        target = replace(corridor, source_id=source, map_id=int(map_id))
        moved = retarget_red_wild_profile(bound, target)
        assert moved.providers[0].parameters["maximum_legs"] == 160
        assert moved.providers[0].parameters["capture_search_budget"] == "bounded-search-v1"
        assert moved.providers[2].parameters["maximum_legs"] == 64
        assert retarget_red_wild_profile(original, target).providers[0].parameters[
            "maximum_legs"
        ] == 64


@pytest.mark.parametrize("key,value", [
    ("capture_search_budget", True), ("capture_search_budget", "unlimited"),
    ("maximum_legs", 161), ("maximum_legs", True),
    ("maximum_seek_steps", 257), ("maximum_encounters", 33),
    ("maximum_seek_steps", 200), ("maximum_legs", 159),
])
def test_search_budget_rejects_malformed_or_expanded_caps(key, value):
    from pokemon_red_completion.red_goal_context_profile import _thaw
    from pokemon_red_completion.red_living_dex_wild_corridor import (
        bind_red_capture_search_budget_profile,
    )
    bound = bind_red_capture_search_budget_profile(_local_discovery_profile())
    parameters = _thaw(bound.providers[0].parameters)
    parameters[key] = value
    with pytest.raises(RedGoalContextProfileError):
        parse_red_goal_context_profile(build_red_goal_context_profile_payload(
            profile_id="invalid-budget", providers=((
                GoalKind.ACQUIRE_SPECIES, RedGoalMechanic.WILD_CORRIDOR_CAPTURE, parameters,
            ), (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
                (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {})),
        ))


def test_search_budget_preserves_tighter_nonleg_limits_and_rejects_discovery_marker():
    from pokemon_red_completion.red_goal_context_profile import _thaw
    from pokemon_red_completion.red_living_dex_wild_corridor import (
        bind_red_capture_search_budget_profile,
    )
    parameters = _thaw(_local_discovery_profile().providers[0].parameters)
    parameters.update(maximum_seek_steps=20, maximum_encounters=3)
    profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id="tight-budget", providers=((
            GoalKind.ACQUIRE_SPECIES, RedGoalMechanic.WILD_CORRIDOR_CAPTURE, parameters,
        ), (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
            (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {})),
    ))
    bound = bind_red_capture_search_budget_profile(profile)
    assert bound.providers[0].parameters["maximum_legs"] == 12
    assert bound.providers[0].parameters["maximum_seek_steps"] == 20
    assert bound.providers[0].parameters["maximum_encounters"] == 3
    parameters["capture_search_budget"] = "bounded-search-v1"
    with pytest.raises(RedGoalContextProfileError, match="capture search budget"):
        parse_red_goal_context_profile(build_red_goal_context_profile_payload(
            profile_id="bad-mechanic", providers=((
                GoalKind.EXPLORE, RedGoalMechanic.WILD_CORRIDOR_DISCOVERY, parameters,
            ), (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
                (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {})),
        ))


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


def test_noncanonical_corridor_requires_matching_cartridge_encounters(monkeypatch):
    terrain = replace(_terrain(), map_id=int(MapId.ROUTE_15))
    target = RedEncounterSourceTarget("wild:Route15:grass")
    with pytest.raises(RedLivingDexWildCorridorError, match="authenticated ordinary"):
        derive_red_living_dex_wild_corridor(target, terrain, _graph())
    monkeypatch.setattr("pokemon_red_completion.gen1_cartridge.wild_tables",
                        lambda rom, *, medium: {int(MapId.ROUTE_15): [(10, 1)]})
    actual = derive_red_living_dex_wild_corridor(target, terrain, _graph(), cartridge=b"fixture")
    assert actual.source_id == target.source_id and actual.map_id == int(MapId.ROUTE_15)
    monkeypatch.setattr("pokemon_red_completion.gen1_cartridge.wild_tables",
                        lambda rom, *, medium: {int(MapId.ROUTE_11): [(10, 1)]})
    with pytest.raises(RedLivingDexWildCorridorError, match="authenticated ordinary"):
        derive_red_living_dex_wild_corridor(target, terrain, _graph(), cartridge=b"fixture")


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
    supported = bind_red_capture_status_profile(profile)
    assert "capture_status_support" not in profile.providers[0].parameters
    assert supported.providers[0].parameters["capture_status_support"] is True
    assert supported.providers[1:] == profile.providers[1:]
    assert supported.profile_sha256 != profile.profile_sha256
    assert retarget_red_wild_profile(supported, corridor).providers[0].parameters[
        "capture_status_support"
    ] is True
    for bad in (1, "true", None):
        with pytest.raises(RedGoalContextProfileError):
            parse_red_goal_context_profile(build_red_goal_context_profile_payload(
                profile_id="invalid-capture-support", providers=((
                    GoalKind.ACQUIRE_SPECIES, RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
                    {**old, "capture_status_support": bad},
                ),),
            ))


def test_opportunistic_capture_retargets_actual_cartridge_offers(monkeypatch):
    from pokemon_red_completion import gen1_cartridge as cartridge
    from pokemon_red_completion.red_living_dex_wild_corridor import (
        bind_red_opportunistic_capture_profile,
    )
    monkeypatch.setattr(cartridge, "internal_to_dex", lambda _: {90: 16, 91: 17, 92: 21})
    def tables(_, *, medium):
        assert medium == "grass"
        return {int(MapId.ROUTE_2): [(2, 90), (3, 91), (4, 90)],
                int(MapId.ROUTE_11): [(9, 92)]}
    monkeypatch.setattr(cartridge, "wild_tables", tables)
    original = _local_discovery_profile()
    bound = bind_red_opportunistic_capture_profile(original, b"fixture")
    assert bound.providers[0].parameters["capture_species_numbers"] == (16, 17)
    assert bound.providers[1:] == original.providers[1:]
    assert "capture_species_numbers" not in original.providers[0].parameters
    from dataclasses import replace
    corridor = replace(derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"), _terrain(), _graph(),
    ), source_id="wild:Route11:grass", map_id=int(MapId.ROUTE_11))
    moved = retarget_red_wild_profile(bound, corridor, rom=b"fixture")
    assert moved.providers[0].parameters["capture_species_numbers"] == (21,)
    with pytest.raises(RedLivingDexWildCorridorError, match="requires cartridge"):
        retarget_red_wild_profile(bound, corridor)


@pytest.mark.parametrize("numbers", [[], [True], [0], [152], [9, 9], [16, 9]])
def test_profile_rejects_invalid_local_capture_species(numbers):
    profile = _local_discovery_profile()
    with pytest.raises(RedGoalContextProfileError, match="local capture species"):
        parse_red_goal_context_profile(build_red_goal_context_profile_payload(
            profile_id="invalid-capture-offers", providers=((
                GoalKind.ACQUIRE_SPECIES, RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
                {**profile.providers[0].parameters, "forward_directions": ["up"],
                 "capture_species_numbers": numbers},
            ),),
        ))


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
