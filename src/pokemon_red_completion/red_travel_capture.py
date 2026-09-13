"""Bounded registered-species capture at an actual wild travel interruption.

This is mechanics support, not a learned encounter policy or destination change.
The caller retains its route and all real costs. No exception triggers a retry.
Initial scope is a full party with room in the active box; existing party members
cannot be replaced by the catch. Integration must preserve historical profiles.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Protocol

from .collection import CollectionLocation, CollectionObservation
from .observation import ItemId, MapId, PokemonRedStateReader, RawGameState
from .red_capture_access import is_unidentified_ghost_encounter
from .red_collection import red_internal_species_number, red_species_ref
from .route_executor import (
    InterruptionHandler,
    InterruptionReceipt,
    RouteExecutionError,
    RouteExecutionFailureReason,
    TraversalSnapshot,
)


class TravelCapturePort(Protocol):
    def read_collection(self) -> CollectionObservation: ...

    def capture_encounter(self, species_ref: str) -> bool: ...


class RedTravelCaptureError(RouteExecutionError):
    """A travel capture cannot truthfully preserve its route or collection."""

    def __init__(self, message: str) -> None:
        super().__init__(message, reason=RouteExecutionFailureReason.INTERRUPTION_UNRECOVERED)


def _balls(raw: RawGameState) -> int:
    inventory = dict(raw.bag_items or ())
    return sum(
        inventory.get(int(item), 0)
        for item in (
            ItemId.POKE_BALL,
            ItemId.GREAT_BALL,
            ItemId.ULTRA_BALL,
        )
    )


def _inventory_preserved(before: RawGameState, after: RawGameState) -> bool:
    """Only ordinary balls may decrease; no replacement of one ball by another."""
    ordinary = {int(ItemId.POKE_BALL), int(ItemId.GREAT_BALL), int(ItemId.ULTRA_BALL)}
    old, new = dict(before.bag_items or ()), dict(after.bag_items or ())
    return all(
        0 <= new.get(item, 0) <= old.get(item, 0)
        if item in ordinary
        else new.get(item, 0) == old.get(item, 0)
        for item in old.keys() | new.keys()
    )


@dataclass(slots=True)
class RegisteredTravelCaptureHandler:
    """Attempt at most one supported missing-species catch, then resume exactly.

    Eligibility depends on a fresh wild encounter, the frozen run's registration
    view and cartridge-derived ordinary encounters. Trainer/special encounters
    retain the existing fallback. A capture controller error is never converted
    to a harmless flee. The capture port must itself enforce input/frame bounds.
    """

    reader: PokemonRedStateReader
    capture: TravelCapturePort
    fallback: InterruptionHandler
    registered: Callable[[CollectionObservation], frozenset[str]]
    targets: frozenset[str]
    ordinary_species: Mapping[int, frozenset[str]]
    frame_count: Callable[[], int]
    action_count: Callable[[], int]
    maximum_capture_actions: int = 512
    maximum_capture_frames: int = 120_000
    attempted: bool = field(default=False, init=False)
    receipts: list[dict[str, object]] = field(default_factory=list, init=False)
    verified_collection: CollectionObservation | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        for value in (self.maximum_capture_actions, self.maximum_capture_frames):
            if type(value) is not int or value <= 0:
                raise ValueError("travel capture bounds must be positive integers")
        self.targets = frozenset(self.targets)
        self.ordinary_species = {k: frozenset(v) for k, v in self.ordinary_species.items()}

    @property
    def handled_hazard_kinds(self) -> frozenset[str]:
        return frozenset(getattr(self.fallback, "handled_hazard_kinds", ()))

    @property
    def handled_interruption_kinds(self) -> frozenset[str]:
        return frozenset(getattr(self.fallback, "handled_interruption_kinds", ()))

    def handle(self, interruption: TraversalSnapshot) -> InterruptionReceipt:
        if self.attempted and not self.receipts:
            raise RedTravelCaptureError("incomplete capture cannot resume or fall back")
        if interruption.interruption != "wild_battle":
            return self.fallback.handle(interruption)
        entry_counts = self.action_count(), self.frame_count()

        def unchanged() -> None:
            if (self.action_count(), self.frame_count()) != entry_counts:
                raise RedTravelCaptureError("travel capture eligibility dispatched input")

        def delegate() -> InterruptionReceipt:
            unchanged()
            return self.fallback.handle(interruption)

        raw = self.reader.read()
        if (
            raw.battle_state != 1
            or raw.map_id != interruption.map_id
            or (raw.player_y, raw.player_x) != interruption.at
        ):
            raise RedTravelCaptureError("wild travel boundary changed before capture")
        if (
            self.attempted
            or is_unidentified_ghost_encounter(raw)
            or int(MapId.SAFARI_ZONE_EAST) <= interruption.map_id <= int(MapId.SAFARI_ZONE_CENTER)
        ):
            return delegate()
        if raw.enemy_species_id is None:
            raise RedTravelCaptureError("wild travel encounter lacks species")
        try:
            species = red_species_ref(red_internal_species_number(raw.enemy_species_id))
        except ValueError as error:
            raise RedTravelCaptureError("wild travel encounter has invalid species") from error
        before = self.capture.read_collection()
        initial_registered = self.registered(before)
        if (
            species not in self.targets
            or species in initial_registered
            or species not in self.ordinary_species.get(interruption.map_id, frozenset())
            or before.party_size != before.party_limit
            or not before.current_box_has_room
            or _balls(raw) <= 0
        ):
            return delegate()
        party = tuple(raw.party_species_ids or ())
        hp = tuple(raw.party_hp or ())
        status = tuple(raw.party_status or ())
        if (
            raw.party_count != before.party_size
            or len(party) != before.party_size
            or len(hp) != before.party_size
            or any(value <= 0 for value in hp)
            or len(status) != before.party_size
            or any(status)
        ):
            raise RedTravelCaptureError("travel capture requires an intact healthy party")
        # Read-only eligibility must not secretly alter the encounter before input.
        if self.reader.read() != raw or self.capture.read_collection() != before:
            raise RedTravelCaptureError("travel capture eligibility became stale")
        unchanged()
        self.attempted = True
        actions, frames = self.action_count(), self.frame_count()
        try:
            caught = self.capture.capture_encounter(species)
        except Exception as error:
            # Route execution attaches its partial trace to this typed failure.
            # Keep the original cause, but never dispatch a flee or retry here.
            raise RedTravelCaptureError("travel capture controller failed") from error
        used_actions = self.action_count() - actions
        used_frames = self.frame_count() - frames
        if (
            type(caught) is not bool
            or not 0 < used_actions <= self.maximum_capture_actions
            or not 0 < used_frames <= self.maximum_capture_frames
        ):
            raise RedTravelCaptureError("travel capture result or budget differs")
        final = self.reader.read()
        after = self.capture.read_collection()
        if (
            final.battle_state != 0
            or not self.reader.read_input_readiness().ready
            or final.map_id != interruption.map_id
            or (final.player_y, final.player_x) != interruption.at
            or tuple(final.party_species_ids or ()) != party
            or final.party_count != raw.party_count
            or len(final.party_hp or ()) != len(hp)
            or any(value <= 0 for value in final.party_hp or ())
            or tuple(final.party_status or ()) != status
        ):
            raise RedTravelCaptureError("travel capture cannot safely resume its boundary")
        # Red prepends a catch to the active box. Every prior active-box slot
        # shifts by one; comparing unshifted identities misreports stock loss.
        old_stock = Counter(
            replace(item, slot_index=item.slot_index + int(caught))
            if item.location is CollectionLocation.BOX
            and item.container_index == before.current_box_index else item
            for item in before.specimens
        )
        new_stock = Counter(after.specimens)
        added = list((new_stock - old_stock).elements())
        expected_boxes = list(before.box_counts)
        expected_boxes[before.current_box_index] += int(caught)
        if (
            old_stock - new_stock
            or after.current_box_index != before.current_box_index
            or after.party_size != before.party_size
            or len(added) != int(caught)
            or any(
                item.species_ref != species
                or item.location is not CollectionLocation.BOX
                or item.container_index != before.current_box_index
                or item.slot_index != 0
                or item.level != raw.enemy_level
                for item in added
            )
            or tuple(expected_boxes) != after.box_counts
            or after.owned_species != before.owned_species | ({species} if caught else set())
            or self.registered(after) != initial_registered | ({species} if caught else set())
            or final.player_money != raw.player_money
            or not _inventory_preserved(raw, final)
            or not 0 <= _balls(final) <= _balls(raw) - int(caught)
        ):
            raise RedTravelCaptureError("travel capture collection or ball delta differs")
        detail: dict[str, object] = {
            "schema": "pokemon.red.registered-travel-capture.v1",
            "species_ref": species,
            "captured": caught,
            "new_registrations": int(caught),
            "actions": used_actions,
            "frames": used_frames,
            "balls_spent": _balls(raw) - _balls(final),
            "route_boundary_preserved": True,
            "destination_changed": False,
            "learned_encounter_choice": False,
        }
        self.verified_collection = after
        self.receipts.append(detail)
        return InterruptionReceipt(
            kind="wild_battle",
            resumed_map=interruption.map_id,
            resumed_at=interruption.at,
            details=detail,
        )
