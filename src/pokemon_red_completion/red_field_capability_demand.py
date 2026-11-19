"""Private conditional route witnesses for an observed missing Cut capability.

Relevance projections are never executable routes or invented native facts.
Existing story gates/static encounters remain; actual story execution must quote
again with its actual party, occupancy and trainer hazards after the exchange.
"""
from dataclasses import dataclass, replace, asdict
from hashlib import sha256

from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .gen1_traversal import CUT_CAPABILITY
from .global_router import GlobalRouterError
from .observation import Badge, ItemId
from .provenance import canonical_sha256
from .red_player_story_travel import DESTINATIONS, story_destination_map
from .red_story_map_frontier import story_object_preview
from .red_training_ground_route import ground_route_capability_projector
from .route_plan import RoutePlanningError


@dataclass(frozen=True)
class CutDependencyWitness:
    objective_ref: str
    destination_map: int
    route_sha256: str
    cut_count: int


def _relevance_plan(world, start, destination):
    try:
        return world.plan_feasible_to_map(start, destination)
    except (RoutePlanningError, GlobalRouterError):
        # Existing complete one-Cut search is relevance-only;retain nontrainer
        # hazards in the occupied representation just as story_frontier_target.
        guarded = replace(start, occupied=start.occupied | frozenset(h.at for h in start.hazards))
        return world.plan_to_map(guarded, destination)


def quote_missing_cut_dependencies(world, start, destinations):
    """Compare legal destinations under no-Cut and Cut-only private probes."""
    preview, base = story_object_preview(world, start)
    without = replace(base, capabilities=base.capabilities - {CUT_CAPABILITY})
    with_cut = replace(without, capabilities=without.capabilities | {CUT_CAPABILITY})
    result = []
    for objective, destination in sorted(destinations):
        try:
            _relevance_plan(preview, without, destination)
        except (RoutePlanningError, GlobalRouterError):
            pass
        else:
            continue
        try:
            plan = _relevance_plan(preview, with_cut, destination)
        except (RoutePlanningError, GlobalRouterError):
            continue
        steps = tuple(dict(kind=s.kind, map=s.expected_map, at=s.expected_at) for s in plan.steps)
        count = sum(s.kind == "cut_mutation" for s in plan.steps)
        if count:
            result.append(CutDependencyWitness(objective, destination, canonical_sha256(steps), count))
    return tuple(result)


def observed_cut_dependencies(runtime, observation, *, route, post_return_moves=None):
    """Only observed badge/HM permission and legal unfinished route metadata."""
    raw = runtime.reader.read()
    if (raw.bag_items is None or dict(raw.bag_items).get(int(ItemId.HM01_CUT), 0) <= 0
            or type(raw.badge_bits) is not int or not raw.badge_bits & int(Badge.CASCADE)):
        return ()
    moves = raw.party_moves if post_return_moves is None else post_return_moves
    if moves is None or any(15 in row for row in moves):
        return ()
    source = runtime.emulator.save_state_bytes()
    legal = {o.id for o in runtime.adapter.graph.available_objectives(observation.game_state)}
    destinations = tuple((o, story_destination_map(o, raw)) for o in sorted(legal & DESTINATIONS.keys()))
    if not destinations:
        return ()
    world = route.route_world.with_current_observation(runtime.reader)
    start = Gen1TraversalObserver(runtime.reader,
        capability_projector=ground_route_capability_projector(route, runtime.emulator),
        hazard_projector=Gen1TrainerSightProjector(route.rom, runtime.reader, full_event_offsets=True)).observe()
    witnesses = quote_missing_cut_dependencies(world, start, destinations)
    if runtime.emulator.save_state_bytes() != source:
        raise ValueError("conditional field-capability probe changed native state")
    return witnesses


def post_return_field_moves(runtime, custody):
    """Observe remaining party plus the exact boxed original,without a PC input."""
    guard = runtime.adapter.party_guard
    refs = guard.reader.preparation_specimen_refs()
    originals = [m for m in runtime.reader.read_box_specimen_identities() if m.preparation_ref == custody.displaced_ref]
    if len(originals) != 1:
        raise ValueError("field-carrier return needs its unique boxed original")
    original = originals[0]
    moves = [m for m in runtime.reader.read_box_move_members(original.box_index) if m.box_slot == original.box_slot]
    if len(moves) != 1:
        raise ValueError("field-carrier return lacks observed original moves")
    remaining = tuple(row for ref,row in zip(refs,runtime.reader.read().party_moves,strict=True)if ref != custody.carrier_ref)
    return remaining + (moves[0].moves,)


def dependency_witness_sha256(witnesses):
    return canonical_sha256(tuple(asdict(w) for w in witnesses))
