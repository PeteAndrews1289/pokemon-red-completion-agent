import pytest

from pokemon_red_completion.collection import CollectionExclusionReason, CollectionLocation
from pokemon_red_completion.observation import (
    RED_BOX_LIMIT,
    RedBoxCollectionState,
    RedCurrentBoxState,
    RedPokedexState,
)
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_collection import (
    NATIONAL_DEX_SIZE_GENERATION_ONE,
    RED_SOLO_COLLECTION_CONTRACT,
    RED_SOLO_LIVING_TARGET_COUNT,
    RED_SOLO_POKEDEX_TARGET_COUNT,
    red_all_living_specimens,
    red_collection_observation,
    red_internal_species_id,
    red_internal_species_number,
    red_species_number,
    red_species_ref,
    red_visible_living_specimens,
    summarize_red_collection,
    summarize_red_pokedex,
)


def test_red_solo_contract_accounts_for_every_generation_one_species() -> None:
    contract = RED_SOLO_COLLECTION_CONTRACT

    assert len(contract.species_universe) == NATIONAL_DEX_SIZE_GENERATION_ONE == 151
    assert len(contract.target_species) == RED_SOLO_POKEDEX_TARGET_COUNT == 124
    assert len(contract.resolved_living_target_species) == RED_SOLO_LIVING_TARGET_COUNT == 120
    assert len(contract.exclusions) == 27
    assert contract.target_level == 100
    assert set(contract.target_species).isdisjoint(
        exclusion.species_ref for exclusion in contract.exclusions
    )
    assert {
        red_species_number(species_ref)
        for species_ref in contract.target_species
        if species_ref not in contract.resolved_living_target_species
    } == {7, 8, 133, 138}


def test_red_solo_contract_keeps_the_route_choices_and_excludes_alternatives() -> None:
    targets = set(RED_SOLO_COLLECTION_CONTRACT.target_species)
    exclusions = {
        red_species_number(item.species_ref): item.reason
        for item in RED_SOLO_COLLECTION_CONTRACT.exclusions
    }

    assert {7, 8, 9, 106, 133, 135, 138, 139} <= {
        red_species_number(species_ref) for species_ref in targets
    }
    assert exclusions[1] is CollectionExclusionReason.ALTERNATE_STARTER
    assert exclusions[65] is CollectionExclusionReason.LINK_TRADE_REQUIRED
    assert exclusions[107] is CollectionExclusionReason.ALTERNATE_DOJO_GIFT
    assert exclusions[127] is CollectionExclusionReason.VERSION_EXCLUSIVE
    assert exclusions[140] is CollectionExclusionReason.ALTERNATE_FOSSIL
    assert exclusions[151] is CollectionExclusionReason.EVENT_ONLY


@pytest.mark.parametrize("number", (1, 9, 124, 151))
def test_red_species_references_round_trip(number: int) -> None:
    assert red_species_number(red_species_ref(number)) == number


