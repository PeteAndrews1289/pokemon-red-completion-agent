"""Cartridge-derived Safari acquisition offers and bounded battle mechanics.

The strategic policy chooses a Safari *area*.  It never receives species IDs,
map IDs, encounter slots, or controller directions as model features.  This
module keeps those private bindings beside a deterministic mechanic that can
throw Safari Balls, distinguish a retained capture from a flee, and stop under
hard encounter and throw bounds.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.collection import CollectionObservation
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.fly_resource import EmulatorState
from pokemon_red_completion.gen1_cartridge import internal_to_dex, wild_tables
from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort
from pokemon_red_completion.gen1_terrain import Terrain
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
from pokemon_red_completion.local_router import (
    Coordinate,
    LocalGraph,
    LocalRouterError,
    find_local_path,
    without_coordinates,
)
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    MapId,
    PokemonRedStateReader,
    RamAddress,
)
from pokemon_red_completion.red_acquisition import RedAreaExecutionError
from pokemon_red_completion.red_collection import (
    RED_SOLO_COLLECTION_CONTRACT,
    red_collection_observation,
    red_internal_species_number,
    red_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.safari import (
    CENTER_TO_EAST,
    CENTER_TO_GATE,
    DEFAULT_SAFARI_TIMING,
    EAST_TO_NORTH,
    SafariTiming,
    _balls,
    _money,
    _move,
    _pulse,
    _steps,
)

SAFARI_ZONE_SOURCES: tuple[tuple[str, MapId], ...] = (
    ("wild:SafariZoneCenter:grass", MapId.SAFARI_ZONE_CENTER),
    ("wild:SafariZoneEast:grass", MapId.SAFARI_ZONE_EAST),
    ("wild:SafariZoneNorth:grass", MapId.SAFARI_ZONE_NORTH),
    ("wild:SafariZoneWest:grass", MapId.SAFARI_ZONE_WEST),
)
SAFARI_ENCOUNTER_SLOTS = 10
SAFARI_ADMISSION_COST = 500
SAFARI_AREA_CHOICE_POLICY = "living-dex-safari-area-softmax-v1"


class SafariControlPort(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


@dataclass(frozen=True, slots=True)
class RedSafariZoneOffer:
    """One private cartridge-derived area binding with an identity-free row."""

    source_id: str
    map_id: int
    slots: tuple[tuple[int, int], ...]
    missing_species_numbers: tuple[int, ...]

    def __post_init__(self) -> None:
        if (self.source_id, MapId(self.map_id)) not in SAFARI_ZONE_SOURCES:
            raise ValueError("Safari offer source and map do not match")
        if len(self.slots) != SAFARI_ENCOUNTER_SLOTS:
            raise ValueError("Safari offer must retain all ten cartridge slots")
        if any(
            type(level) is not int
            or not 1 <= level <= 100
            or type(number) is not int
            or not 1 <= number <= 151
            for level, number in self.slots
        ):
            raise ValueError("Safari encounter slot is invalid")
        available = {number for _, number in self.slots}
        if (
            not self.missing_species_numbers
            or self.missing_species_numbers != tuple(sorted(set(self.missing_species_numbers)))
            or not set(self.missing_species_numbers) <= available
        ):
            raise ValueError("Safari offer must contain distinct missing local species")

    @property
    def productive_slot_count(self) -> int:
        missing = set(self.missing_species_numbers)
        return sum(number in missing for _, number in self.slots)

    def policy_features(self) -> dict[str, int]:
        """Return only semantic progress/resource evidence suitable for scoring."""

        return {
            "admission_cost": SAFARI_ADMISSION_COST,
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


@dataclass(frozen=True, slots=True)
class RedSafariAdmissionReport:
    """Verified arrival in one selected area after exactly one paid admission."""

    selected_source_id: str
    selected_map_id: int
    selected_position: tuple[int, int]
    route_steps: int
    encounters_fled: int
    money_before: int
    money_after: int
    safari_steps_remaining: int
    safari_balls_remaining: int
    actions_executed: int
    frames_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        expected = _SAFARI_AREA_TERMINALS.get(self.selected_source_id)
        return (
            expected is not None
            and expected[0] == self.selected_map_id
            and expected[1] == self.selected_position
            and expected[2] == self.safari_steps_remaining
            and self.money_before - self.money_after == SAFARI_ADMISSION_COST
            and self.safari_balls_remaining == 30
            and self.actions_executed > 0
            and self.frames_executed > 0
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "single_admission": self.money_before - self.money_after == SAFARI_ADMISSION_COST,
            "route_steps": self.route_steps,
            "encounters_fled": self.encounters_fled,
            "safari_steps_remaining": self.safari_steps_remaining,
            "safari_balls_remaining": self.safari_balls_remaining,
            "actions_executed": self.actions_executed,
            "frames_executed": self.frames_executed,
            "private_map_fields": 0,
            "private_source_fields": 0,
            "raw_teacher_direction_steps": 0,
        }


@dataclass(frozen=True, slots=True)
class RedSafariTransportReport:
    """Verified story-neutral transport from any qualified field origin."""

    initial_map_id: int
    initial_position: tuple[int, int]
    landing_map_id: int
    landing_position: tuple[int, int]
    party_species_before: tuple[int, ...]
    party_species_after: tuple[int, ...]
    verified_fly_receipts: int
    final_map_id: int
    final_position: tuple[int, int]
    money_before: int
    money_after: int
    actions_executed: int
    frames_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            0 <= self.initial_map_id <= 0x24
            and self.initial_map_id != int(MapId.FUCHSIA_CITY)
            and self.landing_map_id == int(MapId.FUCHSIA_CITY)
            and self.landing_position == (19, 28)
            and bool(self.party_species_before)
            and self.party_species_after == self.party_species_before
            and self.verified_fly_receipts == 1
            and self.final_map_id == int(MapId.FUCHSIA_POKECENTER)
            and self.final_position == (3, 3)
            and self.money_after == self.money_before
            and self.actions_executed > 0
            and self.frames_executed > 0
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "story_neutral_fly": (
                self.landing_map_id == int(MapId.FUCHSIA_CITY)
                and self.landing_position == (19, 28)
                and self.verified_fly_receipts == 1
            ),
            "exact_party_preserved": self.party_species_after == self.party_species_before,
            "verified_fly_receipts": self.verified_fly_receipts,
            "stable_fuchsia_center": (
                self.final_map_id == int(MapId.FUCHSIA_POKECENTER)
                and self.final_position == (3, 3)
            ),
            "money_spent": self.money_before - self.money_after,
            "actions_executed": self.actions_executed,
            "frames_executed": self.frames_executed,
            "private_coordinate_fields": 0,
            "private_map_fields": 0,
            "raw_teacher_direction_steps": 0,
        }


@dataclass(frozen=True, slots=True)
class RedSafariPatrolPlan:
    """One cartridge-derived approach to a reversible two-tile encounter lane."""

    source_id: str
    map_id: int
    start_at: Coordinate
    approach_directions: tuple[str, ...]
    first_at: Coordinate
    second_at: Coordinate
    encounter_tile_count: int
    forward_direction: str
    backward_direction: str

    def __post_init__(self) -> None:
        if (self.source_id, MapId(self.map_id)) not in SAFARI_ZONE_SOURCES:
            raise ValueError("Safari patrol source and map do not match")
        opposite = {"up": "down", "down": "up", "left": "right", "right": "left"}
        if (
            self.forward_direction not in opposite
            or self.backward_direction != opposite[self.forward_direction]
            or self.encounter_tile_count not in {1, 2}
            or not self.approach_directions
            or any(direction not in opposite for direction in self.approach_directions)
        ):
            raise ValueError("Safari patrol directions are invalid")
        dy = self.second_at[0] - self.first_at[0]
        dx = self.second_at[1] - self.first_at[1]
        expected = {
            "up": (-1, 0),
            "down": (1, 0),
            "left": (0, -1),
            "right": (0, 1),
        }[self.forward_direction]
        if (dy, dx) != expected:
            raise ValueError("Safari patrol endpoints differ from its direction")

    def public_dict(self) -> dict[str, object]:
        return {
            "cartridge_derived": True,
            "approach_steps": len(self.approach_directions),
            "bidirectional_walk_edges": 2,
            "encounter_tiles": self.encounter_tile_count,
            "provider_local_direction_steps": 1,
            "private_coordinate_fields": 0,
            "private_map_fields": 0,
            "private_source_fields": 0,
            "raw_teacher_direction_steps": 0,
        }


_NORTH_TO_WEST_ENCOUNTER_SHELF = tuple(
    {"U": "up", "D": "down", "L": "left", "R": "right"}[step]
    for step in "ULLULLLLLLLLLLLLUUUUULLLUULLLLDDDDLLDDDDDDDLLLLLLLDDD"
)
_SAFARI_AREA_ROUTES: dict[str, tuple[str, ...]] = {
    "wild:SafariZoneCenter:grass": (),
    "wild:SafariZoneEast:grass": CENTER_TO_EAST,
    "wild:SafariZoneNorth:grass": CENTER_TO_EAST + EAST_TO_NORTH,
    "wild:SafariZoneWest:grass": (
        CENTER_TO_EAST + EAST_TO_NORTH + _NORTH_TO_WEST_ENCOUNTER_SHELF
    ),
}
_SAFARI_AREA_TERMINALS: dict[str, tuple[int, tuple[int, int], int]] = {
    "wild:SafariZoneCenter:grass": (int(MapId.SAFARI_ZONE_CENTER), (15, 25), 500),
    "wild:SafariZoneEast:grass": (int(MapId.SAFARI_ZONE_EAST), (0, 23), 472),
    "wild:SafariZoneNorth:grass": (int(MapId.SAFARI_ZONE_NORTH), (39, 31), 376),
    "wild:SafariZoneWest:grass": (int(MapId.SAFARI_ZONE_WEST), (27, 0), 324),
}


def red_safari_admission_route(offer: RedSafariZoneOffer) -> tuple[str, ...]:
    """Return the already-qualified Red area route; it is never a policy feature."""

    if not isinstance(offer, RedSafariZoneOffer):
        raise TypeError("Safari admission route needs one cartridge offer")
    return _SAFARI_AREA_ROUTES[offer.source_id]


def derive_red_safari_patrol(
    offer: RedSafariZoneOffer,
    terrain: Terrain,
    graph: LocalGraph,
    *,
    start_at: Coordinate,
    excluded: Collection[Coordinate] = (),
) -> RedSafariPatrolPlan:
    """Find the nearest reachable reversible pair of encounter tiles."""

    if terrain.map_id != offer.map_id:
        raise ValueError("Safari patrol terrain differs from its offer")
    if not isinstance(graph, LocalGraph):
        raise TypeError("Safari patrol needs a local traversal graph")
    # The area entry is itself a warp coordinate. It must remain a legal
    # departure square while every other warp stays unavailable as a patrol
    # endpoint or transit shortcut.
    blocked = frozenset(excluded) - {start_at}
    available = without_coordinates(graph, blocked)
    directions = (
        ("down", "up", (1, 0)),
        ("right", "left", (0, 1)),
    )
    candidates: list[
        tuple[int, Coordinate, Coordinate, tuple[str, ...], str, str]
    ] = []
    for y in range(terrain.height):
        for x in range(terrain.width):
            first = (y, x)
            if first in blocked:
                continue
            for forward, backward, (dy, dx) in directions:
                second = (y + dy, x + dx)
                if (
                    second in blocked
                    or not 0 <= second[0] < terrain.height
                    or not 0 <= second[1] < terrain.width
                    or not (terrain.grass[y][x] or terrain.grass[second[0]][second[1]])
                    or not _plain_safari_walk(available, first, second, forward)
                    or not _plain_safari_walk(available, second, first, backward)
                ):
                    continue
                for approach_at, other_at, outbound, inbound in (
                    (first, second, forward, backward),
                    (second, first, backward, forward),
                ):
                    try:
                        path = find_local_path(
                            available,
                            start_at,
                            approach_at,
                            start_mode="land",
                            goal_mode="land",
                        )
                    except LocalRouterError:
                        continue
                    path_directions = tuple(edge.action for edge in path.edges)
                    if not path_directions:
                        # A one-step approach gives execution an independently
                        # checked boundary before the first patrol transition.
                        continue
                    candidates.append(
                        (
                            len(path.edges),
                            approach_at,
                            other_at,
                            path_directions,
                            outbound,
                            inbound,
                        )
                    )
    if not candidates:
        raise ValueError("Safari area has no reachable reversible encounter lane")
    _, first, second, approach, forward, backward = min(candidates)
    return RedSafariPatrolPlan(
        offer.source_id,
        offer.map_id,
        start_at,
        approach,
        first,
        second,
        int(terrain.grass[first[0]][first[1]]) + int(terrain.grass[second[0]][second[1]]),
        forward,
        backward,
    )


def _plain_safari_walk(
    graph: LocalGraph,
    source: Coordinate,
    target: Coordinate,
    direction: str,
) -> bool:
    return any(
        edge.target == target
        and edge.action_kind is MacroActionKind.MOVE
        and edge.action == direction
        and edge.permits_mode("land")
        and edge.next_mode("land") == "land"
        and not edge.requirements
        for edge in graph.neighbors(source)
    )


def relocate_red_safari_origin_to_fuchsia_center(
    emulator: EmulatorState,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    *,
    timing: SafariTiming = DEFAULT_SAFARI_TIMING,
) -> RedSafariTransportReport:
    """Fly from the observed qualified field, then enter Fuchsia's stable Center."""

    start_actions = actions.actions_executed
    start_frames = emulator.frame_count
    money_before = _money(emulator)
    initial = reader.read()
    initial_position = (
        -1 if initial.player_x is None else int(initial.player_x),
        -1 if initial.player_y is None else int(initial.player_y),
    )
    party_species = tuple(initial.party_species_ids or ())
    if initial.map_id is None or not party_species:
        raise RedAreaExecutionError(
            "Safari transport lacks a complete outdoor party boundary",
            reason_code="safari_transport_boundary_invalid",
        )
    field_moves = Gen1FieldMovePort(actions, reader, emulator)
    field_moves.execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:fuchsia_city"))
    landing = reader.read()
    if (
        landing.map_id != MapId.FUCHSIA_CITY
        or (landing.player_x, landing.player_y) != (19, 28)
        or tuple(landing.party_species_ids or ()) != party_species
        or len(field_moves.fly_receipts) != 1
    ):
        raise RedAreaExecutionError(
            "Safari transport Fly missed its cartridge-qualified landing",
            reason_code="safari_transport_fly_failed",
        )
    _move(
        actions,
        reader,
        emulator,
        ("up",) * 5,
        timing,
        "Fuchsia Fly landing to Center",
        expected_party_species_ids=party_species,
    )
    final = reader.read()
    report = RedSafariTransportReport(
        int(initial.map_id),
        initial_position,
        -1 if landing.map_id is None else int(landing.map_id),
        (
            -1 if landing.player_x is None else int(landing.player_x),
            -1 if landing.player_y is None else int(landing.player_y),
        ),
        party_species,
        tuple(final.party_species_ids or ()),
        len(field_moves.fly_receipts),
        -1 if final.map_id is None else int(final.map_id),
        (
            -1 if final.player_x is None else int(final.player_x),
            -1 if final.player_y is None else int(final.player_y),
        ),
        money_before,
        _money(emulator),
        actions.actions_executed - start_actions,
        emulator.frame_count - start_frames,
        not emulator.pressed_buttons,
    )
    if not report.passed:
        raise RedAreaExecutionError(
            "Safari transport missed its stable Fuchsia Center boundary",
            reason_code="safari_transport_center_failed",
        )
    return report


