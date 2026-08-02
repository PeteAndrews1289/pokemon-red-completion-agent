from collections import Counter

import pytest

from pokemon_red_completion.capture import (
    CaptureDirective,
    CaptureObservation,
    CapturePolicy,
    plan_capture,
)
from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    StatusCondition,
)
from pokemon_red_completion.red_acquisition import (
    PRET_POKERED_ACQUISITION_COMMIT,
    RED_ACQUISITION_CATALOG,
    RedAcquisitionDirective,
    RedAcquisitionKind,
    RedAreaDirective,
    RedAreaExecutionError,
    RedAreaExecutionPolicy,
    plan_red_acquisition,
    plan_red_area_encounter,
    run_red_area_survey,
    summarize_red_area_survey,
)
from pokemon_red_completion.red_collection import (
    RED_SOLO_COLLECTION_CONTRACT,
    red_species_number,
    red_species_ref,
)


def _observation(
    *living_numbers: int,
    owned_numbers: tuple[int, ...] = (),
) -> CollectionObservation:
    specimens = tuple(
        LivingSpecimen(
            red_species_ref(number),
            30,
            CollectionLocation.BOX,
            container_index=0,
            slot_index=index,
        )
        for index, number in enumerate(living_numbers)
    )
    return CollectionObservation(
        owned_species=frozenset(red_species_ref(number) for number in owned_numbers),
        specimens=specimens,
        party_size=0,
        party_limit=6,
        box_counts=(len(specimens),) + (0,) * 11,
        current_box_index=0,
        box_capacity=20,
    )


def _full_party_observation(
    *,
    box_counts: tuple[int, ...],
    current_box_index: int = 0,
) -> CollectionObservation:
    party = tuple(
        LivingSpecimen(
            red_species_ref(9),
            80,
            CollectionLocation.PARTY,
            slot_index=index,
        )
        for index in range(6)
    )
    return CollectionObservation(
        owned_species=frozenset((red_species_ref(9),)),
        specimens=party,
        party_size=6,
        party_limit=6,
        box_counts=box_counts,
        current_box_index=current_box_index,
        box_capacity=20,
    )


class _RouteOneSurveySimulation:
    def __init__(self, encounters: tuple[int, ...]) -> None:
        self.encounters = list(encounters)
        self.current_encounter: int | None = None
        self.current_box_index = 0
        self.box_counts = [19, 0, *(0 for _ in range(10))]
        self.captured: list[tuple[int, int]] = []

    def read_collection(self) -> CollectionObservation:
        party = tuple(
            LivingSpecimen(
                red_species_ref(9),
                80,
                CollectionLocation.PARTY,
                slot_index=index,
            )
            for index in range(6)
        )
        stored = tuple(
            LivingSpecimen(
                red_species_ref(number),
                3,
                CollectionLocation.BOX,
                container_index=box_index,
                slot_index=index,
            )
            for index, (number, box_index) in enumerate(self.captured)
        )
        return CollectionObservation(
            owned_species=frozenset(
                (red_species_ref(9),)
                + tuple(red_species_ref(number) for number, _ in self.captured)
            ),
            specimens=party + stored,
            party_size=6,
            party_limit=6,
            box_counts=tuple(self.box_counts),
            current_box_index=self.current_box_index,
            box_capacity=20,
        )

    def encountered_species_ref(self) -> str | None:
        return None if self.current_encounter is None else red_species_ref(self.current_encounter)

    def seek_encounter(self) -> None:
        if self.current_encounter is not None:
            raise AssertionError("cannot seek while an encounter is active")
        if not self.encounters:
            raise AssertionError("simulation exhausted its declared encounters")
        self.current_encounter = self.encounters.pop(0)

    def capture_encounter(self, species_ref: str) -> None:
        if species_ref != self.encountered_species_ref():
            raise AssertionError("capture target does not match the live encounter")
        catcher = PartyMemberObservation(
            slot=1,
            species_id=0x1C,
            level=80,
            hp=250,
            max_hp=250,
            moves=(MoveObservation(0x39, 15, 15),),
        )
        capture = plan_capture(
            CaptureObservation(
                target_species_id=self.current_encounter or 0,
                target_level=3,
                target_hp=1,
                target_max_hp=12,
                catcher=catcher,
                balls_available=40,
                party_has_room=False,
                storage_has_room=self.box_counts[self.current_box_index] < 20,
                target_status=StatusCondition.SLEEP,
            ),
            CapturePolicy(),
        )
        if capture.directive is not CaptureDirective.THROW_BALL:
            raise AssertionError(f"capture policy rejected a qualified encounter: {capture}")
        self.captured.append((self.current_encounter or 0, self.current_box_index))
        self.box_counts[self.current_box_index] += 1
        self.current_encounter = None

    def flee_encounter(self) -> None:
        if self.current_encounter is None:
            raise AssertionError("cannot flee without a live encounter")
        self.current_encounter = None

    def switch_box(self, box_index: int) -> None:
        if self.current_encounter is not None:
            raise AssertionError("cannot switch boxes during an encounter")
        self.current_box_index = box_index


