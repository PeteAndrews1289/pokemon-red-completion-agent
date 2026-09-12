"""Verified, non-learning acquisition of Red's free Super Rod.

The Super Rod is a one-time cartridge prerequisite, not a strategic model
choice and not a Mart purchase.  This module owns only the final adjacent NPC
interaction.  Cartridge-derived routing remains outside this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .actions import MacroAction, MacroActionKind
from .executor import CountingExecutor
from .observation import MAX_BAG_ITEMS, InputReadiness, ItemId, MapId, RawGameState

SUPER_ROD_STATUS_MASK = 1 << 5
SUPER_ROD_HOUSE_MAP_ID = int(MapId.ROUTE_12_SUPER_ROD_HOUSE)
SUPER_ROD_NPC_YX = (4, 2)
SUPER_ROD_STANCE_YX = (3, 2)
SUPER_ROD_FACING = "down"


class RedSuperRodSupportError(RuntimeError):
    """The support step was unavailable or lost its verified boundary."""


class RedSuperRodSupportReader(Protocol):
    def read(self) -> RawGameState: ...

    def read_input_readiness(self) -> InputReadiness: ...

    def read_player_facing(self) -> str: ...

    def read_bottom_dialogue_box_visible(self) -> bool: ...


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
        type(item) is not int
        or type(quantity) is not int
        or not 0 <= item <= 0xFF
        or quantity <= 0
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
