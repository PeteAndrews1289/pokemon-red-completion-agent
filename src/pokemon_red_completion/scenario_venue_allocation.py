"""Title-neutral allocation of independent scenario roots to reachable venues.

One retained emulator state can sometimes reach more than the venue implied by
its loaded map.  This module treats that as a small capacitated bipartite
matching problem.  It knows nothing about Red, maps, parties, or emulator
actions; title adapters supply only opaque root identities and semantic venue
identifiers that have already passed their own eligibility checks.
"""

from __future__ import annotations

from dataclasses import dataclass


class ScenarioVenueAllocationError(ValueError):
    """Raised when a prospective allocation contract is malformed."""


@dataclass(frozen=True, slots=True)
class ReachableVenueRoot:
    """One independent root and the venues where it is genuinely eligible."""

    root_id: str
    venue_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.root_id, str)
            or not self.root_id
            or not isinstance(self.venue_ids, tuple)
            or not self.venue_ids
            or any(not isinstance(venue_id, str) or not venue_id for venue_id in self.venue_ids)
            or tuple(sorted(set(self.venue_ids))) != self.venue_ids
        ):
            raise ScenarioVenueAllocationError("reachable venue root differs")


@dataclass(frozen=True, slots=True)
class VenueRootAssignment:
    """One root used once at one reachable venue."""

    root_id: str
    venue_id: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.root_id, str)
            or not self.root_id
            or not isinstance(self.venue_id, str)
            or not self.venue_id
        ):
            raise ScenarioVenueAllocationError("venue root assignment differs")


@dataclass(frozen=True, slots=True)
class ScenarioVenueAllocation:
    """Canonical maximum allocation, kept private until only counts remain."""

    assignments: tuple[VenueRootAssignment, ...]
    required_roots: int
    minimum_distinct_venues: int
    maximum_roots_per_venue: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.assignments, tuple)
            or any(not isinstance(item, VenueRootAssignment) for item in self.assignments)
            or len({item.root_id for item in self.assignments}) != len(self.assignments)
            or type(self.required_roots) is not int  # noqa: E721
            or self.required_roots < 1
            or len(self.assignments) > self.required_roots
            or type(self.minimum_distinct_venues) is not int  # noqa: E721
            or self.minimum_distinct_venues < 1
            or type(self.maximum_roots_per_venue) is not int  # noqa: E721
            or self.maximum_roots_per_venue < 1
        ):
            raise ScenarioVenueAllocationError("scenario venue allocation differs")
        if any(
            count > self.maximum_roots_per_venue
            for count in self.venue_counts.values()
        ):
            raise ScenarioVenueAllocationError("scenario venue allocation exceeds venue cap")

    @property
    def assigned_roots(self) -> int:
        return len(self.assignments)

    @property
    def venue_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for assignment in self.assignments:
            counts[assignment.venue_id] = counts.get(assignment.venue_id, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def distinct_venues(self) -> int:
        return len(self.venue_counts)

    @property
    def capacity_met(self) -> bool:
        return (
            self.assigned_roots >= self.required_roots
            and self.distinct_venues >= self.minimum_distinct_venues
        )


def allocate_reachable_venue_roots(
    roots: tuple[ReachableVenueRoot, ...],
    *,
    required_roots: int,
    minimum_distinct_venues: int,
    maximum_roots_per_venue: int,
) -> ScenarioVenueAllocation:
    """Return a deterministic maximum capacitated root-to-venue matching.

    Roots are never reused.  Search is memoized over the sorted root index and
    small per-venue capacity vector, so it remains exact rather than relying on
    a greedy choice that can miss a valid cross-venue allocation.
    """

    if (
        not isinstance(roots, tuple)
        or any(not isinstance(root, ReachableVenueRoot) for root in roots)
        or len({root.root_id for root in roots}) != len(roots)
        or type(required_roots) is not int  # noqa: E721
        or required_roots < 1
        or type(minimum_distinct_venues) is not int  # noqa: E721
        or minimum_distinct_venues < 1
        or type(maximum_roots_per_venue) is not int  # noqa: E721
        or maximum_roots_per_venue < 1
    ):
        raise ScenarioVenueAllocationError("scenario venue allocation contract differs")
    ordered_roots = tuple(sorted(roots, key=lambda item: item.root_id))
    venue_ids = tuple(sorted({venue for root in ordered_roots for venue in root.venue_ids}))
    venue_index = {venue_id: index for index, venue_id in enumerate(venue_ids)}
    memo: dict[
        tuple[int, tuple[int, ...], int],
        tuple[VenueRootAssignment, ...],
    ] = {}

    def score(
        assignments: tuple[VenueRootAssignment, ...],
        base_counts: tuple[int, ...],
    ) -> tuple[int, int, int, int]:
        counts = {
            venue_id: count
            for venue_id, count in zip(venue_ids, base_counts, strict=True)
            if count
        }
        for assignment in assignments:
            counts[assignment.venue_id] = counts.get(assignment.venue_id, 0) + 1
        distinct = len(counts)
        return (
            sum(counts.values()),
            min(distinct, minimum_distinct_venues),
            distinct,
            -max(counts.values(), default=0),
        )

    def better(
        left: tuple[VenueRootAssignment, ...],
        right: tuple[VenueRootAssignment, ...],
        base_counts: tuple[int, ...],
    ) -> tuple[VenueRootAssignment, ...]:
        left_score = score(left, base_counts)
        right_score = score(right, base_counts)
        if left_score != right_score:
            return left if left_score > right_score else right
        left_key = tuple((item.root_id, item.venue_id) for item in left)
        right_key = tuple((item.root_id, item.venue_id) for item in right)
        return left if left_key <= right_key else right

    def search(
        root_index: int,
        venue_counts: tuple[int, ...],
        assigned_count: int,
    ) -> tuple[VenueRootAssignment, ...]:
        key = (root_index, venue_counts, assigned_count)
        if key in memo:
            return memo[key]
        if root_index == len(ordered_roots) or assigned_count == required_roots:
            return ()
        root = ordered_roots[root_index]
        best = search(root_index + 1, venue_counts, assigned_count)
        for venue_id in root.venue_ids:
            index = venue_index[venue_id]
            if venue_counts[index] >= maximum_roots_per_venue:
                continue
            updated = list(venue_counts)
            updated[index] += 1
            suffix = search(root_index + 1, tuple(updated), assigned_count + 1)
            choice = (VenueRootAssignment(root.root_id, venue_id),) + suffix
            best = better(best, choice, venue_counts)
        memo[key] = best
        return best

    assignments = search(0, (0,) * len(venue_ids), 0)
    allocation = ScenarioVenueAllocation(
        assignments=assignments,
        required_roots=required_roots,
        minimum_distinct_venues=minimum_distinct_venues,
        maximum_roots_per_venue=maximum_roots_per_venue,
    )
    if (
        len({item.root_id for item in allocation.assignments})
        != allocation.assigned_roots
        or any(
            item.venue_id
            not in next(root.venue_ids for root in ordered_roots if root.root_id == item.root_id)
            for item in allocation.assignments
        )
        or any(
            count > maximum_roots_per_venue
            for count in allocation.venue_counts.values()
        )
    ):
        raise ScenarioVenueAllocationError("scenario venue allocation is inconsistent")
    return allocation


__all__ = [
    "ReachableVenueRoot",
    "ScenarioVenueAllocation",
    "ScenarioVenueAllocationError",
    "VenueRootAssignment",
    "allocate_reachable_venue_roots",
]
