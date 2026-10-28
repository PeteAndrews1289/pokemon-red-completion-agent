"""Reach an already selected Mansion venue through observed native transport."""

from .actions import MacroAction, MacroActionKind
from .gen1_field_moves import Gen1FieldMovePort
from .gen1_route_runtime import Gen1TraversalObserver
from .observation import MapId
from .red_collection_fly import red_fly_landings
from .red_training_ground_route import RedVermilionGroundTransition
from .red_training_transitions import red_training_fly_available


def mansion_native_heal_and_return(actions, reader, emulator, *, world, legacy):
    """Transport to the Cinnabar nurse before the existing local return skill.

    A PC loan need not retain Dig. Route planning, visited Fly destinations,
    living move holders and the observed cursor remain the existing adapters'
    responsibility. This executes the selected venue; it never selects another.
    """
    raw = reader.read()
    if raw.battle_state or not reader.read_input_readiness().ready:
        raise ValueError("Mansion return requires settled native field control")

    def ground(destination, at):
        RedVermilionGroundTransition(
            rom=world.rom, route_world=world,
            destination_map=int(destination), destination_at=at,
            full_event_offsets=True, observe_terrain=True, allow_surf=True,
            allow_wild_faints=True, allow_field_faint_dialogue=True,
        )(actions, reader, emulator)

    local_maps = {int(MapId.CINNABAR_ISLAND), int(MapId.CINNABAR_POKECENTER),
                  int(MapId.POKEMON_MANSION_1F)}
    if raw.map_id not in local_maps and red_training_fly_available(raw):
        if int(MapId.CINNABAR_ISLAND) in reader.read_fly_destinations():
            start = Gen1TraversalObserver(reader).observe()
            outside = start.map_id if 0 <= start.map_id <= 0x24 else start.last_outside_map
            landings = dict(red_fly_landings(world.rom))
            if outside not in landings:
                raise ValueError("Mansion transport lacks an observed outdoor Fly boundary")
            if start.map_id != outside:
                ground(outside, landings[outside])
            receipt = Gen1FieldMovePort(actions, reader, emulator).execute(
                MacroAction(MacroActionKind.FIELD_MOVE, "fly:cinnabar_island")
            )
            if (receipt.destination_map != int(MapId.CINNABAR_ISLAND)
                    or receipt.flight_confirmations != 1
                    or reader.read().map_id != int(MapId.CINNABAR_ISLAND)):
                raise ValueError("Mansion transport did not verify Cinnabar Fly arrival")

    raw = reader.read()
    if (raw.map_id, raw.player_y, raw.player_x) != (int(MapId.CINNABAR_POKECENTER), 3, 3):
        ground(MapId.CINNABAR_POKECENTER, (3, 3))
    raw = reader.read()
    if ((raw.map_id, raw.player_y, raw.player_x) != (int(MapId.CINNABAR_POKECENTER), 3, 3)
            or raw.battle_state or not reader.read_input_readiness().ready):
        raise ValueError("Mansion return did not reach the settled Cinnabar nurse")
    legacy(actions, reader, emulator)
    raw = reader.read()
    if ((raw.map_id, raw.player_y, raw.player_x) != (int(MapId.POKEMON_MANSION_1F), 27, 5)
            or raw.battle_state):
        raise ValueError("Mansion return did not verify its native venue boundary")


def mansion_native_transport_ready(runtime, world, party):
    """Quote the existing return commute with the exact retained field helpers.

    These are planned traversal endpoints, never manufactured game observations.
    A failed known route means unavailable; unexpected adapter faults stay typed.
    """
    from dataclasses import replace
    from types import SimpleNamespace
    from .red_resource_goal_router import _supported_plan
    from .red_training_ground_route import ground_route_capability_projector
    from .route_plan import RoutePlanningError

    raw = runtime.reader.read()
    if not party.members:
        return False
    projected = replace(raw, party_count=party.size,
        party_species_ids=tuple(m.species_id for m in party.members),
        party_hp=tuple(m.hp for m in party.members),
        party_moves=tuple(tuple(move.move_id for move in m.moves) for m in party.members))
    permissions = ground_route_capability_projector(SimpleNamespace(allow_surf=True), runtime.emulator)
    start = Gen1TraversalObserver(runtime.reader,
        capability_projector=lambda _observed: permissions(projected)).observe()
    if not start.ready or start.interruption is not None or start.mode != "land":
        return False
    current = world.with_current_observation(runtime.reader)

    def arrive(plan):
        return replace(start, map_id=plan.terminal_map, at=plan.terminal_at,
            mode=plan.terminal_mode, occupied=frozenset(), hazards=(),
            last_outside_map=(plan.terminal_map if plan.terminal_map <= 0x24
                              else start.last_outside_map))

    def quote(destination, at):
        plan = current.plan_feasible_to_map(start, int(destination), goal_at=at)
        if not _supported_plan(plan, allow_cut=True, allow_surf=True, seafoam_state=projected):
            return None
        return plan

    try:
        local_maps = {int(MapId.CINNABAR_ISLAND), int(MapId.CINNABAR_POKECENTER),
                      int(MapId.POKEMON_MANSION_1F)}
        if (start.map_id not in local_maps and red_training_fly_available(projected)
                and int(MapId.CINNABAR_ISLAND) in runtime.reader.read_fly_destinations()):
            outside = start.map_id if start.map_id <= 0x24 else start.last_outside_map
            landings = dict(red_fly_landings(world.rom))
            if outside not in landings:
                return False
            if start.map_id != outside:
                departure = quote(outside, landings[outside])
                if departure is None:
                    return False
                start = arrive(departure)
            # Exactly the destination already used by mansion_native_heal_and_return.
            start = replace(start, map_id=int(MapId.CINNABAR_ISLAND),
                at=landings[int(MapId.CINNABAR_ISLAND)], mode="land",
                occupied=frozenset(), hazards=(), last_outside_map=int(MapId.CINNABAR_ISLAND))
        for destination, at in ((MapId.CINNABAR_POKECENTER, (3, 3)),
                                (MapId.POKEMON_MANSION_1F, (27, 5))):
            route = quote(destination, at)
            if route is None:
                return False
            start = arrive(route)
    except RoutePlanningError:
        return False
    return True
