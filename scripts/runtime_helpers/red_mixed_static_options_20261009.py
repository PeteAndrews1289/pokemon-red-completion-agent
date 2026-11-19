"""Existing local one-offs and routed Master Ball capture as real peers.

No legacy session/admission dispatch, target ordering, supplied resources or
teacher combat. Discovery executes nothing; native providers own verification.
"""

from functools import partial
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.red_capture_preparation import require_capture_party
from pokemon_red_completion.red_capture_lead import RedCaptureLeadError
from pokemon_red_completion.red_resource_goal_router import collection_field_capabilities
from pokemon_red_completion.red_routed_static_capture import RedRoutedStaticCaptureGoalProvider
from pokemon_red_completion.red_static_capture import red_static_capture_targets
from pokemon_red_completion.red_static_capture_goal import RedStaticCaptureGoalProvider
from pokemon_red_completion.route_plan import RoutePlanningError


class NoncombatStaticTransport:
    """Unexpected trainers remain a native checkpoint, never teacher combat."""
    def __init__(self, inner):
        self.inner = inner

    @property
    def handled_hazard_kinds(self):
        return self.inner.handled_hazard_kinds

    @property
    def handled_interruption_kinds(self):
        return self.inner.handled_interruption_kinds

    def handle(self, interruption):
        from pokemon_red_completion.route_executor import RouteExecutionError
        if interruption.interruption in {'trainer_engagement', 'battle:2', 'scripted_dialogue'}:
            raise RouteExecutionError('selected static transport requires ordinary player settlement')
        return self.inner.handle(interruption)


def observed_cave_entrance_world(runtime, world):
    """Remove only the cartridge guard proven hidden by its native toggle.

    Initial off-map occupancy is not the postgame native object state. Live
    arrival still replaces the entire active-map projection. No badge or
    remembered victory substitutes for the observed hidden-object flag.
    """
    from pokemon_red_completion.red_field_item import _field_item_toggle_indices
    from pokemon_red_completion.gen1_traversal import map_object_events
    index = _field_item_toggle_indices(world.rom).get((3, 10))
    objects = tuple(e for e in map_object_events(world.rom, {3}) if e.object_index == 10)
    if index is None or len(objects) != 1 or objects[0].at != (12, 4):
        raise ValueError('cartridge cave entrance guard identity differs')
    if not runtime.reader.read_toggleable_object_hidden(index):
        return world
    blocked = world.object_blockers[3] - {objects[0].at}
    if blocked == world.object_blockers[3]:
        return world
    observed = replace(world, object_blockers={**world.object_blockers, 3: blocked})
    return replace(observed, local_graphs={**world.local_graphs,
        3: observed._graph_for_terrain(world.terrain[3])})