def test_catalog_covers_every_red_target_once_from_the_pinned_source() -> None:
    catalog = RED_ACQUISITION_CATALOG
    kinds = Counter(method.kind for method in catalog.methods)

    assert catalog.source_commit == PRET_POKERED_ACQUISITION_COMMIT
    assert len(catalog.methods) == 124
    assert {method.species_ref for method in catalog.methods} == set(
        RED_SOLO_COLLECTION_CONTRACT.target_species
    )
    assert kinds == {
        RedAcquisitionKind.WILD: 67,
        RedAcquisitionKind.SAFARI: 11,
        RedAcquisitionKind.FISHING: 7,
        RedAcquisitionKind.GIFT: 4,
        RedAcquisitionKind.STATIC: 5,
        RedAcquisitionKind.PRIZE: 2,
        RedAcquisitionKind.FOSSIL: 2,
        RedAcquisitionKind.IN_GAME_TRADE: 4,
        RedAcquisitionKind.EVOLUTION: 22,
    }


def test_catalog_names_exact_source_examples_and_evolution_requirements() -> None:
    route_one_pidgey = RED_ACQUISITION_CATALOG.method_for(red_species_ref(16))
    poliwhirl = RED_ACQUISITION_CATALOG.method_for(red_species_ref(61))
    jolteon = RED_ACQUISITION_CATALOG.method_for(red_species_ref(135))
    mewtwo = RED_ACQUISITION_CATALOG.method_for(red_species_ref(150))

    assert route_one_pidgey.source_id == "wild:Route1:grass"
    assert (route_one_pidgey.minimum_level, route_one_pidgey.maximum_level) == (2, 5)
    assert poliwhirl.source_id == "fishing:super_rod:CeladonCity"
    assert jolteon.consumes_species_ref == red_species_ref(133)
    assert jolteon.required_item_ref == "pokemon:red:item:thunder_stone"
    assert mewtwo.source_id == "static:CeruleanCaveB1F:Mewtwo"
    assert not mewtwo.repeatable

    with pytest.raises(ValueError, match="not present"):
        RED_ACQUISITION_CATALOG.method_for(red_species_ref(151))


def test_living_plan_counts_duplicate_precursors_instead_of_one_of_each() -> None:
    roots = RED_ACQUISITION_CATALOG.required_root_acquisitions()

    assert len(roots) == 98
    assert sum(roots.values()) == 120
    assert roots[red_species_ref(7)] == 1
    assert roots[red_species_ref(17)] == 2
    assert roots[red_species_ref(21)] == 2
    assert roots[red_species_ref(35)] == 2
    assert roots[red_species_ref(61)] == 3
    assert roots[red_species_ref(63)] == 2
    assert roots[red_species_ref(80)] == 2
    assert roots[red_species_ref(147)] == 3
    assert RED_ACQUISITION_CATALOG.reachable_registration_species() == frozenset(
        RED_SOLO_COLLECTION_CONTRACT.target_species
    )


