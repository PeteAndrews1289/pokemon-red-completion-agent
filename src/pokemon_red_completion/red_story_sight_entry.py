"""Explicitly enter one observed trainer's sight; never relax travel hazards."""

from . import silph
from .actions import MacroAction, MacroActionKind


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


def enter_story_sight(reader, actions, *, edge, contract):
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
    silph._await_trainer_battle(actions, reader, silph.DEFAULT_SILPH_TIMING)
    raw = reader.read()
    if (
        raw.battle_state != 2
        or raw.map_id != contract.map_id
        or reader.read_active_trainer_identity() != contract.trainer_identity
    ):
        raise RuntimeError("sight engagement did not reach the declared trainer")
