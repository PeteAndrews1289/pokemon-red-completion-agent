"""One observed indoor-to-outdoor exit, without a chapter route or new input."""

from .actions import MacroActionKind
from .route_plan import RoutePlanningError


def bounded_indoor_departure(start, world):
    outside = start.last_outside_map
    if (
        not start.ready
        or start.interruption is not None
        or start.mode != "land"
        or type(start.map_id) is not int
        or start.map_id < 0x25
        or type(outside) is not int
        or not 0 <= outside <= 0x24
        or outside == 0x0B
    ):
        return None
    try:
        plan = world.plan_feasible_to_map(start, outside)
    except RoutePlanningError:
        return None
    if (
        not plan.steps
        or len(plan.steps) > 128
        or plan.terminal_map != outside
        or plan.terminal_mode not in {None, "land"}
        or any(
            type(s.source_map) is not int
            or s.source_map < 0x25
            or type(s.expected_map) is not int
            or (s.expected_map < 0x25 and s.expected_map != outside)
            or s.kind not in {"walk", "warp", "return"}
            or s.action_kind is not MacroActionKind.MOVE
            or s.action not in {"up", "down", "left", "right"}
            or s.source_mode not in {None, "land"}
            or s.expected_mode not in {None, "land"}
            for s in plan.steps
        )
    ):
        return None
    # A building may contain several interior maps. Require a continuous chain
    # and exactly one outdoor boundary, at the end; never allow outdoor detours.
    current = start.map_id
    for index, step in enumerate(plan.steps):
        if step.source_map != current:
            return None
        if step.expected_map == outside and index != len(plan.steps) - 1:
            return None
        current = step.expected_map
    if current != outside:
        return None
    return plan
