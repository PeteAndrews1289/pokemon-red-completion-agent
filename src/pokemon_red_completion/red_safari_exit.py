"""Bounded semantic handling for Red's active Safari Zone exit prompt.

The Safari gate is not an ordinary route dialogue.  Selecting No returns the
player to the park, while selecting Yes clears the active Safari session and
scripts three steps toward the city.  This module turns that compound cartridge
transition into one route acknowledgement and refuses every nearby lookalike.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .actions import MacroAction, MacroActionKind
from .local_router import LocalPath
from .observation import EventFlag, MapId, PokemonRedStateReader, RawGameState
from .red_super_rod_support import (
    _event_is_set,
    _require_safari_exit_transition,
)
from .route_executor import (
    InterruptionHandler,
    InterruptionReceipt,
    RouteActionPort,
    RouteExecutionError,
    TraversalSnapshot,
)
from .route_plan import RoutePlan


def safari_departure_within_steps(plan: RoutePlan, reader: PokemonRedStateReader) -> bool:
    """Do not advertise an exit that the paid-session timer will interrupt."""
    session = reader.read_safari_session_state()
    if not session.in_safari_zone:
        return True
    steps = 0
    for step in plan.steps:
        if step.source_map == SAFARI_GATE_MAP_ID:
            break
        steps += 1
    # The existing Safari escape controller also needs sixteen steps of headroom.
    return not session.safari_game_over and steps + 16 < session.safari_steps


@dataclass
class RedSafariDepartureInterruptionHandler:
    """Use Safari RUN in the park, ordinary recovery only after departure."""

    controller: object
    executor: RouteActionPort
    reader: PokemonRedStateReader
    fallback: InterruptionHandler
    safari_handler: object = field(init=False)

    def __post_init__(self):
        from .red_safari_fishing import SafariFishingInterruptionHandler

        self.safari_handler = SafariFishingInterruptionHandler(
            self.controller, self.executor, self.reader
        )

    @property
    def handled_hazard_kinds(self):
        return getattr(self.fallback, "handled_hazard_kinds", frozenset())

    @property
    def handled_interruption_kinds(self):
        return getattr(self.fallback, "handled_interruption_kinds", frozenset())

    def handle(self, interruption):
        if (interruption.interruption == "wild_battle"
                and self.reader.read_safari_session_state().in_safari_zone):
            return self.safari_handler.handle(interruption)
        return self.fallback.handle(interruption)

SAFARI_CENTER_MAP_ID = int(MapId.SAFARI_ZONE_CENTER)
SAFARI_GATE_MAP_ID = int(MapId.SAFARI_ZONE_GATE)
SAFARI_CENTER_EXIT_Y = 25
SAFARI_GATE_ENTRY_Y = 0
SAFARI_GATE_SETTLED_Y = 3
SAFARI_GATE_LANES = frozenset({3, 4})
SAFARI_CENTER_TO_GATE_X_OFFSET = 11
SAFARI_EXIT_SETTLE_LIMIT = 16
SAFARI_EXIT_WAIT_FRAMES = 6


def _full_collection_state(reader: PokemonRedStateReader) -> tuple[object, ...]:
    """Read every registration and stored specimen without advancing gameplay."""

    return (
        reader.read_pokedex_state(),
        reader.read_all_box_states(),
        tuple(reader.read_box_move_members(index) for index in range(12)),
    )


def normalize_active_safari_exit_plan(plan: RoutePlan) -> RoutePlan | None:
    """Model the gate's required three-step auto-walk in a cartridge route.

    Returns ``None`` when the plan does not cross the active-Safari exit.  A
    recognized but malformed crossing fails closed instead of being treated as
    an ordinary warp.
    """

    candidates = [
        index
        for index, segment in enumerate(plan.segments[:-1])
        if segment.source_map == SAFARI_CENTER_MAP_ID
        and segment.target_map == SAFARI_GATE_MAP_ID
        and plan.segments[index + 1].source_map == SAFARI_GATE_MAP_ID
    ]
    if not candidates:
        return None
    if len(candidates) != 1:
        raise RouteExecutionError("Safari exit route has no unique gate transition")

    index = candidates[0]
    entrance = plan.segments[index]
    onward = plan.segments[index + 1]
    entry_y, lane = entrance.transition.arrival_at
    source_y, source_x = entrance.transition.exit_at
    settled = (SAFARI_GATE_SETTLED_Y, lane)
    if (
        (entry_y != SAFARI_GATE_ENTRY_Y)
        or lane not in SAFARI_GATE_LANES
        or source_y != SAFARI_CENTER_EXIT_Y
        or source_x - SAFARI_CENTER_TO_GATE_X_OFFSET != lane
        or entrance.transition.action != "down"
        or entrance.transition_action_in_approach
        or onward.approach.coordinates[0] != (entry_y, lane)
        or settled not in onward.approach.coordinates
    ):
        raise RouteExecutionError("Safari exit route has an unsupported gate boundary")

    settled_index = onward.approach.coordinates.index(settled)
    scripted_edges = onward.approach.edges[:settled_index]
    if settled_index != SAFARI_GATE_SETTLED_Y or any(
        edge.action != "down"
        or edge.action_kind is not MacroActionKind.MOVE
        or edge.target != (offset + 1, lane)
        for offset, edge in enumerate(scripted_edges)
    ):
        raise RouteExecutionError("Safari exit route disagrees with the scripted auto-walk")

    normalized_entrance = replace(
        entrance,
        transition=replace(entrance.transition, arrival_at=settled),
    )
    normalized_onward = replace(
        onward,
        approach=LocalPath(
            onward.approach.coordinates[settled_index:],
            onward.approach.edges[settled_index:],
            onward.approach.modes[settled_index:],
        ),
    )
    segments = list(plan.segments)
    segments[index] = normalized_entrance
    segments[index + 1] = normalized_onward
    return replace(plan, segments=tuple(segments))


@dataclass(slots=True)
class RedSafariExitDialogueHandler:
    """Select Yes only at the exact active-Safari gate boundary."""

    executor: RouteActionPort
    reader: PokemonRedStateReader
    fallback: InterruptionHandler
    maximum_exits: int = 1
    settle_limit: int = SAFARI_EXIT_SETTLE_LIMIT
    wait_frames: int = SAFARI_EXIT_WAIT_FRAMES
    evidence: list[InterruptionReceipt] = field(default_factory=list, init=False)

    @property
    def handled_hazard_kinds(self) -> frozenset[str]:
        kinds: object = getattr(self.fallback, "handled_hazard_kinds", frozenset())
        return kinds if isinstance(kinds, frozenset) else frozenset()

    @property
    def handled_interruption_kinds(self) -> frozenset[str]:
        kinds: object = getattr(self.fallback, "handled_interruption_kinds", frozenset())
        return (kinds if isinstance(kinds, frozenset) else frozenset()).union(
            {"scripted_dialogue"}
        )

    def handle(self, interruption: TraversalSnapshot) -> InterruptionReceipt:
        initial = self.reader.read()
        if not self._is_active_safari_prompt(interruption, initial):
            return self.fallback.handle(interruption)
        if len(self.evidence) >= self.maximum_exits:
            raise RouteExecutionError("active Safari exit budget was already consumed")

        collection = _full_collection_state(self.reader)
        lane = interruption.at[1]
        confirms = 0
        selection_moves = 0
        for _ in range(self.settle_limit + 1):
            current = self.reader.read()
            self._require_preserved(initial, current, collection, lane)
            active = _event_is_set(current.event_flags, EventFlag.IN_SAFARI_ZONE)
            game_over = _event_is_set(current.event_flags, EventFlag.SAFARI_GAME_OVER)
            ready = self.reader.read_input_readiness().ready
            dialogue = self.reader.read_bottom_dialogue_box_visible()

            if not active and not game_over and ready and not dialogue:
                if (current.player_y, current.player_x) != (SAFARI_GATE_SETTLED_Y, lane):
                    raise RouteExecutionError("active Safari exit settled at the wrong tile")
                receipt = InterruptionReceipt(
                    kind="scripted_dialogue",
                    resumed_map=SAFARI_GATE_MAP_ID,
                    resumed_at=(SAFARI_GATE_SETTLED_Y, lane),
                    details={
                        "semantic": "active_safari_exit",
                        "confirm_pulses": confirms,
                        "selection_moves": selection_moves,
                        "safari_events_cleared": True,
                        "verified": True,
                    },
                )
                self.evidence.append(receipt)
                return receipt

            if dialogue:
                if active:
                    cursor = self.reader.read_menu_cursor_state()
                    if (
                        cursor.scroll_offset != 0
                        or cursor.maximum_visible_index != 1
                        or cursor.selected_visible_index not in {0, 1}
                    ):
                        raise RouteExecutionError(
                            "active Safari exit did not expose its bounded Yes/No choice"
                        )
                    if cursor.selected_visible_index == 1:
                        self.executor.execute(MacroAction(MacroActionKind.MOVE, "up"))
                        selection_moves += 1
                        selected = self.reader.read_menu_cursor_state()
                        if (
                            selected.scroll_offset != 0
                            or selected.maximum_visible_index != 1
                            or selected.selected_visible_index != 0
                        ):
                            raise RouteExecutionError(
                                "active Safari exit did not acknowledge the Yes selection"
                            )
                self.executor.execute(MacroAction(MacroActionKind.CONFIRM))
                confirms += 1
            else:
                self.executor.execute(
                    MacroAction(MacroActionKind.WAIT, repeat=self.wait_frames)
                )
        raise RouteExecutionError("active Safari exit did not settle within its bound")

    def _is_active_safari_prompt(
        self,
        interruption: TraversalSnapshot,
        raw: RawGameState,
    ) -> bool:
        return (
            interruption.interruption == "scripted_dialogue"
            and interruption.map_id == SAFARI_GATE_MAP_ID
            and interruption.at[0] == SAFARI_GATE_ENTRY_Y
            and interruption.at[1] in SAFARI_GATE_LANES
            and raw.map_id == interruption.map_id
            and (raw.player_y, raw.player_x) == interruption.at
            and raw.battle_state == 0
            and _event_is_set(raw.event_flags, EventFlag.IN_SAFARI_ZONE)
            and not _event_is_set(raw.event_flags, EventFlag.SAFARI_GAME_OVER)
            and not self.reader.read_input_readiness().ready
            and self.reader.read_bottom_dialogue_box_visible()
        )

    def _require_preserved(
        self,
        initial: RawGameState,
        current: RawGameState,
        collection: tuple[object, ...],
        lane: int,
    ) -> None:
        try:
            _require_safari_exit_transition(initial, current)
        except Exception as error:
            raise RouteExecutionError(str(error)) from error
        if _full_collection_state(self.reader) != collection:
            raise RouteExecutionError("active Safari exit changed the protected collection")
        if (
            current.map_id != SAFARI_GATE_MAP_ID
            or current.player_y is None
            or current.player_x != lane
            or not SAFARI_GATE_ENTRY_Y <= current.player_y <= SAFARI_GATE_SETTLED_Y
            or current.battle_state != 0
        ):
            raise RouteExecutionError("active Safari exit left its gate corridor")


__all__ = [
    "RedSafariExitDialogueHandler",
    "normalize_active_safari_exit_plan",
]
