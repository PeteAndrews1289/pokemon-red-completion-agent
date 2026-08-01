"""Bounded controller for Pokémon Red's Bill's PC storage menus.

The collection planner chooses semantic operations.  This specialist is the
Red-specific executor-side adapter that turns one such operation into menu
inputs and proves the resulting party/box transition.  It never chooses which
species should be stored; that decision remains above this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .actions import MacroAction, MacroActionKind
from .observation import MenuCursorState, PokemonRedStateReader

BILLS_PC_WITHDRAW_INDEX = 0
BILLS_PC_DEPOSIT_INDEX = 1
BILLS_PC_RELEASE_INDEX = 2
BILLS_PC_CHANGE_BOX_INDEX = 3
BILLS_PC_EXIT_INDEX = 4
BILLS_PC_MENU_POSITION = (1, 2)
BILLS_PC_MENU_MAXIMUM = BILLS_PC_EXIT_INDEX
GENERIC_PC_MENU_POSITION = (1, 2)
GENERIC_PC_MENU_MAXIMA = frozenset((3, 4))
DEPOSIT_WITHDRAW_MENU_POSITION = (10, 12)
DEPOSIT_WITHDRAW_MENU_MAXIMUM = 2
PARTY_LIMIT = 6
BOX_CAPACITY = 20


class RedPCStorageError(RuntimeError):
    """Raised when one bounded PC operation misses its semantic gate."""


class ActionExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


@dataclass(frozen=True, slots=True)
class RedPCStorageTiming:
    wait_frames: int = 240
    max_dialogue_pulses: int = 8
    max_navigation_pulses: int = 24

    def __post_init__(self) -> None:
        for name in ("wait_frames", "max_dialogue_pulses", "max_navigation_pulses"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_STORAGE_TIMING = RedPCStorageTiming()


@dataclass(frozen=True, slots=True)
class RedPCDepositReport:
    species_id: int
    party_slot: int
    party_before: tuple[int, ...]
    party_after: tuple[int, ...]
    current_box_index: int
    box_before: tuple[int, ...]
    box_after: tuple[int, ...]

    @property
    def passed(self) -> bool:
        target_index = self.party_slot - 1
        return (
            0 <= target_index < len(self.party_before)
            and self.party_before[target_index] == self.species_id
            and self.party_after
            == self.party_before[:target_index] + self.party_before[target_index + 1 :]
            and self.box_after == (*self.box_before, self.species_id)
        )


@dataclass(frozen=True, slots=True)
class RedPCWithdrawReport:
    species_id: int
    box_slot: int
    party_before: tuple[int, ...]
    party_after: tuple[int, ...]
    current_box_index: int
    box_before: tuple[int, ...]
    box_after: tuple[int, ...]

    @property
    def passed(self) -> bool:
        target_index = self.box_slot - 1
        return (
            0 <= target_index < len(self.box_before)
            and self.box_before[target_index] == self.species_id
            and self.party_after == (*self.party_before, self.species_id)
            and self.box_after
            == self.box_before[:target_index] + self.box_before[target_index + 1 :]
        )


def open_bills_pc(
    actions: ActionExecutor,
    reader: PokemonRedStateReader,
    *,
    timing: RedPCStorageTiming = DEFAULT_STORAGE_TIMING,
) -> None:
    """Open Bill's PC from an already verified, PC-facing field position."""

    _pulse(actions, MacroActionKind.INTERACT, timing=timing)
    _pulse(actions, MacroActionKind.CONFIRM, timing=timing)
    generic = reader.read_menu_cursor_state()
    if (
        (generic.top_x, generic.top_y) != GENERIC_PC_MENU_POSITION
        or generic.maximum_visible_index not in GENERIC_PC_MENU_MAXIMA
        or generic.selected_absolute_index != 0
    ):
        raise RedPCStorageError(f"generic PC menu did not open: {generic!r}")

    # Select Bill's PC, clear its access text, and clear the WHAT? prompt.
    for _ in range(3):
        _pulse(actions, MacroActionKind.CONFIRM, timing=timing)
    _require_bills_pc_menu(reader.read_menu_cursor_state())


