"""Full 151-entry Red registration inventory and dependency classification.

The historical Red acquisition catalog intentionally covers one 124-entry,
single-save route.  That catalog remains useful plannable catalog machinery, but it is
not the product completion denominator.  This module layers the complete
Generation I target above it without turning shared credit or physical stock
into local Red Pokédex flags.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from .collection import CollectionExclusionReason
from .red_acquisition import RED_ACQUISITION_CATALOG
from .red_collection import (
    NATIONAL_DEX_SIZE_GENERATION_ONE,
    RED_SOLO_COLLECTION_CONTRACT,
    red_species_number,
    red_species_ref,
)


class RedFullPokedexResolutionKind(StrEnum):
    """The declared path that can produce one local Red registration."""

    SOLO_CATALOG_PLAN = "solo_catalog_plan"
    VERSION_TRADE = "version_trade"
    LINK_TRADE = "link_trade"
    SUPPORTING_SAVE_TRADE = "supporting_save_trade"
    LEGITIMATE_EVENT_INPUT = "legitimate_event_input"
    UNSUPPORTED = "unsupported"


class RedFullPokedexCapability(StrEnum):
    """External or local capability required by a declared resolution path."""

    RED_SOLO_CATALOG_PLAN = "red_solo_catalog_plan"
    PAIRED_BLUE_SAVE = "paired_blue_save"
    SUPPORTING_RED_SAVE = "supporting_red_save"
    LINK_TRADE = "link_trade"
    LEGITIMATE_EVENT_INPUT = "legitimate_event_input"


@dataclass(frozen=True, slots=True)
class RedFullPokedexTargetInventory:
    """One species' local state, independent annotations, and resolution path."""

    national_dex_number: int
    species_ref: str
    locally_registered: bool
    shared_registered: bool
    physical_specimen_present: bool
    resolution_kind: RedFullPokedexResolutionKind
    required_capabilities: tuple[RedFullPokedexCapability, ...]
    solo_acquisition_kind: str | None = None
    solo_source_id: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.national_dex_number) is not int
            or not 1 <= self.national_dex_number <= NATIONAL_DEX_SIZE_GENERATION_ONE
            or self.species_ref != red_species_ref(self.national_dex_number)
        ):
            raise ValueError("full Red target identity differs")
        for name in (
            "locally_registered",
            "shared_registered",
            "physical_specimen_present",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be boolean")
        if not isinstance(self.resolution_kind, RedFullPokedexResolutionKind):
            raise TypeError("resolution_kind must be a RedFullPokedexResolutionKind")
        if (
            len(self.required_capabilities) != len(set(self.required_capabilities))
            or any(
                not isinstance(item, RedFullPokedexCapability)
                for item in self.required_capabilities
            )
        ):
            raise ValueError("full Red required capabilities differ")
        has_solo_method = (
            self.solo_acquisition_kind is not None and self.solo_source_id is not None
        )
        if (self.solo_acquisition_kind is None) != (self.solo_source_id is None):
            raise ValueError("full Red solo acquisition binding is partial")
        if (
            self.resolution_kind is RedFullPokedexResolutionKind.SOLO_CATALOG_PLAN
        ) != has_solo_method:
            raise ValueError("full Red solo acquisition binding differs")

    @property
    def status(self) -> str:
        """Local completion state; other views never override it."""

        return (
            "locally_registered"
            if self.locally_registered
            else self.resolution_kind.value
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "national_dex_number": self.national_dex_number,
            "species_ref": self.species_ref,
            "status": self.status,
            "locally_registered": self.locally_registered,
            "shared_registered": self.shared_registered,
            "physical_specimen_present": self.physical_specimen_present,
            "resolution_kind": self.resolution_kind.value,
            "required_capabilities": [item.value for item in self.required_capabilities],
            "solo_acquisition_kind": self.solo_acquisition_kind,
            "solo_source_id": self.solo_source_id,
        }


@dataclass(frozen=True, slots=True)
class RedFullPokedexInventory:
    """All 151 Red targets, with completion and dependency views kept separate."""

    targets: tuple[RedFullPokedexTargetInventory, ...]

    def __post_init__(self) -> None:
        expected = tuple(range(1, NATIONAL_DEX_SIZE_GENERATION_ONE + 1))
        if tuple(item.national_dex_number for item in self.targets) != expected:
            raise ValueError("full Red inventory must contain ordered targets 1 through 151")

    @property
    def local_registered_count(self) -> int:
        return sum(item.locally_registered for item in self.targets)

    @property
    def missing_local_count(self) -> int:
        return len(self.targets) - self.local_registered_count

    @property
    def full_local_registration_complete(self) -> bool:
        return self.missing_local_count == 0

    def target(self, national_dex_number: int) -> RedFullPokedexTargetInventory:
        if type(national_dex_number) is not int or not 1 <= national_dex_number <= len(
            self.targets
        ):
            raise ValueError("national_dex_number must be between 1 and 151")
        return self.targets[national_dex_number - 1]

    def status_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(item.status for item in self.targets).items()))

    def missing_resolution_counts(self) -> dict[str, int]:
        return dict(
            sorted(
                Counter(
                    item.resolution_kind.value
                    for item in self.targets
                    if not item.locally_registered
                ).items()
            )
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.full-pokedex-inventory.v1",
            "target_count": len(self.targets),
            "local_registered_count": self.local_registered_count,
            "missing_local_count": self.missing_local_count,
            "full_local_registration_complete": self.full_local_registration_complete,
            "status_counts": self.status_counts(),
            "missing_resolution_counts": self.missing_resolution_counts(),
            "targets": [item.public_dict() for item in self.targets],
        }