def test_living_plan_derives_the_exact_finite_evolution_item_budget() -> None:
    items = RED_ACQUISITION_CATALOG.required_item_quantities()
    transformations = RED_ACQUISITION_CATALOG.required_transformation_counts()

    assert items == {
        "pokemon:red:item:fire_stone": 1,
        "pokemon:red:item:leaf_stone": 2,
        "pokemon:red:item:moon_stone": 3,
        "pokemon:red:item:thunder_stone": 1,
        "pokemon:red:item:water_stone": 3,
    }
    assert transformations[red_species_ref(18)] == 1
    assert transformations[red_species_ref(122)] == 1
    assert transformations[red_species_ref(148)] == 2
    assert transformations[red_species_ref(149)] == 1


def test_safari_sources_are_not_misrepresented_as_ordinary_wild_captures() -> None:
    tauros = RED_ACQUISITION_CATALOG.method_for(red_species_ref(128))
    scyther = RED_ACQUISITION_CATALOG.method_for(red_species_ref(123))

    assert tauros.kind is RedAcquisitionKind.SAFARI
    assert scyther.kind is RedAcquisitionKind.SAFARI


def test_route_one_survey_targets_pidgey_and_rattata_semantically() -> None:
    pending = summarize_red_area_survey("wild:Route1:grass", _observation())
    pidgey_done = summarize_red_area_survey(
        "wild:Route1:grass",
        _observation(16, owned_numbers=(16,)),
    )
    complete = summarize_red_area_survey(
        "wild:Route1:grass",
        _observation(16, 19, owned_numbers=(16, 19)),
    )

    assert tuple(red_species_number(ref) for ref in pending.missing_species_refs) == (16, 19)
    assert tuple(red_species_number(ref) for ref in pidgey_done.missing_species_refs) == (19,)
    assert complete.complete


def test_area_survey_requires_duplicate_root_specimens_for_downstream_evolution() -> None:
    empty = summarize_red_area_survey("wild:Route14:grass", _observation())
    one_pidgeotto = summarize_red_area_survey("wild:Route14:grass", _observation(17))

    pidgeotto_empty = next(
        item for item in empty.requirements if item.species_ref == red_species_ref(17)
    )
    pidgeotto_one = next(
        item for item in one_pidgeotto.requirements if item.species_ref == red_species_ref(17)
    )
    assert (pidgeotto_empty.required_count, pidgeotto_empty.missing_count) == (2, 2)
    assert (pidgeotto_one.retained_count, pidgeotto_one.missing_count) == (1, 1)


def test_area_controller_seeks_catches_flees_and_stops_from_semantic_state() -> None:
    seek = plan_red_area_encounter("wild:Route1:grass", _observation())
    catch = plan_red_area_encounter(
        "wild:Route1:grass",
        _observation(),
        encountered_species_ref=red_species_ref(16),
    )
    flee = plan_red_area_encounter(
        "wild:Route1:grass",
        _observation(),
        encountered_species_ref=red_species_ref(21),
    )
    stop = plan_red_area_encounter("wild:Route1:grass", _observation(16, 19))

    assert seek.directive is RedAreaDirective.SEEK_ENCOUNTER
    assert seek.species_ref == red_species_ref(16)
    assert catch.directive is RedAreaDirective.CAPTURE_ENCOUNTER
    assert flee.directive is RedAreaDirective.FLEE_ENCOUNTER
    assert stop.directive is RedAreaDirective.STOP


def test_area_controller_rotates_full_storage_before_seeking() -> None:
    rotate = plan_red_area_encounter(
        "wild:Route1:grass",
        _full_party_observation(box_counts=(20, 3) + (20,) * 10),
    )
    no_capacity = plan_red_area_encounter(
        "wild:Route1:grass",
        _full_party_observation(box_counts=(20,) * 12),
    )
    flee_required = plan_red_area_encounter(
        "wild:Route1:grass",
        _full_party_observation(box_counts=(20, 3) + (20,) * 10),
        encountered_species_ref=red_species_ref(16),
    )

    assert rotate.directive is RedAreaDirective.SWITCH_BOX
    assert rotate.box_index == 1
    assert no_capacity.directive is RedAreaDirective.MAKE_STORAGE_ROOM
    assert flee_required.directive is RedAreaDirective.FLEE_ENCOUNTER
    assert "storage" in flee_required.reason


