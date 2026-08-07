"""A venue bundles a measured band with the navigation that makes it usable."""

from __future__ import annotations

import pytest

from pokemon_red_completion.observation import MapId, RawGameState
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    StatusCondition,
)
from pokemon_red_completion.team_training import BalancedTeamPolicy, GrindingArea
from pokemon_red_completion.training_venue import (
    TrainingVenue,
    VenueNavigationError,
    select_training_venue,
    venue_for_map,
)

DIGLETTS_CAVE = int(MapId.DIGLETTS_CAVE)
MANSION = int(MapId.POKEMON_MANSION_1F)


def band(
    area_id: str, low: int, high: int, rare: int | None = None, samples: int = 29
) -> GrindingArea:
    return GrindingArea(
        area_id=area_id,
        minimum_encounter_level=low,
        maximum_encounter_level=high,
        rare_maximum_encounter_level=rare,
        measured_samples=samples,
    )


def venue(area_id: str, map_id: int, low: int, high: int, rare: int | None = None) -> TrainingVenue:
    return TrainingVenue(
        band=band(area_id, low, high, rare),
        map_id=map_id,
        walk_to_grass=lambda *_args: 1,
        heal_and_return=lambda *_args: None,
        is_in_center=lambda _raw: False,
        move_slot=lambda _raw: 1,
    )


def trainee(level: int) -> PartyMemberObservation:
    return PartyMemberObservation(
        slot=1,
        species_id=0x3B,
        level=level,
        hp=80,
        max_hp=80,
        status=StatusCondition.HEALTHY,
        moves=(MoveObservation(move_id=0x5B, current_pp=30),),
        experience=0,
    )


def raw(map_id: int) -> RawGameState:
    return RawGameState(  # type: ignore[call-arg]
        game_started=True,
        map_id=map_id,
        player_x=1,
        player_y=1,
        party_count=6,
        battle_state=0,
    )


def test_a_venue_cannot_rest_on_an_unmeasured_band() -> None:
    """The one rule the type exists to enforce.

    A venue built from a guessed band would let a guess route a real run, which
    is the failure the surrounding measurement work exists to prevent.
    """

    guessed = GrindingArea(
        area_id="digletts_cave", minimum_encounter_level=15, maximum_encounter_level=21
    )

    with pytest.raises(VenueNavigationError, match="unmeasured"):
        TrainingVenue(
            band=guessed,
            map_id=DIGLETTS_CAVE,
            walk_to_grass=lambda *_args: 1,
            heal_and_return=lambda *_args: None,
            is_in_center=lambda _raw: False,
            move_slot=lambda _raw: 1,
        )


def test_selection_hands_back_something_trainable_not_a_label() -> None:
    """The reason for the type.

    choose_grinding_area returns a band, and a band cannot be trained in. The
    caller previously had to translate the label back into navigation by hand,
    which is where a venue and its paths could silently disagree.
    """

    venues = (
        venue("digletts_cave", DIGLETTS_CAVE, 15, 21, rare=31),
        venue("pokemon_mansion_1f", MANSION, 28, 34, rare=39),
    )
    policy = BalancedTeamPolicy(minimum_level=55, max_enemy_level_delta=2)

    chosen = select_training_venue(venues, trainee(20), policy, require_healer=False)

    assert chosen is not None
    assert chosen.area_id == "digletts_cave"
    assert chosen.map_id == DIGLETTS_CAVE
    assert callable(chosen.walk_to_grass), "the caller can train here without a lookup"


def test_a_trainee_too_weak_for_every_measured_venue_gets_nothing() -> None:
    """Better than being sent somewhere it will flee thirty-three times."""

    venues = (venue("pokemon_mansion_1f", MANSION, 28, 34, rare=39),)
    policy = BalancedTeamPolicy(minimum_level=55, max_enemy_level_delta=2)

    assert select_training_venue(venues, trainee(20), policy, require_healer=False) is None


def test_the_rare_ceiling_does_not_veto_the_venue() -> None:
    """Diglett's Cave for a level-20 trainee, one Dugtrio at 31 notwithstanding."""

    cave = venue("digletts_cave", DIGLETTS_CAVE, 15, 21, rare=31)
    policy = BalancedTeamPolicy(minimum_level=55, max_enemy_level_delta=2)

    chosen = select_training_venue((cave,), trainee(20), policy, require_healer=False)

    assert chosen is cave
    assert chosen.band.worst_case_encounter_level == 31


def test_a_venue_recognises_its_own_map_and_describes_itself() -> None:
    cave = venue("digletts_cave", DIGLETTS_CAVE, 15, 21, rare=31)

    assert cave.is_in_map(raw(DIGLETTS_CAVE))
    assert not cave.is_in_map(raw(MANSION))
    assert venue_for_map((cave,), DIGLETTS_CAVE) is cave
    assert venue_for_map((cave,), MANSION) is None

    described = cave.describe()
    assert "digletts_cave" in described
    assert "15-21" in described
    assert "rare to 31" in described
    assert "29 encounters" in described, "a description without its sample count is a claim"
