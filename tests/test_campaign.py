"""What a campaign reaches, as opposed to what one save reaches.

The distinction this file exists to hold is that replaying a cartridge is not
the same as running two of them. Three sequential runs register species across
time; they never hold them at the same moment, so nothing can be traded between
them and no living collection ever exists. Concurrency is the property that
matters, and it is easy to lose because a schedule of three runs and a plan of
three vessels look alike on paper.
"""

from __future__ import annotations

import pytest

from pokemon_red_completion.campaign import (
    CampaignPlan,
    CampaignPlanError,
    Vessel,
    campaign_reach,
    consolidation_required,
)
from pokemon_red_completion.pokedex import ExclusionReason, PokedexTarget

#: Evolved species mapped to the precursor that has to be traded for it.
TRADE_EVOLUTIONS = {65: 64, 68: 67, 76: 75, 94: 93}


TOY_SPECIES = 10
ALL_TEN = set(range(1, TOY_SPECIES + 1))


def target(obtainable: set[int], exclusions: dict[int, ExclusionReason]) -> PokedexTarget:
    """A toy target that accounts for every species, as the contract demands.

    Anything not named obtainable and not given an explicit reason is filled in
    as UNIMPLEMENTED, because PokedexTarget refuses to exist with a species
    unaccounted for -- the denominator has to be auditable.
    """

    filled = dict(exclusions)
    for species in ALL_TEN:
        if species not in obtainable and species not in filled:
            filled[species] = ExclusionReason.UNIMPLEMENTED
    return PokedexTarget(
        total_species=TOY_SPECIES, obtainable=frozenset(obtainable), exclusions=filled
    )


def simple(vessel_id: str, obtainable: set[int], exclusions: dict[int, ExclusionReason]) -> Vessel:
    return Vessel(vessel_id, "toy", target(obtainable, exclusions))


def test_one_vessel_lifts_nothing() -> None:
    """A save cannot trade with itself, so the single-cartridge answer stands."""

    plan = CampaignPlan((simple("a", ALL_TEN - {5}, {5: ExclusionReason.REQUIRES_TRADE}),))

    reach = campaign_reach(plan, trade_evolutions={5: 4})

    assert not plan.has_trade_partner
    assert reach.lifted_by_trade == frozenset()
    assert 5 in reach.unreachable


def test_a_trade_partner_lifts_a_trade_evolution() -> None:
    """The finding that motivated this module.

    Alakazam, Machamp, Golem and Gengar are marked REQUIRES_TRADE because one
    cartridge cannot get them. A campaign with a second live save can: trade
    the precursor across, it evolves on arrival, trade it back.
    """

    plan = CampaignPlan(
        (
            simple("a", ALL_TEN - {5}, {5: ExclusionReason.REQUIRES_TRADE}),
            simple("b", ALL_TEN - {5}, {5: ExclusionReason.REQUIRES_TRADE}),
        )
    )

    reach = campaign_reach(plan, trade_evolutions={5: 4})

    assert reach.lifted_by_trade == frozenset({5})
    assert 5 in reach.obtainable
    assert 5 not in reach.unreachable


def test_a_trade_evolution_needs_its_precursor_obtainable_somewhere() -> None:
    """Trading requires something to send.

    A plan that cannot produce the precursor cannot produce the evolution,
    however many vessels it runs. Lifting on vessel count alone would count a
    species nobody can actually get.
    """

    plan = CampaignPlan(
        (
            simple("a", {1, 2, 3}, {5: ExclusionReason.REQUIRES_TRADE}),
            simple("b", {1, 2, 3}, {5: ExclusionReason.REQUIRES_TRADE}),
        )
    )

    reach = campaign_reach(plan, trade_evolutions={5: 4})

    assert 4 not in plan.union_obtainable(), "the precursor is not obtainable here"
    assert reach.lifted_by_trade == frozenset()
    assert 5 in reach.unreachable


