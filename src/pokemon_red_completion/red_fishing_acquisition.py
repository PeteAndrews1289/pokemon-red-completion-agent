"""Cartridge-derived fishing destinations for model-directed Red collection."""

from __future__ import annotations

import math
import random
from collections.abc import Collection
from dataclasses import dataclass

from pokemon_red_completion.gen1_cartridge import (
    FishingSlot,
    RodKind,
    fishing_tables,
)
from pokemon_red_completion.living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOptionValueModel,
)
from pokemon_red_completion.red_collection import (
    RED_SOLO_COLLECTION_CONTRACT,
    red_species_number,
)

FISHING_DESTINATION_POLICY = "living-dex-fishing-destination-softmax-v1"


@dataclass(frozen=True, slots=True)
class RedFishingDestinationOffer:
    """Private map binding paired with an identity-free policy description."""

    source_ref: str
    map_id: int
    slots: tuple[FishingSlot, ...]
    missing_species_numbers: tuple[int, ...]

    def __post_init__(self) -> None:
        if (
            not self.source_ref.startswith("fishing-map-private-")
            or type(self.map_id) is not int
            or not 0 <= self.map_id <= 0xFF
            or not self.slots
            or any(slot.rod is not RodKind.SUPER for slot in self.slots)
        ):
            raise ValueError("Red fishing destination binding differs")
        available = {slot.species for slot in self.slots}
        if (
            not self.missing_species_numbers
            or self.missing_species_numbers
            != tuple(sorted(set(self.missing_species_numbers)))
            or not set(self.missing_species_numbers) <= available
        ):
            raise ValueError("Red fishing destination lacks distinct missing species")

    @property
    def productive_slot_count(self) -> int:
        missing = set(self.missing_species_numbers)
        return sum(slot.species in missing for slot in self.slots)

    def policy_features(self) -> dict[str, int]:
        return {
            "encounter_slot_count": len(self.slots),
            "missing_species_count": len(self.missing_species_numbers),
            "productive_slot_count": self.productive_slot_count,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "cartridge_derived": True,
            "feature_values": self.policy_features(),
            "private_map_fields": 0,
            "private_species_fields": 0,
            "private_source_fields": 0,
            "raw_teacher_direction_steps": 0,
        }


def red_super_rod_destination_offers(
    rom: bytes,
    registered_species_numbers: Collection[int],
) -> tuple[RedFishingDestinationOffer, ...]:
    """Return productive Super Rod map families from cartridge data and credit."""

    if not isinstance(rom, bytes):
        raise TypeError("Red fishing inventory needs immutable cartridge bytes")
    registered = frozenset(registered_species_numbers)
    if any(type(number) is not int or not 1 <= number <= 151 for number in registered):
        raise ValueError("registered fishing credit must contain Pokédex numbers")
    targets = {
        red_species_number(reference)
        for reference in RED_SOLO_COLLECTION_CONTRACT.target_species
    }
    offers = []
    for map_id, slots in sorted(fishing_tables(rom).by_map.items()):
        missing = tuple(
            sorted({slot.species for slot in slots} & targets - registered)
        )
        if missing:
            offers.append(
                RedFishingDestinationOffer(
                    f"fishing-map-private-{map_id}",
                    map_id,
                    tuple(slots),
                    missing,
                )
            )
    return tuple(offers)


