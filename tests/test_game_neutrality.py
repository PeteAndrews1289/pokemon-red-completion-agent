"""Can the shared contracts describe a game that is not Red?

``party``, ``team_training``, ``capture``, ``pokedex`` and ``collection`` all
declare themselves game-neutral. Until now nothing checked that. A claim no test
can fail is not a property, it is a hope, and this project has a long record of
those surviving because everything available to contradict them was written from
the same assumption.

So this file states facts that are true of a later mainline title and false of
Red, and asks the contracts to hold them. Nothing here needs a second ROM: the
question is whether the *types* can represent a second game, which is answerable
today and is the load-bearing part of the transfer claim.

Where a fact cannot be represented, the test says so out loud rather than being
deleted. A xfail here is a measurement of how far the neutrality claim actually
reaches.
"""

from __future__ import annotations

import pytest

from pokemon_red_completion.capture import CapturePolicy
from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.encounters import summarize_encounters
from pokemon_red_completion.party import (
    Gender,
    MoveObservation,
    PartyMemberObservation,
    StatusCondition,
)
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    GrindingArea,
    choose_grinding_area,
)

GEN2 = "crystal"


def member(**changes: object) -> PartyMemberObservation:
    values: dict[str, object] = {
        "slot": 1,
        "species_id": 155,
        "level": 5,
        "hp": 20,
        "max_hp": 20,
        "moves": (MoveObservation(move_id=1, current_pp=30),),
    }
    values.update(changes)
    return PartyMemberObservation(**values)  # type: ignore[arg-type]


# -- things a later title has and Red does not --------------------------------


def test_a_member_can_be_carrying_something() -> None:
    """Held items decide whether a member survives a turn it otherwise would not.

    Red has none, so its adapter leaves this unset. A planner in any later title
    that cannot see Leftovers is reasoning about a different game than the one
    it is playing.
    """

    carrying = member(held_item_ref=f"{GEN2}:leftovers")

    assert carrying.held_item_ref == f"{GEN2}:leftovers"
    assert member().held_item_ref is None, "Red must be able to say 'nothing', not guess"


def test_a_held_item_reference_is_namespaced() -> None:
    """An unqualified name collides across titles the moment there are two."""

    with pytest.raises(ValueError, match="namespaced"):
        member(held_item_ref="leftovers")


def test_badly_poisoned_is_not_the_same_as_poisoned() -> None:
    """Toxic damage escalates, so it changes whether a member is safe to keep in.

    Gen 1 carries it as a volatile battle flag and reports plain poison in the
    persistent byte, so a Red adapter never emits it. A contract without it
    forces every later adapter to report something it knows to be false.
    """

    assert StatusCondition.TOXIC != StatusCondition.POISON
    assert member(status=StatusCondition.TOXIC).status is StatusCondition.TOXIC


def test_gender_is_expressible_and_optional() -> None:
    """Breeding is an acquisition route, and it depends on this.

    Red has no concept of gender, so the field stays None there rather than
    being invented.
    """

    assert member(gender=Gender.FEMALE).gender is Gender.FEMALE
    assert member().gender is None


# -- the encounter model, which is where Red-shaped thinking hid ---------------


def test_one_area_can_hold_two_bands_under_different_conditions() -> None:
    """A route that fields different species at night is two tables, not one.

    This is the failure that motivated the condition key. Keyed on the area
    alone, a night band and a day band merge into a band describing neither --
    and nothing raises, so the only symptom is training that will not converge.
    """

    day = GrindingArea(
        area_id="route_29",
        minimum_encounter_level=2,
        maximum_encounter_level=4,
        measured_samples=40,
        conditions=("day",),
    )
    night = GrindingArea(
        area_id="route_29",
        minimum_encounter_level=3,
        maximum_encounter_level=6,
        measured_samples=40,
        conditions=("night",),
    )

    assert day.identity != night.identity, "the same place under two conditions is two bands"
    assert day.area_id == night.area_id


def test_red_reports_no_conditions_rather_than_guessing() -> None:
    """Empty is a claim: 'this title's tables do not vary'. It is true of Red."""

    band = GrindingArea(
        area_id="pokemon_mansion_1f",
        minimum_encounter_level=28,
        maximum_encounter_level=34,
        measured_samples=164,
    )

    assert band.conditions == ()
    assert band.identity == ("pokemon_mansion_1f", ())


