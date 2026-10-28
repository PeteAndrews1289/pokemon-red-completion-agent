"""Quote a reachable trainer whose sight blocks the selected story destination.

Hypothetical sight removal is a planning query ONLY. It never edits native
events, executes movement or supplies an executable route through unbeaten sight.
The actual trainer interaction must use the original guarded observation.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace

from .gen1_field_moves import surf_permission
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector, trainer_headers, trainer_sight_zones
from .gen1_traversal import cut_capabilities, map_object_events, surf_capabilities
from .goal_manager_runtime import ExecutableGoalBinding
from .red_player_field_goals import _field_ready
from .red_player_story_battle import story_battle_binding
from .red_player_story_travel import DESTINATIONS, story_destination_map
from .red_story_battle import StoryTrainerContract
from .red_story_map_frontier import story_frontier_target, story_object_preview
from .red_story_sight_entry import planned_sight_approaches
from .red_trainer_funding import local_trainer_funding_candidates
from .route_plan import RoutePlanningError


@dataclass(frozen=True)
class SightObstructionCandidate:
    trainer: object
    approach: object


def blocking_story_trainers(
    rom, world, start, zones, destination, *, allow_sequence=False, destination_at=None
):
    """All safely approachable local trainers whose defeat would open a route."""
    if type(allow_sequence) is not bool:
        raise TypeError("explicit sequential-obstruction scope required")
    try:
        world.plan_feasible_to_map(
            start,
            destination,
            **({"goal_at": destination_at} if destination_at is not None else {}),
        )
    except RoutePlanningError:
        pass
    else:
        return ()
    candidates = local_trainer_funding_candidates(
        rom, world, start, zones, allow_ledges=True, allow_cut=True, allow_forced_motion=True
    )
    result = []
    for candidate in candidates:
        target = candidate.trainer
        other_lanes = {at for t in zones if t != target and t.active for at in t.lane}
        removed = set(target.lane) - other_lanes
        hypothetical = replace(
            start,
            hazards=tuple(
                h for h in start.hazards if not (h.kind == "trainer_sight" and h.at in removed)
            ),
        )
        try:
            world.plan_feasible_to_map(
                hypothetical,
                destination,
                **({"goal_at": destination_at} if destination_at is not None else {}),
            )
        except RoutePlanningError:
            continue
        result.append(candidate)
    if result or not allow_sequence:
        return tuple(result)
    # A chain of trainers may prevent any single defeat from opening the exit.
    # Use a non-executable hypothetical route to identify its FIRST obstruction;
    # only a safely approachable trainer from the original inventory may be offered.
    active = tuple(t for t in zones if t.active)
    lanes = {at for t in active for at in t.lane}
    hypothetical = replace(
        start,
        hazards=tuple(
            h for h in start.hazards if not (h.kind == "trainer_sight" and h.at in lanes)
        ),
    )
    try:
        plan = world.plan_feasible_to_map(
            hypothetical,
            destination,
            **({"goal_at": destination_at} if destination_at is not None else {}),
        )
    except RoutePlanningError:
        # A later scripted NPC may block the map even after ordinary sight
        # clears. The relaxed route is ONLY a first-obstacle relevance query.
        from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld

        if not isinstance(world, StrategicScenarioRouteWorld):
            return ()
        try:
            preview, probe = story_object_preview(world, start)
            plan = preview.plan_feasible_to_map(
                probe,
                destination,
                **({"goal_at": destination_at} if destination_at is not None else {}),
            )
        except RoutePlanningError:
            return ()
    for step in plan.steps:
        if step.expected_map == start.map_id and step.expected_at in start.occupied:
            return ()  # Unknown scripted objects require their own mechanic.
        if step.expected_map != start.map_id or step.expected_at not in lanes:
            continue
        owners = [t for t in active if step.expected_at in t.lane]
        if len(owners) != 1:
            return ()  # No claimed first defeat can clear shared sight alone.
        adjacent = tuple(c for c in candidates if c.trainer == owners[0])
        if adjacent:
            return adjacent
        target = owners[0]
        from types import SimpleNamespace

        contract = SimpleNamespace(
            map_id=start.map_id,
            defeated_event=target.event_flag,
            trainer_identity=(target.trainer_class, target.trainer_class - 200, target.trainer_set),
        )
        sights = planned_sight_approaches(world, start, zones, contract)
        if not sights:
            return ()
        return (SightObstructionCandidate(target, min(sights, key=lambda x: x[0].cost)[0]),)
    return ()


def obstructing_story_battle_binding(
    runtime,
    actions,
    *,
    objective_id,
    route,
    battler,
    intermediate_map=None,
    allow_sequence=False,
    frontier=False,
    destination_at=None,
    before_challenge=None,
    trainer_battler_for_contract=None,
    allow_surf=False,
    observe_binding: Callable[[StoryTrainerContract, ExecutableGoalBinding], None] | None = None,
):
    if observe_binding is not None and not callable(observe_binding):
        raise TypeError("obstruction binding observer must be callable")
    if type(allow_surf) is not bool:
        raise TypeError("story obstruction Surf scope must be boolean")
    if allow_surf and getattr(route, "allow_surf", False) is not True:
        raise ValueError("story obstruction Surf quote requires a Surf-enabled native executor")
    if trainer_battler_for_contract is not None and not callable(trainer_battler_for_contract):
        raise TypeError("obstruction battler resolver must be callable")
    if objective_id not in DESTINATIONS:
        raise ValueError("undeclared story destination")
    if type(frontier) is not bool or (frontier and intermediate_map is not None):
        raise ValueError("frontier and fixed intermediate scopes differ")
    if destination_at is not None and (
        frontier
        or intermediate_map is not None
        or not isinstance(destination_at, tuple)
        or len(destination_at) != 2
        or any(type(v) is not int or v < 0 for v in destination_at)
    ):
        raise ValueError("explicit final interaction target requires an unambiguous story scope")
    if not _field_ready(runtime):
        return None
    raw = runtime.reader.read()

    def field_capabilities(raw):
        return cut_capabilities(raw) | surf_capabilities(
            raw, surf_allowed=surf_permission(runtime.emulator, raw).allowed,
        )

    start = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=field_capabilities if allow_surf else cut_capabilities,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()
    destination = story_destination_map(objective_id, raw)
    if frontier:
        try:
            destination, destination_at = story_frontier_target(
                route.route_world, start, destination
            )
        except RoutePlanningError:
            return None
    if intermediate_map is not None:
        if type(intermediate_map) is int and intermediate_map == start.map_id:
            return None
        from .global_router import find_macro_path

        corridor = find_macro_path(
            route.route_world.macro_graph,
            start.map_id,
            destination,
            last_outside=start.last_outside_map,
        )
        if type(intermediate_map) is not int or intermediate_map not in corridor.maps[1:]:
            raise ValueError("obstruction intermediate is outside the story corridor")
        destination = intermediate_map
    zones = trainer_sight_zones(
        trainer_headers(route.rom, {raw.map_id}, full_event_offsets=True),
        map_object_events(route.rom, {raw.map_id}),
        raw,
        runtime.reader.read_current_map_objects(),
    )
    candidates = blocking_story_trainers(
        route.rom,
        route.route_world,
        start,
        zones,
        destination,
        allow_sequence=allow_sequence,
        destination_at=destination_at,
    )
    if not candidates:
        return None
    # Adapter-private obstacle planning, not a learned choice among trainers.
    target = min(candidates, key=lambda c: c.approach.cost)
    contract = StoryTrainerContract.from_cartridge(
        route.rom,
        raw,
        objective_id=objective_id,
        battle_plan_id="observed-story-obstruction",
        map_id=raw.map_id,
        defeated_event=target.trainer.event_flag,
    )
    actor = (
        battler if trainer_battler_for_contract is None else trainer_battler_for_contract(contract)
    )
    binding = story_battle_binding(
        runtime,
        actions,
        contract=contract,
        route=route,
        battler=actor,
        completes_objective=False,
        before_challenge=before_challenge,
    )
    # Disclose only the exact contract whose current approach was admitted.
    # A failed probe supplies no witness; this observer cannot select the actor.
    if binding is not None and observe_binding is not None:
        observe_binding(contract, binding)
    return binding
