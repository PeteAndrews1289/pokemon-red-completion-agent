"""Game-neutral species-registration contract for Pokédex completion.

Completing the Pokédex is the long-horizon goal that makes a teacher exercise
the *breadth* of Pokémon mechanics rather than the minimum path to a credits
screen: encounter tables, every evolution method, storage management, and the
areas a completion route skips.  Those are the skills that carry into later
games, where breeding, held items, and day/night stack more of the same kind of
complexity on top.

This module supplies the measurement.  It contains no species names, no memory
addresses, and no game-specific rules: a target set is *declared* by each
adapter, together with the reason every unreachable species is excluded.  That
declaration is the point.  A completion percentage measured against an unstated
denominator is exactly the kind of number that reads as progress without being
checkable.

Identifier space is the adapter's choice, but it must be consistent within one
target: Pokédex ordinals and internal species indices are different numbering
systems in most titles, and mixing them silently produces a plausible,
meaningless percentage.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class ExclusionReason(StrEnum):
    """Why a species cannot be registered by single-cartridge play."""

    VERSION_EXCLUSIVE = "version_exclusive"
    REQUIRES_TRADE = "requires_trade"
    EVENT_DISTRIBUTION = "event_distribution"
    MUTUALLY_EXCLUSIVE_CHOICE = "mutually_exclusive_choice"
    UNIMPLEMENTED = "unimplemented"


@dataclass(frozen=True, slots=True)
class PokedexObservation:
    """Which species have been encountered and which are owned."""

    seen: frozenset[int] = frozenset()
    owned: frozenset[int] = frozenset()

    def __post_init__(self) -> None:
        for name in ("seen", "owned"):
            value = getattr(self, name)
            if not isinstance(value, frozenset):
                object.__setattr__(self, name, frozenset(value))
            if any(type(entry) is not int or entry <= 0 for entry in getattr(self, name)):
                raise ValueError(f"{name} must contain positive species identifiers")
        if not self.owned <= self.seen:
            raise ValueError("every owned species must also have been seen")

    @property
    def seen_count(self) -> int:
        """How many distinct species have been encountered."""

        return len(self.seen)

    @property
    def owned_count(self) -> int:
        """How many distinct species have been registered as owned."""

        return len(self.owned)


@dataclass(frozen=True, slots=True)
class PokedexTarget:
    """The declared completion target for one game, with its exclusions stated.

    ``obtainable`` is the denominator.  ``exclusions`` records every species
    outside it and why, so "100% complete" means something a reader can audit
    rather than a percentage of an unstated set.
    """

    total_species: int
    obtainable: frozenset[int]
    exclusions: Mapping[int, ExclusionReason] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.total_species) is not int or self.total_species <= 0:
            raise ValueError("total_species must be a positive integer")
        obtainable = frozenset(self.obtainable)
        object.__setattr__(self, "obtainable", obtainable)
        if any(not 1 <= entry <= self.total_species for entry in obtainable):
            raise ValueError("obtainable holds an identifier outside the species range")
        if any(not 1 <= entry <= self.total_species for entry in self.exclusions):
            raise ValueError("exclusions holds an identifier outside the species range")
        if any(
            not isinstance(reason, ExclusionReason) for reason in self.exclusions.values()
        ):
            raise TypeError("every exclusion must carry an ExclusionReason")
        overlap = obtainable & frozenset(self.exclusions)
        if overlap:
            raise ValueError(
                f"{len(overlap)} species are both obtainable and excluded"
            )
        expected = frozenset(range(1, self.total_species + 1))
        unaccounted = expected - obtainable - frozenset(self.exclusions)
        if unaccounted:
            raise ValueError(
                f"{len(unaccounted)} species are neither obtainable nor excluded; "
                "every species must be accounted for so the denominator is explicit"
            )

    @property
    def obtainable_count(self) -> int:
        """The completion denominator this game actually supports."""

        return len(self.obtainable)

    def excluded_for(self, reason: ExclusionReason) -> frozenset[int]:
        """Every species excluded for one stated reason."""

        return frozenset(
            species for species, entry in self.exclusions.items() if entry is reason
        )


@dataclass(frozen=True, slots=True)
class PokedexProgress:
    """Completion measured against a declared, auditable target."""

    target: PokedexTarget
    observation: PokedexObservation

    @property
    def registered(self) -> frozenset[int]:
        """Owned species that count toward this target."""

        return self.observation.owned & self.target.obtainable

    @property
    def missing(self) -> frozenset[int]:
        """Obtainable species not yet owned."""

        return self.target.obtainable - self.observation.owned

    @property
    def unexpected(self) -> frozenset[int]:
        """Owned species the target declared unobtainable.

        A non-empty result means the declaration is wrong, not that the run
        cheated—treat it as a prompt to re-check the exclusions.
        """

        return self.observation.owned - self.target.obtainable

    @property
    def completion(self) -> float:
        """Fraction of the obtainable set that is owned, in ``[0, 1]``."""

        if not self.target.obtainable_count:
            return 0.0
        return len(self.registered) / self.target.obtainable_count

    @property
    def is_complete(self) -> bool:
        """Whether every obtainable species has been registered."""

        return not self.missing


def declare_target(
    total_species: int,
    exclusions: Mapping[int, ExclusionReason],
) -> PokedexTarget:
    """Build a target from its exclusions, deriving the obtainable set.

    Stating what a game *cannot* reach is far shorter and far easier to review
    than listing everything it can, so the denominator stays auditable.
    """

    obtainable = frozenset(range(1, total_species + 1)) - frozenset(exclusions)
    return PokedexTarget(
        total_species=total_species,
        obtainable=obtainable,
        exclusions=dict(exclusions),
    )


def summarize(target: PokedexTarget, observation: PokedexObservation) -> PokedexProgress:
    """Measure one observation against a declared target."""

    return PokedexProgress(target=target, observation=observation)


def registration_from_flags(flags: Iterable[int], total_species: int) -> frozenset[int]:
    """Decode a little-endian bitfield into a set of species identifiers.

    Mainline titles store the Pokédex as one bit per species, ordinal ``n``
    living in bit ``(n - 1) % 8`` of byte ``(n - 1) // 8``.  Keeping the decode
    here means an adapter only has to supply bytes.
    """

    payload = tuple(flags)
    if any(type(byte) is not int or not 0 <= byte <= 0xFF for byte in payload):
        raise ValueError("flags must be unsigned bytes")
    return frozenset(
        species
        for species in range(1, total_species + 1)
        if (species - 1) // 8 < len(payload)
        and payload[(species - 1) // 8] >> ((species - 1) % 8) & 1
    )
