from __future__ import annotations

import json

import pytest

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_living_dex_dependency_adapter import (
    RedDependencyExecutionFacts,
)
from pokemon_red_completion.red_living_dex_multifamily_curriculum import (
    RedLivingDexMultifamilyError,
    RedMultifamilyContext,
    freeze_two_family_curriculum,
    inventory_red_multifamily_contexts,
    map_id_for_wild_source,
    raw_exit_coordinates,
)


def _observation() -> CollectionObservation:
    species = (11, 11, 14, 14)
    specimens = tuple(
        LivingSpecimen(
            red_species_ref(number),
            4,
            CollectionLocation.BOX,
            container_index=0,
            slot_index=index,
        )
        for index, number in enumerate(species)
    )
    return CollectionObservation(
        owned_species=frozenset(item.species_ref for item in specimens),
        specimens=specimens,
        party_size=0,
        party_limit=6,
        box_counts=(len(specimens),),
        current_box_index=0,
        box_capacity=20,
    )


def _facts() -> RedDependencyExecutionFacts:
    metapod = (red_species_ref(11), red_species_ref(12))
    kakuna = (red_species_ref(14), red_species_ref(15))
    return RedDependencyExecutionFacts(
        acquirable_precursor_refs=frozenset({metapod[0], kakuna[0]}),
        trainable_evolution_pairs=frozenset({metapod, kakuna}),
    )


def _contexts(*, unavailable: frozenset[int] = frozenset()) -> tuple[RedMultifamilyContext, ...]:
    rows = []
    for index in range(20):
        rows.append(
            RedMultifamilyContext(
                f"{index + 1:064x}",
                f"{index + 101:064x}",
                "train" if index < 10 else "development",
                _observation(),
                _facts(),
                index not in unavailable,
            )
        )
    return tuple(rows)


def _family(inventory: object, precursor: int, evolved: int) -> str:
    opportunities = inventory.opportunities  # type: ignore[attr-defined]
    return next(
        item.family_identity_sha256
        for item in opportunities
        if item.opportunity.binding.precursor_species_ref == red_species_ref(precursor)
        and item.opportunity.binding.evolved_species_ref == red_species_ref(evolved)
    )


def test_inventory_finds_complete_executable_menus_without_acting_or_leaking() -> None:
    inventory = inventory_red_multifamily_contexts(_contexts())

    assert len(inventory.contexts) == 20
    assert len(inventory.opportunities) == 40
    assert len(inventory.available_opportunities) == 40
    assert all(len(item.policy_rows()) == 2 for item in inventory.opportunities)
    public = json.dumps(inventory.public_dict(), sort_keys=True).lower()
    assert inventory.public_dict()["qualified_families"] == 2
    assert inventory.public_dict()["controller_actions"] == 0
    for forbidden in (
        red_species_ref(11),
        red_species_ref(12),
        red_species_ref(14),
        red_species_ref(15),
        _family(inventory, 11, 12),
        _family(inventory, 14, 15),
        _contexts()[0].root_consumption_sha256,
    ):
        assert forbidden.lower() not in public


def test_freeze_uses_distinct_roots_counterbalanced_candidates_and_disjoint_families() -> None:
    inventory = inventory_red_multifamily_contexts(_contexts())
    train_family = _family(inventory, 11, 12)
    development_family = _family(inventory, 14, 15)

    plan = freeze_two_family_curriculum(
        inventory,
        train_family_identity_sha256=train_family,
        development_family_identity_sha256=development_family,
    )

    assert [item.candidate_index for item in plan.train_trials] == [0, 1] * 4
    assert [item.candidate_index for item in plan.development_trials] == [0, 1] * 4
    assert len(
        {
            item.opportunity.context.root_consumption_sha256
            for item in (*plan.train_trials, *plan.development_trials)
        }
    ) == 16
    public = json.dumps(plan.public_dict(), sort_keys=True).lower()
    assert plan.public_dict()["family_overlap"] == 0
    assert plan.public_dict()["root_overlap"] == 0
    assert plan.public_dict()["fit_partition"] == "train_only"
    assert train_family not in public
    assert development_family not in public
    assert red_species_ref(11) not in public
    assert red_species_ref(15) not in public


def test_freeze_rejects_family_overlap_and_insufficient_untouched_roots() -> None:
    inventory = inventory_red_multifamily_contexts(_contexts(unavailable=frozenset({10, 11, 12})))
    metapod = _family(inventory, 11, 12)
    kakuna = _family(inventory, 14, 15)

    with pytest.raises(RedLivingDexMultifamilyError, match="families overlap"):
        freeze_two_family_curriculum(
            inventory,
            train_family_identity_sha256=metapod,
            development_family_identity_sha256=metapod,
        )
    with pytest.raises(RedLivingDexMultifamilyError, match="7 roots; 8 are required"):
        freeze_two_family_curriculum(
            inventory,
            train_family_identity_sha256=metapod,
            development_family_identity_sha256=kakuna,
        )


def test_inventory_rejects_physical_root_aliasing_across_contexts() -> None:
    contexts = list(_contexts())
    contexts[1] = RedMultifamilyContext(
        contexts[1].context_identity_sha256,
        contexts[0].root_consumption_sha256,
        contexts[1].partition,
        contexts[1].observation,
        contexts[1].execution_facts,
        True,
    )

    with pytest.raises(RedLivingDexMultifamilyError, match="physical root"):
        inventory_red_multifamily_contexts(contexts)


@pytest.mark.parametrize(
    ("source_id", "expected"),
    (
        ("wild:ViridianForest:grass", MapId.VIRIDIAN_FOREST),
        ("wild:DiglettsCave:grass", MapId.DIGLETTS_CAVE),
        ("wild:PokemonMansion1F:grass", MapId.POKEMON_MANSION_1F),
    ),
)
def test_wild_source_resolves_title_adapter_map_without_family_tables(
    source_id: str,
    expected: MapId,
) -> None:
    assert map_id_for_wild_source(source_id) is expected


def test_warp_coordinates_convert_from_router_yx_to_raw_xy() -> None:
    assert raw_exit_coordinates(((0, 1), (47, 18))) == frozenset({(1, 0), (18, 47)})
    with pytest.raises(RedLivingDexMultifamilyError, match="coordinates"):
        raw_exit_coordinates(((0, -1),))
