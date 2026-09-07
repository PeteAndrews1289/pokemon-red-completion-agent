from dataclasses import replace

import pytest

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_owned_evolution_inventory import (
    inventory_red_owned_level_evolutions,
    unique_owned_level_evolution,
)


def observation(*numbers, owned=()):
    return CollectionObservation(
        frozenset(map(red_species_ref, owned)),
        tuple(LivingSpecimen(red_species_ref(n), 4 + i, CollectionLocation.BOX,
                             container_index=i // 20, slot_index=i % 20)
              for i, n in enumerate(numbers)),
        0, 6, (min(20, len(numbers)), max(0, len(numbers) - 20)), 0, 20,
    )


GRAPH = {
    14: (Evolution(14, 15, EvolutionMethod.LEVEL, 10),),
    56: (Evolution(56, 57, EvolutionMethod.LEVEL, 28),),
    63: (Evolution(63, 64, EvolutionMethod.LEVEL, 16),),
    25: (Evolution(25, 26, EvolutionMethod.STONE, 33),),
    64: (Evolution(64, 65, EvolutionMethod.TRADE),),
}
TARGETS = frozenset(map(red_species_ref, (15, 57, 64, 26, 65)))


def inventory(obs, graph=GRAPH, targets=TARGETS):
    return inventory_red_owned_level_evolutions(obs, graph, target_species=targets)


def test_distinct_targets_not_duplicate_specimens_and_explicit_prerequisites():
    rows = inventory(observation(14, 14, 56, 63, 64, 25))
    assert [(row.target_species_ref, row.retained_source_copies,
             row.duplicate_acquisitions_needed) for row in rows] == [
        ("pokemon:national:015", 2, 0), ("pokemon:national:057", 1, 1),
    ]
    assert rows[0].has_owned_surplus and not rows[1].has_owned_surplus
    assert [s.slot_index for s in rows[0].party_or_box_precursors] == [0, 1]
    assert [s.level for s in rows[0].party_or_box_precursors] == [4, 5]
    assert rows[0].evolution_level == 10 and rows[1].evolution_level == 28


def test_registered_is_not_living_and_more_than_two_copies_still_preserves_source():
    rows = inventory(observation(14, 14, 14, owned=(15,)))
    assert len(rows) == 1 and rows[0].retained_source_copies == 3
    assert rows[0].has_owned_surplus
    assert inventory(observation(14, 14, 15)) == ()


def test_permutation_and_inactive_box_identity_do_not_change_objective_inventory():
    obs = observation(*(25 for _ in range(20)), 14, 14, 56)
    rows = inventory(obs)
    assert [s.container_index for s in rows[0].party_or_box_precursors] == [1, 1]
    assert [s.slot_index for s in rows[0].party_or_box_precursors] == [0, 1]
    assert inventory(replace(obs, specimens=tuple(reversed(obs.specimens)))) == rows


def test_level_changes_do_not_create_fake_objectives_and_unowned_sources_are_absent():
    obs = observation(14, 14)
    advanced = replace(obs, specimens=tuple(replace(s, level=50) for s in obs.specimens))
    assert len(inventory(advanced)) == 1
    assert inventory(advanced)[0].evolution_level == 10
    assert inventory(observation(25)) == ()
    assert inventory(obs, targets=frozenset()) == ()


def test_daycare_counts_for_retention_but_is_not_a_party_or_box_specimen():
    obs = observation(14, 14)
    daycare = replace(obs.specimens[0], location=CollectionLocation.DAYCARE)
    row = inventory(replace(obs, specimens=(daycare, obs.specimens[1])))[0]
    assert row.has_owned_surplus
    assert row.party_or_box_precursors == (obs.specimens[1],)


@pytest.mark.parametrize("rule", [
    Evolution(56, 15, EvolutionMethod.LEVEL, 10),
    Evolution(14, 15, EvolutionMethod.LEVEL, None),
    Evolution(14, 15, EvolutionMethod.LEVEL, True),
    Evolution(14, 15, EvolutionMethod.LEVEL, 0),
    Evolution(14, 15, EvolutionMethod.LEVEL, 101),
    Evolution(14, 14, EvolutionMethod.LEVEL, 10),
    Evolution(14, 152, EvolutionMethod.LEVEL, 10),
])
def test_malformed_rules_are_rejected(rule):
    with pytest.raises(ValueError):
        inventory(observation(14, 14), {14: (rule,)})


def test_duplicate_rules_are_not_duplicate_choices():
    rule = GRAPH[14][0]
    with pytest.raises(ValueError, match="duplicate"):
        inventory(observation(14, 14), {14: (rule, rule)})


def test_unique_supported_target_is_derived_not_selected_by_specimen_order():
    obs = observation(56, 14, 63, 14)
    row = unique_owned_level_evolution(obs, GRAPH, target_species=TARGETS)
    assert (row.source_species_ref, row.target_species_ref, row.evolution_level) == (
        "pokemon:national:014", "pokemon:national:015", 10,
    )
    assert unique_owned_level_evolution(
        replace(obs, specimens=tuple(reversed(obs.specimens))), GRAPH,
        target_species=TARGETS,
    ) == row


@pytest.mark.parametrize("numbers", [(14,), (14, 14, 14), (14, 14, 56, 56), (25, 25)])
def test_unique_binding_refuses_unsupported_or_ambiguous_objectives(numbers):
    with pytest.raises(ValueError, match="exactly one"):
        unique_owned_level_evolution(observation(*numbers), GRAPH, target_species=TARGETS)


def test_unique_binding_needs_an_accessible_specimen_not_only_daycare_stock():
    obs = observation(14, 14)
    obs = replace(obs, specimens=tuple(
        replace(s, location=CollectionLocation.DAYCARE) for s in obs.specimens
    ))
    with pytest.raises(ValueError, match="exactly one"):
        unique_owned_level_evolution(obs, GRAPH, target_species=TARGETS)
