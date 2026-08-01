import pytest

from pokemon_red_completion.collection import (
    CollectionContract,
    CollectionDecision,
    CollectionDirective,
    CollectionExclusion,
    CollectionExclusionReason,
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
    plan_collection,
    summarize_collection,
)

A = "pokemon:test:a"
B = "pokemon:test:b"
C = "pokemon:test:c"
D = "pokemon:test:d"


def _contract(*, target_level: int = 100) -> CollectionContract:
    return CollectionContract(
        game_id="pokemon.test",
        species_universe=(A, B, C, D),
        target_species=(A, B, C),
        exclusions=(CollectionExclusion(D, CollectionExclusionReason.VERSION_EXCLUSIVE),),
        target_level=target_level,
    )


def _specimen(
    species_ref: str,
    level: int,
    *,
    location: CollectionLocation = CollectionLocation.BOX,
    container_index: int = 0,
    slot_index: int = 0,
) -> LivingSpecimen:
    return LivingSpecimen(
        species_ref=species_ref,
        level=level,
        location=location,
        container_index=container_index,
        slot_index=slot_index,
    )


def _observation(
    *,
    owned: frozenset[str] = frozenset(),
    specimens: tuple[LivingSpecimen, ...] = (),
    party_size: int = 0,
    box_counts: tuple[int, ...] = (0, 0),
    current_box_index: int = 0,
) -> CollectionObservation:
    return CollectionObservation(
        owned_species=owned,
        specimens=specimens,
        party_size=party_size,
        party_limit=6,
        box_counts=box_counts,
        current_box_index=current_box_index,
        box_capacity=20,
    )


def test_contract_requires_an_explicit_partition_of_the_species_universe() -> None:
    with pytest.raises(ValueError, match="partition"):
        CollectionContract(
            game_id="pokemon.test",
            species_universe=(A, B),
            target_species=(A,),
            exclusions=(),
        )

    with pytest.raises(ValueError, match="disjoint"):
        CollectionContract(
            game_id="pokemon.test",
            species_universe=(A, B),
            target_species=(A, B),
            exclusions=(CollectionExclusion(B, CollectionExclusionReason.EVENT_ONLY),),
        )


def test_report_distinguishes_historical_ownership_living_retention_and_level_cap() -> None:
    report = summarize_collection(
        _contract(),
        _observation(
            owned=frozenset((A, B)),
            specimens=(_specimen(B, 45), _specimen(C, 100)),
            box_counts=(2, 0),
        ),
    )

    assert report.target_count == 3
    assert report.pokedex_owned_count == 2
    assert report.living_count == 2
    assert report.level_cap_count == 1
    assert report.missing_owned == (C,)
    assert report.missing_living == (A,)
    assert report.underleveled == ((B, 45),)
    assert not report.passed


def test_missing_living_species_is_reacquired_even_when_its_dex_flag_survived() -> None:
    decision = plan_collection(
        _contract(),
        _observation(owned=frozenset((A,)), specimens=()),
    )

    assert decision == CollectionDecision(
        CollectionDirective.ACQUIRE_SPECIES,
        "reacquire the first missing living target",
        species_ref=A,
    )


def test_full_party_and_current_box_switch_to_an_available_box_before_capture() -> None:
    party = tuple(
        _specimen(
            f"pokemon:test:party-{index}",
            50,
            location=CollectionLocation.PARTY,
            slot_index=index,
        )
        for index in range(6)
    )
    decision = plan_collection(
        _contract(),
        _observation(
            specimens=party,
            party_size=6,
            box_counts=(20, 19),
        ),
    )

    assert decision.directive is CollectionDirective.SWITCH_BOX
    assert decision.species_ref == A
    assert decision.box_index == 1


def test_all_full_storage_fails_closed_before_requesting_another_capture() -> None:
    party = tuple(
        _specimen(
            f"pokemon:test:party-{index}",
            50,
            location=CollectionLocation.PARTY,
            slot_index=index,
        )
        for index in range(6)
    )
    decision = plan_collection(
        _contract(),
        _observation(
            specimens=party,
            party_size=6,
            box_counts=(20, 20),
        ),
    )

    assert decision.directive is CollectionDirective.MAKE_STORAGE_ROOM
    assert decision.species_ref == A


def test_training_rotates_the_weakest_target_from_storage_then_trains_it() -> None:
    boxed = _observation(
        owned=frozenset((A, B, C)),
        specimens=(_specimen(A, 100), _specimen(B, 60), _specimen(C, 70)),
        box_counts=(3, 0),
    )
    rotate = plan_collection(_contract(), boxed)
    assert rotate.directive is CollectionDirective.WITHDRAW_SPECIES
    assert rotate.species_ref == B
    assert rotate.box_index == 0
    assert rotate.goal_species_ref == B

    party = _observation(
        owned=boxed.owned_species,
        specimens=(
            _specimen(A, 100),
            _specimen(B, 60, location=CollectionLocation.PARTY),
            _specimen(C, 70),
        ),
        party_size=1,
        box_counts=(2, 0),
    )
    train = plan_collection(_contract(), party)
    assert train.directive is CollectionDirective.TRAIN_SPECIES
    assert train.species_ref == B


def test_training_rotation_deposits_before_switching_to_a_stored_target() -> None:
    party = tuple(
        _specimen(
            species_ref,
            level,
            location=CollectionLocation.PARTY,
            slot_index=index,
        )
        for index, (species_ref, level) in enumerate(
            (
                (A, 100),
                (C, 90),
                ("pokemon:test:p1", 80),
                ("pokemon:test:p2", 70),
                ("pokemon:test:p3", 60),
                ("pokemon:test:p4", 50),
            )
        )
    )
    observation = _observation(
        owned=frozenset((A, B, C)),
        specimens=(*party, _specimen(B, 40, container_index=1)),
        party_size=6,
        box_counts=(5, 1),
        current_box_index=0,
    )

    decision = plan_collection(_contract(), observation)

    assert decision.directive is CollectionDirective.DEPOSIT_SPECIES
    assert decision.species_ref == A
    assert decision.box_index == 0
    assert decision.goal_species_ref == B


def test_training_rotation_switches_to_the_target_box_after_a_slot_is_open() -> None:
    observation = _observation(
        owned=frozenset((A, B, C)),
        specimens=(
            _specimen(A, 100, location=CollectionLocation.PARTY),
            _specimen(B, 40, container_index=1),
            _specimen(C, 100),
        ),
        party_size=1,
        box_counts=(1, 1),
        current_box_index=0,
    )

    decision = plan_collection(_contract(), observation)

    assert decision.directive is CollectionDirective.SWITCH_BOX
    assert decision.species_ref == B
    assert decision.box_index == 1
    assert decision.goal_species_ref == B


def test_stop_requires_every_target_to_be_living_owned_and_level_100() -> None:
    observation = _observation(
        owned=frozenset((A, B, C)),
        specimens=(_specimen(A, 100), _specimen(B, 100), _specimen(C, 100)),
        box_counts=(3, 0),
    )

    report = summarize_collection(_contract(), observation)
    decision = plan_collection(_contract(), observation)

    assert report.passed
    assert decision.directive is CollectionDirective.STOP
