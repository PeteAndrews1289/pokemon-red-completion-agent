"""Metered observed Safari travel, including its reward house; no capture policy."""

from .actions import MacroActionKind
from .gen1_route_runtime import Gen1TraversalObserver
from .observation import MapId
from .red_safari_fishing import SAFARI_FISHING_MAPS, SafariFishingInterruptionHandler
from .route_executor import execute_route

OBJECTIVE_MAPS = SAFARI_FISHING_MAPS | {int(MapId.SAFARI_ZONE_SECRET_HOUSE)}


def require_objective_route(plan, session):
    if (
        not session.in_safari_zone
        or session.safari_game_over
        or session.safari_balls < 2
        or len(plan.steps) + 16 >= session.safari_steps
        or plan.terminal_map not in OBJECTIVE_MAPS
        or plan.terminal_mode not in {None, "land"}
        or any(
            s.source_map not in OBJECTIVE_MAPS
            or s.expected_map not in OBJECTIVE_MAPS
            or s.kind not in {"walk", "warp"}
            or s.action_kind is not MacroActionKind.MOVE
            or s.source_mode not in {None, "land"}
            or s.expected_mode not in {None, "land"}
            for s in plan.steps
        )
    ):
        raise ValueError("Safari objective route is unsupported or exceeds paid steps")


def route_safari_objective(controller, reader, actions, world, *, map_id, at):
    before = reader.read()
    observer = Gen1TraversalObserver(reader)
    start = observer.observe()
    if not start.ready or start.interruption is not None or start.map_id not in OBJECTIVE_MAPS:
        raise ValueError("Safari objective requires a ready paid field origin")
    session = reader.read_safari_session_state()
    plan = world.with_current_blocks(reader.read_current_map_blocks()).plan_feasible_to_map(
        start, map_id, goal_at=at
    )
    require_objective_route(plan, session)
    handler = SafariFishingInterruptionHandler(controller, actions, reader)

    def replan(request):
        replacement = world.with_current_blocks(reader.read_current_map_blocks()).replanner()(
            request
        )
        require_objective_route(replacement, reader.read_safari_session_state())
        return replacement

    report = execute_route(plan, actions, observer, interruption_handler=handler, replanner=replan)
    after = reader.read()
    terminal_session = reader.read_safari_session_state()
    for field in (
        "bag_items",
        "player_money",
        "party_species_ids",
        "party_levels",
        "party_moves",
        "party_pp",
        "party_hp",
        "party_status",
    ):
        if getattr(before, field) != getattr(after, field):
            raise RuntimeError("Safari travel changed protected " + field)
    if (
        not report.passed
        or after.battle_state
        or after.map_id != map_id
        or (after.player_y, after.player_x) != at
        or not reader.read_input_readiness().ready
        or not terminal_session.in_safari_zone
        or terminal_session.safari_game_over
        or terminal_session.safari_balls != session.safari_balls
        or not 16 < terminal_session.safari_steps <= session.safari_steps
    ):
        raise RuntimeError("Safari objective route did not preserve its paid boundary")
    return {
        "map_id": map_id,
        "at": list(at),
        "planned_steps": len(plan.steps),
        "steps_before": session.safari_steps,
        "steps_after": terminal_session.safari_steps,
        "encounters_fled": handler.flees,
    }
