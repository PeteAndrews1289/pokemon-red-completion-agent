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
from dataclasses import dataclass, field
from typing import Any, Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
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
WalkToGrassFactory = Callable[[], WalkToGrass]

#: Heal at this venue's own healer and come back to the grass.
HealAndReturn = Callable[[_Executor, Any, Any], None]
MoveGuard = Callable[[RawGameState], None]

_DIRECTION_DELTAS = {
    "up": (0, -1),
    "right": (1, 0),
    "down": (0, 1),
    "left": (-1, 0),
}
_DIRECTION_ORDER = tuple(_DIRECTION_DELTAS)
_OPPOSITE_DIRECTION = {
    "up": "down",
    "right": "left",
    "down": "up",
    "left": "right",
}


@dataclass(slots=True)
class WarpSafeVenueWalker:
    """Take real encounter steps without crossing a declared exit trigger.

    The state belongs to one training run. A module-level bounce direction can
    leak from one independently restored candidate into the next, while a fixed
    two-direction walker can reverse straight onto the warp it arrived through.
    This walker keeps only portable control state: the previous successful
    direction, movement success, blocked attempts, and excluded-transition
    skips. Map and coordinate identities remain adapter-owned execution inputs.
    """

    expected_map_id: int
    excluded_coordinates: frozenset[tuple[int, int]]
    move_wait_frames: int = 120
    maximum_no_progress_cycles: int = 2
    preferred_direction: str | None = field(default=None, init=False)
    movement_attempts: int = field(default=0, init=False)
    successful_steps: int = field(default=0, init=False)
    blocked_attempts: int = field(default=0, init=False)
    excluded_transition_skips: int = field(default=0, init=False)
    no_progress_cycles: int = field(default=0, init=False)
    _consecutive_no_progress_cycles: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if type(self.expected_map_id) is not int or self.expected_map_id < 0:  # noqa: E721
            raise VenueNavigationError("warp-safe walker needs a valid expected map")
        if not isinstance(self.excluded_coordinates, frozenset) or any(
            not isinstance(coordinate, tuple)
            or len(coordinate) != 2
            or any(type(value) is not int or value < 0 for value in coordinate)  # noqa: E721
            for coordinate in self.excluded_coordinates
        ):
            raise VenueNavigationError("warp-safe walker exclusions are invalid")
        if type(self.move_wait_frames) is not int or self.move_wait_frames < 1:  # noqa: E721
            raise VenueNavigationError("warp-safe walker wait must be positive")
        if (
            type(self.maximum_no_progress_cycles) is not int  # noqa: E721
            or self.maximum_no_progress_cycles < 1
        ):
            raise VenueNavigationError("warp-safe walker progress bound must be positive")

    def __call__(self, actions: _Executor, reader: Any, emulator: Any) -> int:
        """Attempt one verified step and return one only when movement occurred."""

        del emulator
        before = reader.read()
        if before.map_id != self.expected_map_id:
            raise VenueNavigationError("warp-safe walker started outside its venue")
        if before.battle_state:
            raise VenueNavigationError("warp-safe walker cannot run during battle")
        if before.player_x is None or before.player_y is None:
            raise VenueNavigationError("warp-safe walker needs live coordinates")

        origin = (before.player_x, before.player_y)
        for direction in self._candidate_directions(origin):
            dx, dy = _DIRECTION_DELTAS[direction]
            if (origin[0] + dx, origin[1] + dy) in self.excluded_coordinates:
                self.excluded_transition_skips += 1
                continue
            self.movement_attempts += 1
            actions.execute(MacroAction(MacroActionKind.MOVE, direction))
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=self.move_wait_frames))
            after = reader.read()
            if after.map_id != self.expected_map_id:
                raise VenueNavigationError("warp-safe walker crossed an undeclared exit trigger")
            moved = (after.player_x, after.player_y) != origin
            if moved or after.battle_state:
                self.successful_steps += 1
                self._consecutive_no_progress_cycles = 0
                self.preferred_direction = _OPPOSITE_DIRECTION[direction]
                return 1
            self.blocked_attempts += 1

        self.preferred_direction = None
        self.no_progress_cycles += 1
        self._consecutive_no_progress_cycles += 1
        if self._consecutive_no_progress_cycles >= self.maximum_no_progress_cycles:
            raise VenueNavigationError("warp-safe walker found no executable encounter step")
        return 0

    def _candidate_directions(self, origin: tuple[int, int]) -> tuple[str, ...]:
        del origin  # retained in the seam so later terrain adapters can rank neighbors
        if self.preferred_direction is None:
            return _DIRECTION_ORDER
        return (self.preferred_direction,) + tuple(
            direction for direction in _DIRECTION_ORDER if direction != self.preferred_direction
        )

    def public_summary(self) -> dict[str, int]:
        """Return identity-free reliability counters for later learner features."""

        return {
            "movement_attempts": self.movement_attempts,
            "successful_steps": self.successful_steps,
            "blocked_attempts": self.blocked_attempts,
            "excluded_transition_skips": self.excluded_transition_skips,
            "no_progress_cycles": self.no_progress_cycles,
        }


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
    walk_to_grass_factory: WalkToGrassFactory | None = None

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
        if self.walk_to_grass_factory is not None and not callable(self.walk_to_grass_factory):
            raise TypeError("walk_to_grass_factory must be callable")

    @property
    def area_id(self) -> str:
        """The venue's semantic label, taken from its measurement."""

        return self.band.area_id

    def is_in_map(self, raw: RawGameState) -> bool:
        """Whether we are standing in this venue."""

        return raw.map_id == self.map_id

    def fresh_walk_to_grass(self) -> WalkToGrass:
        """Return a run-local walker so independently restored trials cannot share state."""

        walker = (
            self.walk_to_grass_factory()
            if self.walk_to_grass_factory is not None
            else self.walk_to_grass
        )
        if not callable(walker):  # pragma: no cover - type checker and constructor own this seam
            raise VenueNavigationError(f"venue {self.area_id} produced no executable walker")
        return walker

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
