"""Cartridge-derived Fly transport for regional trainer funding.

Prospective candidate helper across reachable town landings and connected maps.
The existing funding runtime owns execution, requalification and outcome verification.
Neither a cartridge payout quote nor a computed route is earned income.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_field_moves import Gen1FieldMoveError, fly_menu_indices
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.gen1_trainer_sight import (
    TrainerSightZone,
    static_trainer_sight_zones,
    trainer_headers,
)
from pokemon_red_completion.gen1_traversal import map_object_events
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import (
    RED_FLY_TOWN_NAMES,
    Badge,
    OverworldMovementMode,
)
from pokemon_red_completion.red_collection_fly import red_fly_landings
from pokemon_red_completion.red_regional_trainer_funding import (
    funding_scope,
    regional_trainer_funding_candidates,
)
from pokemon_red_completion.red_trainer_funding import TrainerFundingCandidate

if TYPE_CHECKING:
    from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter


@dataclass(frozen=True, slots=True)
class FundingFlyCandidate:
    town: int
    landing: tuple[int, int]
    target: TrainerFundingCandidate


def _funding_fly_opted_in(router: RedResourceGoalRouter) -> bool:
    if getattr(router, "regional_trainer_funding", False) is not True:
        return False
    runtime = getattr(router, "runtime", None)
    profile = getattr(runtime, "profile", None)
    if profile is None or not hasattr(profile, "providers"):
        return False
    return any(
        getattr(spec, "kind", None) is GoalKind.RESUPPLY
        and isinstance(getattr(spec, "parameters", None), Mapping)
        and spec.parameters.get("funding_fly_transport") is True
        for spec in profile.providers
    )


def funding_fly_candidates(
    router: RedResourceGoalRouter,
) -> tuple[FundingFlyCandidate, ...]:
    """Return prospective regional trainer funding candidates via legal Fly landings.

    Must return empty unless regional_trainer_funding is true and a RESUPPLY spec
    has funding_fly_transport is True.
    """
    if not _funding_fly_opted_in(router):
        return ()

    reader = router.runtime.reader
    rom = router.world.rom
    raw = reader.read()

    if raw is None or raw.map_id is None or raw.player_y is None or raw.player_x is None:
        return ()
    if not raw.game_started or raw.battle_state != 0:
        return ()
    if raw.event_flags is None:
        return ()

    if (
        type(raw.map_id) is not int
        or isinstance(raw.map_id, bool)
        or not (0 <= raw.map_id <= 0x24)
        or raw.map_id == 0x0B
    ):
        return ()

    if (
        reader.read_bottom_dialogue_box_visible()
        or reader.read_pending_trainer_battle_identity() is not None
        or reader.read_fly_menu_state() is not None
        or reader.read_overworld_movement_mode() is not OverworldMovementMode.WALKING
        or not reader.read_input_readiness().ready
    ):
        return ()

    if not (int(raw.badge_bits or 0) & int(Badge.THUNDER)):
        return ()

    try:
        fly_menu_indices(raw)
    except Gen1FieldMoveError:
        return ()

    start = Gen1TraversalObserver(reader).observe()

    if (
        not start.ready
        or start.interruption is not None
        or start.mode != "land"
        or type(start.map_id) is not int
        or isinstance(start.map_id, bool)
        or not (0 <= start.map_id <= 0x24)
        or start.map_id == 0x0B
    ):
        return ()
    if (start.map_id, *start.at) != (raw.map_id, raw.player_y, raw.player_x):
        raise CartridgeReadError("funding Fly origin changed during observation")

    landings = dict(red_fly_landings(rom))
    destinations = reader.read_fly_destinations()

    results: list[FundingFlyCandidate] = []
    seen_towns: set[int] = set()

    for town in destinations:
        if (
            type(town) is not int
            or isinstance(town, bool)
            or not (0 <= town < len(RED_FLY_TOWN_NAMES))
        ):
            continue
        if town in seen_towns or town not in landings or town == start.map_id:
            continue
        seen_towns.add(town)

        landing = landings[town]
        local_graphs = getattr(router.world, "local_graphs", {})
        graph = local_graphs.get(town)
        if graph is None or landing not in graph.edges:
            continue

        object_blockers_map = router.world.object_blockers
        if town not in object_blockers_map:
            raise CartridgeReadError("funding Fly landing lacks static object inventory")
        blockers = object_blockers_map[town]
        if landing in blockers:
            continue

        projected = replace(
            start,
            map_id=town,
            at=landing,
            last_outside_map=town,
            occupied=blockers,
            hazards=(),
        )

        scope_maps = funding_scope(router.world.macro_graph, projected)
        if any(m not in local_graphs for m in scope_maps):
            continue

        zones: list[TrainerSightZone] = []
        for map_id in sorted(scope_maps):
            headers = trainer_headers(rom, {map_id}, full_event_offsets=True)
            events = map_object_events(rom, {map_id})
            zones.extend(static_trainer_sight_zones(headers, events, raw.event_flags))

        candidates = regional_trainer_funding_candidates(
            rom,
            router.world,
            projected,
            tuple(zones),
            inventoried_maps=scope_maps,
            static_blockers={m: object_blockers_map[m] for m in scope_maps},
        )

        for target in candidates:
            results.append(FundingFlyCandidate(town=town, landing=landing, target=target))

    if reader.read() != raw or reader.read_fly_destinations() != destinations:
        raise CartridgeReadError("funding Fly origin or unlocks changed during planning")
    return tuple(results)
