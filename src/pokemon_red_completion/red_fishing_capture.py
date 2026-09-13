"""Bounded route-terminal fishing capture for the registered Red objective.

The strategic model chooses a destination elsewhere.  This module owns only
the deterministic terminal mechanic: cast the selected rod, authenticate the
encounter against cartridge slots, retain a missing registration, or flee.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.fishing import (
    FishingCastExecutor,
    FishingCastOutcome,
    FishingCastResult,
    ShorelineStance,
)
from pokemon_red_completion.gen1_cartridge import RodKind
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.red_acquisition import RedAreaExecutor
from pokemon_red_completion.red_collection import red_species_number, red_species_ref
from pokemon_red_completion.red_fishing_acquisition import RedFishingDestinationOffer


class RedFishingCaptureError(RuntimeError):
    """Fishing capture lost its selected destination or protected collection."""


class RedFishingCapturePort(Protocol):
    """Minimal adapter needed by the portable bounded fishing survey."""

    def registered_species_numbers(self) -> frozenset[int]: ...

    def current_map_id(self) -> int: ...

    def cast(self) -> FishingCastResult: ...

    def encountered_species_number(self) -> int | None: ...

    def capture_encounter(self, species_number: int) -> bool: ...

    def flee_encounter(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RedFishingCaptureReport:
    casts: int
    encounters: int
    no_bites: int
    captures: int
    failed_captures: int
    flees: int
    initial_missing_count: int
    final_missing_count: int
    new_registrations: int
    search_exhausted: bool

    def __post_init__(self) -> None:
        values = (
            self.casts,
            self.encounters,
            self.no_bites,
            self.captures,
            self.failed_captures,
            self.flees,
            self.initial_missing_count,
            self.final_missing_count,
            self.new_registrations,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("fishing capture counts must be non-negative integers")
        if (
            self.encounters != self.captures + self.failed_captures + self.flees
            or self.casts != self.encounters + self.no_bites
            or self.new_registrations != self.captures
            or self.final_missing_count
            != self.initial_missing_count - self.new_registrations
            or type(self.search_exhausted) is not bool
            or self.search_exhausted == bool(self.new_registrations)
        ):
            raise ValueError("fishing capture report arithmetic differs")

    @property
    def passed(self) -> bool:
        return self.new_registrations > 0 and not self.search_exhausted

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.registered-fishing-capture.v1",
            "status": "succeeded" if self.passed else "search_exhausted",
            "casts": self.casts,
            "encounters": self.encounters,
            "no_bites": self.no_bites,
            "captures": self.captures,
            "failed_captures": self.failed_captures,
            "flees": self.flees,
            "initial_missing_count": self.initial_missing_count,
            "final_missing_count": self.final_missing_count,
            "new_registrations": self.new_registrations,
            "search_exhausted": self.search_exhausted,
            "private_map_fields": 0,
            "private_species_fields": 0,
            "raw_teacher_direction_steps": 0,
            "teacher_labels": 0,
        }


@dataclass(slots=True)
class LiveRedFishingCapturePort:
    """Join one existing controller to the cast and wild-capture mechanics."""

    caster: FishingCastExecutor
    encounters: RedAreaExecutor
    reader: PokemonRedStateReader
    stance: ShorelineStance

    def registered_species_numbers(self) -> frozenset[int]:
        return frozenset(self.reader.read_pokedex_state().owned_species)

    def current_map_id(self) -> int:
        map_id = self.reader.read().map_id
        if type(map_id) is not int:
            raise RedFishingCaptureError("live fishing capture lacks a map identity")
        return map_id

    def cast(self) -> FishingCastResult:
        return self.caster.execute(self.stance, rod=RodKind.SUPER)

    def encountered_species_number(self) -> int | None:
        species_ref = self.encounters.encountered_species_ref()
        return None if species_ref is None else red_species_number(species_ref)

    def capture_encounter(self, species_number: int) -> bool:
        result = self.encounters.capture_encounter(red_species_ref(species_number))
        if type(result) is not bool:
            raise RedFishingCaptureError("wild capture returned an unknown result")
        return result

    def flee_encounter(self) -> None:
        self.encounters.flee_encounter()


def run_red_fishing_capture(
    offer: RedFishingDestinationOffer,
    port: RedFishingCapturePort,
    *,
    maximum_casts: int,
) -> RedFishingCaptureReport:
    """Try to add exactly one selected-map registration under a hard cast bound."""

    if not isinstance(offer, RedFishingDestinationOffer):
        raise TypeError("fishing capture needs a selected destination offer")
    if type(maximum_casts) is not int or maximum_casts <= 0:
        raise ValueError("maximum_casts must be a positive integer")
    initial = port.registered_species_numbers()
    available = frozenset(slot.species for slot in offer.slots)
    missing = frozenset(offer.missing_species_numbers)
    if missing.intersection(initial):
        raise RedFishingCaptureError("selected fishing destination became stale")
    if port.current_map_id() != offer.map_id:
        raise RedFishingCaptureError("fishing capture is not at its selected map")
    if port.encountered_species_number() is not None:
        raise RedFishingCaptureError("fishing capture must start outside battle")

    encounters = no_bites = captures = failed = flees = 0
    for cast_number in range(1, maximum_casts + 1):
        before = port.registered_species_numbers()
        if before != initial or port.current_map_id() != offer.map_id:
            raise RedFishingCaptureError("registration changed between fishing casts")
        result = port.cast()
        if not isinstance(result, FishingCastResult):
            raise RedFishingCaptureError("fishing cast returned an invalid receipt")
        encountered = port.encountered_species_number()
        if port.current_map_id() != offer.map_id:
            raise RedFishingCaptureError("fishing cast left its selected map")
        if result.rod_kind is not RodKind.SUPER:
            raise RedFishingCaptureError("selected fishing capture used another rod")
        if result.outcome is FishingCastOutcome.NO_BITE:
            no_bites += 1
            if encountered is not None or port.registered_species_numbers() != before:
                raise RedFishingCaptureError("no-bite cast changed encounter or registration")
            continue
        if result.outcome is not FishingCastOutcome.WILD_ENCOUNTER:
            raise RedFishingCaptureError("fishing cast returned an unsupported outcome")
        encounters += 1
        if encountered is None or encountered not in available:
            raise RedFishingCaptureError("fishing encounter differs from cartridge slots")
        if encountered not in missing:
            port.flee_encounter()
            flees += 1
            if (
                port.encountered_species_number() is not None
                or port.registered_species_numbers() != before
            ):
                raise RedFishingCaptureError("fishing flee changed protected collection")
            continue

        caught = port.capture_encounter(encountered)
        after = port.registered_species_numbers()
        if port.encountered_species_number() is not None:
            raise RedFishingCaptureError("fishing capture did not settle its battle")
        if caught:
            if after != before | {encountered}:
                raise RedFishingCaptureError(
                    "successful fishing capture did not add exactly its registration"
                )
            captures += 1
            return RedFishingCaptureReport(
                cast_number,
                encounters,
                no_bites,
                captures,
                failed,
                flees,
                len(missing),
                len(missing) - 1,
                1,
                False,
            )
        if after != before:
            raise RedFishingCaptureError("failed fishing capture changed registration")
        failed += 1

    return RedFishingCaptureReport(
        maximum_casts,
        encounters,
        no_bites,
        captures,
        failed,
        flees,
        len(missing),
        len(missing),
        0,
        True,
    )