def red_fishing_destination_menu(
    context: LivingDexOptionContext,
    offers: tuple[RedFishingDestinationOffer, ...],
    *,
    route_steps: tuple[int, ...],
    maximum_route_steps: int,
    free_storage_slots: int,
) -> LivingDexOptionMenu:
    """Project executable fishing maps into the shared option-value vocabulary."""

    if (
        len(offers) < 2
        or len(offers) != len(route_steps)
        or len({offer.source_ref for offer in offers}) != len(offers)
    ):
        raise ValueError("fishing learning needs distinct executable destinations")
    if type(maximum_route_steps) is not int or maximum_route_steps <= 0:
        raise ValueError("fishing route bound must be positive")
    if any(
        type(value) is not int or not 0 <= value <= maximum_route_steps
        for value in route_steps
    ):
        raise ValueError("fishing route steps exceed their bound")
    if type(free_storage_slots) is not int or free_storage_slots <= 0:
        raise ValueError("fishing destination menu needs immediate storage")
    candidates = tuple(
        LivingDexOptionCandidate(
            binding_ref=f"fishing-destination-private-{index}",
            features=LivingDexOptionFeatures(
                kind=LivingDexOptionKind.ACQUIRE,
                completion_gain=min(
                    1.0, len(offer.missing_species_numbers) / 7.0
                ),
                dependency_unlock_gain=0.0,
                travel_effort=route_steps[index] / maximum_route_steps,
                execution_effort=1.0
                - offer.productive_slot_count / len(offer.slots),
                resource_cost=0.0,
                storage_cost=min(1.0, 1.0 / free_storage_slots),
                party_risk=0.0,
                irreversibility_risk=0.0,
                uncertainty=1.0
                - offer.productive_slot_count / len(offer.slots),
            ),
            availability=LivingDexOptionAvailability.AVAILABLE,
        )
        for index, offer in enumerate(offers)
    )
    menu = LivingDexOptionMenu(context, candidates)
    if len({menu.candidate_vector(index) for index in menu.available_indices}) < 2:
        raise ValueError("fishing destinations have no distinguishable semantic features")
    return menu


@dataclass(frozen=True, slots=True)
class RedFishingDestinationChoice:
    menu: LivingDexOptionMenu
    offers: tuple[RedFishingDestinationOffer, ...]
    selected_candidate_index: int
    scores: tuple[float | None, ...]
    probabilities: tuple[float, ...]
    seed: int
    model_sha256: str

    def __post_init__(self) -> None:
        if (
            len(self.offers) != len(self.menu.candidates)
            or len(self.scores) != len(self.offers)
            or len(self.probabilities) != len(self.offers)
            or self.selected_candidate_index not in self.menu.available_indices
            or type(self.seed) is not int
            or self.seed < 0
            or not math.isclose(sum(self.probabilities), 1.0)
        ):
            raise ValueError("fishing choice does not match its policy menu")

    @property
    def selected_offer(self) -> RedFishingDestinationOffer:
        return self.offers[self.selected_candidate_index]

    def public_dict(self) -> dict[str, object]:
        return {
            "policy_id": FISHING_DESTINATION_POLICY,
            "candidate_count": len(self.offers),
            "menu_sha256": self.menu.policy_sha256,
            "model_sha256": self.model_sha256,
            "seed": self.seed,
            "scores": list(self.scores),
            "probabilities": list(self.probabilities),
            "selected_candidate_index": self.selected_candidate_index,
            "private_map_fields": 0,
            "private_species_fields": 0,
            "private_source_fields": 0,
            "teacher_labels": 0,
        }


def select_red_fishing_destination(
    model: LivingDexOptionValueModel,
    menu: LivingDexOptionMenu,
    offers: tuple[RedFishingDestinationOffer, ...],
    *,
    seed: int,
) -> RedFishingDestinationChoice:
    """Sample one fishing destination using the existing registered-goal model."""

    if type(seed) is not int or seed < 0 or model.feature_version < menu.feature_version:
        raise ValueError("fishing selection seed or model feature version differs")
    if len(offers) != len(menu.candidates):
        raise ValueError("fishing offers differ from their policy menu")
    scores = model.scores(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY)
    utilities = [scores[index] for index in menu.available_indices]
    if any(value is None or not math.isfinite(value) for value in utilities):
        raise ValueError("fishing model returned invalid scores")
    concrete = [float(value) for value in utilities if value is not None]
    peak = max(concrete)
    exponentials = [math.exp(value - peak) for value in concrete]
    total = sum(exponentials)
    probabilities = [0.0] * len(offers)
    for index, value in zip(menu.available_indices, exponentials, strict=True):
        probabilities[index] = 0.75 * value / total + 0.25 / len(exponentials)
    selected = random.Random(seed).choices(
        range(len(probabilities)), weights=probabilities, k=1
    )[0]
    return RedFishingDestinationChoice(
        menu,
        offers,
        selected,
        tuple(scores),
        tuple(probabilities),
        seed,
        model.model_sha256,
    )
