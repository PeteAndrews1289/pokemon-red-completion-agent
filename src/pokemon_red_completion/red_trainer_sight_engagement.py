"""Deliberately trigger one quoted trainer; every other sight lane stays blocked.

Navigation stops at a safe prefix. One ordinary walking edge enters an exclusive
sight tile, then only bounded waits and identity-bound dialogue may start battle.
No combat decision, hazard-wide exception, recovery or retry belongs here.
"""

from dataclasses import dataclass, replace

from .actions import MacroAction, MacroActionKind
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import (
    Gen1TrainerSightProjector,
    TrainerSightZone,
    trainer_headers,
    trainer_sight_zones,
)
from .gen1_traversal import cut_capabilities, map_object_events
from .local_router import LocalEdge
from .red_training_ground_route import RedVermilionGroundTransition
from .route_plan import RoutePlanningError


class TrainerSightEngagementError(RuntimeError):
    """Retain the actual terminal; no automatic trigger retry is authorized."""


@dataclass(frozen=True)
class TrainerSightApproach:
    trainer: TrainerSightZone
    prefix_at: tuple[int, int]
    trigger: LocalEdge
    prefix_steps: int


def plan_sight_approaches(world, start, zones, *, stationary_slots):
    """Quote only safe-prefix, single-walk triggers in the current map."""
    if not start.ready or start.interruption is not None or start.mode != "land":
        return ()
    zones = tuple(z for z in zones if z.map_id == start.map_id and z.active)
    if len({z.sprite_index for z in zones}) != len(zones):
        raise TrainerSightEngagementError("duplicate trainer sight identity")
    hazards = {h.at for h in start.hazards}
    graph = world.local_graphs[start.map_id]
    result = []
    for target in zones:
        if target.sprite_index not in stationary_slots:
            continue
        for prefix, edges in graph.edges.items():
            if prefix in hazards or prefix in start.occupied:
                continue
            for edge in edges:
                if (
                    edge.kind != "walk" or edge.action_kind != MacroActionKind.MOVE
                    or edge.via or edge.transient is not None
                    or edge.next_mode(start.mode) != start.mode
                    or not edge.permits_mode(start.mode)
                    or not edge.requirements.issubset(start.capabilities)
                    or edge.target not in target.lane or edge.target in start.occupied
                    or sum(edge.target in z.lane for z in zones) != 1
                    or any(h.at == edge.target and h.kind != "trainer_sight"
                           for h in start.hazards)
                ):
                    continue
                delta = {"up": (-1, 0), "down": (1, 0),
                         "left": (0, -1), "right": (0, 1)}.get(edge.action)
                if delta is None or edge.target != (prefix[0] + delta[0], prefix[1] + delta[1]):
                    continue
                try:
                    plan = world.plan_feasible_to_map(start, start.map_id, goal_at=prefix)
                except RoutePlanningError:
                    continue
                # Deliberate sight engagement is map-local; no exit/re-entry bypass.
                if plan.segments:
                    continue
                result.append(TrainerSightApproach(target, prefix, edge, len(plan.steps)))
    return tuple(sorted(result, key=lambda p: (
        p.prefix_steps, p.trainer.sprite_index, p.prefix_at, p.trigger.target,
    )))


def _context(rom, reader):
    route = replace(RedVermilionGroundTransition.from_rom(rom),
                    full_event_offsets=True, observe_terrain=True, maximum_readiness_waits=100)
    observer = Gen1TraversalObserver(reader, Gen1TrainerSightProjector(
        rom, reader, full_event_offsets=True), cut_capabilities)
    raw = reader.read()
    objects = map_object_events(rom, {raw.map_id})
    headers = trainer_headers(rom, {raw.map_id}, full_event_offsets=True)
    zones = trainer_sight_zones(headers, objects, raw, reader.read_current_map_objects())
    world = route.route_world.with_current_blocks(reader.read_current_map_blocks())
    return route, observer, world, zones, objects, headers


def discover_sight_approaches(rom, reader):
    _, observer, world, zones, objects, _ = _context(rom, reader)
    return plan_sight_approaches(world, observer.observe(), zones, stationary_slots={
        o.object_index for o in objects if o.is_trainer and o.movement == 255
    })


_PROTECTED = (
    "party_count", "party_species_ids", "party_levels", "party_hp", "party_moves",
    "party_pp", "party_status", "bag_items", "player_money", "badge_bits", "event_flags",
)


