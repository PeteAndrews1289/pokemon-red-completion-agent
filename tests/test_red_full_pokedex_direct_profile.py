from dataclasses import replace

import pytest
from test_current_route_terrain import _world
from test_registered_runtime_binding import bound_fixture

from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_full_pokedex_direct_profile import (
    RedFullPokedexDirectProfileError,
    derive_direct_full_pokedex_profile,
)
from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic
from pokemon_red_completion.red_living_dex_wild_corridor import RedLivingDexWildCorridor


def _corridor():
    return RedLivingDexWildCorridor(
        "wild:Route1:grass",
        int(MapId.ROUTE_1),
        (3, 1),
        (2, 1),
    )


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
