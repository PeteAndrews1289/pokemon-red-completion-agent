"""Explicitly enter one observed trainer's sight; never relax travel hazards."""

from . import silph
from .actions import MacroAction, MacroActionKind


def planned_sight_approaches(world, start, zones, contract):
    """Safe real routes to one-step engagement; offscreen previews never authorize input."""
    from dataclasses import replace

    from .route_plan import RoutePlanningError

    if start.map_id != contract.map_id:
        return ()
    matches = [z for z in zones if z.event_flag == contract.defeated_event and not z.defeated]
    if len(matches) != 1:
        return ()
    target = matches[0]
    preview = tuple(replace(z, visible=True) if z is target else z for z in zones)
    blocked = start.occupied | frozenset(h.at for h in start.hazards)
    result = []
    for at, edges in world.local_graphs[start.map_id].edges.items():
        if at in blocked or not any(e.target in target.lane for e in edges):
            continue
        try:
            edge = sight_entry_edge(replace(start, at=at), edges, preview, contract)
            plan = world.plan_feasible_to_map(start, start.map_id, goal_at=at)
        except (ValueError, RoutePlanningError):
            continue
        result.append((plan, edge))
    return tuple(result)


def sight_entry_edge(start, edges, zones, contract):
    """Choose an adjacent walk into exactly the declared, visible trainer lane."""
    if not start.ready or start.interruption is not None or start.map_id != contract.map_id:
        raise ValueError("sight entry requires a ready field boundary")
    matches = [
        z
        for z in zones
        if z.event_flag == contract.defeated_event
        and (z.trainer_class, z.trainer_class - 200, z.trainer_set) == contract.trainer_identity
        and z.map_id == contract.map_id
        and not z.defeated
        and z.visible
    ]
    if len(matches) != 1:
        raise ValueError("sight entry requires one live declared trainer")
    target = matches[0]
    choices = []
    for edge in edges:
        dy, dx = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}.get(
            edge.action, (0, 0)
        )
        if (
            edge.kind != "walk"
            or edge.action_kind is not MacroActionKind.MOVE
            or edge.transient is not None
            or edge.requirements
            or edge.required_mode not in {None, "land"}
            or edge.result_mode not in {None, "land"}
            or start.mode != "land"
            or edge.target != (start.at[0] + dy, start.at[1] + dx)
            or edge.target in start.occupied
            or edge.target not in target.lane
        ):
            continue
        if any(z is not target and not z.defeated and edge.target in z.lane for z in zones):
            continue
        if any(h.at == edge.target and h.kind != "trainer_sight" for h in start.hazards):
            continue
        choices.append(edge)
    if not choices:
        raise ValueError("no unambiguous adjacent trainer sight entry")
    return min(choices, key=lambda e: (e.target, e.action))


def enter_story_sight(reader, actions, *, edge, contract, rom):
    """Execute the validated one-step engagement, then authenticate the opponent.

    Caller must derive the edge from the current observation immediately before
    this call. The battle controller still checks its own independent contract.
    """
    dy, dx = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}[edge.action]
    raw = reader.read()
    if (
        raw.battle_state
        or raw.map_id != contract.map_id
        or not reader.read_input_readiness().ready
        or (raw.player_y + dy, raw.player_x + dx) != edge.target
    ):
        raise ValueError("sight entry source changed before engagement")
    actions.execute(MacroAction(MacroActionKind.MOVE, edge.action))

    def settle_wild():
        from .gen1_route_runtime import Gen1TraversalObserver
        from .red_player_wild_recovery import retained_native_static_target

        encounter = reader.read()
        if (
            encounter.battle_state != 1
            or encounter.map_id != contract.map_id
            or (encounter.player_y, encounter.player_x) != edge.target
            or retained_native_static_target(reader, rom) is not None
        ):
            raise RuntimeError("sight entry wild interruption changed the declared boundary")
        # The final sight-entry input is outside the walking route's handler.
        # Reuse one bounded ordinary escape, never confirm through a wild fight
        # or treat its outcome as the selected trainer's victory.
        receipt = flee.handle(Gen1TraversalObserver(reader).observe())
        after = reader.read()
        if (
            receipt.kind != "wild_battle"
            or receipt.details.get("verified") is not True
            or receipt.resumed_map != contract.map_id
            or receipt.resumed_at != edge.target
            or after.battle_state != 0
            or (after.map_id, after.player_y, after.player_x)
            != (contract.map_id, *edge.target)
        ):
            raise RuntimeError("sight entry wild recovery lost the declared trainer boundary")
        record = getattr(actions, "record_diagnostic_event", None)
        if callable(record):
            record("story_sight_wild_recovery", dict(
                objective=contract.objective_id, learned=False,
                supplied_strategy=False, receipt=receipt.details,
            ))

    from .gen1_route_runtime import Gen1WildFleeHandler

    flee = Gen1WildFleeHandler(
        actions, reader, maximum_flees=1, stabilization_frames=120,
        route_name="model-selected trainer sight entry",
    )
    silph._await_trainer_battle(
        actions, reader, silph.DEFAULT_SILPH_TIMING, settle_wild=settle_wild,
    )
    raw = reader.read()
    if (
        raw.battle_state != 2
        or raw.map_id != contract.map_id
        or reader.read_active_trainer_identity() != contract.trainer_identity
    ):
        raise RuntimeError("sight engagement did not reach the declared trainer")
