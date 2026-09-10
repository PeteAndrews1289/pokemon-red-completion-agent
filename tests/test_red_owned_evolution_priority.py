from dataclasses import FrozenInstanceError

import pytest

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_owned_evolution_inventory import (
    RedOwnedEvolutionPrerequisite,
    inventory_red_owned_level_evolutions,
)
from pokemon_red_completion.red_owned_evolution_priority import (
    PrioritizedOwnedLevelEvolution,
    prioritize_owned_level_evolutions,
)


def make_specimen(
    national_dex: int,
    level: int,
    location: CollectionLocation = CollectionLocation.BOX,
    slot_index: int = 0,
) -> LivingSpecimen:
    return LivingSpecimen(
        species_ref=red_species_ref(national_dex),
        level=level,
        location=location,
        container_index=0,
        slot_index=slot_index,
    )


def make_prerequisite(
    source_num: int,
    target_num: int,
    evolution_level: int,
    retained_copies: int,
    deficit: int,
    precursor_levels: tuple[int, ...] = (5,),
    location: CollectionLocation = CollectionLocation.BOX,
) -> RedOwnedEvolutionPrerequisite:
    precursors = tuple(
        make_specimen(source_num, lvl, location=location, slot_index=i)
        for i, lvl in enumerate(precursor_levels)
    )
    return RedOwnedEvolutionPrerequisite(
        source_species_ref=red_species_ref(source_num),
        target_species_ref=red_species_ref(target_num),
        evolution_level=evolution_level,
        retained_source_copies=retained_copies,
        duplicate_acquisitions_needed=deficit,
        party_or_box_precursors=precursors,
    )


def make_observation(
    *numbers: int,
    owned: tuple[int, ...] = (),
    locations: tuple[CollectionLocation, ...] | None = None,
) -> CollectionObservation:
    specimens = []
    for i, n in enumerate(numbers):
        loc = locations[i] if locations is not None else CollectionLocation.BOX
        specimens.append(
            LivingSpecimen(
                species_ref=red_species_ref(n),
                level=5,
                location=loc,
                container_index=i // 20,
                slot_index=i % 20,
            )
        )
    return CollectionObservation(
        owned_species=frozenset(map(red_species_ref, owned)),
        specimens=tuple(specimens),
        party_size=0,
        party_limit=6,
        box_counts=(min(20, len(numbers)), max(0, len(numbers) - 20)),
        current_box_index=0,
        box_capacity=20,
    )


def test_reordered_inputs_produce_identical_priority_order():
    # Four distinct eligible rows with different required gains and tie breakers
    # Row 1: Kakuna -> Beedrill (level 7 -> 10, gains = 3)
    row_beedrill = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=2, deficit=0, precursor_levels=(7,)
    )
    # Row 2: Caterpie -> Metapod (level 6 -> 7, gains = 1)
    row_metapod = make_prerequisite(
        10, 11, evolution_level=7, retained_copies=2, deficit=0, precursor_levels=(6,)
    )
    # Row 3: Pidgeotto -> Pidgeot (level 30 -> 36, gains = 6)
    row_pidgeot = make_prerequisite(
        17, 18, evolution_level=36, retained_copies=2, deficit=0, precursor_levels=(30,)
    )
    # Row 4: Pidgey -> Pidgeotto (level 15 -> 18, gains = 3)
    row_pidgeotto = make_prerequisite(
        16, 17, evolution_level=18, retained_copies=2, deficit=0, precursor_levels=(15,)
    )

    expected_targets = [
        red_species_ref(11),  # gains = 1
        red_species_ref(15),  # gains = 3, target 015 < target 017
        red_species_ref(17),  # gains = 3, target 017
        red_species_ref(18),  # gains = 6
    ]

    order_1 = [row_beedrill, row_metapod, row_pidgeot, row_pidgeotto]
    order_2 = [row_pidgeot, row_pidgeotto, row_beedrill, row_metapod]
    order_3 = [row_metapod, row_pidgeot, row_beedrill, row_pidgeotto]

    res_1 = prioritize_owned_level_evolutions(order_1)
    res_2 = prioritize_owned_level_evolutions(order_2)
    res_3 = prioritize_owned_level_evolutions(order_3)

    assert res_1 == res_2 == res_3
    assert [item.prerequisite.target_species_ref for item in res_1] == expected_targets
    assert [item.minimum_level_gains for item in res_1] == [1, 3, 3, 6]