def enter_red_safari_area(
    emulator: SafariControlPort,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    offer: RedSafariZoneOffer,
    *,
    timing: SafariTiming = DEFAULT_SAFARI_TIMING,
) -> RedSafariAdmissionReport:
    """Pay once and reach the already-selected area from Fuchsia's stable center."""

    before = reader.read()
    if (
        before.map_id != MapId.FUCHSIA_POKECENTER
        or (before.player_x, before.player_y) != (3, 3)
        or before.battle_state
        or _money(emulator) < SAFARI_ADMISSION_COST
    ):
        raise RedAreaExecutionError(
            "Safari admission lacks the stable funded Fuchsia boundary",
            reason_code="safari_admission_boundary_invalid",
        )
    start_actions = actions.actions_executed
    start_frames = emulator.frame_count
    money_before = _money(emulator)
    party_species = tuple(before.party_species_ids or ())
    if not party_species:
        raise RedAreaExecutionError(
            "Safari admission lacks a complete party observation",
            reason_code="safari_admission_party_invalid",
        )
    encounters = _move(
        actions,
        reader,
        emulator,
        CENTER_TO_GATE,
        timing,
        "Safari gate",
        expected_party_species_ids=party_species,
    )
    gate = reader.read()
    if gate.map_id != MapId.SAFARI_ZONE_GATE or (gate.player_x, gate.player_y) != (3, 5):
        raise RedAreaExecutionError(
            "Safari admission route missed the gate",
            reason_code="safari_gate_route_failed",
        )
    _move(
        actions,
        reader,
        emulator,
        ("up", "up", "up"),
        timing,
        "Safari clerk",
        expected_party_species_ids=party_species,
    )
    for _ in range(timing.dialogue_pulses):
        admitted = reader.read()
        if admitted.map_id == MapId.SAFARI_ZONE_CENTER:
            break
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.wait_frames))
    else:
        raise RedAreaExecutionError(
            "Safari clerk did not admit the player",
            reason_code="safari_admission_dialogue_failed",
        )
    if money_before - _money(emulator) != SAFARI_ADMISSION_COST or _balls(emulator) != 30:
        raise RedAreaExecutionError(
            "Safari admission fee or ball grant differs",
            reason_code="safari_admission_resources_changed",
        )
    route = red_safari_admission_route(offer)
    encounters += _move(
        actions,
        reader,
        emulator,
        route,
        timing,
        "selected Safari area",
        expected_party_species_ids=party_species,
    )
    final = reader.read()
    expected_map, expected_position, expected_steps = _SAFARI_AREA_TERMINALS[offer.source_id]
    report = RedSafariAdmissionReport(
        offer.source_id,
        -1 if final.map_id is None else int(final.map_id),
        (
            -1 if final.player_x is None else int(final.player_x),
            -1 if final.player_y is None else int(final.player_y),
        ),
        len(route),
        encounters,
        money_before,
        _money(emulator),
        _steps(emulator),
        _balls(emulator),
        actions.actions_executed - start_actions,
        emulator.frame_count - start_frames,
        not emulator.pressed_buttons,
    )
    if (final.map_id, (final.player_x, final.player_y), report.safari_steps_remaining) != (
        expected_map,
        expected_position,
        expected_steps,
    ) or not report.passed:
        raise RedAreaExecutionError(
            "Safari selected-area arrival failed its postconditions",
            reason_code="safari_area_arrival_failed",
        )
    return report


