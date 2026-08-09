"""A training venue: a measured encounter band plus the way to train in it.

``run_red_team_balancing`` takes the five pieces of a venue as five loose
arguments -- where the healer is, how to reach the grass, how to recognise the
map, how to recognise the centre, which move to use -- alongside thirteen
others.  Nothing binds them together, so nothing can say "this trainee belongs
somewhere else, go there instead": choosing a venue and training at a venue are
expressed in different vocabularies.

Bundling them makes the choice sayable.  A venue knows the band it was measured
to field and the navigation that makes it usable, so venue selection can return
something the caller can immediately train in rather than a label it has to
translate by hand.

The band is not restated here.  It is the :class:`GrindingArea` harvested into
``docs/evidence``, so a venue cannot drift from its measurement without the
band drifting too, and that is already guarded.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pokemon_red_completion.battle_runtime import (
    DEFAULT_BATTLE_RUNTIME_TIMING,
    BattleRuntimeTiming,
)
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.party import PartyMemberObservation
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    GrindingArea,
    choose_grinding_area,
)


class VenueNavigationError(RuntimeError):
    """Raised when a venue is described in a way that cannot be trained in."""


class _Executor(Protocol):
    def execute(self, action: Any) -> object: ...


#: Reach the grass from wherever the venue's entrance leaves us, returning the
#: number of steps taken so the training loop can bound its own walking.
WalkToGrass = Callable[[_Executor, Any, Any], int]

#: Heal at this venue's own healer and come back to the grass.
HealAndReturn = Callable[[_Executor, Any, Any], None]
MoveGuard = Callable[[RawGameState], None]


@dataclass(frozen=True, slots=True)
class TrainingVenue:
    """One place a member can actually be trained, and how to do it there.

    ``band`` is the measured evidence; everything else is the navigation that
    makes the measurement usable.  A venue whose band claims a nearby healer
    but supplies no way to reach one is rejected at construction, because that
    combination is exactly the one that strands a run: the policy sends a
    trainee somewhere on the strength of a healer that the code cannot use.
    """

    band: GrindingArea
    map_id: int
    walk_to_grass: WalkToGrass
    heal_and_return: HealAndReturn
    is_in_center: Callable[[RawGameState], bool]
    move_slot: Callable[[RawGameState], int]
    move_guard: MoveGuard | None = None
    battle_timing: BattleRuntimeTiming = DEFAULT_BATTLE_RUNTIME_TIMING

    def __post_init__(self) -> None:
        if not isinstance(self.band, GrindingArea):
            raise TypeError("band must be a measured GrindingArea")
        if not self.band.is_measured:
            raise VenueNavigationError(
                f"venue {self.band.area_id} rests on an unmeasured band; "
                "harvest it before training there"
            )
        if type(self.map_id) is not int or self.map_id < 0:
            raise VenueNavigationError(f"venue {self.band.area_id} has no valid map id")
        if not isinstance(self.battle_timing, BattleRuntimeTiming):
            raise TypeError("battle_timing must be a BattleRuntimeTiming")

    @property
    def area_id(self) -> str:
        """The venue's semantic label, taken from its measurement."""

        return self.band.area_id

    def is_in_map(self, raw: RawGameState) -> bool:
        """Whether we are standing in this venue."""

        return raw.map_id == self.map_id

    def describe(self) -> str:
        """A one-line account fit for an error message or a receipt."""

        rare = (
            f", rare to {self.band.rare_maximum_encounter_level}"
            if self.band.has_rare_ceiling
            else ""
        )
        return (
            f"{self.area_id} ({self.band.minimum_encounter_level}-"
            f"{self.band.maximum_encounter_level}{rare}), measured over "
            f"{self.band.measured_samples} encounters"
        )


def select_training_venue(
    venues: Iterable[TrainingVenue],
    trainee: PartyMemberObservation,
    policy: BalancedTeamPolicy,
    require_healer: bool = True,
    *,
    active_conditions: tuple[str, ...] = (),
) -> TrainingVenue | None:
    """Pick the venue this trainee should actually be trained in.

    Delegates the judgement to :func:`choose_grinding_area` so that venue
    choice and matchup acceptance keep answering the same question, and then
    hands back the venue rather than the band -- which is the whole point of
    the type.
    """

    by_band = {venue.band: venue for venue in venues}
    chosen = choose_grinding_area(
        by_band,
        trainee,
        policy,
        require_healer=require_healer,
        active_conditions=active_conditions,
    )
    return by_band.get(chosen) if chosen is not None else None


def venue_for_map(venues: Sequence[TrainingVenue], map_id: int) -> TrainingVenue | None:
    """The venue describing a given map, if one has been measured."""

    return next((venue for venue in venues if venue.map_id == map_id), None)
