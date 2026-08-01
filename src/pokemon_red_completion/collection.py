"""Game-neutral living-Pokédex and level-cap completion policy.

The ordinary Hall-of-Fame teacher is allowed to evolve or trade away a species
after its Pokédex flag is set.  A completionist teacher has a stricter job: it
must retain one living specimen of every in-scope species and train each one to
the declared level cap.  This module expresses that contract without maps,
RAM addresses, cartridge-specific identifiers, or menu coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .party import MAX_LEVEL, MIN_LEVEL


class CollectionLocation(StrEnum):
    """Portable storage location for one living specimen."""

    PARTY = "party"
    BOX = "box"
    DAYCARE = "daycare"


class CollectionExclusionReason(StrEnum):
    """Why a species is outside one declared completion contract."""

    VERSION_EXCLUSIVE = "version_exclusive"
    LINK_TRADE_REQUIRED = "link_trade_required"
    ALTERNATE_STARTER = "alternate_starter"
    ALTERNATE_FOSSIL = "alternate_fossil"
    ALTERNATE_DOJO_GIFT = "alternate_dojo_gift"
    ALTERNATE_BRANCH_EVOLUTION = "alternate_branch_evolution"
    EVENT_ONLY = "event_only"


@dataclass(frozen=True, slots=True)
class CollectionExclusion:
    """One explicit, auditable out-of-scope species."""

    species_ref: str
    reason: CollectionExclusionReason

    def __post_init__(self) -> None:
        _require_species_ref(self.species_ref)
        if not isinstance(self.reason, CollectionExclusionReason):
            raise TypeError("reason must be a CollectionExclusionReason")


@dataclass(frozen=True, slots=True)
class LivingSpecimen:
    """One currently retained Pokémon visible through a game adapter."""

    species_ref: str
    level: int
    location: CollectionLocation
    container_index: int = 0
    slot_index: int = 0

    def __post_init__(self) -> None:
        _require_species_ref(self.species_ref)
        if type(self.level) is not int or not MIN_LEVEL <= self.level <= MAX_LEVEL:
            raise ValueError(f"level must be between {MIN_LEVEL} and {MAX_LEVEL}")
        if not isinstance(self.location, CollectionLocation):
            raise TypeError("location must be a CollectionLocation")
        for name in ("container_index", "slot_index"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.location is CollectionLocation.PARTY and self.container_index != 0:
            raise ValueError("party specimens cannot name a non-zero container")


@dataclass(frozen=True, slots=True)
class CollectionContract:
    """A complete partition of a game's species universe into targets and exclusions."""

    game_id: str
    species_universe: tuple[str, ...]
    target_species: tuple[str, ...]
    exclusions: tuple[CollectionExclusion, ...]
    target_level: int = MAX_LEVEL

    def __post_init__(self) -> None:
        if not self.game_id:
            raise ValueError("game_id must not be empty")
        if type(self.target_level) is not int or not MIN_LEVEL <= self.target_level <= MAX_LEVEL:
            raise ValueError(f"target_level must be between {MIN_LEVEL} and {MAX_LEVEL}")
        for sequence_name in ("species_universe", "target_species"):
            sequence = getattr(self, sequence_name)
            if not sequence:
                raise ValueError(f"{sequence_name} must not be empty")
            if len(sequence) != len(set(sequence)):
                raise ValueError(f"{sequence_name} must not contain duplicates")
            for species_ref in sequence:
                _require_species_ref(species_ref)
        excluded = tuple(item.species_ref for item in self.exclusions)
        if len(excluded) != len(set(excluded)):
            raise ValueError("exclusions must not contain duplicate species")
        universe = set(self.species_universe)
        targets = set(self.target_species)
        excluded_set = set(excluded)
        if targets & excluded_set:
            raise ValueError("target species and exclusions must be disjoint")
        if targets | excluded_set != universe:
            raise ValueError("targets and exclusions must partition the species universe")


