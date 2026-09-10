from dataclasses import replace

import pytest

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.collection_acquisition_demand import useful_registered_capture_counts
from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_owned_evolution_inventory import (
    inventory_red_owned_level_evolutions,
)
from pokemon_red_completion.registered_collection import collection_registration_refs
from pokemon_red_completion.registration_memory import (
    RegistrationMemory,
    RegistrationObservation,
    observation_from_collection,
)


def fixture(tmp_path):
    mapping = {red_species_ref(n): n for n in (14, 15, 56, 57)}
    observation = CollectionObservation(
        frozenset(map(red_species_ref, (14, 56))),
        (LivingSpecimen(red_species_ref(14), 9, CollectionLocation.BOX, slot_index=0),
         LivingSpecimen(red_species_ref(56), 27, CollectionLocation.BOX, slot_index=1)),
        0, 6, (2,), 0, 20,
    )
    memory = RegistrationMemory(tmp_path / "dex.sqlite")
    memory.record(RegistrationObservation(
        "prior", "red", "red-ordinal-v1", "a" * 64, "b" * 64, 0,
        frozenset({14, 15}), frozenset({14, 15}), {15: 1},
    ))
    memory.record(observation_from_collection(
        observation, seen_species=observation.owned_species, national_ids=mapping,
        run_id="current", game_id="blue", adapter_id="blue-ordinal-v1",
        cartridge_sha256="c" * 64, snapshot_sha256="d" * 64, sequence=0,
    ))
    return mapping, observation, memory


def test_durable_memory_drives_capture_and_evolution_priorities_not_fake_local_flags(tmp_path):
    mapping, obs, memory = fixture(tmp_path)
    refs = collection_registration_refs(
        memory.snapshot(), obs, run_id="current", snapshot_sha256="d" * 64,
        national_ids=mapping,
    )
    assert refs == frozenset(map(red_species_ref, (14, 15, 56)))
    targets = frozenset(map(red_species_ref, (15, 57)))
    graph = {14: (Evolution(14, 15, EvolutionMethod.LEVEL, 10),),
             56: (Evolution(56, 57, EvolutionMethod.LEVEL, 28),)}
    rows = inventory_red_owned_level_evolutions(obs, graph, target_species=targets,
                                              registered_species=refs)
    assert len(rows) == 1 and rows[0].target_species_ref == red_species_ref(57)
    assert rows[0].duplicate_acquisitions_needed == 0
    assert rows[0].evolution_level == 28  # Not an arbitrary training cap.
    result = useful_registered_capture_counts(
        targets, refs, {red_species_ref(14): 1, red_species_ref(56): 1},
        ((red_species_ref(14), red_species_ref(15)),
         (red_species_ref(56), red_species_ref(57))),
        (red_species_ref(14), red_species_ref(56)),
    )
    assert result == {red_species_ref(14): 0, red_species_ref(56): 0}
    assert obs.owned_species == frozenset(map(red_species_ref, (14, 56)))


@pytest.mark.parametrize("change", ["checkpoint", "local_flags", "physical", "mapping"])
def test_stale_or_aliased_planning_inputs_are_rejected(tmp_path, change):
    mapping, obs, memory = fixture(tmp_path)
    snapshot = "d" * 64
    if change == "checkpoint":
        snapshot = "e" * 64
    elif change == "local_flags":
        obs = replace(obs, owned_species=obs.owned_species | {red_species_ref(15)})
    elif change == "physical":
        obs = replace(obs, specimens=obs.specimens[:1], box_counts=(1,))
    else:
        mapping[red_species_ref(14)] = 15
    with pytest.raises(ValueError):
        collection_registration_refs(memory.snapshot(), obs, run_id="current",
                                     snapshot_sha256=snapshot, national_ids=mapping)