def engage_trainer_sight(emulator, reader, actions, *, rom, approach,
                         maximum_transition_actions=160):
    """Return at the exact trainer's battle intro, before choosing any move.

    The caller must supply its existing shared hard action/frame/time limiter.
    Transition allowance is consumed by the sole trigger and all later inputs.
    """
    if type(maximum_transition_actions) is not int or not 1 <= maximum_transition_actions <= 160:
        raise ValueError("trainer engagement needs a bounded transition allowance")
    if not isinstance(approach, TrainerSightApproach):
        raise TypeError("trainer engagement requires a quoted approach")
    before = reader.read()
    target = approach.trainer
    def unchanged():
        raw = reader.read()
        if raw.map_id != target.map_id or any(
            getattr(raw, key) != getattr(before, key) for key in _PROTECTED
        ):
            raise TrainerSightEngagementError("trainer approach changed protected resources")
        return raw

    def rebind():
        route, observer, world, zones, objects, headers = _context(rom, reader)
        matches = plan_sight_approaches(world, observer.observe(), zones, stationary_slots={
            o.object_index for o in objects if o.is_trainer and o.movement == 255
        })
        found = [p for p in matches if (
            replace(p.trainer, visible=False) == replace(target, visible=False)
            and p.prefix_at == approach.prefix_at and p.trigger == approach.trigger
        )]
        if len(found) != 1:
            raise TrainerSightEngagementError("trainer sight binding changed before trigger")
        return route, found[0], headers

    if (before.battle_state != 0 or reader.read_pending_trainer_battle_identity() is not None
            or reader.trainer_engagement_active()):
        raise TrainerSightEngagementError("trainer sight origin is not unengaged field")
    route, _, _ = rebind()
    replace(route, destination_map=target.map_id, destination_at=approach.prefix_at)(
        actions, reader, emulator,
    )
    raw = unchanged()
    route, live, headers = rebind()
    if (raw.player_y, raw.player_x) != approach.prefix_at or not live.trainer.visible:
        raise TrainerSightEngagementError("trainer is not visible at the safe prefix")
    if (reader.read_pending_trainer_battle_identity() is not None
            or reader.trainer_engagement_active()):
        raise TrainerSightEngagementError("unexpected trainer armed before trigger")
    header = [h for h in headers if h.sprite_index == target.sprite_index
              and h.event_flag == target.event_flag]
    if len(header) != 1:
        raise TrainerSightEngagementError("trainer dialogue header is not uniquely bound")
    actions.execute(approach.trigger.macro_action)
    return _await_sight_battle(reader, actions, approach=approach, before=before,
                              header_address=header[0].address,
                              table_address=min(h.address for h in headers),
                              maximum_actions=maximum_transition_actions - 1,
                              trigger_actions=1)


def resume_trainer_sight(reader, actions, *, rom, approach, before,
                        maximum_transition_actions):
    """Settle an already-triggered retained encounter, never repeat its walk.

    Caller authenticates retained source/plan and subtracts all prior attempt costs.
    Only the declared target's active sight dialogue may resume through this API.
    """
    if type(maximum_transition_actions) is not int or not 1 <= maximum_transition_actions <= 160:
        raise ValueError("retained sight transition needs a remaining allowance")
    target = approach.trainer
    headers = trainer_headers(rom, {target.map_id}, full_event_offsets=True)
    matches = [h for h in headers if h.sprite_index == target.sprite_index
               and h.event_flag == target.event_flag]
    if len(matches) != 1:
        raise TrainerSightEngagementError("retained trainer header is not bound")
    raw = reader.read()
    allowed_contexts = {(matches[0].address, target.sprite_index),
                        (min(h.address for h in headers), target.sprite_index)}
    if (raw.battle_state != 0 or (raw.player_y, raw.player_x) != approach.trigger.target
            or not reader.trainer_engagement_active()
            or reader.read_trainer_dialogue_context() not in allowed_contexts):
        raise TrainerSightEngagementError("retained sight trigger is not the declared trainer")
    return _await_sight_battle(reader, actions, approach=approach, before=before,
                              header_address=matches[0].address,
                              table_address=min(h.address for h in headers),
                              maximum_actions=maximum_transition_actions, trigger_actions=0)


def _await_sight_battle(reader, actions, *, approach, before, header_address,
                       table_address, maximum_actions, trigger_actions):
    target = approach.trainer
    expected = (target.trainer_class, target.trainer_class - 200, target.trainer_set)
    dialogue_context = (header_address, target.sprite_index)
    for consumed in range(maximum_actions + 1):
        raw = reader.read()
        if raw.map_id != target.map_id or any(
            getattr(raw, key) != getattr(before, key) for key in _PROTECTED
        ):
            raise TrainerSightEngagementError("trainer approach changed protected resources")
        if (raw.player_y, raw.player_x) not in (approach.prefix_at, approach.trigger.target):
            raise TrainerSightEngagementError("trainer trigger left its declared edge")
        if raw.battle_state == 2:
            if reader.read_active_trainer_identity() != expected:
                raise TrainerSightEngagementError("wrong trainer battle identity")
            return {"map_id": target.map_id, "object_index": target.sprite_index,
                    "event": target.event_flag, "trainer_identity": expected,
                    "prefix_at": approach.prefix_at, "trigger_at": approach.trigger.target,
                    "transition_actions": consumed + trigger_actions, "combat_choices": 0}
        if raw.battle_state != 0:
            raise TrainerSightEngagementError("unexpected battle during trainer engagement")
        pending = reader.read_pending_trainer_battle_identity()
        if pending is not None and pending != (expected[0], expected[2]):
            raise TrainerSightEngagementError("wrong pending trainer identity")
        if consumed == maximum_actions:
            break
        if reader.read_bottom_dialogue_box_visible():
            context = reader.read_trainer_dialogue_context()
            if context == dialogue_context:
                action = MacroAction(MacroActionKind.INTERACT)
            elif context == (table_address, target.sprite_index):
                # ExecuteCurMapScriptInTable restores the table pointer before
                # DisplayTextID draws its box; TalkToTrainer binds the specific
                # header later. Wait neutrally through this cartridge phase.
                action = MacroAction(MacroActionKind.WAIT, repeat=12)
            else:
                raise TrainerSightEngagementError("wrong trainer dialogue identity")
        else:
            action = MacroAction(MacroActionKind.WAIT, repeat=12)
        actions.execute(action)
    raise TrainerSightEngagementError("trainer engagement transition budget consumed")