@dataclass(frozen=True, slots=True)
class CollectionObservation:
    """Policy-visible global ownership and living-storage state."""

    owned_species: frozenset[str]
    specimens: tuple[LivingSpecimen, ...]
    party_size: int
    party_limit: int
    box_counts: tuple[int, ...]
    current_box_index: int
    box_capacity: int

    def __post_init__(self) -> None:
        for species_ref in self.owned_species:
            _require_species_ref(species_ref)
        for name in ("party_size", "party_limit", "current_box_index", "box_capacity"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.party_limit <= 0 or self.party_size > self.party_limit:
            raise ValueError("party size must fit a positive party limit")
        if self.box_capacity <= 0 or not self.box_counts:
            raise ValueError("box storage must expose a positive capacity and at least one box")
        if not 0 <= self.current_box_index < len(self.box_counts):
            raise ValueError("current_box_index must identify a box")
        if any(
            type(count) is not int or not 0 <= count <= self.box_capacity
            for count in self.box_counts
        ):
            raise ValueError("every box count must fit the declared box capacity")
        party_specimens = sum(
            specimen.location is CollectionLocation.PARTY for specimen in self.specimens
        )
        if party_specimens != self.party_size:
            raise ValueError("party_size must equal the number of party specimens")

    @property
    def current_box_has_room(self) -> bool:
        return self.box_counts[self.current_box_index] < self.box_capacity

    @property
    def next_box_with_room(self) -> int | None:
        return next(
            (
                index
                for index, count in enumerate(self.box_counts)
                if index != self.current_box_index and count < self.box_capacity
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class CollectionReport:
    """Auditable progress against one completion contract."""

    target_count: int
    pokedex_owned_count: int
    living_count: int
    level_cap_count: int
    missing_owned: tuple[str, ...]
    missing_living: tuple[str, ...]
    underleveled: tuple[tuple[str, int], ...]

    @property
    def passed(self) -> bool:
        return not self.missing_owned and not self.missing_living and not self.underleveled


class CollectionDirective(StrEnum):
    """One semantic action for the completionist teacher."""

    ACQUIRE_SPECIES = "acquire_species"
    SWITCH_BOX = "switch_box"
    MAKE_STORAGE_ROOM = "make_storage_room"
    ROTATE_FOR_TRAINING = "rotate_for_training"
    TRAIN_SPECIES = "train_species"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class CollectionDecision:
    directive: CollectionDirective
    reason: str
    species_ref: str | None = None
    box_index: int | None = None


def summarize_collection(
    contract: CollectionContract,
    observation: CollectionObservation,
) -> CollectionReport:
    """Compare Pokédex history and living specimens with the declared targets."""

    targets = set(contract.target_species)
    living_levels: dict[str, int] = {}
    for specimen in observation.specimens:
        if specimen.species_ref in targets:
            living_levels[specimen.species_ref] = max(
                specimen.level,
                living_levels.get(specimen.species_ref, 0),
            )
    missing_owned = tuple(
        species for species in contract.target_species if species not in observation.owned_species
    )
    missing_living = tuple(
        species for species in contract.target_species if species not in living_levels
    )
    underleveled = tuple(
        (species, living_levels[species])
        for species in contract.target_species
        if species in living_levels and living_levels[species] < contract.target_level
    )
    return CollectionReport(
        target_count=len(contract.target_species),
        pokedex_owned_count=len(targets & observation.owned_species),
        living_count=len(living_levels),
        level_cap_count=sum(level >= contract.target_level for level in living_levels.values()),
        missing_owned=missing_owned,
        missing_living=missing_living,
        underleveled=underleveled,
    )


def plan_collection(
    contract: CollectionContract,
    observation: CollectionObservation,
) -> CollectionDecision:
    """Select acquisition, storage rotation, or weakest-species training work."""

    report = summarize_collection(contract, observation)
    if report.missing_living:
        species_ref = report.missing_living[0]
        if observation.party_size < observation.party_limit or observation.current_box_has_room:
            verb = "reacquire" if species_ref in observation.owned_species else "acquire"
            return CollectionDecision(
                CollectionDirective.ACQUIRE_SPECIES,
                f"{verb} the first missing living target",
                species_ref=species_ref,
            )
        next_box = observation.next_box_with_room
        if next_box is not None:
            return CollectionDecision(
                CollectionDirective.SWITCH_BOX,
                "the active party and current box are full",
                species_ref=species_ref,
                box_index=next_box,
            )
        return CollectionDecision(
            CollectionDirective.MAKE_STORAGE_ROOM,
            "all living-storage capacity is full",
            species_ref=species_ref,
        )

    if report.underleveled:
        species_ref, level = min(
            report.underleveled,
            key=lambda item: (item[1], contract.target_species.index(item[0])),
        )
        in_party = any(
            specimen.species_ref == species_ref and specimen.location is CollectionLocation.PARTY
            for specimen in observation.specimens
        )
        if not in_party:
            return CollectionDecision(
                CollectionDirective.ROTATE_FOR_TRAINING,
                f"withdraw the weakest target at level {level}",
                species_ref=species_ref,
            )
        return CollectionDecision(
            CollectionDirective.TRAIN_SPECIES,
            f"train the weakest living target from level {level} to {contract.target_level}",
            species_ref=species_ref,
        )

    return CollectionDecision(
        CollectionDirective.STOP,
        f"all {report.target_count} living targets reached level {contract.target_level}",
    )


def _require_species_ref(species_ref: str) -> None:
    if not isinstance(species_ref, str) or not species_ref or ":" not in species_ref:
        raise ValueError("species_ref must be a non-empty namespaced string")