def red_safari_zone_offers(
    rom: bytes,
    registered_species_numbers: Collection[int],
) -> tuple[RedSafariZoneOffer, ...]:
    """Inventory productive Safari areas from cartridge slots and global credit."""

    if not isinstance(rom, bytes):
        raise TypeError("Safari inventory needs immutable cartridge bytes")
    registered = frozenset(registered_species_numbers)
    if any(type(number) is not int or not 1 <= number <= 151 for number in registered):
        raise ValueError("registered Safari credit must contain Pokédex numbers")
    mapping = internal_to_dex(rom)
    tables = wild_tables(rom, medium="grass")
    targets = {red_species_number(ref) for ref in RED_SOLO_COLLECTION_CONTRACT.target_species}
    offers: list[RedSafariZoneOffer] = []
    for source_id, map_id in SAFARI_ZONE_SOURCES:
        raw_slots = tables.get(int(map_id), ())
        slots = tuple((level, mapping[internal]) for level, internal in raw_slots)
        missing = tuple(sorted({number for _, number in slots} & targets - registered))
        if missing:
            offers.append(RedSafariZoneOffer(source_id, int(map_id), slots, missing))
    return tuple(offers)


@dataclass(frozen=True, slots=True)
class RedSafariAreaChoice:
    """One model selection joined privately to the chosen cartridge area."""

    menu: LivingDexOptionMenu
    offers: tuple[RedSafariZoneOffer, ...]
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
            raise ValueError("Safari area choice does not match its policy menu")

    @property
    def selected_offer(self) -> RedSafariZoneOffer:
        return self.offers[self.selected_candidate_index]

    def public_dict(self) -> dict[str, object]:
        return {
            "policy_id": SAFARI_AREA_CHOICE_POLICY,
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


def red_safari_area_menu(
    context: LivingDexOptionContext,
    offers: tuple[RedSafariZoneOffer, ...],
    *,
    route_steps: tuple[int, ...],
    maximum_route_steps: int,
    available_money: int,
    free_storage_slots: int,
) -> LivingDexOptionMenu:
    """Project two or more executable Safari areas into existing model features."""

    if (
        len(offers) < 2
        or len(offers) != len(route_steps)
        or len({offer.source_id for offer in offers}) != len(offers)
    ):
        raise ValueError("Safari area learning needs distinct candidate areas")
    if type(maximum_route_steps) is not int or maximum_route_steps <= 0:
        raise ValueError("Safari area route bound must be positive")
    if any(
        type(value) is not int or not 0 <= value <= maximum_route_steps for value in route_steps
    ):
        raise ValueError("Safari area route steps exceed their bound")
    if type(available_money) is not int or available_money < SAFARI_ADMISSION_COST:
        raise ValueError("Safari area menu needs one funded admission")
    if type(free_storage_slots) is not int or free_storage_slots <= 0:
        raise ValueError("Safari area menu needs immediate storage")
    candidates = tuple(
        LivingDexOptionCandidate(
            binding_ref=f"safari-area-private-{index}",
            features=LivingDexOptionFeatures(
                kind=LivingDexOptionKind.ACQUIRE,
                completion_gain=min(1.0, len(offer.missing_species_numbers) / 6.0),
                dependency_unlock_gain=0.0,
                travel_effort=route_steps[index] / maximum_route_steps,
                execution_effort=1.0 - offer.productive_slot_count / len(offer.slots),
                resource_cost=min(1.0, SAFARI_ADMISSION_COST / available_money),
                storage_cost=min(1.0, 1.0 / free_storage_slots),
                party_risk=0.0,
                irreversibility_risk=0.0,
                uncertainty=1.0 - offer.productive_slot_count / len(offer.slots),
            ),
            availability=LivingDexOptionAvailability.AVAILABLE,
        )
        for index, offer in enumerate(offers)
    )
    menu = LivingDexOptionMenu(context, candidates)
    if len({menu.candidate_vector(index) for index in menu.available_indices}) < 2:
        raise ValueError("Safari area candidates have no distinguishable semantic features")
    return menu


def select_red_safari_area(
    model: LivingDexOptionValueModel,
    menu: LivingDexOptionMenu,
    offers: tuple[RedSafariZoneOffer, ...],
    *,
    seed: int,
) -> RedSafariAreaChoice:
    """Sample one Safari destination with the existing learned value model."""

    if type(seed) is not int or seed < 0 or model.feature_version < menu.feature_version:
        raise ValueError("Safari selection seed or model feature version differs")
    if len(offers) != len(menu.candidates):
        raise ValueError("Safari offers differ from the policy menu")
    scores = model.scores(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY)
    utilities = [scores[index] for index in menu.available_indices]
    if any(value is None or not math.isfinite(value) for value in utilities):
        raise ValueError("Safari model returned invalid scores")
    concrete = [float(value) for value in utilities if value is not None]
    peak = max(concrete)
    exp = [math.exp(value - peak) for value in concrete]
    total = sum(exp)
    probabilities = [0.0] * len(offers)
    for index, value in zip(menu.available_indices, exp, strict=True):
        probabilities[index] = 0.75 * value / total + 0.25 / len(exp)
    selected = random.Random(seed).choices(range(len(probabilities)), weights=probabilities, k=1)[0]
    return RedSafariAreaChoice(
        menu,
        offers,
        selected,
        tuple(scores),
        tuple(probabilities),
        seed,
        model.model_sha256,
    )


class LiveSafariPatrol:
    """Execute one derived two-tile patrol without consuming encounters."""

    def __init__(
        self,
        emulator: SafariControlPort,
        actions: CountingExecutor,
        reader: PokemonRedStateReader,
        plan: RedSafariPatrolPlan,
        *,
        timing: SafariTiming = DEFAULT_SAFARI_TIMING,
    ) -> None:
        if not isinstance(plan, RedSafariPatrolPlan):
            raise TypeError("Safari patrol needs a derived plan")
        self._emulator = emulator
        self._actions = actions
        self._reader = reader
        self._plan = plan
        self._timing = timing
        self._entered = False
        self._at_first = True

    def enter(self) -> int:
        if self._entered:
            raise RedAreaExecutionError(
                "Safari patrol approach was already executed",
                reason_code="safari_patrol_approach_repeated",
            )
        raw = self._reader.read()
        party_species = tuple(raw.party_species_ids or ())
        if (
            raw.map_id != self._plan.map_id
            or (raw.player_y, raw.player_x) != self._plan.start_at
            or raw.battle_state
            or not party_species
        ):
            raise RedAreaExecutionError(
                "Safari patrol approach lacks its selected-area boundary",
                reason_code="safari_patrol_boundary_invalid",
            )
        encounters = _move(
            self._actions,
            self._reader,
            self._emulator,
            self._plan.approach_directions,
            self._timing,
            "Safari encounter lane",
            expected_party_species_ids=party_species,
        )
        final = self._reader.read()
        if (
            final.map_id != self._plan.map_id
            or (final.player_y, final.player_x) != self._plan.first_at
            or final.battle_state
            or _balls(self._emulator) <= 0
        ):
            raise RedAreaExecutionError(
                "Safari patrol approach missed its encounter lane",
                reason_code="safari_patrol_approach_failed",
            )
        self._entered = True
        return encounters

    def resume_from_encounter(self) -> None:
        """Restore patrol phase from a retained battle at either derived endpoint."""

        if self._entered:
            raise RedAreaExecutionError(
                "Safari patrol was already entered before encounter recovery",
                reason_code="safari_patrol_recovery_repeated",
            )
        raw = self._reader.read()
        at = (raw.player_y, raw.player_x)
        if (
            raw.map_id != self._plan.map_id
            or raw.battle_state != 1
            or at not in {self._plan.first_at, self._plan.second_at}
            or _balls(self._emulator) <= 0
            or not raw.party_species_ids
        ):
            raise RedAreaExecutionError(
                "Safari patrol recovery lacks a retained endpoint encounter",
                reason_code="safari_patrol_recovery_boundary_invalid",
            )
        self._entered = True
        self._at_first = at == self._plan.first_at

    def seek_step(self) -> None:
        if not self._entered:
            raise RedAreaExecutionError(
                "Safari patrol must enter its lane before seeking",
                reason_code="safari_patrol_not_entered",
            )
        before = self._reader.read()
        expected_at = self._plan.first_at if self._at_first else self._plan.second_at
        target_at = self._plan.second_at if self._at_first else self._plan.first_at
        direction = (
            self._plan.forward_direction if self._at_first else self._plan.backward_direction
        )
        if (
            before.map_id != self._plan.map_id
            or (before.player_y, before.player_x) != expected_at
            or before.battle_state
            or _balls(self._emulator) <= 0
        ):
            raise RedAreaExecutionError(
                "Safari patrol step lacks its expected endpoint",
                reason_code="safari_patrol_endpoint_changed",
            )
        for _ in range(self._timing.movement_retries):
            _pulse(
                self._actions,
                MacroActionKind.MOVE,
                direction,
                frames=self._timing.movement_frames,
            )
            after = self._reader.read()
            if after.map_id != self._plan.map_id:
                raise RedAreaExecutionError(
                    "Safari patrol step left its selected area",
                    reason_code="safari_patrol_left_area",
                )
            if (after.player_y, after.player_x) == target_at:
                self._at_first = not self._at_first
                return
            if after.battle_state:
                # A random encounter can take control before the overworld
                # coordinate acknowledges this pulse.  That is the patrol's
                # successful handoff to the battle mechanic, not a blocked
                # traversal.  Keep the current endpoint so a failed capture
                # can resume the same reversible edge after battle cleanup.
                return
        raise RedAreaExecutionError(
            "Safari patrol step did not traverse its reversible edge",
            reason_code="safari_patrol_step_blocked",
        )


class LiveSafariAreaExecutor:
    """Implement the reusable area port for one already-admitted Safari area."""

    def __init__(
        self,
        emulator: SafariControlPort,
        actions: CountingExecutor,
        reader: PokemonRedStateReader,
        *,
        source_id: str,
        map_id: int,
        seek_step: Callable[[], None],
        maximum_throws_per_encounter: int = 8,
        settle_pulses: int = 48,
        wait_frames: int = 180,
        collection_reader: Callable[[], CollectionObservation] | None = None,
    ) -> None:
        if (source_id, MapId(map_id)) not in SAFARI_ZONE_SOURCES:
            raise ValueError("Safari executor source and map do not match")
        if not callable(seek_step):
            raise TypeError("Safari executor needs a bounded encounter step")
        for name, value in (
            ("maximum_throws_per_encounter", maximum_throws_per_encounter),
            ("settle_pulses", settle_pulses),
            ("wait_frames", wait_frames),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self._emulator = emulator
        self._actions = actions
        self._reader = reader
        self._source_id = source_id
        self._map_id = map_id
        self._seek_step = seek_step
        self._maximum_throws = maximum_throws_per_encounter
        self._settle_pulses = settle_pulses
        self._wait_frames = wait_frames
        self._collection_reader = collection_reader

    def read_collection(self) -> CollectionObservation:
        if self._collection_reader is not None:
            return self._collection_reader()
        return red_collection_observation(
            self._reader.read_pokedex_state(),
            PokemonRedPartyReader(self._emulator).read(),
            self._reader.read_all_box_states(),
        )

    def encountered_species_ref(self) -> str | None:
        raw = self._reader.read()
        if not raw.battle_state:
            return None
        if raw.map_id != self._map_id or raw.enemy_species_id is None:
            raise RedAreaExecutionError(
                "Safari encounter left its bound area or lacks species evidence",
                reason_code="safari_encounter_boundary_invalid",
            )
        try:
            return red_species_ref(red_internal_species_number(raw.enemy_species_id))
        except ValueError as error:
            raise RedAreaExecutionError(
                "Safari encounter exposed an invalid species",
                reason_code="encounter_species_invalid",
            ) from error

    def seek_encounter(self) -> None:
        if self.encountered_species_ref() is not None:
            raise RedAreaExecutionError(
                "Safari encounter step was requested during battle",
                reason_code="seek_requested_during_encounter",
            )
        before = self._reader.read()
        if before.map_id != self._map_id or self._balls() <= 0:
            raise RedAreaExecutionError(
                "Safari encounter step lacks an active admitted area",
                reason_code="safari_admission_unavailable",
            )
        self._seek_step()
        after = self._reader.read()
        if after.map_id != self._map_id:
            raise RedAreaExecutionError(
                "Safari encounter step crossed the bound area",
                reason_code="safari_seek_left_area",
            )

    def capture_encounter(self, species_ref: str) -> bool:
        if self.encountered_species_ref() != species_ref:
            raise RedAreaExecutionError(
                "Safari capture target differs from the observed encounter",
                reason_code="capture_target_mismatch",
            )
        before_collection = self.read_collection()
        before_counts = Counter(item.species_ref for item in before_collection.specimens)
        before_bag = self._reader.read().bag_items
        before_hp = self._reader.read().party_hp
        throws = 0
        while throws < self._maximum_throws and self.encountered_species_ref() is not None:
            before_balls = self._balls()
            self._select_ball()
            spent = self._settle_throw(before_balls)
            if spent:
                throws += 1
            if self.encountered_species_ref() is None:
                break
        if self.encountered_species_ref() is not None:
            self.flee_encounter()
        retained = self._settle_outcome(species_ref, before_counts)
        final = self._reader.read()
        if final.bag_items != before_bag:
            raise RedAreaExecutionError(
                "Safari capture changed ordinary inventory",
                reason_code="safari_capture_inventory_changed",
            )
        if (
            before_hp is not None
            and final.party_hp is not None
            and (final.party_hp[: len(before_hp)] != before_hp)
        ):
            raise RedAreaExecutionError(
                "Safari capture changed the existing party HP",
                reason_code="safari_capture_party_changed",
            )
        return retained

    def flee_encounter(self) -> None:
        if self.encountered_species_ref() is None:
            raise RedAreaExecutionError(
                "Safari flee was requested without an encounter",
                reason_code="flee_without_encounter",
            )
        before_balls = self._balls()
        for _ in range(12):
            if self.encountered_species_ref() is None:
                break
            for kind, direction in (
                (MacroActionKind.CANCEL, None),
                (MacroActionKind.MOVE, "down"),
                (MacroActionKind.MOVE, "right"),
                (MacroActionKind.CONFIRM, None),
            ):
                self._pulse(kind, direction)
                if self.encountered_species_ref() is None:
                    break
        else:
            raise RedAreaExecutionError(
                "Safari RUN did not settle",
                reason_code="safari_flee_failed",
            )
        if self._balls() != before_balls:
            raise RedAreaExecutionError(
                "Safari RUN changed Safari Balls",
                reason_code="safari_flee_ball_count_changed",
            )

    def switch_box(self, box_index: int) -> None:
        raise RedAreaExecutionError(
            f"Safari area cannot switch to box {box_index} during one admission",
            reason_code="box_switch_requires_source_exit",
        )

    def safari_balls_available(self) -> bool:
        return self._balls() > 0

    def _select_ball(self) -> None:
        # Red stores Safari's row in wCurrentMenuItem and its column in
        # wTopMenuItemX.  Wait for that live signature instead of sending a
        # blind B/up/left sequence while encounter text still owns input.
        for _ in range(self._settle_pulses):
            raw = self._reader.read()
            menu = self._reader.read_battle_menu_state(raw)
            if menu.phase is not BattleMenuPhase.MAIN:
                self._pulse(MacroActionKind.CANCEL)
                continue
            selected = menu.selected_main_command
            if selected is None or not 0 <= selected <= 3:
                raise RedAreaExecutionError(
                    "Safari menu exposed an invalid command",
                    reason_code="safari_menu_command_invalid",
                )
            if selected == 0:
                self._pulse(MacroActionKind.CONFIRM, frames=360)
                return
            direction = "left" if selected >= 2 else "up"
            expected = selected - 2 if selected >= 2 else 0
            self._pulse(MacroActionKind.MOVE, direction)
            after = self._reader.read_battle_menu_state(self._reader.read())
            if (
                after.phase is not BattleMenuPhase.MAIN
                or after.selected_main_command != expected
            ):
                raise RedAreaExecutionError(
                    "Safari menu did not acknowledge the selected direction",
                    reason_code="safari_menu_selection_unacknowledged",
                )
        raise RedAreaExecutionError(
            "Safari command menu did not become observable",
            reason_code="safari_menu_unavailable",
        )

    def _settle_throw(self, before_balls: int) -> bool:
        spent = False
        for _ in range(self._settle_pulses):
            balls = self._balls()
            if balls == before_balls - 1:
                spent = True
            elif balls != before_balls:
                raise RedAreaExecutionError(
                    "Safari Ball count changed by more than one throw",
                    reason_code="safari_ball_accounting_changed",
                )
            raw = self._reader.read()
            if not raw.battle_state:
                return spent
            if spent and 0 <= self._emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) <= 3:
                return True
            self._pulse(MacroActionKind.CANCEL)
        if not spent:
            raise RedAreaExecutionError(
                "Safari BALL command did not consume one ball",
                reason_code="safari_throw_not_observed",
            )
        return True

    def _settle_outcome(self, species_ref: str, before: Counter[str]) -> bool:
        for _ in range(self._settle_pulses):
            after_observation = self.read_collection()
            after = Counter(item.species_ref for item in after_observation.specimens)
            delta = after - before
            retained = after[species_ref] == before[species_ref] + 1
            if retained and delta == Counter({species_ref: 1}):
                return True
            ready = self._reader.read_input_readiness().ready
            if ready and after == before:
                return False
            self._pulse(MacroActionKind.CANCEL)
        raise RedAreaExecutionError(
            "Safari encounter ended without a stable retention outcome",
            reason_code="safari_capture_outcome_unsettled",
        )

    def _balls(self) -> int:
        return self._emulator.read_u8(RamAddress.SAFARI_BALLS)

    def _pulse(
        self,
        kind: MacroActionKind,
        direction: str | None = None,
        *,
        frames: int | None = None,
    ) -> None:
        self._actions.execute(
            MacroAction(kind, direction) if direction is not None else MacroAction(kind)
        )
        # Macro-action compilers own their button timing; WAIT provides the
        # bounded observation window without direct controller access here.
        self._actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames or self._wait_frames))


__all__ = [
    "LiveSafariAreaExecutor",
    "LiveSafariPatrol",
    "RedSafariAdmissionReport",
    "RedSafariAreaChoice",
    "RedSafariPatrolPlan",
    "RedSafariTransportReport",
    "RedSafariZoneOffer",
    "SAFARI_ADMISSION_COST",
    "SAFARI_AREA_CHOICE_POLICY",
    "SAFARI_ZONE_SOURCES",
    "derive_red_safari_patrol",
    "enter_red_safari_area",
    "red_safari_area_menu",
    "red_safari_admission_route",
    "red_safari_zone_offers",
    "relocate_red_safari_origin_to_fuchsia_center",
    "select_red_safari_area",
]