def test_conditions_have_a_stable_order_so_identity_is_stable() -> None:
    """Two adapters reporting the same conditions must produce the same band."""

    with pytest.raises(ValueError, match="sorted"):
        GrindingArea(
            area_id="route_29",
            minimum_encounter_level=2,
            maximum_encounter_level=4,
            conditions=("night", "day"),
        )


def test_the_harvest_separates_bands_by_condition() -> None:
    """The contract change is cosmetic unless measurement carries it through."""

    rows = [
        {
            "map_id": 29,
            "enemy_species": 16,
            "enemy_level": 3,
            "battle_state": 1,
            "conditions": ["day"],
        }
        for _ in range(5)
    ] + [
        {
            "map_id": 29,
            "enemy_species": 163,
            "enemy_level": 6,
            "battle_state": 1,
            "conditions": ["night"],
        }
        for _ in range(5)
    ]

    bands = summarize_encounters(rows)

    assert len(bands) == 2, "one map, two conditions, two bands"
    by_condition = {band.conditions: band for band in bands}
    assert by_condition[("day",)].species_ids == (16,)
    assert by_condition[("night",)].species_ids == (163,)


def test_venue_selection_refuses_a_band_from_the_wrong_condition() -> None:
    """Separating rows is insufficient unless runtime choice honors the key."""

    day = GrindingArea(
        area_id="route_29",
        minimum_encounter_level=2,
        maximum_encounter_level=4,
        measured_samples=40,
        conditions=("day",),
    )
    night = GrindingArea(
        area_id="route_29",
        minimum_encounter_level=3,
        maximum_encounter_level=6,
        measured_samples=40,
        conditions=("night",),
    )
    policy = BalancedTeamPolicy(minimum_level=20, maximum_level_spread=5, required_size=1)

    assert (
        choose_grinding_area((night, day), member(level=10), policy, active_conditions=("day",))
        == day
    )
    assert choose_grinding_area((night, day), member(level=10), policy) is None


def test_a_log_without_conditions_still_produces_one_band() -> None:
    """Every Red harvest ever taken must keep meaning what it meant."""

    rows = [
        {"map_id": 165, "enemy_species": 0x21, "enemy_level": 30, "battle_state": 1}
        for _ in range(4)
    ]

    (band,) = summarize_encounters(rows)

    assert band.conditions == ()
    assert band.samples == 4


# -- things that were already neutral, pinned so they stay that way ------------


def test_the_collection_scales_past_one_generation() -> None:
    """251 species and fourteen boxes, with references that survive a sequel."""

    observation = CollectionObservation(
        owned_species=frozenset({f"{GEN2}:species_{index}" for index in range(1, 252)}),
        specimens=(
            LivingSpecimen(
                species_ref=f"{GEN2}:togepi",
                location=CollectionLocation.PARTY,
                slot_index=0,
                level=5,
            ),
        ),
        party_size=1,
        party_limit=6,
        box_counts=(0,) * 14,
        box_capacity=20,
        current_box_index=0,
    )

    assert len(observation.owned_species) == 251
    assert len(observation.box_counts) == 14


def test_the_capture_policy_names_no_ball() -> None:
    """Deliberate, and correct.

    Which ball to throw is an adapter's business; the neutral policy says when
    to throw and when to disengage. Every later title adds balls, and none of
    them change that rule.
    """

    fields = set(CapturePolicy.__dataclass_fields__)

    assert not any("ball" in name for name in fields)
    assert {"throw_at_or_below_hp_ratio", "prefer_status_first", "max_throws"} <= fields


# -- what still cannot be said ------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "An egg occupies a party slot and has no level. LivingSpecimen requires "
        "1..100, so breeding cannot be represented. This is a real gap in the "
        "collection contract, kept visible rather than deleted."
    ),
    strict=True,
)
def test_an_egg_can_occupy_a_party_slot() -> None:
    LivingSpecimen(
        species_ref=f"{GEN2}:egg",
        location=CollectionLocation.PARTY,
        slot_index=1,
        level=0,
    )