def test_only_a_trade_exclusion_is_lifted_by_a_partner() -> None:
    """A partner save does not conjure an event distribution."""

    plan = CampaignPlan(
        (
            simple("a", ALL_TEN - {5}, {5: ExclusionReason.EVENT_DISTRIBUTION}),
            simple("b", ALL_TEN - {5}, {5: ExclusionReason.EVENT_DISTRIBUTION}),
        )
    )

    reach = campaign_reach(plan, trade_evolutions={5: 4})

    assert reach.lifted_by_trade == frozenset()
    assert reach.unreachable[5] is ExclusionReason.EVENT_DISTRIBUTION


def test_a_second_title_lifts_what_the_first_excludes() -> None:
    """Version exclusivity is answered by running the other version."""

    plan = CampaignPlan(
        (
            Vessel("red", "red", target({1, 2, 3}, {4: ExclusionReason.VERSION_EXCLUSIVE})),
            Vessel("blue", "blue", target({1, 2, 4}, {3: ExclusionReason.VERSION_EXCLUSIVE})),
        )
    )

    reach = campaign_reach(plan)

    assert {3, 4} <= reach.obtainable
    assert reach.lifted_by_version == frozenset({3, 4})
    assert plan.titles == frozenset({"red", "blue"})


def test_consolidation_names_what_must_be_traded_home() -> None:
    """A living Pokedex is one collection, not several.

    Everything the other vessels hold has to reach the home save, and that
    number is the real cost of a multi-vessel plan.
    """

    plan = CampaignPlan(
        (
            Vessel("home", "red", target({1, 2, 3}, {4: ExclusionReason.VERSION_EXCLUSIVE})),
            Vessel("away", "blue", target({1, 2, 4}, {3: ExclusionReason.VERSION_EXCLUSIVE})),
        )
    )

    reach = campaign_reach(plan)

    assert consolidation_required(plan, reach) == frozenset({4})


def test_a_single_vessel_can_never_hold_a_living_collection() -> None:
    """Replaying a cartridge is not running two of them.

    This is the distinction the module exists for. A single vessel has nothing
    to trade with, so nothing can be consolidated into it -- which is why three
    sequential runs reach a species count they can never simultaneously hold.
    """

    plan = CampaignPlan((simple("only", {1, 2, 3}, {4: ExclusionReason.REQUIRES_TRADE}),))

    reach = campaign_reach(plan, trade_evolutions=TRADE_EVOLUTIONS)

    assert consolidation_required(plan, reach) == frozenset()
    assert not plan.has_trade_partner


def test_a_campaign_needs_at_least_one_vessel() -> None:
    with pytest.raises(CampaignPlanError, match="at least one vessel"):
        CampaignPlan(())


def test_vessels_are_distinguishable() -> None:
    """Two saves with one identity cannot be told apart when trading."""

    with pytest.raises(CampaignPlanError, match="distinct"):
        CampaignPlan((simple("a", {1}, {}), simple("a", {2}, {})))


# -- against the real Red target ----------------------------------------------


def test_two_concurrent_red_saves_reach_more_than_one_ever_can() -> None:
    """Measured, not asserted, against the repository's own Red target."""

    from pokemon_red_completion.red_pokedex import RedRunChoices, red_target

    def red(vessel_id: str, **choices: str) -> Vessel:
        return Vessel(vessel_id, "red", red_target(RedRunChoices(**choices)))  # type: ignore[arg-type]

    alone = CampaignPlan(
        (
            red(
                "a",
                starter="bulbasaur",
                fossil="dome",
                dojo_prize="hitmonchan",
                eevee_evolution="flareon",
            ),
        )
    )
    paired = CampaignPlan(
        (
            red(
                "a",
                starter="bulbasaur",
                fossil="dome",
                dojo_prize="hitmonchan",
                eevee_evolution="flareon",
            ),
            red(
                "b",
                starter="charmander",
                fossil="helix",
                dojo_prize="hitmonlee",
                eevee_evolution="jolteon",
            ),
        )
    )

    one = campaign_reach(alone, trade_evolutions=TRADE_EVOLUTIONS)
    two = campaign_reach(paired, trade_evolutions=TRADE_EVOLUTIONS)

    assert one.total_obtainable == 125
    assert two.total_obtainable == 136
    assert two.lifted_by_trade == frozenset({65, 68, 76, 94}), "the four trade evolutions"
    assert len(consolidation_required(paired, two)) == 11


