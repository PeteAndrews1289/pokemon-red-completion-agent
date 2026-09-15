from dataclasses import replace

import pytest
from test_current_route_terrain import _world
from test_red_living_dex_wild_corridor import _graph, _terrain
from test_registered_runtime_binding import bound_fixture

from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_full_pokedex_direct_profile import (
    RedFullPokedexDirectProfileError,
    _capture_corridor,
    _wild_sources,
    derive_direct_full_pokedex_profile,
)
from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic
from pokemon_red_completion.red_living_dex_multifamily_curriculum import (
    map_id_for_wild_source,
)
from pokemon_red_completion.red_living_dex_wild_corridor import RedLivingDexWildCorridor


def _corridor():
    return RedLivingDexWildCorridor(
        "wild:Route1:grass",
        int(MapId.ROUTE_1),
        (3, 1),
        (2, 1),
    )


def _with_missing(observed, *numbers, map_id=None):
    owned = frozenset(
        red_species_ref(number) for number in range(1, 152) if number not in numbers
    )
    raw = observed.raw if map_id is None else replace(observed.raw, map_id=int(map_id))
    return replace(
        observed,
        raw=raw,
        collection_observation=replace(
            observed.collection_observation,
            owned_species=owned,
        ),
    )


def _route_2_world():
    world = _world()
    map_id = int(MapId.ROUTE_2)
    return replace(
        world,
        local_graphs={map_id: _graph()},
        terrain={map_id: _terrain()},
        object_blockers={map_id: frozenset()},
    )


@pytest.mark.nonconsuming_direct_rehearsal
def test_direct_wild_sources_are_grass_compatible_across_complete_catalog(tmp_path):
    runtime, _, _ = bound_fixture(tmp_path)
    observed = _with_missing(runtime.adapter.observe(), *range(1, 152))
    sources = tuple(_wild_sources(observed))
    assert "wild:Route21:water" not in sources
    assert sources
    assert all(source.endswith(":grass") for source in sources)
    assert len(tuple(map_id_for_wild_source(source) for source in sources)) == len(sources)


@pytest.mark.nonconsuming_direct_rehearsal
def test_direct_wild_sources_prefer_route_21_grass_over_colocated_water(tmp_path):
    runtime, _, _ = bound_fixture(tmp_path)
    observed = _with_missing(
        runtime.adapter.observe(),
        72,
        114,
        map_id=MapId.ROUTE_21,
    )
    assert tuple(_wild_sources(observed)) == ("wild:Route21:grass",)


@pytest.mark.nonconsuming_direct_rehearsal
def test_direct_profile_uses_real_catalog_and_corridor_derivation(tmp_path):
    runtime, _, _ = bound_fixture(tmp_path)
    observed = _with_missing(
        runtime.adapter.observe(),
        13,
        72,
        78,
        map_id=MapId.ROUTE_2,
    )
    profile = derive_direct_full_pokedex_profile(
        runtime.profile,
        observed,
        _route_2_world(),
    )
    capture = next(spec for spec in profile.providers if spec.kind is GoalKind.ACQUIRE_SPECIES)
    assert capture.parameters["source_id"] == "wild:Route2:grass"
    assert capture.parameters["map_id"] == int(MapId.ROUTE_2)


@pytest.mark.nonconsuming_direct_rehearsal
def test_direct_profile_reports_clean_exhaustion_when_only_water_is_missing(tmp_path):
    runtime, _, _ = bound_fixture(tmp_path)
    observed = _with_missing(runtime.adapter.observe(), 72, 78)
    with pytest.raises(
        RedFullPokedexDirectProfileError,
        match="no missing cartridge-derived wild corridor",
    ):
        derive_direct_full_pokedex_profile(runtime.profile, observed, _world())


@pytest.mark.nonconsuming_direct_rehearsal
def test_capture_corridor_defends_against_an_invalid_candidate(tmp_path, monkeypatch):
    runtime, _, _ = bound_fixture(tmp_path)
    monkeypatch.setattr(
        "pokemon_red_completion.red_full_pokedex_direct_profile._wild_sources",
        lambda observation: ("wild:Route21:water",),
    )
    with pytest.raises(
        RedFullPokedexDirectProfileError,
        match="no missing cartridge-derived wild corridor",
    ):
        _capture_corridor(runtime.adapter.observe(), _world())


def test_direct_profile_derives_targets_from_inventory_and_cartridge_adapter(
    tmp_path, monkeypatch
):
    runtime, _, _ = bound_fixture(tmp_path)
    observed = runtime.adapter.observe()
    monkeypatch.setattr(
        "pokemon_red_completion.red_full_pokedex_direct_profile._capture_corridor",
        lambda actual, world: _corridor()
        if actual is observed and world is not None
        else pytest.fail("wrong derivation inputs"),
    )
    profile = derive_direct_full_pokedex_profile(runtime.profile, observed, _world())
    specs = {spec.kind: spec for spec in profile.providers}
    assert specs[GoalKind.ACQUIRE_SPECIES].mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE
    assert specs[GoalKind.ACQUIRE_SPECIES].parameters["source_id"] == "wild:Route1:grass"
    evolution = specs[GoalKind.EVOLVE_SPECIES]
    assert evolution.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION
    assert evolution.parameters == {
        "source_species_ref": "pokemon:national:077",
        "target_species_ref": "pokemon:national:078",
        "evolution_level": 40,
    }
    assert {
        spec.kind
        for spec in runtime.profile.providers
        if spec.kind not in {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}
    } <= set(specs)


def test_direct_profile_refuses_to_invent_evolution_without_boxed_precursor(
    tmp_path,
):
    runtime, _, _ = bound_fixture(tmp_path)
    observed = runtime.adapter.observe()
    collection = replace(
        observed.collection_observation,
        specimens=tuple(
            specimen
            for specimen in observed.collection_observation.specimens
            if specimen.location is not CollectionLocation.BOX
        ),
    )
    with pytest.raises(RedFullPokedexDirectProfileError, match="boxed level evolution"):
        derive_direct_full_pokedex_profile(
            runtime.profile,
            replace(observed, collection_observation=collection),
            _world(),
        )
