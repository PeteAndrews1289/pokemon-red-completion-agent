"""Quote a next map boundary toward a story destination, not an executable shortcut."""

from dataclasses import replace
from functools import lru_cache

from .gen1_acquisition import static_encounters
from .route_plan import RoutePlanningError


@lru_cache(maxsize=2)
def _static_capture_locations(rom):
    """Scripted encounters are not ordinary NPCs that a relevance quote may erase."""
    return tuple((entry.map_id, entry.at) for entry in static_encounters(rom))


def story_cut_frontier_target(world, start, destination_at):
    """Quote a real Cut endpoint before trainer sight, then reobserve/replan.

    A tree can occupy the safe tile needed for a later sight-entry quote. Never
    execute the relaxed preview: independently quote the post-Cut tile with all
    original hazards and occupancy, and require an actual Cut in that route.
    """
    preview, probe = story_object_preview(world, start)
    plan = preview.plan_feasible_to_map(probe, start.map_id, goal_at=destination_at)
    cut_seen = False
    blocked = start.occupied | frozenset(h.at for h in start.hazards)
    for step in plan.steps:
        if step.expected_map != start.map_id or step.expected_at in blocked:
            break
        if step.kind == "cut_mutation":
            cut_seen = True
            continue
        if not cut_seen or step.expected_at == start.at:
            continue
        real = world.plan_feasible_to_map(start, start.map_id, goal_at=step.expected_at)
        if any(s.kind == "cut_mutation" for s in real.steps):
            return step.expected_at
    raise RoutePlanningError("no safe story Cut frontier before the obstruction")


def story_object_preview(world, start):
    """Non-executable relevance projection; all story/terrain gates remain."""
    locations = (_static_capture_locations(world.rom) if getattr(world, "rom", None) else ())
    protected = {
        m: frozenset(at for map_id, at in locations if map_id == m)
        for m in world.object_blockers
    }
    # Keep only still-present capture objects. Cleared encounters already removed
    # by live observation remain clear; event-backed passage guards remain below.
    preview = replace(world, object_blockers={
        m: occupied & protected[m] for m, occupied in world.object_blockers.items()
    })
    preview = replace(
        preview, local_graphs={m: preview._graph_for_terrain(t) for m, t in preview.terrain.items()}
    )
    probe = replace(
        start,
        occupied=start.occupied & protected.get(start.map_id, frozenset()),
        hazards=tuple(h for h in start.hazards if h.kind != "trainer_sight"),
    )
    return preview, probe


def story_frontier_target(world, start, destination):
    """Find the next connecting passage past future NPCs for a REAL re-quote.

    Object-free geometry is ONLY a relevance query. Callers must quote and
    execute the coordinate using original occupancy, sight and story gates.
    """
    if start.map_id == destination:
        return destination, start.at
    preview, probe = story_object_preview(world, start)
    try:
        plan = preview.plan_feasible_to_map(probe, destination)
    except RoutePlanningError:
        # The cheap Cut search considers only the topology-shortest corridor.
        # A closed story gate there can hide a legal, longer Cut route. Reuse
        # the existing complete search for relevance ONLY; the next boundary
        # still needs a real occupancy/sight-aware quote before execution.
        # The historical search reserves occupancy, not the hazard field.
        # Preserve nontrainer hazards in that representation as well.
        guarded = replace(probe, occupied=frozenset(h.at for h in probe.hazards))
        plan = preview.plan_to_map(guarded, destination)
    edge = next(s for s in plan.steps if s.expected_map != start.map_id)
    return edge.expected_map, edge.expected_at
