"""Bounded settlement of a qualified event-dependent entrance text/push loop.

This adapter has no battle authority and never chooses a destination. The route
still must reach its exact predicted endpoint. Default route handling is intact.
"""
from __future__ import annotations

from dataclasses import fields

from .actions import MacroAction, MacroActionKind
from .gen1_scripted_arrival import trainer_room_arrival
from .route_executor import InterruptionReceipt, RouteExecutionError


def _resources(raw):
    names = [f.name for f in fields(raw) if f.name.startswith("party_")]
    names += ["badge_bits", "bag_items", "bag_item_ids", "player_money", "event_flags"]
    return tuple(getattr(raw, name) for name in names)


class ScriptedArrivalInterruptionHandler:
    """One fresh routed re-entry; consume on attempt, including failed attempts."""

    def __init__(self, rom, arrival, reader, actions, fallback):
        initial = reader.read()
        qualified = trainer_room_arrival(
            rom, arrival.map_id, initial.event_flags, allow_reentry=True,
        )
        if qualified != arrival or arrival.reentry_text_id is None:
            raise RouteExecutionError("reentry requires current qualified cartridge metadata")
        if initial.map_id == arrival.map_id or initial.battle_state != 0:
            raise RouteExecutionError("reentry must bind before a fresh room transition")
        self.arrival, self.reader, self.actions, self.fallback = arrival, reader, actions, fallback
        self.resources = _resources(initial)
        self.claimed = False

    @property
    def handled_hazard_kinds(self):
        return self.fallback.handled_hazard_kinds

    @property
    def handled_interruption_kinds(self):
        return self.fallback.handled_interruption_kinds | frozenset({"scripted_dialogue"})

    def handle(self, interruption):
        a, r = self.arrival, self.reader
        if interruption.map_id != a.map_id:
            return self.fallback.handle(interruption)
        if self.claimed or interruption.interruption != "scripted_dialogue":
            raise RouteExecutionError("unowned or repeated reentry interruption")
        self.claimed = True
        current = r.read()
        if (interruption.at not in a.entrance_coordinates
                or (current.map_id, current.player_y, current.player_x)
                != (interruption.map_id, *interruption.at)):
            raise RouteExecutionError("reentry did not start at a bound entrance")
        positions = tuple((interruption.at[0] + a.direction[0] * i,
                           interruption.at[1] + a.direction[1] * i)
                          for i in range(a.steps + 1))
        confirmations = waits = progress = 0
        stable = False
        for _ in range(96):
            raw = r.read()
            at = (raw.player_y, raw.player_x)
            if (raw.map_id != a.map_id or raw.battle_state != 0
                    or r.read_pending_trainer_battle_identity() is not None
                    or r.trainer_engagement_active()
                    or _resources(raw) != self.resources or at not in positions
                    or positions.index(at) < progress):
                raise RouteExecutionError("reentry state, resources or battle boundary changed")
            progress = positions.index(at)
            visible = r.read_bottom_dialogue_box_visible()
            script = r.read_current_map_script()
            if script not in {0, 3}:
                raise RouteExecutionError("reentry script left the qualified lifecycle")
            if (at == positions[-1] and not visible
                    and r.read_input_readiness().ready and script == 0):
                if stable:
                    return InterruptionReceipt("scripted_dialogue", raw.map_id, at, {
                        "source": "cartridge_reentry", "push_steps": progress,
                        "confirmations": confirmations, "waits": waits,
                    })
                stable = True
            else:
                stable = False
            if visible:
                if (at not in a.reentry_triggers or script != 0
                        or r.read_trainer_dialogue_context()[1] != a.reentry_text_id):
                    raise RouteExecutionError("visible text is not the qualified entrance warning")
                self.actions.execute(MacroAction(MacroActionKind.CONFIRM))
                confirmations += 1
            else:
                self.actions.execute(MacroAction(MacroActionKind.WAIT, 8))
                waits += 1
        raise RouteExecutionError("reentry did not settle within its action budget")