def test_level_above_threshold_requires_at_least_one_level_gain():
    # Precursor level is above evolution threshold: max(1, 10 - 25) = 1, NOT 0 or negative
    row_above = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=2, deficit=0, precursor_levels=(25,)
    )
    prioritized_above = prioritize_owned_level_evolutions([row_above])
    assert len(prioritized_above) == 1
    assert prioritized_above[0].minimum_level_gains == 1

    # Precursor level is exactly at evolution threshold: max(1, 10 - 10) = 1
    row_equal = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=2, deficit=0, precursor_levels=(10,)
    )
    prioritized_equal = prioritize_owned_level_evolutions([row_equal])
    assert len(prioritized_equal) == 1
    assert prioritized_equal[0].minimum_level_gains == 1

    # Precursor level far above threshold (e.g. level 70, evo 16)
    row_far_above = make_prerequisite(
        16, 17, evolution_level=16, retained_copies=1, deficit=0, precursor_levels=(70,)
    )
    prioritized_far = prioritize_owned_level_evolutions([row_far_above])
    assert len(prioritized_far) == 1
    assert prioritized_far[0].minimum_level_gains == 1


def test_level_100_precursors_cannot_gain_level_and_are_ignored():
    # A sole level-100 precursor cannot gain a level.
    row_only_100 = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=2, deficit=0, precursor_levels=(100,)
    )
    assert prioritize_owned_level_evolutions([row_only_100]) == ()

    # All precursors are level 100 -> rejected
    row_all_100 = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=2, deficit=0, precursor_levels=(100, 100)
    )
    assert prioritize_owned_level_evolutions([row_all_100]) == ()

    # Multiple precursors: one is level 100 (ignored), one is level 12 (used: 16 - 12 = 4)
    row_mixed = make_prerequisite(
        16, 17, evolution_level=16, retained_copies=2, deficit=0, precursor_levels=(100, 12)
    )
    prioritized = prioritize_owned_level_evolutions([row_mixed])
    assert len(prioritized) == 1
    assert prioritized[0].minimum_level_gains == 4


def test_daycare_precursors_already_excluded_by_inventory_causes_rejection():
    # Integration with inventory: daycare specimens count toward retention,
    # but inventory does not include them in party_or_box_precursors.
    graph = {14: (Evolution(14, 15, EvolutionMethod.LEVEL, 10),)}
    targets = frozenset([red_species_ref(15)])
    obs = make_observation(
        14,
        14,
        locations=(CollectionLocation.DAYCARE, CollectionLocation.DAYCARE),
    )
    inv_rows = inventory_red_owned_level_evolutions(obs, graph, target_species=targets)
    assert len(inv_rows) == 1
    assert inv_rows[0].retained_source_copies == 2
    assert inv_rows[0].duplicate_acquisitions_needed == 0
    assert inv_rows[0].party_or_box_precursors == ()

    # When passed to priority, empty controllable precursors cause rejection
    assert prioritize_owned_level_evolutions(inv_rows) == ()

    # Direct fixture with empty precursors tuple
    row_empty = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=2, deficit=0, precursor_levels=()
    )
    assert prioritize_owned_level_evolutions([row_empty]) == ()

    # Direct fixture where precursor is only at DAYCARE
    row_daycare_only = make_prerequisite(
        14,
        15,
        evolution_level=10,
        retained_copies=2,
        deficit=0,
        precursor_levels=(5,),
        location=CollectionLocation.DAYCARE,
    )
    assert prioritize_owned_level_evolutions([row_daycare_only]) == ()