def prepared_master_binding(runtime, observation, actions, world, target, directory, observer):
    """Quote Fly plus the existing cave route; execute only after selection."""
    from pokemon_red_completion.red_collection_fly import red_fly_landings
    from pokemon_red_completion.red_routed_static_capture import prepared_static_acquisition_binding
    from pokemon_red_completion.red_resource_goal_router import _supported_plan
    from pokemon_red_completion.gen1_field_moves import fly_menu_indices, Gen1FieldMoveError
    from pokemon_red_completion.observation import MapId
    import red_current_source_preparation_20261004 as prep

    start = observer.observe()
    if (not start.ready or start.interruption is not None or start.mode != 'land'
            or 3 not in runtime.reader.read_fly_destinations()):
        return None
    # Match route_to's supported source departure before quoting a future Fly
    # landing. A living Fly holder alone cannot leave a one-way indoor room.
    world = world.with_current_observation(runtime.reader)
    same_cave = False
    if start.map_id != target.map_id:
        same_cave = prep.same_cave_transit(start.map_id, target.map_id)
        if start.map_id >= 0x25 and not same_cave:
            departure = prep.source_departure(start, world, observation.raw)
            if departure is None:
                return None
            start = replace(start, map_id=departure.terminal_map,
                at=departure.terminal_at, mode=departure.terminal_mode or "land",
                last_outside_map=departure.terminal_map,
                occupied=frozenset(), hazards=())
    landing = start
    if start.map_id != target.map_id and start.map_id != 3 and not same_cave:
        try:
            fly_menu_indices(observation.raw)
        except Gen1FieldMoveError:
            return None
        # Conditional geometry only; native execution still walks the departure,
        # flies and reobserves actual destination objects before each route.
        landing = replace(start, map_id=3, at=dict(red_fly_landings(world.rom))[3],
                          last_outside_map=3, occupied=frozenset(), hazards=())
    plans = []
    for dy, dx in ((1,0),(0,-1),(0,1),(-1,0)):
        at = (target.at[0]+dy, target.at[1]+dx)
        if min(at) < 0:
            continue
        try:
            plan = world.plan_feasible_to_map(landing, target.map_id, goal_at=at)
        except RoutePlanningError:
            continue
        if (plan.terminal_mode in (None,'land') and len(plan.steps) <= 1500
                and _supported_plan(plan,allow_cut=True,allow_surf=True,
                                    seafoam_state=runtime.reader.read())):
            plans.append(plan)
    if not plans:
        return None
    arrival = min(plans,key=lambda p:(p.cost,p.terminal_at)).terminal_at

    def execute(_target):
        from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
        from pokemon_red_completion.goal_manager import GoalDecisionOutcome
        from red_earned_collection_connection_20261005 import restore_metered_collection_party
        from pokemon_red_completion.red_pc_storage import face_pc_boundary
        before = actions.actions_executed, runtime.emulator.frame_count
        session = SimpleNamespace(rt=runtime,em=runtime.emulator,ctrl=runtime.emulator,
                                  actions=actions,output=directory.parent)
        prep.route_to(session,world,town=3,map_id=target.map_id,at=arrival,
                      route_handler_wrapper=NoncombatStaticTransport)
        prep.prepare_static_facing(session,target)
        provider = RedStaticCaptureGoalProvider(world.rom,target,ItemId.MASTER_BALL,1,
            runtime.reader,runtime.adapter,runtime.emulator,actions,directory,
            prepare_status=False,weaken_capture=False,prepare_facing=False)
        native = provider.offer(runtime.adapter.observe()).binding
        if native is None:
            raise RuntimeError('selected Master Ball arrival did not requalify')
        report = native.execute()
        if native.verify(report).status is not GoalDecisionOutcome.SUCCEEDED:
            raise RuntimeError('native Master Ball outcome was not verified')
        prep.route_to(session,world,town=3,map_id=int(MapId.CERULEAN_POKECENTER),at=(3,3),
                      allow_surf_origin=True,route_handler_wrapper=NoncombatStaticTransport)
        face_pc_boundary(actions,runtime.reader,'up')
        restore_metered_collection_party(runtime,actions)
        runtime.adapter.party_guard.verify_active_roster_restored()
        return GoalExecutionReport(actions.actions_executed-before[0],
            runtime.emulator.frame_count-before[1],dict(report.evidence))

    def returned():
        from pokemon_red_completion.red_player_field_goals import _field_ready
        runtime.adapter.party_guard.verify_active_roster_restored()
        return _field_ready(runtime)

    return prepared_static_acquisition_binding(runtime,actions,rom=world.rom,target=target,
        execute_prepared=execute,verify_return=returned,estimated_effort=.25,
        estimated_risk=.05)


def routed_master_bindings(runtime, observation, actions, world):
    raw = observation.raw
    if (not runtime.scripted_gifts or raw.badge_bits != 255
            or dict(raw.bag_items or ()).get(int(ItemId.MASTER_BALL)) != 1
            or 150 in runtime.reader.read_pokedex_state().owned_species):
        return ()
    try:
        require_capture_party(observation)
    except RedCaptureLeadError:
        return ()
    world = observed_cave_entrance_world(runtime, world)
    targets = tuple(t for t in red_static_capture_targets(world.rom)
                    if t.species_number == 150)
    if len(targets) != 1:
        raise ValueError('native Mewtwo source must be unambiguous')
    owner = getattr(runtime.trainer_battle_runner, '__self__', None)
    if owner is None or not hasattr(owner, 'output'):
        return ()
    directory = Path(owner.output).parent / ('mixed-master-'
        + sha256(runtime.emulator.save_state_bytes()).hexdigest()[:16])
    capture = RedStaticCaptureGoalProvider(world.rom, targets[0], ItemId.MASTER_BALL, 1,
        runtime.reader, runtime.adapter, runtime.emulator, actions, directory,
        prepare_status=False, weaken_capture=False, prepare_facing=True)
    observer = Gen1TraversalObserver(runtime.reader,
        capability_projector=partial(collection_field_capabilities, runtime.emulator,
                                     allow_cut=True, allow_surf=True),
        hazard_projector=Gen1TrainerSightProjector(world.rom, runtime.reader,
                                                  full_event_offsets=True))
    binding = prepared_master_binding(runtime,observation,actions,world,targets[0],
                                     directory,observer)
    if binding is None:
        binding = RedRoutedStaticCaptureGoalProvider(capture, world, observer,
            maximum_actions=20000, maximum_frames=2000000).offer(observation).binding
    return () if binding is None else (binding,)


def postgame_native_oneoff_bindings(runtime, observation, actions, world):
    from red_remaining_static_20261004 import local_static_bindings
    from red_dojo_gift_20261004 import local_dojo_gift_bindings
    local = tuple(b for b in local_static_bindings(runtime, observation, actions, world)
                  if not b.binding_ref.startswith('pokemon.red:static-capture:227:'))
    return (local + local_dojo_gift_bindings(runtime, observation, actions, world)
            + routed_master_bindings(runtime, observation, actions, world))