def deposit_party_member(
    actions: ActionExecutor,
    reader: PokemonRedStateReader,
    *,
    party_slot: int,
    expected_species_id: int,
    timing: RedPCStorageTiming = DEFAULT_STORAGE_TIMING,
) -> RedPCDepositReport:
    """Deposit one exact one-based party slot from Bill's PC main menu."""

    if type(party_slot) is not int or not 1 <= party_slot <= PARTY_LIMIT:
        raise ValueError(f"party_slot must be between 1 and {PARTY_LIMIT}")
    if type(expected_species_id) is not int or expected_species_id <= 0:
        raise ValueError("expected_species_id must be a positive integer")

    party_before = reader.read().party_species_ids or ()
    box_before = reader.read_current_box_state()
    target_index = party_slot - 1
    if len(party_before) <= 1:
        raise RedPCStorageError("Red cannot deposit the last party member")
    if target_index >= len(party_before) or party_before[target_index] != expected_species_id:
        raise RedPCStorageError(
            f"party slot {party_slot} does not contain species {expected_species_id:#04x}"
        )
    if len(box_before.species_ids) >= BOX_CAPACITY:
        raise RedPCStorageError("the current PC box is full")

    _require_bills_pc_menu(reader.read_menu_cursor_state())
    _select_absolute_index(
        actions,
        reader,
        BILLS_PC_DEPOSIT_INDEX,
        timing=timing,
    )
    _pulse(actions, MacroActionKind.CONFIRM, timing=timing)
    _select_absolute_index(actions, reader, target_index, timing=timing)
    _pulse(actions, MacroActionKind.CONFIRM, timing=timing)

    action_menu = reader.read_menu_cursor_state()
    if (
        (action_menu.top_x, action_menu.top_y) != DEPOSIT_WITHDRAW_MENU_POSITION
        or action_menu.maximum_visible_index != DEPOSIT_WITHDRAW_MENU_MAXIMUM
        or action_menu.selected_absolute_index != 0
    ):
        raise RedPCStorageError(f"deposit action menu did not open: {action_menu!r}")
    _pulse(actions, MacroActionKind.CONFIRM, timing=timing)

    expected_party = party_before[:target_index] + party_before[target_index + 1 :]
    expected_box = (*box_before.species_ids, expected_species_id)
    for _ in range(timing.max_dialogue_pulses + 1):
        party_after = reader.read().party_species_ids or ()
        box_after = reader.read_current_box_state()
        if party_after == expected_party and box_after.species_ids == expected_box:
            report = RedPCDepositReport(
                species_id=expected_species_id,
                party_slot=party_slot,
                party_before=party_before,
                party_after=party_after,
                current_box_index=box_before.box_index,
                box_before=box_before.species_ids,
                box_after=box_after.species_ids,
            )
            if not report.passed or box_after.box_index != box_before.box_index:
                raise RedPCStorageError("deposit result failed its immutable transition gate")
            return report
        _pulse(actions, MacroActionKind.CONFIRM, timing=timing)
    raise RedPCStorageError(
        f"deposit did not reach its bounded transition: party={party_after!r}, "
        f"box={box_after.species_ids!r}"
    )