def test_protected_and_reserve_deficits_rejected():
    # Legacy mode deficit: only 1 copy owned when 2 copies are required -> deficit = 1
    row_legacy_deficit = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=1, deficit=1, precursor_levels=(5,)
    )
    assert prioritize_owned_level_evolutions([row_legacy_deficit]) == ()

    # Registered mode deficit: 1 copy owned, but 1 protected -> deficit = 1
    row_protected_deficit = make_prerequisite(
        56, 57, evolution_level=28, retained_copies=1, deficit=1, precursor_levels=(15,)
    )
    assert prioritize_owned_level_evolutions([row_protected_deficit]) == ()

    # Deficit with 2 copies owned but 2 protected -> deficit = 1
    row_double_protected_deficit = make_prerequisite(
        56, 57, evolution_level=28, retained_copies=2, deficit=1, precursor_levels=(15, 20)
    )
    assert prioritize_owned_level_evolutions([row_double_protected_deficit]) == ()


def test_three_plus_stock_rejected_due_to_current_engine_limitation():
    # 3 copies owned (outside {1, 2}) -> rejected
    row_3_stock = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=3, deficit=0, precursor_levels=(5, 6, 7)
    )
    assert prioritize_owned_level_evolutions([row_3_stock]) == ()

    # 4 copies owned -> rejected
    row_4_stock = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=4, deficit=0, precursor_levels=(5, 6, 7, 8)
    )
    assert prioritize_owned_level_evolutions([row_4_stock]) == ()

    # 1 copy owned (retained_copies == 1 in {1, 2}, deficit == 0 in registered mode) -> eligible
    row_1_stock = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=1, deficit=0, precursor_levels=(7,)
    )
    res_1 = prioritize_owned_level_evolutions([row_1_stock])
    assert len(res_1) == 1
    assert res_1[0].minimum_level_gains == 3

    # 2 copies owned (retained_copies == 2 in {1, 2}, deficit == 0) -> eligible
    row_2_stock = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=2, deficit=0, precursor_levels=(7, 8)
    )
    res_2 = prioritize_owned_level_evolutions([row_2_stock])
    assert len(res_2) == 1
    assert res_2[0].minimum_level_gains == 2  # min(10-7, 10-8) = 2


def test_unavailable_rows_filtered_leaving_only_eligible_shortlist():
    # Mix of unavailable and eligible rows
    row_deficit = make_prerequisite(
        56, 57, 28, retained_copies=1, deficit=1, precursor_levels=(10,)
    )
    row_3_copies = make_prerequisite(
        19, 20, 20, retained_copies=3, deficit=0, precursor_levels=(15,)
    )
    row_0_copies = make_prerequisite(29, 30, 16, retained_copies=0, deficit=0, precursor_levels=())
    row_empty_precursors = make_prerequisite(
        21, 22, 20, retained_copies=2, deficit=0, precursor_levels=()
    )
    row_level_100 = make_prerequisite(
        23, 24, 22, retained_copies=2, deficit=0, precursor_levels=(100,)
    )

    # Two eligible rows
    row_eligible_1 = make_prerequisite(
        10, 11, 7, retained_copies=2, deficit=0, precursor_levels=(5,)
    )  # 7 - 5 = 2
    row_eligible_2 = make_prerequisite(
        14, 15, 10, retained_copies=2, deficit=0, precursor_levels=(4,)
    )  # 10 - 4 = 6

    all_rows = [
        row_deficit,
        row_eligible_2,
        row_3_copies,
        row_0_copies,
        row_empty_precursors,
        row_level_100,
        row_eligible_1,
    ]

    result = prioritize_owned_level_evolutions(all_rows)
    assert len(result) == 2
    assert result[0].prerequisite.target_species_ref == red_species_ref(11)
    assert result[0].minimum_level_gains == 2
    assert result[1].prerequisite.target_species_ref == red_species_ref(15)
    assert result[1].minimum_level_gains == 6

    # All-unavailable input
    assert prioritize_owned_level_evolutions([row_deficit, row_3_copies, row_level_100]) == ()
    # Empty input
    assert prioritize_owned_level_evolutions([]) == ()


