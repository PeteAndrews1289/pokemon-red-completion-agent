"""Bounded live qualification for Red's warp-safe Cave venue walker.

This is deliberately not a party-development outcome.  It spends one fresh,
non-sealed train context only to answer whether the repaired controller can
enter the venue, avoid reversing across its arrival trigger, and make enough
real progress to justify collecting later party outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.observation import PokemonRedStateReader, ReadOnlyMemory
from pokemon_red_completion.party import StatusCondition
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.training_venue import TrainingVenue, WarpSafeVenueWalker


class CaveTraversalQualificationError(RuntimeError):
    """Raised when the bounded qualification cannot support its declared claim."""


@dataclass(frozen=True, slots=True)
class CaveTraversalQualificationPolicy:
    """Prospectively bounded evidence required from one live qualification."""

    minimum_successful_steps: int = 2
    maximum_successful_steps: int = 12
    maximum_movement_attempts: int = 48
    require_excluded_transition_skip: bool = True

    def __post_init__(self) -> None:
        if (
            type(self.minimum_successful_steps) is not int  # noqa: E721
            or self.minimum_successful_steps < 2
        ):
            raise CaveTraversalQualificationError(
                "Cave qualification needs at least two successful steps"
            )
        if (
            type(self.maximum_successful_steps) is not int  # noqa: E721
            or self.maximum_successful_steps < self.minimum_successful_steps
        ):
            raise CaveTraversalQualificationError(
                "Cave qualification step ceiling is invalid"
            )
        if (
            type(self.maximum_movement_attempts) is not int  # noqa: E721
            or self.maximum_movement_attempts < self.maximum_successful_steps
        ):
            raise CaveTraversalQualificationError(
                "Cave qualification movement-attempt ceiling is invalid"
            )
        if not isinstance(self.require_excluded_transition_skip, bool):
            raise CaveTraversalQualificationError(
                "Cave qualification transition requirement is invalid"
            )

    def public_dict(self) -> dict[str, int | bool]:
        return {
            "minimum_successful_steps": self.minimum_successful_steps,
            "maximum_successful_steps": self.maximum_successful_steps,
            "maximum_movement_attempts": self.maximum_movement_attempts,
            "require_excluded_transition_skip": self.require_excluded_transition_skip,
        }


@dataclass(frozen=True, slots=True)
class CaveTraversalQualificationResult:
    """Identity-free evidence from the bounded live traversal."""

    recovery_completed: bool
    entered_on_declared_transition: bool
    terminal_reason: str
    battle_started: bool
    movement_attempts: int
    successful_steps: int
    blocked_attempts: int
    excluded_transition_skips: int
    no_progress_cycles: int

    def __post_init__(self) -> None:
        if self.terminal_reason not in {"battle_after_minimum", "step_ceiling"}:
            raise CaveTraversalQualificationError(
                "Cave qualification terminal reason is invalid"
            )
        counters = (
            self.movement_attempts,
            self.successful_steps,
            self.blocked_attempts,
            self.excluded_transition_skips,
            self.no_progress_cycles,
        )
        if any(type(value) is not int or value < 0 for value in counters):  # noqa: E721
            raise CaveTraversalQualificationError(
                "Cave qualification counters are invalid"
            )
        if self.successful_steps + self.blocked_attempts != self.movement_attempts:
            raise CaveTraversalQualificationError(
                "Cave qualification movement accounting is incomplete"
            )
        if self.battle_started != (self.terminal_reason == "battle_after_minimum"):
            raise CaveTraversalQualificationError(
                "Cave qualification battle accounting is inconsistent"
            )

    @property
    def passed(self) -> bool:
        return (
            self.recovery_completed
            and self.entered_on_declared_transition
            and self.successful_steps >= 2
            and self.excluded_transition_skips >= 1
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "recovery_completed": self.recovery_completed,
            "entered_on_declared_transition": self.entered_on_declared_transition,
            "terminal_reason": self.terminal_reason,
            "battle_started": self.battle_started,
            "movement_attempts": self.movement_attempts,
            "successful_steps": self.successful_steps,
            "blocked_attempts": self.blocked_attempts,
            "excluded_transition_skips": self.excluded_transition_skips,
            "no_progress_cycles": self.no_progress_cycles,
            "map_departures": 0,
        }


def run_cave_traversal_qualification(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: ReadOnlyMemory,
    *,
    venue: TrainingVenue,
    policy: CaveTraversalQualificationPolicy,
) -> CaveTraversalQualificationResult:
    """Heal, enter the Cave once, and exercise the repaired boundary once.

    A battle is a natural terminal only after the two-step reversal seam has
    been exercised.  No battle command is sent here.  Unexpected map departure,
    early encounter, missing recovery, uninstrumented walking, or incomplete
    transition coverage fails closed.
    """

    venue.heal_and_return(actions, reader, emulator)
    entry = reader.read()
    if (
        entry.map_id != venue.map_id
        or entry.battle_state
        or entry.player_x is None
        or entry.player_y is None
    ):
        raise CaveTraversalQualificationError(
            "Cave qualification did not reach a stable venue entry"
        )

    party = PokemonRedPartyReader(emulator).read()
    recovery_completed = bool(party.members) and all(
        member.hp == member.max_hp
        and member.status is StatusCondition.HEALTHY
        and not member.is_fainted
        for member in party.members
    )
    if not recovery_completed:
        raise CaveTraversalQualificationError(
            "Cave qualification did not preserve its recovery boundary"
        )

    walker = venue.fresh_walk_to_grass()
    if not isinstance(walker, WarpSafeVenueWalker):
        raise CaveTraversalQualificationError(
            "Cave qualification requires the instrumented warp-safe walker"
        )
    entered_on_declared_transition = (
        entry.player_x,
        entry.player_y,
    ) in walker.excluded_coordinates
    if not entered_on_declared_transition:
        raise CaveTraversalQualificationError(
            "Cave qualification did not begin on the declared transition seam"
        )

    terminal_reason: str | None = None
    while terminal_reason is None:
        walker(actions, reader, emulator)
        summary = walker.public_summary()
        if summary["movement_attempts"] > policy.maximum_movement_attempts:
            raise CaveTraversalQualificationError(
                "Cave qualification exhausted its movement-attempt bound"
            )
        after = reader.read()
        if after.map_id != venue.map_id:
            raise CaveTraversalQualificationError(
                "Cave qualification departed its venue"
            )
        if after.battle_state:
            if summary["successful_steps"] < policy.minimum_successful_steps:
                raise CaveTraversalQualificationError(
                    "Cave qualification met a battle before exercising the reversal seam"
                )
            terminal_reason = "battle_after_minimum"
            break
        if summary["successful_steps"] >= policy.maximum_successful_steps:
            terminal_reason = "step_ceiling"

    summary = walker.public_summary()
    if summary["successful_steps"] < policy.minimum_successful_steps:
        raise CaveTraversalQualificationError(
            "Cave qualification did not make enough successful progress"
        )
    if (
        policy.require_excluded_transition_skip
        and summary["excluded_transition_skips"] < 1
    ):
        raise CaveTraversalQualificationError(
            "Cave qualification did not exercise its transition exclusion"
        )

    result = CaveTraversalQualificationResult(
        recovery_completed=recovery_completed,
        entered_on_declared_transition=entered_on_declared_transition,
        terminal_reason=terminal_reason,
        battle_started=terminal_reason == "battle_after_minimum",
        movement_attempts=summary["movement_attempts"],
        successful_steps=summary["successful_steps"],
        blocked_attempts=summary["blocked_attempts"],
        excluded_transition_skips=summary["excluded_transition_skips"],
        no_progress_cycles=summary["no_progress_cycles"],
    )
    if not result.passed:  # pragma: no cover - individual fail-closed guards own this
        raise CaveTraversalQualificationError("Cave qualification did not pass")
    return result


__all__ = [
    "CaveTraversalQualificationError",
    "CaveTraversalQualificationPolicy",
    "CaveTraversalQualificationResult",
    "run_cave_traversal_qualification",
]
