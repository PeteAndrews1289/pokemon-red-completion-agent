"""Game-neutral party observation contract for balanced multi-member teams.

A completion agent that intends to transfer between Pokémon titles cannot
reason about "the lead Pokémon" alone.  This module describes a whole party
using reusable concepts—membership, species, active position, level, health,
status, moves, and experience—so a planner can compare a six-member roster
without knowing any revision's memory layout.

As with :mod:`pokemon_red_completion.domain`, this module deliberately contains
no ROM paths, memory addresses, screenshots, save states, controller timing, or
map coordinates.  Each game adapter is responsible for projecting its own state
into these types.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

PARTY_SLOT_LIMIT = 6
MOVE_SLOT_LIMIT = 4
MIN_LEVEL = 1
MAX_LEVEL = 100
EMPTY_MOVE_ID = 0


class StatusCondition(StrEnum):
    """Persistent, non-volatile conditions shared by the Pokémon mainline.

    Fainting is deliberately absent: it is derived from current health rather
    than stored here, so a fainted member keeps whatever condition it carried.
    """

    HEALTHY = "healthy"
    SLEEP = "sleep"
    POISON = "poison"
    BURN = "burn"
    FREEZE = "freeze"
    PARALYSIS = "paralysis"
    #: Badly poisoned. Early games carry the escalating condition in battle
    #: substatus while the party byte reports ordinary poison, so a party-only
    #: Red or Crystal adapter does not emit it. A battle adapter may still need
    #: this value because the increasing damage changes whether a member is safe
    #: to keep in; later title adapters must follow their own storage semantics.
    TOXIC = "toxic"


class Gender(StrEnum):
    """A member's gender, where the title tracks one.

    Gen 1 has no concept of gender at all, so a Red adapter leaves this unset
    rather than guessing. From Gen 2 it decides breeding compatibility, which
    is an acquisition route a living Pokedex needs.
    """

    MALE = "male"
    FEMALE = "female"
    GENDERLESS = "genderless"


class PartyRole(StrEnum):
    """Reusable team roles that do not name any specific species.

    Roles let a roster be planned, substituted, and documented in transferable
    terms.  A game adapter binds each role to a concrete species.
    """

    LEAD_ATTACKER = "lead_attacker"
    PHYSICAL_SWEEPER = "physical_sweeper"
    SPECIAL_SWEEPER = "special_sweeper"
    BULKY_ABSORBER = "bulky_absorber"
    SPEED_CONTROL = "speed_control"
    FIELD_UTILITY = "field_utility"


@dataclass(frozen=True, slots=True)
class MoveObservation:
    """One known move and its remaining power points."""

    move_id: int
    current_pp: int
    max_pp: int | None = None

    def __post_init__(self) -> None:
        for name in ("move_id", "current_pp"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.max_pp is not None:
            if type(self.max_pp) is not int or self.max_pp < 0:
                raise ValueError("max_pp must be a non-negative integer or None")
            if self.current_pp > self.max_pp:
                raise ValueError("current_pp cannot exceed max_pp")

    @property
    def is_known(self) -> bool:
        """Whether this slot holds a real move rather than an empty slot."""

        return self.move_id != EMPTY_MOVE_ID

    @property
    def is_usable(self) -> bool:
        """Whether this move could be selected right now."""

        return self.is_known and self.current_pp > 0


@dataclass(frozen=True, slots=True)
class PartyMemberObservation:
    """One active party member observed at a single point in time.

    ``slot`` is the one-based active-party position; it is the position a
    planner would use to switch to this member, not a storage-box index.
    """

    slot: int
    species_id: int
    level: int
    hp: int
    max_hp: int
    status: StatusCondition = StatusCondition.HEALTHY
    moves: tuple[MoveObservation, ...] = ()
    experience: int | None = None
    experience_floor: int | None = None
    experience_next: int | None = None
    #: What this member is carrying, as a namespaced reference, or ``None``
    #: where the title has no held items. Gen 1 has none; from Gen 2 a held
    #: item decides whether a member survives a turn it otherwise would not,
    #: so a planner that cannot see it is reasoning about a different game.
    held_item_ref: str | None = None
    #: ``None`` where the title does not track gender, which is Gen 1 only.
    gender: Gender | None = None

    def __post_init__(self) -> None:
        if type(self.slot) is not int or not 1 <= self.slot <= PARTY_SLOT_LIMIT:
            raise ValueError(f"slot must be a one-based position within {PARTY_SLOT_LIMIT}")
        if type(self.species_id) is not int or self.species_id <= 0:
            raise ValueError("species_id must be a positive integer")
        if type(self.level) is not int or not MIN_LEVEL <= self.level <= MAX_LEVEL:
            raise ValueError(f"level must be between {MIN_LEVEL} and {MAX_LEVEL}")
        if type(self.max_hp) is not int or self.max_hp <= 0:
            raise ValueError("max_hp must be a positive integer")
        if type(self.hp) is not int or not 0 <= self.hp <= self.max_hp:
            raise ValueError("hp must be between zero and max_hp")
        if not isinstance(self.status, StatusCondition):
            raise TypeError("status must be a StatusCondition")
        if self.held_item_ref is not None and (
            not isinstance(self.held_item_ref, str) or ":" not in self.held_item_ref
        ):
            raise ValueError("held_item_ref must be a namespaced reference or None")
        if self.gender is not None and not isinstance(self.gender, Gender):
            raise TypeError("gender must be a Gender or None")
        if len(self.moves) > MOVE_SLOT_LIMIT:
            raise ValueError(f"a member cannot know more than {MOVE_SLOT_LIMIT} moves")
        if any(not isinstance(move, MoveObservation) for move in self.moves):
            raise TypeError("moves must contain MoveObservation entries")
        for name in ("experience", "experience_floor", "experience_next"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if (
            self.experience_floor is not None
            and self.experience_next is not None
            and self.experience_next <= self.experience_floor
        ):
            raise ValueError("experience_next must exceed experience_floor")

    @property
    def hp_ratio(self) -> float:
        """Remaining health as a fraction of maximum health."""

        return self.hp / self.max_hp if self.max_hp > 0 else 0.0

    @property
    def is_fainted(self) -> bool:
        """Whether this member has no remaining health."""

        return self.hp == 0

    @property
    def known_moves(self) -> tuple[MoveObservation, ...]:
        """Every non-empty move slot."""

        return tuple(move for move in self.moves if move.is_known)

    @property
    def usable_moves(self) -> tuple[MoveObservation, ...]:
        """Every move that could be selected right now."""

        return tuple(move for move in self.moves if move.is_usable)

    @property
    def total_pp(self) -> int:
        """Remaining power points summed across every known move."""

        return sum(move.current_pp for move in self.known_moves)

    @property
    def can_battle(self) -> bool:
        """Whether this member could take a turn without first being restored."""

        return not self.is_fainted and bool(self.usable_moves)

    @property
    def is_trainable(self) -> bool:
        """Whether this member could gain experience from a battle right now.

        A trainable member must be able to act and must not already sit at the
        level ceiling.
        """

        return self.can_battle and self.level < MAX_LEVEL

    @property
    def level_progress(self) -> float | None:
        """Fraction of the way from this level to the next, when observable.

        Adapters that cannot supply the experience curve for a species return
        ``None`` rather than guessing a denominator.
        """

        if self.experience is None or self.experience_floor is None:
            return None
        if self.experience_next is None:
            return None
        span = self.experience_next - self.experience_floor
        if span <= 0:
            return None
        earned = self.experience - self.experience_floor
        return min(1.0, max(0.0, earned / span))


@dataclass(frozen=True, slots=True)
class PartyObservation:
    """An immutable snapshot of the whole active party.

    Members are stored in active-party order.  An empty party is legal and is
    reported as incomplete rather than as an error, because the earliest game
    states genuinely have no party at all.
    """

    members: tuple[PartyMemberObservation, ...] = ()
    capacity: int = PARTY_SLOT_LIMIT

    def __post_init__(self) -> None:
        if type(self.capacity) is not int or not 1 <= self.capacity <= PARTY_SLOT_LIMIT:
            raise ValueError(f"capacity must be between 1 and {PARTY_SLOT_LIMIT}")
        if any(not isinstance(member, PartyMemberObservation) for member in self.members):
            raise TypeError("members must contain PartyMemberObservation entries")
        if len(self.members) > self.capacity:
            raise ValueError("party holds more members than its capacity")
        expected = tuple(range(1, len(self.members) + 1))
        if tuple(member.slot for member in self.members) != expected:
            raise ValueError("members must occupy contiguous one-based slots in party order")

    @property
    def size(self) -> int:
        """How many members the party currently holds."""

        return len(self.members)

    @property
    def open_slots(self) -> int:
        """How many active-party positions remain unfilled."""

        return self.capacity - self.size

    @property
    def is_complete(self) -> bool:
        """Whether every active-party position is filled."""

        return self.size == self.capacity

    @property
    def is_incomplete(self) -> bool:
        """Whether the party still has room for another member."""

        return not self.is_complete

    @property
    def lead(self) -> PartyMemberObservation | None:
        """The member occupying the first active-party position."""

        return self.members[0] if self.members else None

    @property
    def levels(self) -> tuple[int, ...]:
        """Every member's level in active-party order."""

        return tuple(member.level for member in self.members)

    @property
    def minimum_level(self) -> int | None:
        """The lowest level present, or ``None`` for an empty party."""

        return min(self.levels) if self.members else None

    @property
    def maximum_level(self) -> int | None:
        """The highest level present, or ``None`` for an empty party."""

        return max(self.levels) if self.members else None

    @property
    def level_spread(self) -> int | None:
        """The distance between the highest and lowest level present."""

        if not self.members:
            return None
        return max(self.levels) - min(self.levels)

    @property
    def average_level(self) -> float | None:
        """The mean level across the party, or ``None`` for an empty party."""

        if not self.members:
            return None
        return sum(self.levels) / len(self.levels)

    @property
    def fainted_count(self) -> int:
        """How many members currently have no health."""

        return sum(1 for member in self.members if member.is_fainted)

    @property
    def battle_ready_count(self) -> int:
        """How many members could take a turn without being restored first."""

        return sum(1 for member in self.members if member.can_battle)

    @property
    def is_wiped_out(self) -> bool:
        """Whether a non-empty party has no member left able to act."""

        return bool(self.members) and self.battle_ready_count == 0

    @property
    def weakest_trainable_member(self) -> PartyMemberObservation | None:
        """The lowest-level member that can still gain experience.

        Ties are broken by active-party position so the choice is stable across
        observations rather than dependent on iteration order.
        """

        trainable = [member for member in self.members if member.is_trainable]
        if not trainable:
            return None
        return min(trainable, key=lambda member: (member.level, member.slot))

    def member_in_slot(self, slot: int) -> PartyMemberObservation | None:
        """Return the member at a one-based active-party position."""

        for member in self.members:
            if member.slot == slot:
                return member
        return None

    def members_below_level(self, level: int) -> tuple[PartyMemberObservation, ...]:
        """Every member beneath a level threshold, in active-party order."""

        return tuple(member for member in self.members if member.level < level)

    def meets_minimum_level(self, level: int) -> bool:
        """Whether a complete party has every member at or above a level."""

        return self.is_complete and not self.members_below_level(level)

    def is_level_balanced(self, maximum_spread: int) -> bool:
        """Whether the observed level spread sits within an allowed maximum."""

        if maximum_spread < 0:
            raise ValueError("maximum_spread must be non-negative")
        spread = self.level_spread
        return spread is not None and spread <= maximum_spread

    def species_ids(self) -> tuple[int, ...]:
        """Every member's species in active-party order."""

        return tuple(member.species_id for member in self.members)

    def has_species(self, species_id: int) -> bool:
        """Whether a species currently occupies an active-party position."""

        return species_id in self.species_ids()
