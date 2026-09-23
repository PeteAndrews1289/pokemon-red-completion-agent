"""Paid-session fishing support; no admission, ordinary combat or goal selection."""

from dataclasses import dataclass

from .actions import MacroActionKind
from .fishing import FishingCastExecutor
from .observation import MapId, RedSafariSessionState
from .red_fishing_capture import LiveRedFishingCapturePort, run_red_fishing_capture
from .red_safari_acquisition import SAFARI_ZONE_SOURCES, LiveSafariAreaExecutor
from .route_executor import InterruptionReceipt, execute_route

SAFARI_FISHING_MAPS = frozenset(
    {
        int(MapId.SAFARI_ZONE_EAST),
        int(MapId.SAFARI_ZONE_NORTH),
        int(MapId.SAFARI_ZONE_WEST),
        int(MapId.SAFARI_ZONE_CENTER),
    }
)
SAFARI_STEP_RESERVE = 16


class SafariFishingError(RuntimeError):
    """The paid session cannot support the selected fishing attempt."""


def require_safari_session(reader, *, battle=False, require_ready=True):
    raw = reader.read()
    session = reader.read_safari_session_state()
    if (
        not isinstance(session, RedSafariSessionState)
        or not session.in_safari_zone
        or session.safari_game_over
        or session.safari_balls < 2
        or session.safari_steps <= SAFARI_STEP_RESERVE
        or raw.map_id not in SAFARI_FISHING_MAPS
        or raw.battle_state != (1 if battle else 0)
        # Overworld readiness is false during a battle introduction. The Safari
        # encounter port owns that UI and its bounded settling, not this gate.
        or (require_ready and not battle and not reader.read_input_readiness().ready)
    ):
        raise SafariFishingError("Safari fishing requires an active, funded, ready session")
    return session


def safari_route_supported(plan, remaining_steps):
    """Keep every transition within the paid area and retain step headroom."""
    return (
        type(remaining_steps) is int
        and remaining_steps > SAFARI_STEP_RESERVE
        and len(plan.steps) <= remaining_steps - SAFARI_STEP_RESERVE
        and plan.terminal_map in SAFARI_FISHING_MAPS
        and plan.terminal_mode in {None, "land"}
        and all(
            s.source_map in SAFARI_FISHING_MAPS
            and s.expected_map in SAFARI_FISHING_MAPS
            and s.kind in {"walk", "warp"}
            and s.action_kind is MacroActionKind.MOVE
            and s.source_mode in {None, "land"}
            and s.expected_mode in {None, "land"}
            for s in plan.steps
        )
    )


def safari_encounters(controller, actions, reader):
    raw = reader.read()
    source = next((name for name, map_id in SAFARI_ZONE_SOURCES if map_id == raw.map_id), None)
    if source is None:
        raise SafariFishingError("Safari encounter is outside a supported paid area")
    balls = reader.read_safari_session_state().safari_balls
    if balls < 2:
        raise SafariFishingError("Safari fishing retains one ball for a safe session boundary")

    def no_seek():
        raise SafariFishingError("Fishing port cannot start a grass search")

    return LiveSafariAreaExecutor(
        controller,
        actions,
        reader,
        source_id=source,
        map_id=raw.map_id,
        seek_step=no_seek,
        maximum_throws_per_encounter=min(8, balls - 1),
    )


@dataclass
class SafariFishingRoutePort:
    actions: object
    reader: object

    def execute(self, action):
        require_safari_session(self.reader, require_ready=action.kind is not MacroActionKind.WAIT)
        if action.kind not in {MacroActionKind.MOVE, MacroActionKind.WAIT}:
            raise SafariFishingError("Paid-session route cannot open menus or use field moves")
        return self.actions.execute(action)


@dataclass
class SafariFishingInterruptionHandler:
    controller: object
    actions: object
    reader: object
    maximum_flees: int = 16
    flees: int = 0

    def handle(self, interruption):
        if interruption.interruption != "wild_battle" or self.flees >= self.maximum_flees:
            raise SafariFishingError("Safari route interruption is unsupported or exhausted")
        session = require_safari_session(self.reader, battle=True)
        before = self.reader.read()
        if (before.map_id, before.player_y, before.player_x) != (
            interruption.map_id,
            *interruption.at,
        ):
            raise SafariFishingError("Safari route encounter changed before recovery")
        safari_encounters(self.controller, self.actions, self.reader).flee_encounter()
        after = self.reader.read()
        if (
            self.reader.read_safari_session_state() != session
            or after.battle_state
            or (after.map_id, after.player_y, after.player_x)
            != (before.map_id, before.player_y, before.player_x)
            or after.player_money != before.player_money
            or after.bag_items != before.bag_items
            or after.party_hp != before.party_hp
        ):
            raise SafariFishingError("Safari route flee changed protected resources or boundary")
        self.flees += 1
        return InterruptionReceipt(
            kind="wild_battle",
            resumed_map=after.map_id,
            resumed_at=(after.player_y, after.player_x),
            details={"safari_flees": self.flees},
        )


class SafariFishingCapturePort(LiveRedFishingCapturePort):
    def cast(self):
        require_safari_session(self.reader)
        return super().cast()

    def capture_encounter(self, species_number):
        # Refresh the throw ceiling for every actual encounter; never spend the
        # final Safari Ball and trigger a game-over teleport mid-verification.
        self.encounters = safari_encounters(
            self.caster.emulator,
            self.caster.actions,
            self.reader,
        )
        return super().capture_encounter(species_number)


def run_safari_fishing(destination, *, world, observer, controller, actions, reader, maximum_casts):
    session = require_safari_session(reader)
    before = reader.read()
    plan = world.plan_feasible_to_map(
        observer.observe(),
        destination.offer.map_id,
        goal_at=destination.stance.at,
    )
    if not safari_route_supported(plan, session.safari_steps):
        raise SafariFishingError("Selected Safari shoreline exceeds the paid route budget")
    handler = SafariFishingInterruptionHandler(controller, actions, reader)

    def replan(*args, **kwargs):
        updated = world.replanner()(*args, **kwargs)
        current = require_safari_session(reader)
        if not safari_route_supported(updated, current.safari_steps):
            raise SafariFishingError("Replanned Safari route exceeds remaining paid steps")
        return updated

    route = execute_route(
        plan,
        SafariFishingRoutePort(actions, reader),
        observer,
        interruption_handler=handler,
        replanner=replan,
    )
    if not route.passed:
        raise SafariFishingError("Safari route did not reach the selected shoreline")
    require_safari_session(reader)
    port = SafariFishingCapturePort(
        FishingCastExecutor(actions, reader, controller),
        safari_encounters(controller, actions, reader),
        reader,
        destination.stance,
    )
    result = run_red_fishing_capture(destination.offer, port, maximum_casts=maximum_casts)
    after = reader.read()
    final = reader.read_safari_session_state()
    if (
        before.player_money != after.player_money
        or before.bag_items != after.bag_items
        or before.party_hp != after.party_hp
        or before.party_pp != after.party_pp
        or not final.in_safari_zone
        or final.safari_game_over
        or after.battle_state
        or final.safari_steps > session.safari_steps
        or final.safari_balls > session.safari_balls
        or not reader.read_input_readiness().ready
        or controller.pressed_buttons
    ):
        raise SafariFishingError("Safari fishing did not preserve a safe paid-session boundary")
    return result