def test_bounded_route_one_executor_flees_catches_and_rotates_storage() -> None:
    executor = _RouteOneSurveySimulation((21, 16, 19))

    report = run_red_area_survey("wild:Route1:grass", executor)

    assert report.passed
    assert report.initial_missing_species_refs == (red_species_ref(16), red_species_ref(19))
    assert report.final_missing_species_refs == ()
    assert report.encounters_seen == 3
    assert report.captures == 2
    assert report.flees == 1
    assert report.box_switches == 1
    assert executor.box_counts[:2] == [20, 1]
    assert executor.current_box_index == 1


def test_area_executor_enforces_its_encounter_bound() -> None:
    executor = _RouteOneSurveySimulation((21, 21, 16, 19))

    with pytest.raises(RedAreaExecutionError, match="exceeded 1 encountered"):
        run_red_area_survey(
            "wild:Route1:grass",
            executor,
            policy=RedAreaExecutionPolicy(max_actions=20, max_encounters=1),
        )


def test_planner_seeks_a_direct_source_and_stops_for_a_retained_target() -> None:
    seek = plan_red_acquisition(red_species_ref(16), _observation())
    done = plan_red_acquisition(red_species_ref(16), _observation(16))

    assert seek.directive is RedAcquisitionDirective.SEEK_SOURCE
    assert seek.action_species_ref == red_species_ref(16)
    assert seek.source_id == "wild:Route1:grass"
    assert done.directive is RedAcquisitionDirective.COMPLETE


def test_planner_preserves_one_pidgeotto_before_evolving_another() -> None:
    acquire_duplicate = plan_red_acquisition(red_species_ref(18), _observation(17))
    evolve = plan_red_acquisition(red_species_ref(18), _observation(17, 17))

    assert acquire_duplicate.directive is RedAcquisitionDirective.SEEK_SOURCE
    assert acquire_duplicate.action_species_ref == red_species_ref(17)
    assert acquire_duplicate.source_id == "wild:Route14:grass"
    assert evolve.directive is RedAcquisitionDirective.EVOLVE_SPECIES
    assert evolve.action_species_ref == red_species_ref(18)
    assert evolve.consumes_species_ref == red_species_ref(17)


def test_planner_preserves_trade_material_before_requesting_the_trade() -> None:
    acquire_duplicate = plan_red_acquisition(red_species_ref(122), _observation(63))
    trade = plan_red_acquisition(red_species_ref(122), _observation(63, 63))

    assert acquire_duplicate.directive is RedAcquisitionDirective.SEEK_SOURCE
    assert acquire_duplicate.action_species_ref == red_species_ref(63)
    assert acquire_duplicate.source_id == "wild:Route24:grass"
    assert trade.directive is RedAcquisitionDirective.PERFORM_TRADE
    assert trade.consumes_species_ref == red_species_ref(63)


def test_planner_fails_closed_when_a_unique_consumed_source_is_gone() -> None:
    exhausted = plan_red_acquisition(
        red_species_ref(135),
        _observation(owned_numbers=(133,)),
    )
    ready = plan_red_acquisition(red_species_ref(135), _observation(133))

    assert exhausted.directive is RedAcquisitionDirective.SOURCE_EXHAUSTED
    assert exhausted.action_species_ref == red_species_ref(133)
    assert ready.directive is RedAcquisitionDirective.EVOLVE_SPECIES
    assert ready.consumes_species_ref == red_species_ref(133)


def test_planner_rejects_registration_only_or_excluded_goals() -> None:
    for number in (7, 8, 133, 138, 151):
        with pytest.raises(ValueError, match="120 coexisting"):
            plan_red_acquisition(red_species_ref(number), _observation())
