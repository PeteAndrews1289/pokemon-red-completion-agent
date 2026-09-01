from __future__ import annotations

import pytest

from pokemon_red_completion.scenario_venue_allocation import (
    ReachableVenueRoot,
    ScenarioVenueAllocationError,
    allocate_additive_reachable_venue_roots,
    allocate_reachable_venue_roots,
)


def _root(root_id: str, *venue_ids: str) -> ReachableVenueRoot:
    return ReachableVenueRoot(root_id, tuple(sorted(venue_ids)))


def test_allocator_finds_cross_venue_matching_that_greedy_order_can_miss() -> None:
    roots = (
        _root("a-flexible", "cave", "route"),
        _root("b-route-only", "route"),
        _root("c-route-only", "route"),
    )

    allocation = allocate_reachable_venue_roots(
        roots,
        required_roots=3,
        minimum_distinct_venues=2,
        maximum_roots_per_venue=2,
    )

    assert allocation.capacity_met
    assert allocation.assigned_roots == 3
    assert allocation.venue_counts == {"cave": 1, "route": 2}


def test_allocator_scores_later_choices_against_venues_used_by_earlier_roots() -> None:
    allocation = allocate_reachable_venue_roots(
        (
            _root("a-route-only", "route"),
            _root("b-flexible", "cave", "route"),
        ),
        required_roots=2,
        minimum_distinct_venues=2,
        maximum_roots_per_venue=2,
    )

    assert allocation.capacity_met
    assert allocation.venue_counts == {"cave": 1, "route": 1}


def test_allocator_never_reuses_a_root_or_exceeds_a_venue_cap() -> None:
    roots = tuple(_root(f"root-{index}", "cave", "route") for index in range(8))

    allocation = allocate_reachable_venue_roots(
        roots,
        required_roots=7,
        minimum_distinct_venues=2,
        maximum_roots_per_venue=6,
    )

    assert allocation.capacity_met
    assert len({item.root_id for item in allocation.assignments}) == 7
    assert max(allocation.venue_counts.values()) <= 6


def test_allocator_reports_partial_capacity_without_inventing_supply() -> None:
    roots = tuple(_root(f"root-{index}", "route") for index in range(8))

    allocation = allocate_reachable_venue_roots(
        roots,
        required_roots=7,
        minimum_distinct_venues=2,
        maximum_roots_per_venue=6,
    )

    assert not allocation.capacity_met
    assert allocation.assigned_roots == 6
    assert allocation.venue_counts == {"route": 6}


def test_allocator_is_invariant_to_input_order() -> None:
    roots = (
        _root("root-c", "mansion"),
        _root("root-a", "cave", "route"),
        _root("root-b", "route"),
    )
    kwargs = {
        "required_roots": 3,
        "minimum_distinct_venues": 2,
        "maximum_roots_per_venue": 2,
    }

    forward = allocate_reachable_venue_roots(roots, **kwargs)
    reverse = allocate_reachable_venue_roots(tuple(reversed(roots)), **kwargs)

    assert forward == reverse


def test_allocator_rejects_duplicate_roots_and_noncanonical_venues() -> None:
    with pytest.raises(ScenarioVenueAllocationError, match="contract"):
        allocate_reachable_venue_roots(
            (_root("same", "route"), _root("same", "cave")),
            required_roots=1,
            minimum_distinct_venues=1,
            maximum_roots_per_venue=1,
        )
    with pytest.raises(ScenarioVenueAllocationError, match="root differs"):
        ReachableVenueRoot("root", ("route", "cave"))


def test_additive_allocator_preserves_retained_seats_and_fills_only_the_gap() -> None:
    allocation = allocate_additive_reachable_venue_roots(
        tuple(_root(f"root-{index}", "cave", "route") for index in range(3)),
        retained_venue_counts=(("cave", 2), ("route", 3)),
        required_additional_roots=2,
        minimum_total_distinct_venues=2,
        maximum_total_roots_per_venue=6,
    )

    assert allocation.capacity_met
    assert len(allocation.assignments) == 2
    assert allocation.total_venue_counts == {"cave": 4, "route": 3}


def test_additive_allocator_uses_new_venue_when_retained_seats_need_diversity() -> None:
    allocation = allocate_additive_reachable_venue_roots(
        (_root("a-flexible", "cave", "route"), _root("b-route", "route")),
        retained_venue_counts=(("route", 5),),
        required_additional_roots=1,
        minimum_total_distinct_venues=2,
        maximum_total_roots_per_venue=6,
    )

    assert allocation.capacity_met
    assert allocation.assignments[0].venue_id == "cave"
    assert allocation.total_venue_counts == {"cave": 1, "route": 5}


def test_additive_allocator_fails_without_replacing_or_hiding_retained_seats() -> None:
    allocation = allocate_additive_reachable_venue_roots(
        (_root("route-only", "route"),),
        retained_venue_counts=(("route", 6),),
        required_additional_roots=1,
        minimum_total_distinct_venues=2,
        maximum_total_roots_per_venue=6,
    )

    assert not allocation.capacity_met
    assert allocation.assignments == ()
    assert allocation.total_venue_counts == {"route": 6}


def test_additive_allocator_is_invariant_to_new_root_order() -> None:
    roots = (
        _root("root-c", "cave", "route"),
        _root("root-a", "cave", "route"),
        _root("root-b", "route"),
    )
    kwargs = {
        "retained_venue_counts": (("cave", 2), ("route", 3)),
        "required_additional_roots": 2,
        "minimum_total_distinct_venues": 2,
        "maximum_total_roots_per_venue": 6,
    }

    assert allocate_additive_reachable_venue_roots(
        roots,
        **kwargs,
    ) == allocate_additive_reachable_venue_roots(tuple(reversed(roots)), **kwargs)