def withdraw_box_member(
    actions: ActionExecutor,
    reader: PokemonRedStateReader,
    *,
    box_slot: int,
    expected_species_id: int,
    timing: RedPCStorageTiming = DEFAULT_STORAGE_TIMING,
) -> RedPCWithdrawReport:
    """Withdraw one exact one-based slot from the current box into the party."""

    if type(box_slot) is not int or not 1 <= box_slot <= BOX_CAPACITY:
        raise ValueError(f"box_slot must be between 1 and {BOX_CAPACITY}")
    if type(expected_species_id) is not int or expected_species_id <= 0:
        raise ValueError("expected_species_id must be a positive integer")

    party_before = reader.read().party_species_ids or ()
    box_before = reader.read_current_box_state()
    target_index = box_slot - 1
    if len(party_before) >= PARTY_LIMIT:
        raise RedPCStorageError("Red cannot withdraw into a full party")
    if target_index >= len(box_before.species_ids):
        raise RedPCStorageError(f"box slot {box_slot} is empty")
    if box_before.species_ids[target_index] != expected_species_id:
        raise RedPCStorageError(
            f"box slot {box_slot} does not contain species {expected_species_id:#04x}"
        )

    _require_bills_pc_menu(reader.read_menu_cursor_state())
    _select_absolute_index(actions, reader, BILLS_PC_WITHDRAW_INDEX, timing=timing)
    _pulse(actions, MacroActionKind.CONFIRM, timing=timing)
    _select_absolute_index(actions, reader, target_index, timing=timing)
    _pulse(actions, MacroActionKind.CONFIRM, timing=timing)

    action_menu = reader.read_menu_cursor_state()
    if (
        (action_menu.top_x, action_menu.top_y) != DEPOSIT_WITHDRAW_MENU_POSITION
        or action_menu.maximum_visible_index != DEPOSIT_WITHDRAW_MENU_MAXIMUM
        or action_menu.selected_absolute_index != 0
    ):
        raise RedPCStorageError(f"withdraw action menu did not open: {action_menu!r}")
    _pulse(actions, MacroActionKind.CONFIRM, timing=timing)

    expected_party = (*party_before, expected_species_id)
    expected_box = (
        box_before.species_ids[:target_index] + box_before.species_ids[target_index + 1 :]
    )
    for _ in range(timing.max_dialogue_pulses + 1):
        party_after = reader.read().party_species_ids or ()
        box_after = reader.read_current_box_state()
        if party_after == expected_party and box_after.species_ids == expected_box:
            report = RedPCWithdrawReport(
                species_id=expected_species_id,
                box_slot=box_slot,
                party_before=party_before,
                party_after=party_after,
                current_box_index=box_before.box_index,
                box_before=box_before.species_ids,
                box_after=box_after.species_ids,
            )
            if not report.passed or box_after.box_index != box_before.box_index:
                raise RedPCStorageError("withdraw result failed its immutable transition gate")
            return report
        _pulse(actions, MacroActionKind.CONFIRM, timing=timing)
    raise RedPCStorageError(
        f"withdraw did not reach its bounded transition: party={party_after!r}, "
        f"box={box_after.species_ids!r}"
    )


def _require_bills_pc_menu(state: MenuCursorState) -> None:
    if (
        (state.top_x, state.top_y) != BILLS_PC_MENU_POSITION
        or state.maximum_visible_index != BILLS_PC_MENU_MAXIMUM
        or state.scroll_offset != 0
    ):
        raise RedPCStorageError(f"Bill's PC main menu is unavailable: {state!r}")


def _select_absolute_index(
    actions: ActionExecutor,
    reader: PokemonRedStateReader,
    target: int,
    *,
    timing: RedPCStorageTiming,
) -> None:
    if type(target) is not int or target < 0:
        raise ValueError("target menu index must be a non-negative integer")
    for _ in range(timing.max_navigation_pulses + 1):
        state = reader.read_menu_cursor_state()
        if state.selected_absolute_index == target:
            return
        _pulse(
            actions,
            MacroActionKind.MOVE,
            "down" if state.selected_absolute_index < target else "up",
            timing=timing,
        )
    raise RedPCStorageError(f"could not select menu index {target}")


def _pulse(
    actions: ActionExecutor,
    kind: MacroActionKind,
    value: str | None = None,
    *,
    timing: RedPCStorageTiming,
) -> None:
    actions.execute(MacroAction(kind, value))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.wait_frames))
