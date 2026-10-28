"""Bounded route-terminal fishing capture for the registered Red objective.

The strategic model chooses a destination elsewhere.  This module owns only
the deterministic terminal mechanic: cast the selected rod, authenticate the
encounter against cartridge slots, retain a missing registration, or flee.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Protocol

from pokemon_red_completion.fishing import (
    FishingCastExecutor,
    FishingCastOutcome,
    FishingCastResult,
    ShorelineStance,
)
from pokemon_red_completion.gen1_cartridge import RodKind
from pokemon_red_completion.observation import ItemId, PokemonRedStateReader
from pokemon_red_completion.red_acquisition import RedAreaExecutor
from pokemon_red_completion.red_collection import red_species_number, red_species_ref
from pokemon_red_completion.red_fishing_acquisition import RedFishingDestinationOffer


class RedFishingCaptureError(RuntimeError):
    """Fishing capture lost its selected destination or protected collection."""


def ordinary_fishing_capture_items_available(reader: PokemonRedStateReader) -> bool:
    """Observe ordinary balls only; the protected Master Ball is excluded."""
    bag = dict(reader.read().bag_items or ())
    return any(
        bag.get(int(item), 0) > 0
        for item in (
            ItemId.POKE_BALL,
            ItemId.GREAT_BALL,
            ItemId.ULTRA_BALL,
        )
    )


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
    capture_items_exhausted: bool = False
    physical_acquisitions: int = 0

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
            self.physical_acquisitions,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("fishing capture counts must be non-negative integers")
        if (
            self.encounters != self.captures + self.failed_captures + self.flees
            or self.casts != self.encounters + self.no_bites
            or self.new_registrations + self.physical_acquisitions != self.captures
            or self.final_missing_count != self.initial_missing_count - self.captures
            or type(self.search_exhausted) is not bool
            or self.search_exhausted == bool(self.captures)
            or type(self.capture_items_exhausted) is not bool
            or (self.capture_items_exhausted and not self.search_exhausted)
        ):
            raise ValueError("fishing capture report arithmetic differs")

    @property
    def passed(self) -> bool:
        return self.captures > 0 and not self.search_exhausted

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.registered-fishing-capture.v1",
            "status": (
                "succeeded"
                if self.passed
                else "capture_items_exhausted"
                if self.capture_items_exhausted
                else "search_exhausted"
            ),
            "casts": self.casts,
            "encounters": self.encounters,
            "no_bites": self.no_bites,
            "captures": self.captures,
            "failed_captures": self.failed_captures,
            "flees": self.flees,
            "initial_missing_count": self.initial_missing_count,
            "final_missing_count": self.final_missing_count,
            "new_registrations": self.new_registrations,
            "physical_acquisitions": self.physical_acquisitions,
            "search_exhausted": self.search_exhausted,
            "capture_items_exhausted": self.capture_items_exhausted,
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

    def physical_species_count(self, species_number: int) -> int:
        from .red_collection import red_internal_species_id

        internal = red_internal_species_id(species_number)
        raw = self.reader.read()
        boxes = self.reader.read_all_box_states()
        return tuple(raw.party_species_ids or ()).count(internal) + sum(
            tuple(box.species_ids).count(internal) for box in boxes.boxes
        )

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

    def capture_items_available(self) -> bool:
        return ordinary_fishing_capture_items_available(self.reader)


def run_red_fishing_capture(
    offer: RedFishingDestinationOffer,
    port: RedFishingCapturePort,
    *,
    maximum_casts: int,
    capture_items_available: Callable[[], bool] | None = None,
    record_diagnostic_event: Callable[[str, dict[str, object]], None] | None = None,
    observe_diagnostics: Callable[[], dict[str, object]] | None = None,
) -> RedFishingCaptureReport:
    """Try to add exactly one selected-map registration under a hard cast bound."""

    if not isinstance(offer, RedFishingDestinationOffer):
        raise TypeError("fishing capture needs a selected destination offer")
    if type(maximum_casts) is not int or maximum_casts <= 0:
        raise ValueError("maximum_casts must be a positive integer")
    for callback in (record_diagnostic_event, observe_diagnostics):
        if callback is not None and not callable(callback):
            raise TypeError("fishing diagnostics need read-only observers")
    initial = port.registered_species_numbers()
    available = frozenset(slot.species for slot in offer.slots)
    missing = frozenset(offer.missing_species_numbers)
    physical = frozenset(offer.physical_species_numbers)
    if missing.intersection(initial) != physical:
        raise RedFishingCaptureError("selected fishing destination became stale")
    count_stock = getattr(port, "physical_species_count", None)
    if physical and not callable(count_stock):
        raise RedFishingCaptureError("physical fishing demand lacks a stock observer")
    stock = {n: count_stock(n) for n in physical}
    if any(type(n) is not int or n < 0 for n in stock.values()):
        raise RedFishingCaptureError("physical fishing stock is unknown")
    if port.current_map_id() != offer.map_id:
        raise RedFishingCaptureError("fishing capture is not at its selected map")
    if port.encountered_species_number() is not None:
        raise RedFishingCaptureError("fishing capture must start outside battle")

    encounters = no_bites = captures = failed = flees = casts = 0
    items_exhausted = False

    def emit(kind, **payload):
        if record_diagnostic_event is not None:
            row = dict(
                schema="pokemon.red.fishing-diagnostics.v1", diagnostic_only=True,
                selection_authority="deterministic_capture_support", rod="super",
                map_id=offer.map_id, missing_species=sorted(missing),
                physical_species=sorted(physical),
                cartridge_slots=[dict(slot=i, species=s.species, level=s.level)
                                 for i, s in enumerate(offer.slots)],
                slot_order_does_not_imply_equal_weights=True,
                casts=casts, encounters=encounters, no_bites=no_bites,
                captures=captures, failed_captures=failed, flees=flees,
                training_admission=False, **payload,
            )
            if observe_diagnostics is not None:
                row["state"] = observe_diagnostics()
            record_diagnostic_event(kind, row)

    for cast_number in range(1, maximum_casts + 1):
        before = port.registered_species_numbers()
        if before != initial or port.current_map_id() != offer.map_id:
            raise RedFishingCaptureError("registration changed between fishing casts")
        if any(count_stock(n) != count for n, count in stock.items()):
            raise RedFishingCaptureError("physical fishing demand changed between casts")
        if capture_items_available is not None:
            available_items = capture_items_available()
            if type(available_items) is not bool:
                raise RedFishingCaptureError("capture inventory returned an unknown result")
            if not available_items:
                items_exhausted = True
                break
        before_diagnostics = None if observe_diagnostics is None else observe_diagnostics()
        started = monotonic()
        try:
            result = port.cast()
        except BaseException as error:
            emit("fishing_cast_failed", cast_attempt=cast_number,
                 before=before_diagnostics, error_type=type(error).__name__)
            raise
        if not isinstance(result, FishingCastResult):
            raise RedFishingCaptureError("fishing cast returned an invalid receipt")
        casts = cast_number
        encountered = port.encountered_species_number()
        emit("fishing_cast_observed", cast_attempt=cast_number,
             before=before_diagnostics, elapsed_seconds=monotonic() - started,
             outcome=result.outcome.value, encountered_species=encountered,
             selected_target_seen=encountered in missing if encountered is not None else False)
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
            if any(count_stock(n) != count + int(n == encountered)
                   for n, count in stock.items()):
                raise RedFishingCaptureError("successful fishing capture lacks exact physical stock")
            captures += 1
            emit("fishing_capture_verified", encountered_species=encountered,
                 physical_stock_before=stock.get(encountered),
                 new_registration=encountered not in physical)
            return RedFishingCaptureReport(
                cast_number,
                encounters,
                no_bites,
                captures,
                failed,
                flees,
                len(missing),
                len(missing) - 1,
                int(encountered not in physical),
                False,
                physical_acquisitions=int(encountered in physical),
            )
        if after != before:
            raise RedFishingCaptureError("failed fishing capture changed registration")
        if any(count_stock(n) != count for n, count in stock.items()):
            raise RedFishingCaptureError("failed fishing capture changed physical stock")
        failed += 1
        emit("fishing_capture_not_retained", encountered_species=encountered)

    emit("fishing_search_stopped", reason=(
        "capture_items_exhausted" if items_exhausted else "cast_limit"
    ))
    return RedFishingCaptureReport(
        casts,
        encounters,
        no_bites,
        captures,
        failed,
        flees,
        len(missing),
        len(missing),
        0,
        True,
        items_exhausted,
    )
