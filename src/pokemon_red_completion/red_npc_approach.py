"""Choose a reachable interaction side from cartridge objects and current terrain."""

from dataclasses import replace

from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import (
    Gen1TrainerSightProjector,
    static_trainer_sight_zones,
    trainer_headers,
    trainer_sight_zones,
)
from .gen1_traversal import cut_capabilities, map_object_events
from .red_routed_trainer_funding import _face_trainer_boundary
from .red_training_ground_route import RedVermilionGroundTransition
from .route_plan import RoutePlanningError


def approach_npc(
    emulator, reader, actions, *, rom, map_id, object_index, maximum_readiness_waits=16
):
    objects = [o for o in map_object_events(rom, {map_id}) if o.object_index == object_index]
    if len(objects) != 1:
        raise ValueError("NPC interaction requires one cartridge object")
    target = objects[0]
    if target.movement != 255:
        raise ValueError("NPC approach requires a stationary object")
    route = replace(
        RedVermilionGroundTransition.from_rom(rom), full_event_offsets=True, observe_terrain=True,
        maximum_readiness_waits=maximum_readiness_waits,
    )
    observer = Gen1TraversalObserver(
        reader,
        hazard_projector=Gen1TrainerSightProjector(rom, reader, full_event_offsets=True),
        capability_projector=cut_capabilities,
    )
    start = observer.observe()
    # Hazard tiles are separate from occupied tiles. The route executor refuses
    # them, so they cannot be selected as the interaction destination either.
    reserved = {hazard.at for hazard in start.hazards} if start.map_id == map_id else set()
    headers = trainer_headers(rom, {map_id}, full_event_offsets=True)
    objects_on_map = map_object_events(rom, {map_id})
    raw = reader.read()
    zones = (
        trainer_sight_zones(headers, objects_on_map, raw, reader.read_current_map_objects())
        if raw.map_id == map_id
        else static_trainer_sight_zones(headers, objects_on_map, raw.event_flags)
    )
    reserved.update(tile for zone in zones for tile in zone.lane)
    world = route.route_world.with_current_blocks(reader.read_current_map_blocks())
    choices = []
    for dy, dx, facing in ((1, 0, "up"), (0, -1, "right"), (0, 1, "left"), (-1, 0, "down")):
        at = (target.y + dy, target.x + dx)
        if at in reserved:
            continue
        try:
            # Optimistic plans may cross a trainer's reserved sight corridor.
            # Select only executable interaction sides, before routing there.
            plan = world.plan_feasible_to_map(start, map_id, goal_at=at)
        except RoutePlanningError:
            continue
        choices.append(
            (
                len(plan.terminal_approach.edges)
                + sum(len(s.approach.edges) + 1 for s in plan.segments),
                at,
                facing,
            )
        )
    if not choices:
        raise RoutePlanningError("no reachable NPC interaction side")
    _, at, facing = min(choices)
    replace(route, destination_map=map_id, destination_at=at)(actions, reader, emulator)
    raw = reader.read()
    if raw.map_id != map_id or (raw.player_y, raw.player_x) != at or raw.battle_state:
        raise RuntimeError("NPC approach did not reach its field boundary")
    _face_trainer_boundary(actions, reader, facing)
    return {"map_id": map_id, "object_index": object_index, "at": at, "facing": facing}