# -- the pair of cartridges ---------------------------------------------------


def test_the_two_versions_have_no_shared_exclusive() -> None:
    """The pair is only complete if each game covers the other's gap.

    Any overlap here means some species neither cartridge offers, and the
    living Pokedex would be short by that many with no way to notice.
    """

    from pokemon_red_completion.blue_pokedex import BLUE_CARTRIDGE_EXCLUSIONS
    from pokemon_red_completion.red_pokedex import RED_CARTRIDGE_EXCLUSIONS

    def exclusives(table: dict[int, ExclusionReason]) -> set[int]:
        return {
            species
            for species, reason in table.items()
            if reason is ExclusionReason.VERSION_EXCLUSIVE
        }

    red_only = exclusives(RED_CARTRIDGE_EXCLUSIONS)
    blue_only = exclusives(BLUE_CARTRIDGE_EXCLUSIONS)

    assert len(red_only) == len(blue_only) == 10
    assert not red_only & blue_only, "a species neither cartridge offers would be invisible"


def test_adding_blue_leaves_only_mew() -> None:
    """The headline number for a Gen 1 living Pokedex, measured not asserted."""

    from pokemon_red_completion.blue_pokedex import blue_target
    from pokemon_red_completion.red_pokedex import RedRunChoices, red_target

    def vessel(vessel_id: str, title: str, **choices: str) -> Vessel:
        build = red_target if title == "red" else blue_target
        return Vessel(vessel_id, title, build(RedRunChoices(**choices)))  # type: ignore[arg-type]

    plan = CampaignPlan(
        (
            vessel(
                "red-a",
                "red",
                starter="bulbasaur",
                fossil="dome",
                dojo_prize="hitmonchan",
                eevee_evolution="flareon",
            ),
            vessel(
                "red-b",
                "red",
                starter="charmander",
                fossil="helix",
                dojo_prize="hitmonlee",
                eevee_evolution="jolteon",
            ),
            vessel(
                "blue-a",
                "blue",
                starter="squirtle",
                fossil="dome",
                dojo_prize="hitmonchan",
                eevee_evolution="vaporeon",
            ),
        )
    )

    reach = campaign_reach(plan, trade_evolutions=TRADE_EVOLUTIONS)

    assert reach.total_obtainable == 150
    assert set(reach.unreachable) == {151}, "only Mew"
    assert reach.unreachable[151] is ExclusionReason.EVENT_DISTRIBUTION


def test_a_third_red_save_adds_nothing_once_blue_is_present() -> None:
    """Three concurrent saves suffice, not four.

    Worth stating because the obvious plan -- three Reds for the branch
    coverage, plus a Blue for its exclusives -- buys a whole extra save and
    reaches exactly the same 150.
    """

    from pokemon_red_completion.blue_pokedex import blue_target
    from pokemon_red_completion.red_pokedex import RedRunChoices, red_target

    def red(vessel_id: str, **choices: str) -> Vessel:
        return Vessel(vessel_id, "red", red_target(RedRunChoices(**choices)))  # type: ignore[arg-type]

    blue = Vessel(
        "blue-a",
        "blue",
        blue_target(
            RedRunChoices(
                starter="squirtle",
                fossil="dome",
                dojo_prize="hitmonchan",
                eevee_evolution="vaporeon",
            )
        ),
    )
    two_red = (
        red(
            "a",
            starter="bulbasaur",
            fossil="dome",
            dojo_prize="hitmonchan",
            eevee_evolution="flareon",
        ),
        red(
            "b",
            starter="charmander",
            fossil="helix",
            dojo_prize="hitmonlee",
            eevee_evolution="jolteon",
        ),
    )
    three_red = two_red + (
        red(
            "c",
            starter="squirtle",
            fossil="dome",
            dojo_prize="hitmonchan",
            eevee_evolution="vaporeon",
        ),
    )

    smaller = campaign_reach(CampaignPlan(two_red + (blue,)), trade_evolutions=TRADE_EVOLUTIONS)
    larger = campaign_reach(CampaignPlan(three_red + (blue,)), trade_evolutions=TRADE_EVOLUTIONS)

    assert smaller.total_obtainable == larger.total_obtainable == 150