@pytest.mark.parametrize("number", (0, 152, True))
def test_red_species_reference_rejects_out_of_range_numbers(number: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 151"):
        red_species_ref(number)


def test_red_pokedex_progress_uses_the_declared_124_species_denominator() -> None:
    progress = summarize_red_pokedex(
        RedPokedexState(
            owned_species=frozenset((7, 8, 9, 127, 151)),
            seen_species=frozenset((7, 8, 9, 25, 127, 150, 151)),
        )
    )

    assert progress.target_count == 124
    assert progress.owned_target_numbers == (7, 8, 9)
    assert progress.seen_target_numbers == (7, 8, 9, 25, 150)
    assert progress.excluded_owned_numbers == (127, 151)
    assert not progress.pokedex_target_complete
    assert progress.public_dict()["living_collection_verified"] is False
    assert progress.public_dict()["level_100_collection_verified"] is False


@pytest.mark.parametrize(
    ("internal_id", "national_number"),
    ((0x1C, 9), (0x40, 83), (0x76, 51), (0x68, 135), (0x2B, 106), (0x84, 143)),
)
def test_internal_red_species_ids_translate_to_national_numbers(
    internal_id: int,
    national_number: int,
) -> None:
    assert red_internal_species_number(internal_id) == national_number


@pytest.mark.parametrize("national_number", (1, 11, 12, 14, 15, 151))
def test_national_numbers_round_trip_through_red_internal_ids(
    national_number: int,
) -> None:
    internal = red_internal_species_id(national_number)
    assert red_internal_species_number(internal) == national_number


@pytest.mark.parametrize("national_number", (0, 152))
def test_red_internal_species_id_rejects_numbers_outside_generation_one(
    national_number: int,
) -> None:
    with pytest.raises(ValueError, match="between 1 and 151"):
        red_internal_species_id(national_number)


def test_internal_missingno_holes_are_rejected() -> None:
    with pytest.raises(ValueError, match="MissingNo"):
        red_internal_species_number(31)


def test_visible_living_inventory_combines_party_and_current_box() -> None:
    party = PartyObservation(
        members=(
            PartyMemberObservation(slot=1, species_id=0x1C, level=88, hp=200, max_hp=200),
            PartyMemberObservation(slot=2, species_id=0x40, level=84, hp=120, max_hp=120),
        )
    )
    current_box = RedCurrentBoxState(
        box_index=3,
        species_ids=(0x54, 0x3A),
        levels=(44, 73),
    )

    specimens = red_visible_living_specimens(party, current_box)

    assert tuple(specimen.species_ref for specimen in specimens) == (
        red_species_ref(9),
        red_species_ref(83),
        red_species_ref(25),
        red_species_ref(86),
    )
    assert tuple(specimen.level for specimen in specimens) == (88, 84, 44, 73)
    assert tuple(specimen.location for specimen in specimens) == (
        CollectionLocation.PARTY,
        CollectionLocation.PARTY,
        CollectionLocation.BOX,
        CollectionLocation.BOX,
    )
    assert specimens[-1].container_index == 3


def test_all_box_projection_builds_a_game_neutral_collection_observation() -> None:
    party = PartyObservation(
        members=(PartyMemberObservation(slot=1, species_id=0x1C, level=88, hp=200, max_hp=200),)
    )
    boxes = RedBoxCollectionState(
        boxes=tuple(
            RedCurrentBoxState(7, (0x3A, 0x40), (73, 50))
            if index == 7
            else RedCurrentBoxState(index, (), ())
            for index in range(RED_BOX_LIMIT)
        ),
        current_box_index=2,
        storage_initialized=True,
    )
    pokedex = RedPokedexState(
        owned_species=frozenset((9, 25, 83, 86)),
        seen_species=frozenset((9, 25, 83, 86)),
    )

    specimens = red_all_living_specimens(party, boxes)
    observation = red_collection_observation(pokedex, party, boxes)
    progress = summarize_red_collection(pokedex, party, boxes)

    assert tuple(red_species_number(item.species_ref) for item in specimens) == (9, 86, 83)
    assert observation.box_counts == (0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0)
    assert observation.current_box_index == 2
    assert progress.collection.pokedex_owned_count == 4
    assert progress.collection.living_count == 3
    assert progress.collection.level_cap_count == 0
    assert progress.public_dict()["all_boxes_verified"] is True
    assert progress.public_dict()["living_collection_verified"] is False


def test_maximal_coexisting_level_100_census_passes_all_collection_gates() -> None:
    targets = tuple(
        red_species_number(species_ref)
        for species_ref in RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species
    )
    registered_targets = tuple(
        red_species_number(species_ref)
        for species_ref in RED_SOLO_COLLECTION_CONTRACT.target_species
    )
    internal_by_national = {
        red_internal_species_number(internal_id): internal_id
        for internal_id in range(1, 191)
        if _is_real_red_species(internal_id)
    }
    box_states = []
    for box_index in range(RED_BOX_LIMIT):
        chunk = targets[box_index * 20 : (box_index + 1) * 20]
        box_states.append(
            RedCurrentBoxState(
                box_index=box_index,
                species_ids=tuple(internal_by_national[number] for number in chunk),
                levels=(100,) * len(chunk),
            )
        )
    boxes = RedBoxCollectionState(
        boxes=tuple(box_states),
        current_box_index=0,
        storage_initialized=True,
    )
    pokedex = RedPokedexState(
        owned_species=frozenset(registered_targets),
        seen_species=frozenset(registered_targets),
    )

    progress = summarize_red_collection(pokedex, PartyObservation(), boxes)

    assert progress.collection.passed
    assert progress.collection.target_count == 124
    assert progress.collection.living_target_count == 120
    assert progress.public_dict()["pokedex_target_complete"] is True
    assert progress.public_dict()["living_collection_verified"] is True
    assert progress.public_dict()["level_100_collection_verified"] is True


def _is_real_red_species(internal_id: int) -> bool:
    try:
        red_internal_species_number(internal_id)
    except ValueError:
        return False
    return True