def test_ties_broken_solely_by_target_then_source_species_ref():
    # Two rows with identical required level gains (4 gains)
    # Row A: target 015 (Beedrill), source 014 (Kakuna), evo 10, lvl 6 -> gain 4
    row_a = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=2, deficit=0, precursor_levels=(6,)
    )
    # Row B: target 018 (Pidgeot), source 017 (Pidgeotto), evo 36, lvl 32 -> gain 4
    row_b = make_prerequisite(
        17, 18, evolution_level=36, retained_copies=2, deficit=0, precursor_levels=(32,)
    )

    # Target "015" < "018", so row_a must precede row_b regardless of input order
    res_ab = prioritize_owned_level_evolutions([row_a, row_b])
    res_ba = prioritize_owned_level_evolutions([row_b, row_a])
    assert res_ab == res_ba
    assert res_ab[0].prerequisite.target_species_ref == red_species_ref(15)
    assert res_ab[1].prerequisite.target_species_ref == red_species_ref(18)

    # Identical target, different sources (tie broken on source_species_ref)
    row_c1 = RedOwnedEvolutionPrerequisite(
        source_species_ref=red_species_ref(29),
        target_species_ref=red_species_ref(30),
        evolution_level=16,
        retained_source_copies=2,
        duplicate_acquisitions_needed=0,
        party_or_box_precursors=(make_specimen(29, 12),),
    )
    row_c2 = RedOwnedEvolutionPrerequisite(
        source_species_ref=red_species_ref(32),
        target_species_ref=red_species_ref(30),
        evolution_level=16,
        retained_source_copies=2,
        duplicate_acquisitions_needed=0,
        party_or_box_precursors=(make_specimen(32, 12),),
    )
    res_source_tie = prioritize_owned_level_evolutions([row_c2, row_c1])
    assert res_source_tie[0].prerequisite.source_species_ref == red_species_ref(29)
    assert res_source_tie[1].prerequisite.source_species_ref == red_species_ref(32)


def test_no_mutation_of_input_rows():
    row_1 = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=2, deficit=0, precursor_levels=(7,)
    )
    row_2 = make_prerequisite(
        10, 11, evolution_level=7, retained_copies=2, deficit=0, precursor_levels=(5,)
    )
    input_list = [row_1, row_2]
    original_copy = list(input_list)

    result = prioritize_owned_level_evolutions(input_list)

    assert input_list == original_copy
    assert input_list[0] is row_1
    assert input_list[1] is row_2
    assert len(result) == 2


def test_immutability_and_validation():
    row = make_prerequisite(
        14, 15, evolution_level=10, retained_copies=2, deficit=0, precursor_levels=(7,)
    )
    item = PrioritizedOwnedLevelEvolution(prerequisite=row, minimum_level_gains=3)

    # Frozen record
    with pytest.raises(FrozenInstanceError):
        item.minimum_level_gains = 5  # type: ignore[misc]

    # Record validation
    with pytest.raises(TypeError, match="prerequisite"):
        PrioritizedOwnedLevelEvolution(prerequisite="not_a_prereq", minimum_level_gains=3)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="minimum_level_gains"):
        PrioritizedOwnedLevelEvolution(prerequisite=row, minimum_level_gains=0)
    with pytest.raises(ValueError, match="minimum_level_gains"):
        PrioritizedOwnedLevelEvolution(prerequisite=row, minimum_level_gains=-1)
    with pytest.raises(ValueError, match="minimum_level_gains"):
        PrioritizedOwnedLevelEvolution(prerequisite=row, minimum_level_gains=True)  # type: ignore[arg-type]

    # Function input validation
    with pytest.raises(TypeError, match="iterable"):
        prioritize_owned_level_evolutions(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="iterable"):
        prioritize_owned_level_evolutions(123)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RedOwnedEvolutionPrerequisite"):
        prioritize_owned_level_evolutions([row, "invalid"])  # type: ignore[list-item]