_SECOND_SAVE_REASONS = frozenset(
    {
        CollectionExclusionReason.ALTERNATE_STARTER,
        CollectionExclusionReason.ALTERNATE_FOSSIL,
        CollectionExclusionReason.ALTERNATE_DOJO_GIFT,
        CollectionExclusionReason.ALTERNATE_BRANCH_EVOLUTION,
    }
)


def _dependency_for_exclusion(
    reason: CollectionExclusionReason,
) -> tuple[RedFullPokedexResolutionKind, tuple[RedFullPokedexCapability, ...]]:
    if reason is CollectionExclusionReason.VERSION_EXCLUSIVE:
        return (
            RedFullPokedexResolutionKind.VERSION_TRADE,
            (
                RedFullPokedexCapability.PAIRED_BLUE_SAVE,
                RedFullPokedexCapability.LINK_TRADE,
            ),
        )
    if reason is CollectionExclusionReason.LINK_TRADE_REQUIRED:
        return (
            RedFullPokedexResolutionKind.LINK_TRADE,
            (RedFullPokedexCapability.LINK_TRADE,),
        )
    if reason in _SECOND_SAVE_REASONS:
        return (
            RedFullPokedexResolutionKind.SUPPORTING_SAVE_TRADE,
            (
                RedFullPokedexCapability.SUPPORTING_RED_SAVE,
                RedFullPokedexCapability.LINK_TRADE,
            ),
        )
    if reason is CollectionExclusionReason.EVENT_ONLY:
        return (
            RedFullPokedexResolutionKind.LEGITIMATE_EVENT_INPUT,
            (RedFullPokedexCapability.LEGITIMATE_EVENT_INPUT,),
        )
    return RedFullPokedexResolutionKind.UNSUPPORTED, ()


def build_red_full_pokedex_inventory(
    local_owned_numbers: frozenset[int],
    *,
    shared_registered_numbers: frozenset[int] = frozenset(),
    physical_specimen_numbers: frozenset[int] = frozenset(),
) -> RedFullPokedexInventory:
    """Classify every Red target without granting local credit from other views."""

    for name, numbers in (
        ("local_owned_numbers", local_owned_numbers),
        ("shared_registered_numbers", shared_registered_numbers),
        ("physical_specimen_numbers", physical_specimen_numbers),
    ):
        if not isinstance(numbers, frozenset) or any(
            type(number) is not int
            or not 1 <= number <= NATIONAL_DEX_SIZE_GENERATION_ONE
            for number in numbers
        ):
            raise ValueError(f"{name} must contain Red National Pokédex numbers")

    solo_methods = {
        red_species_number(method.species_ref): method
        for method in RED_ACQUISITION_CATALOG.methods
    }
    exclusions = {
        red_species_number(item.species_ref): item.reason
        for item in RED_SOLO_COLLECTION_CONTRACT.exclusions
    }
    targets: list[RedFullPokedexTargetInventory] = []
    for number in range(1, NATIONAL_DEX_SIZE_GENERATION_ONE + 1):
        method = solo_methods.get(number)
        capabilities: tuple[RedFullPokedexCapability, ...]
        if method is not None:
            resolution = RedFullPokedexResolutionKind.SOLO_CATALOG_PLAN
            capabilities = (RedFullPokedexCapability.RED_SOLO_CATALOG_PLAN,)
            method_kind = method.kind.value
            source_id = method.source_id
        else:
            resolution, capabilities = _dependency_for_exclusion(exclusions[number])
            method_kind = None
            source_id = None
        targets.append(
            RedFullPokedexTargetInventory(
                national_dex_number=number,
                species_ref=red_species_ref(number),
                locally_registered=number in local_owned_numbers,
                shared_registered=number in shared_registered_numbers,
                physical_specimen_present=number in physical_specimen_numbers,
                resolution_kind=resolution,
                required_capabilities=capabilities,
                solo_acquisition_kind=method_kind,
                solo_source_id=source_id,
            )
        )
    return RedFullPokedexInventory(tuple(targets))


__all__ = [
    "RedFullPokedexCapability",
    "RedFullPokedexInventory",
    "RedFullPokedexResolutionKind",
    "RedFullPokedexTargetInventory",
    "build_red_full_pokedex_inventory",
]
