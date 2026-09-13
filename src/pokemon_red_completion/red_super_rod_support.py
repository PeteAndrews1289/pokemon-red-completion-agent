"""Verified, non-learning acquisition of Red's free Super Rod.

The Super Rod is a one-time cartridge prerequisite, not a strategic model
choice and not a Mart purchase.  This module composes cartridge-derived routing,
an exact active-Safari exit boundary when needed, and the final NPC gift while
publishing no route identity or learner label.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Protocol

from .actions import MacroAction, MacroActionKind
from .executor import CountingExecutor
from .gen1_field_moves import Gen1FieldMovePort
from .gen1_route_runtime import Gen1RouteInterruptionHandler, Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .observation import (
    MAX_BAG_ITEMS,
    EventFlag,
    InputReadiness,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RawGameState,
    ReadOnlyMemory,
)
from .red_resource_goal_router import _supported_plan, collection_field_capabilities
from .route_executor import RouteExecutionLimits, execute_route
from .route_plan import RoutePlan, RoutePlanningError
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld

SUPER_ROD_STATUS_MASK = 1 << 5
SUPER_ROD_HOUSE_MAP_ID = int(MapId.ROUTE_12_SUPER_ROD_HOUSE)
SUPER_ROD_NPC_YX = (4, 2)
SUPER_ROD_STANCE_YX = (3, 2)
SUPER_ROD_FACING = "down"
SAFARI_GATE_MAP_ID = int(MapId.SAFARI_ZONE_GATE)
SAFARI_CENTER_MAP_ID = int(MapId.SAFARI_ZONE_CENTER)
SAFARI_CENTER_EXIT_SOURCE_YX = (25, 15)
SAFARI_GATE_ENTRY_YX = (0, 4)
SAFARI_EXIT_SETTLE_LIMIT = 16
SAFARI_EXIT_WAIT_REPEATS = 6
SAFARI_AUTOWALK_SETTLE_LIMIT = 32
SAFARI_AUTOWALK_WAIT_REPEATS = 24


class RedSuperRodSupportError(RuntimeError):
    """The support step was unavailable or lost its verified boundary."""


class RedSuperRodSupportReader(Protocol):
    def read(self) -> RawGameState: ...

    def read_input_readiness(self) -> InputReadiness: ...

    def read_player_facing(self) -> str: ...

    def read_bottom_dialogue_box_visible(self) -> bool: ...


class RedSuperRodSupportEmulator(ReadOnlyMemory, Protocol):
    @property
    def frame_count(self) -> int: ...


@dataclass(frozen=True, slots=True)
class RedSuperRodSupportObservation:
    map_id: int
    player_yx: tuple[int, int]
    facing: str
    input_ready: bool
    dialogue_visible: bool
    bag_slots: int
    rod_quantity: int
    status_recorded: bool
    in_battle: bool

    @property
    def acquired(self) -> bool:
        return self.rod_quantity == 1 and self.status_recorded

    @property
    def ready_to_receive(self) -> bool:
        return (
            self.map_id == SUPER_ROD_HOUSE_MAP_ID
            and self.player_yx == SUPER_ROD_STANCE_YX
            and self.facing == SUPER_ROD_FACING
            and self.input_ready
            and not self.dialogue_visible
            and self.bag_slots < MAX_BAG_ITEMS
            and self.rod_quantity == 0
            and not self.status_recorded
            and not self.in_battle
        )


def observe_red_super_rod_support(
    reader: RedSuperRodSupportReader,
) -> RedSuperRodSupportObservation:
    """Read the exact gift boundary without input or inferred ownership."""

    raw = reader.read()
    if (
        not raw.game_started
        or raw.map_id is None
        or raw.player_x is None
        or raw.player_y is None
        or raw.battle_state is None
        or raw.bag_items is None
        or raw.status_flags_1 is None
    ):
        raise RedSuperRodSupportError("Super Rod support observation is incomplete")
    inventory = dict(raw.bag_items)
    if len(inventory) != len(raw.bag_items) or any(
        type(item) is not int or type(quantity) is not int or not 0 <= item <= 0xFF or quantity <= 0
        for item, quantity in raw.bag_items
    ):
        raise RedSuperRodSupportError("Super Rod support bag is malformed")
    quantity = inventory.get(int(ItemId.SUPER_ROD), 0)
    recorded = bool(raw.status_flags_1 & SUPER_ROD_STATUS_MASK)
    if (quantity > 0) != recorded or quantity not in {0, 1}:
        raise RedSuperRodSupportError("Super Rod item and status evidence disagree")
    return RedSuperRodSupportObservation(
        map_id=raw.map_id,
        player_yx=(raw.player_y, raw.player_x),
        facing=reader.read_player_facing(),
        input_ready=reader.read_input_readiness().ready,
        dialogue_visible=reader.read_bottom_dialogue_box_visible(),
        bag_slots=len(raw.bag_items),
        rod_quantity=quantity,
        status_recorded=recorded,
        in_battle=raw.battle_state != 0,
    )


@dataclass(frozen=True, slots=True)
class RedSuperRodSupportResult:
    actions: int
    frames: int
    bag_slots_before: int
    bag_slots_after: int

    def __post_init__(self) -> None:
        if (
            type(self.actions) is not int
            or type(self.frames) is not int
            or self.actions < 2
            or self.frames <= 0
            or type(self.bag_slots_before) is not int
            or type(self.bag_slots_after) is not int
            or self.bag_slots_after != self.bag_slots_before + 1
        ):
            raise ValueError("Super Rod support result has invalid accounting")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.super-rod-support.v1",
            "status": "verified_super_rod_received",
            "item_id": int(ItemId.SUPER_ROD),
            "item_added": True,
            "status_bit_set": True,
            "actions": self.actions,
            "frames": self.frames,
            "bag_slots_before": self.bag_slots_before,
            "bag_slots_after": self.bag_slots_after,
            "forced_support_step": True,
            "learned_goal_authority": False,
            "training_examples": 0,
        }


def _protected_state(raw: RawGameState) -> tuple[object, ...]:
    return (
        raw.game_started,
        raw.map_id,
        raw.player_x,
        raw.player_y,
        raw.battle_state,
        raw.badge_bits,
        raw.event_flags,
        raw.party_count,
        raw.party_species_ids,
        raw.party_levels,
        raw.party_hp,
        raw.party_max_hp,
        raw.party_status,
        raw.party_moves,
        raw.party_pp,
        raw.player_money,
    )


def _require_transition_state(initial: RawGameState, current: RawGameState) -> None:
    if _protected_state(current) != _protected_state(initial):
        raise RedSuperRodSupportError("Super Rod dialogue changed protected game state")
    if initial.bag_items is None or current.bag_items is None:
        raise RedSuperRodSupportError("Super Rod dialogue lost bag observation")
    old = dict(initial.bag_items)
    new = dict(current.bag_items)
    old_status, new_status = initial.status_flags_1, current.status_flags_1
    if old_status is None or new_status is None:
        raise RedSuperRodSupportError("Super Rod dialogue lost status observation")
    unchanged = current.bag_items == initial.bag_items and new_status == old_status
    acquired = (
        len(new) == len(old) + 1
        and new.get(int(ItemId.SUPER_ROD)) == 1
        and {key: value for key, value in new.items() if key != int(ItemId.SUPER_ROD)} == old
        and new_status == old_status | SUPER_ROD_STATUS_MASK
    )
    if not (unchanged or acquired):
        raise RedSuperRodSupportError("Super Rod dialogue produced an invalid item transition")


@dataclass(slots=True)
class RedSuperRodSupportExecutor:
    """Accept and settle one bound Super Rod gift with no learner label."""

    actions: CountingExecutor
    reader: RedSuperRodSupportReader
    emulator: object
    maximum_confirm_pulses: int = 12

    def __post_init__(self) -> None:
        if type(self.maximum_confirm_pulses) is not int or self.maximum_confirm_pulses <= 0:
            raise ValueError("maximum_confirm_pulses must be a positive integer")

    def execute(self) -> RedSuperRodSupportResult:
        initial_observation = observe_red_super_rod_support(self.reader)
        if not initial_observation.ready_to_receive:
            raise RedSuperRodSupportError("Super Rod support is not ready to receive")
        initial = self.reader.read()
        before_actions = self.actions.actions_executed
        before_frames = self._frame_count()
        self.actions.execute(MacroAction(MacroActionKind.INTERACT))
        for _ in range(self.maximum_confirm_pulses + 1):
            current = self.reader.read()
            _require_transition_state(initial, current)
            observation = observe_red_super_rod_support(self.reader)
            if (
                observation.acquired
                and observation.input_ready
                and not observation.dialogue_visible
            ):
                result = RedSuperRodSupportResult(
                    actions=self.actions.actions_executed - before_actions,
                    frames=self._frame_count() - before_frames,
                    bag_slots_before=initial_observation.bag_slots,
                    bag_slots_after=observation.bag_slots,
                )
                if self.actions.actions_executed - before_actions > 1 + self.maximum_confirm_pulses:
                    raise RedSuperRodSupportError("Super Rod support exceeded its action bound")
                return result
            if not observation.dialogue_visible:
                raise RedSuperRodSupportError("Super Rod interaction left its dialogue boundary")
            if self.actions.actions_executed - before_actions >= 1 + self.maximum_confirm_pulses:
                break
            self.actions.execute(MacroAction(MacroActionKind.CONFIRM))
        raise RedSuperRodSupportError("Super Rod dialogue exceeded its confirmation bound")

    def _frame_count(self) -> int:
        value = getattr(self.emulator, "frame_count", None)
        if type(value) is not int or value < 0:
            raise RedSuperRodSupportError("Super Rod support lacks frame accounting")
        return value


@dataclass(frozen=True, slots=True)
class RedSuperRodDialogueSettlementResult:
    actions: int
    frames: int
    bag_slots: int

    def __post_init__(self) -> None:
        if (
            type(self.actions) is not int
            or type(self.frames) is not int
            or type(self.bag_slots) is not int
            or self.actions <= 0
            or self.frames <= 0
            or not 0 < self.bag_slots <= MAX_BAG_ITEMS
        ):
            raise ValueError("Super Rod dialogue settlement has invalid accounting")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.super-rod-dialogue-settlement.v1",
            "status": "verified_acquired_super_rod_dialogue_settled",
            "item_id": int(ItemId.SUPER_ROD),
            "item_already_owned": True,
            "actions": self.actions,
            "frames": self.frames,
            "bag_slots": self.bag_slots,
            "forced_support_step": True,
            "learned_goal_authority": False,
            "training_examples": 0,
        }


@dataclass(slots=True)
class RedAcquiredSuperRodDialogueSettlement:
    """Finish a retained gift conversation after the item was already written."""

    actions: CountingExecutor
    reader: RedSuperRodSupportReader
    emulator: object
    maximum_confirm_pulses: int = 12

    def __post_init__(self) -> None:
        if type(self.maximum_confirm_pulses) is not int or self.maximum_confirm_pulses <= 0:
            raise ValueError("maximum_confirm_pulses must be a positive integer")

    def execute(self) -> RedSuperRodDialogueSettlementResult:
        initial_observation = observe_red_super_rod_support(self.reader)
        if (
            not initial_observation.acquired
            or initial_observation.map_id != SUPER_ROD_HOUSE_MAP_ID
            or initial_observation.player_yx != SUPER_ROD_STANCE_YX
            or initial_observation.facing != SUPER_ROD_FACING
            or initial_observation.in_battle
            or not initial_observation.input_ready
            or not initial_observation.dialogue_visible
        ):
            raise RedSuperRodSupportError("acquired Super Rod dialogue is not ready to settle")
        initial = self.reader.read()
        before_actions = self.actions.actions_executed
        before_frames = self._frame_count()
        for _ in range(self.maximum_confirm_pulses + 1):
            current = self.reader.read()
            _require_transition_state(initial, current)
            observation = observe_red_super_rod_support(self.reader)
            if (
                observation.acquired
                and observation.input_ready
                and not observation.dialogue_visible
            ):
                return RedSuperRodDialogueSettlementResult(
                    actions=self.actions.actions_executed - before_actions,
                    frames=self._frame_count() - before_frames,
                    bag_slots=observation.bag_slots,
                )
            if not observation.dialogue_visible:
                raise RedSuperRodSupportError(
                    "acquired Super Rod dialogue left its settlement boundary"
                )
            if self.actions.actions_executed - before_actions >= self.maximum_confirm_pulses:
                break
            # A can close the final text box and immediately re-trigger the NPC
            # while the player remains facing him. B advances/dismisses dialogue
            # but cannot start a new interaction at the field boundary.
            self.actions.execute(MacroAction(MacroActionKind.CANCEL))
        raise RedSuperRodSupportError("acquired Super Rod dialogue exceeded its confirmation bound")

    def _frame_count(self) -> int:
        value = getattr(self.emulator, "frame_count", None)
        if type(value) is not int or value < 0:
            raise RedSuperRodSupportError("acquired Super Rod dialogue lacks frame accounting")
        return value


SUPER_ROD_ROUTE_LIMITS = RouteExecutionLimits(
    max_step_attempts=8,
    max_readiness_waits=16,
    max_interruptions=136,
    max_replans=8,
    replan_after_unchanged=2,
    retry_wait_frames=24,
    readiness_wait_frames=24,
    transition_settle_frames=180,
)


def _event_is_set(flags: bytes | None, event: EventFlag) -> bool:
    if flags is None:
        raise RedSuperRodSupportError("Safari exit lost event observation")
    byte_index, bit_index = divmod(int(event), 8)
    if byte_index >= len(flags):
        raise RedSuperRodSupportError("Safari exit event observation is truncated")
    return bool(flags[byte_index] & (1 << bit_index))


def _events_with_safari_exit_cleared(flags: bytes) -> bytes:
    result = bytearray(flags)
    for event in (EventFlag.SAFARI_GAME_OVER, EventFlag.IN_SAFARI_ZONE):
        byte_index, bit_index = divmod(int(event), 8)
        result[byte_index] &= ~(1 << bit_index)
    return bytes(result)


def _safari_exit_protected_state(raw: RawGameState) -> tuple[object, ...]:
    return (
        raw.game_started,
        raw.battle_state,
        raw.badge_bits,
        raw.status_flags_1,
        raw.party_count,
        raw.party_species_ids,
        raw.party_levels,
        raw.party_hp,
        raw.party_max_hp,
        raw.party_status,
        raw.party_moves,
        raw.party_pp,
        raw.player_money,
        raw.bag_items,
    )


def _require_safari_exit_transition(
    initial: RawGameState,
    current: RawGameState,
) -> None:
    if _safari_exit_protected_state(current) != _safari_exit_protected_state(initial):
        raise RedSuperRodSupportError("Safari exit changed protected game state")
    if initial.event_flags is None or current.event_flags is None:
        raise RedSuperRodSupportError("Safari exit lost event observation")
    allowed = {
        initial.event_flags,
        _events_with_safari_exit_cleared(initial.event_flags),
    }
    if current.event_flags not in allowed:
        raise RedSuperRodSupportError("Safari exit changed unrelated story events")


@dataclass(frozen=True, slots=True)
class _SafariExitReceipt:
    route_steps: int
    route_replans: int
    route_interruptions: int


@dataclass(frozen=True, slots=True)
class RedRoutedSuperRodSupportResult:
    gift: RedSuperRodSupportResult
    route_steps: int
    route_replans: int
    route_interruptions: int
    safari_exit_used: bool
    facing_action_used: bool
    actions: int
    frames: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.gift, RedSuperRodSupportResult)
            or type(self.route_steps) is not int
            or type(self.route_replans) is not int
            or type(self.route_interruptions) is not int
            or min(self.route_steps, self.route_replans, self.route_interruptions) < 0
            or type(self.safari_exit_used) is not bool
            or type(self.facing_action_used) is not bool
            or type(self.actions) is not int
            or type(self.frames) is not int
            or self.actions < self.gift.actions
            or self.frames < self.gift.frames
        ):
            raise ValueError("routed Super Rod support has invalid accounting")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.routed-super-rod-support.v1",
            "status": "verified_super_rod_received",
            "gift": self.gift.public_dict(),
            "route_steps": self.route_steps,
            "route_replans": self.route_replans,
            "route_interruptions": self.route_interruptions,
            "safari_exit_used": self.safari_exit_used,
            "facing_action_used": self.facing_action_used,
            "actions": self.actions,
            "frames": self.frames,
            "private_coordinates_published": 0,
            "forced_support_step": True,
            "learned_goal_authority": False,
            "training_examples": 0,
        }


@dataclass(slots=True)
class RedRoutedSuperRodSupport:
    """Route to and verify the one-time support prerequisite."""

    actions: CountingExecutor
    reader: PokemonRedStateReader
    emulator: RedSuperRodSupportEmulator
    world: StrategicScenarioRouteWorld
    maximum_controller_actions: int = 6_000
    maximum_emulator_frames: int = 600_000
    route_limits: RouteExecutionLimits = SUPER_ROD_ROUTE_LIMITS

    def __post_init__(self) -> None:
        if not isinstance(self.actions, CountingExecutor):
            raise TypeError("routed Super Rod support needs a CountingExecutor")
        for name in ("maximum_controller_actions", "maximum_emulator_frames"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    def execute(self) -> RedRoutedSuperRodSupportResult:
        initial = observe_red_super_rod_support(self.reader)
        initial_raw = self.reader.read()
        safari_active = _event_is_set(
            initial_raw.event_flags,
            EventFlag.IN_SAFARI_ZONE,
        )
        safari_game_over = _event_is_set(
            initial_raw.event_flags,
            EventFlag.SAFARI_GAME_OVER,
        )
        recovering_gate_transition = (
            safari_active
            and initial.map_id == SAFARI_GATE_MAP_ID
            and initial.player_yx == SAFARI_CENTER_EXIT_SOURCE_YX
            and not initial.in_battle
            and not initial.dialogue_visible
            and not initial.input_ready
        )
        recovering_gate_autowalk = (
            not safari_active
            and not safari_game_over
            and initial.map_id == SAFARI_GATE_MAP_ID
            and initial.player_yx[1] == SAFARI_GATE_ENTRY_YX[1]
            and SAFARI_GATE_ENTRY_YX[0] <= initial.player_yx[0] <= 3
            and not initial.in_battle
            and not initial.dialogue_visible
            and not initial.input_ready
        )
        safari_exit_used = safari_active or recovering_gate_autowalk
        if (
            initial.acquired
            or initial.in_battle
            or initial.bag_slots >= MAX_BAG_ITEMS
            or (
                not (recovering_gate_transition or recovering_gate_autowalk)
                and (not initial.input_ready or initial.dialogue_visible)
            )
        ):
            raise RedSuperRodSupportError("routed Super Rod support is unavailable")
        before_actions = self.actions.actions_executed
        before_frames = self.emulator.frame_count
        field_actions = Gen1FieldMovePort(
            self.actions,
            self.reader,
            self.emulator,
            cut_block_swaps={swap.before: swap.after for swap in self.world.rules.cut_block_swaps},
        )
        observer = Gen1TraversalObserver(
            self.reader,
            hazard_projector=Gen1TrainerSightProjector(self.world.rom, self.reader),
            capability_projector=partial(
                collection_field_capabilities,
                self.emulator,
                allow_cut=True,
                allow_surf=True,
            ),
        )
        interruptions = Gen1RouteInterruptionHandler(
            self.actions,
            self.reader,
            maximum_flees=128,
            maximum_trainer_battles=8,
            stabilization_frames=180,
            route_name="Super Rod support transport",
        )
        safari_exit = _SafariExitReceipt(0, 0, 0)
        if recovering_gate_transition:
            self._settle_active_safari_gate(initial_raw)
            plan = self._plan_to_super_rod(
                observer,
                unavailable="no cartridge route reaches the Super Rod after Safari exit",
                unsupported="post-Safari Super Rod route needs unsupported transport",
            )
        elif recovering_gate_autowalk:
            self._settle_post_safari_gate_autowalk(initial_raw)
            plan = self._plan_to_super_rod(
                observer,
                unavailable="no cartridge route reaches the Super Rod after Safari exit",
                unsupported="post-Safari Super Rod route needs unsupported transport",
            )
        else:
            plan = self._plan_to_super_rod(
                observer,
                unavailable="no cartridge route reaches the Super Rod boundary",
                unsupported="Super Rod route needs unsupported transport",
            )
        if safari_exit_used and not (recovering_gate_transition or recovering_gate_autowalk):
            safari_exit = self._leave_active_safari(
                plan,
                field_actions,
                observer,
                interruptions,
            )
            plan = self._plan_to_super_rod(
                observer,
                unavailable="no cartridge route reaches the Super Rod after Safari exit",
                unsupported="post-Safari Super Rod route needs unsupported transport",
            )
        report = execute_route(
            plan,
            field_actions,
            observer,
            interruption_handler=interruptions,
            replanner=self.world.replanner(),
            limits=self.route_limits,
        )
        if not report.passed:
            raise RedSuperRodSupportError("Super Rod route missed its terminal boundary")
        at_stance = self.reader.read()
        if (
            at_stance.map_id != SUPER_ROD_HOUSE_MAP_ID
            or (at_stance.player_y, at_stance.player_x) != SUPER_ROD_STANCE_YX
            or at_stance.battle_state != 0
            or not self.reader.read_input_readiness().ready
        ):
            raise RedSuperRodSupportError("Super Rod route terminal changed")
        facing_action_used = self.reader.read_player_facing() != SUPER_ROD_FACING
        if facing_action_used:
            self.actions.execute(MacroAction(MacroActionKind.MOVE, SUPER_ROD_FACING))
            faced = self.reader.read()
            _require_transition_state(at_stance, faced)
            if (
                (faced.player_y, faced.player_x) != SUPER_ROD_STANCE_YX
                or self.reader.read_player_facing() != SUPER_ROD_FACING
                or not self.reader.read_input_readiness().ready
            ):
                raise RedSuperRodSupportError("Super Rod NPC facing was not acknowledged")
        gift = RedSuperRodSupportExecutor(
            self.actions,
            self.reader,
            self.emulator,
        ).execute()
        actions = self.actions.actions_executed - before_actions
        frames = self.emulator.frame_count - before_frames
        if (
            actions <= 0
            or frames <= 0
            or actions > self.maximum_controller_actions
            or frames > self.maximum_emulator_frames
        ):
            raise RedSuperRodSupportError("routed Super Rod support exceeded its budget")
        return RedRoutedSuperRodSupportResult(
            gift=gift,
            route_steps=safari_exit.route_steps + len(report.executed_steps),
            route_replans=safari_exit.route_replans + len(report.replans),
            route_interruptions=(safari_exit.route_interruptions + len(report.interruptions)),
            safari_exit_used=safari_exit_used,
            facing_action_used=facing_action_used,
            actions=actions,
            frames=frames,
        )

    def _plan_to_super_rod(
        self,
        observer: Gen1TraversalObserver,
        *,
        unavailable: str,
        unsupported: str,
    ) -> RoutePlan:
        try:
            plan = self.world.plan_feasible_to_map(
                observer.observe(),
                SUPER_ROD_HOUSE_MAP_ID,
                goal_at=SUPER_ROD_STANCE_YX,
            )
        except RoutePlanningError as error:
            raise RedSuperRodSupportError(unavailable) from error
        if not plan.steps or not _supported_plan(plan, allow_cut=True, allow_surf=True):
            raise RedSuperRodSupportError(unsupported)
        return plan

    def _leave_active_safari(
        self,
        onward_plan: RoutePlan,
        field_actions: Gen1FieldMovePort,
        observer: Gen1TraversalObserver,
        interruptions: Gen1RouteInterruptionHandler,
    ) -> _SafariExitReceipt:
        """Accept Red's observed leave-early prompt before ordinary routing.

        The cartridge script presents a two-row Yes/No choice after the warp
        into the gate, then clears the active-session event and walks the
        player down.  The route planner may propose that warp, but generic
        readiness cannot dismiss the script; this title adapter owns only that
        exact support boundary.
        """

        transitions = tuple(
            step
            for step in onward_plan.steps
            if step.source_map == SAFARI_CENTER_MAP_ID
            and step.expected_map == SAFARI_GATE_MAP_ID
            and not step.stays_on_map
        )
        if len(transitions) != 1:
            raise RedSuperRodSupportError("Safari exit route has no unique gate transition")
        transition = transitions[0]
        try:
            prefix = self.world.plan_feasible_to_map(
                observer.observe(),
                transition.source_map,
                goal_at=transition.source_at,
            )
        except RoutePlanningError as error:
            raise RedSuperRodSupportError("Safari exit source is unreachable") from error
        if prefix.steps and not _supported_plan(prefix, allow_cut=True, allow_surf=True):
            raise RedSuperRodSupportError("Safari exit prefix needs unsupported transport")
        report = execute_route(
            prefix,
            field_actions,
            observer,
            interruption_handler=interruptions,
            replanner=self.world.replanner(),
            limits=self.route_limits,
        )
        if not report.passed:
            raise RedSuperRodSupportError("Safari exit prefix missed its terminal boundary")
        before_exit = self.reader.read()
        if (
            before_exit.map_id != transition.source_map
            or (before_exit.player_y, before_exit.player_x) != transition.source_at
            or before_exit.battle_state != 0
            or not self.reader.read_input_readiness().ready
            or not _event_is_set(before_exit.event_flags, EventFlag.IN_SAFARI_ZONE)
            or _event_is_set(before_exit.event_flags, EventFlag.SAFARI_GAME_OVER)
        ):
            raise RedSuperRodSupportError("Safari exit source changed before input")

        field_actions.execute(transition.macro_action)
        self.actions.execute(MacroAction(MacroActionKind.WAIT, repeat=SAFARI_EXIT_WAIT_REPEATS))
        self._settle_active_safari_gate(before_exit, expected_at=transition.expected_at)
        return _SafariExitReceipt(
            route_steps=len(report.executed_steps) + 1,
            route_replans=len(report.replans),
            route_interruptions=len(report.interruptions),
        )

    def _settle_active_safari_gate(
        self,
        before_exit: RawGameState,
        *,
        expected_at: tuple[int, int] = SAFARI_GATE_ENTRY_YX,
    ) -> None:
        """Settle the gate prompt, including a retained mid-warp terminal.

        Red writes the destination map id before replacing the source-room player
        coordinates.  While movement remains busy and no dialogue is visible,
        that one exact stale coordinate pair is a valid transition state rather
        than evidence of route divergence.
        """

        if (
            before_exit.player_y is None
            or before_exit.player_x is None
            or before_exit.battle_state != 0
            or not _event_is_set(before_exit.event_flags, EventFlag.IN_SAFARI_ZONE)
            or _event_is_set(before_exit.event_flags, EventFlag.SAFARI_GAME_OVER)
        ):
            raise RedSuperRodSupportError("Safari exit recovery source is invalid")
        stale_at = (before_exit.player_y, before_exit.player_x)
        if stale_at != SAFARI_CENTER_EXIT_SOURCE_YX:
            raise RedSuperRodSupportError("Safari exit source coordinate is invalid")
        for _ in range(SAFARI_EXIT_SETTLE_LIMIT + 1):
            current = self.reader.read()
            _require_safari_exit_transition(before_exit, current)
            if current.player_y is None or current.player_x is None:
                raise RedSuperRodSupportError("Safari exit lost player coordinates")
            active = _event_is_set(current.event_flags, EventFlag.IN_SAFARI_ZONE)
            ready = self.reader.read_input_readiness().ready
            dialogue = self.reader.read_bottom_dialogue_box_visible()
            at = (current.player_y, current.player_x)
            in_gate_corridor = (
                current.map_id == SAFARI_GATE_MAP_ID
                and current.player_x == expected_at[1]
                and expected_at[0] <= current.player_y <= 3
            )
            retained_mid_warp = (
                current.map_id == SAFARI_GATE_MAP_ID
                and at == stale_at
                and active
                and not ready
                and not dialogue
            )
            if current.battle_state != 0 or not (in_gate_corridor or retained_mid_warp):
                raise RedSuperRodSupportError("Safari exit left its gate boundary")
            if not active and ready and not dialogue:
                if not in_gate_corridor:
                    raise RedSuperRodSupportError("Safari exit settled outside its gate corridor")
                return
            if dialogue:
                if active:
                    cursor = self.reader.read_menu_cursor_state()
                    if (
                        cursor.scroll_offset != 0
                        or cursor.maximum_visible_index != 1
                        or cursor.selected_visible_index not in {0, 1}
                    ):
                        raise RedSuperRodSupportError(
                            "Safari exit did not expose its bounded Yes/No choice"
                        )
                    if cursor.selected_visible_index == 1:
                        self.actions.execute(MacroAction(MacroActionKind.MOVE, "up"))
                        selected = self.reader.read_menu_cursor_state()
                        if (
                            selected.scroll_offset != 0
                            or selected.maximum_visible_index != 1
                            or selected.selected_visible_index != 0
                        ):
                            raise RedSuperRodSupportError(
                                "Safari exit did not acknowledge the Yes selection"
                            )
                self.actions.execute(MacroAction(MacroActionKind.CONFIRM))
            else:
                self.actions.execute(
                    MacroAction(MacroActionKind.WAIT, repeat=SAFARI_EXIT_WAIT_REPEATS)
                )
        raise RedSuperRodSupportError("Safari exit did not settle within its bound")

    def _settle_post_safari_gate_autowalk(self, initial: RawGameState) -> None:
        """Wait out the gate's retained scripted walk after its event cleared."""

        if (
            initial.map_id != SAFARI_GATE_MAP_ID
            or initial.player_y is None
            or initial.player_x != SAFARI_GATE_ENTRY_YX[1]
            or not SAFARI_GATE_ENTRY_YX[0] <= initial.player_y <= 3
            or initial.battle_state != 0
            or _event_is_set(initial.event_flags, EventFlag.IN_SAFARI_ZONE)
            or _event_is_set(initial.event_flags, EventFlag.SAFARI_GAME_OVER)
            or self.reader.read_input_readiness().ready
            or self.reader.read_bottom_dialogue_box_visible()
        ):
            raise RedSuperRodSupportError("post-Safari gate autowalk source is invalid")
        initial_y = initial.player_y
        for _ in range(SAFARI_AUTOWALK_SETTLE_LIMIT + 1):
            current = self.reader.read()
            _require_safari_exit_transition(initial, current)
            if current.player_y is None or current.player_x is None:
                raise RedSuperRodSupportError("post-Safari gate autowalk lost coordinates")
            ready = self.reader.read_input_readiness().ready
            dialogue = self.reader.read_bottom_dialogue_box_visible()
            in_corridor = (
                current.map_id == SAFARI_GATE_MAP_ID
                and current.player_x == SAFARI_GATE_ENTRY_YX[1]
                and initial_y <= current.player_y <= 3
            )
            if (
                current.battle_state != 0
                or not in_corridor
                or dialogue
                or _event_is_set(current.event_flags, EventFlag.IN_SAFARI_ZONE)
                or _event_is_set(current.event_flags, EventFlag.SAFARI_GAME_OVER)
            ):
                raise RedSuperRodSupportError("post-Safari gate autowalk left its boundary")
            if ready:
                if current.player_y != 3:
                    raise RedSuperRodSupportError(
                        "post-Safari gate autowalk settled at the wrong tile"
                    )
                return
            self.actions.execute(
                MacroAction(
                    MacroActionKind.WAIT,
                    repeat=SAFARI_AUTOWALK_WAIT_REPEATS,
                )
            )
        raise RedSuperRodSupportError("post-Safari gate autowalk did not settle within its bound")
