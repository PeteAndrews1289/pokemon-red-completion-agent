from dataclasses import replace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import (
    MapId,
    MenuCursorState,
    RawGameState,
    RedCurrentBoxState,
)
from pokemon_red_completion.red_pc_storage import (
    RedPCStorageError,
    RedPCStorageTiming,
    deposit_party_member,
    open_bills_pc,
    withdraw_box_member,
)

WARTORTLE = 0xB3
ZUBAT = 0x6B


def _raw(*species_ids: int) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.CERULEAN_POKECENTER,
        player_x=13,
        player_y=4,
        party_count=len(species_ids),
        battle_state=0,
        party_species_ids=tuple(species_ids),
    )


class _Reader:
    def __init__(self) -> None:
        self.raw = _raw(WARTORTLE, ZUBAT)
        self.box = RedCurrentBoxState(0, (), ())
        self.menu = MenuCursorState(0, 0, 4, 1, 2)

    def read(self) -> RawGameState:
        return self.raw

    def read_current_box_state(self) -> RedCurrentBoxState:
        return self.box

    def read_menu_cursor_state(self) -> MenuCursorState:
        return self.menu


class _DepositExecutor:
    def __init__(self, reader: _Reader) -> None:
        self.reader = reader
        self.actions: list[MacroAction] = []
        self.phase = "bills"

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.MOVE:
            selected = self.reader.menu.selected_visible_index
            selected += 1 if action.value == "down" else -1
            self.reader.menu = replace(self.reader.menu, selected_visible_index=selected)
            return
        if action.kind is not MacroActionKind.CONFIRM:
            return
        if self.phase == "bills":
            assert self.reader.menu.selected_absolute_index == 1
            self.phase = "party"
            self.reader.menu = MenuCursorState(0, 0, 2, 1, 2)
        elif self.phase == "party":
            assert self.reader.menu.selected_absolute_index == 1
            self.phase = "action"
            self.reader.menu = MenuCursorState(0, 0, 2, 10, 12)
        elif self.phase == "action":
            self.phase = "complete"
            self.reader.raw = _raw(WARTORTLE)
            self.reader.box = RedCurrentBoxState(0, (ZUBAT,), (7,))
            self.reader.menu = MenuCursorState(1, 0, 4, 1, 2)


def test_deposit_party_member_executes_and_proves_exact_transition() -> None:
    reader = _Reader()
    executor = _DepositExecutor(reader)

    report = deposit_party_member(
        executor,
        reader,  # type: ignore[arg-type]
        party_slot=2,
        expected_species_id=ZUBAT,
        timing=RedPCStorageTiming(wait_frames=1),
    )

    assert report.passed
    assert report.party_before == (WARTORTLE, ZUBAT)
    assert report.party_after == (WARTORTLE,)
    assert report.box_before == ()
    assert report.box_after == (ZUBAT,)
    assert tuple(
        action.kind for action in executor.actions if action.kind is not MacroActionKind.WAIT
    ) == (
        MacroActionKind.MOVE,
        MacroActionKind.CONFIRM,
        MacroActionKind.MOVE,
        MacroActionKind.CONFIRM,
        MacroActionKind.CONFIRM,
    )


def test_deposit_rejects_last_member_and_wrong_slot_before_input() -> None:
    reader = _Reader()
    reader.raw = _raw(WARTORTLE)
    executor = _DepositExecutor(reader)
    with pytest.raises(RedPCStorageError, match="last party member"):
        deposit_party_member(
            executor,
            reader,  # type: ignore[arg-type]
            party_slot=1,
            expected_species_id=WARTORTLE,
            timing=RedPCStorageTiming(wait_frames=1),
        )
    assert executor.actions == []


class _WithdrawExecutor:
    def __init__(self, reader: _Reader) -> None:
        self.reader = reader
        self.actions: list[MacroAction] = []
        self.phase = "bills"

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.MOVE:
            selected = self.reader.menu.selected_visible_index
            selected += 1 if action.value == "down" else -1
            self.reader.menu = replace(self.reader.menu, selected_visible_index=selected)
            return
        if action.kind is not MacroActionKind.CONFIRM:
            return
        if self.phase == "bills":
            assert self.reader.menu.selected_absolute_index == 0
            self.phase = "box"
            self.reader.menu = MenuCursorState(0, 0, 2, 1, 2)
        elif self.phase == "box":
            assert self.reader.menu.selected_absolute_index == 1
            self.phase = "action"
            self.reader.menu = MenuCursorState(0, 0, 2, 10, 12)
        elif self.phase == "action":
            self.phase = "complete"
            self.reader.raw = _raw(WARTORTLE, ZUBAT)
            self.reader.box = RedCurrentBoxState(0, (0x54,), (5,))
            self.reader.menu = MenuCursorState(0, 0, 4, 1, 2)


def test_withdraw_box_member_executes_and_proves_exact_transition() -> None:
    reader = _Reader()
    reader.raw = _raw(WARTORTLE)
    reader.box = RedCurrentBoxState(0, (0x54, ZUBAT), (5, 7))
    executor = _WithdrawExecutor(reader)

    report = withdraw_box_member(
        executor,
        reader,  # type: ignore[arg-type]
        box_slot=2,
        expected_species_id=ZUBAT,
        timing=RedPCStorageTiming(wait_frames=1),
    )

    assert report.passed
    assert report.party_after == (WARTORTLE, ZUBAT)
    assert report.box_after == (0x54,)


def test_withdraw_rejects_full_party_and_wrong_species_before_input() -> None:
    reader = _Reader()
    reader.box = RedCurrentBoxState(0, (ZUBAT,), (7,))
    reader.raw = _raw(WARTORTLE, 2, 3, 4, 5, 6)
    executor = _WithdrawExecutor(reader)
    with pytest.raises(RedPCStorageError, match="full party"):
        withdraw_box_member(
            executor,
            reader,  # type: ignore[arg-type]
            box_slot=1,
            expected_species_id=ZUBAT,
            timing=RedPCStorageTiming(wait_frames=1),
        )
    assert executor.actions == []

    reader.raw = _raw(WARTORTLE)
    with pytest.raises(RedPCStorageError, match="does not contain"):
        withdraw_box_member(
            executor,
            reader,  # type: ignore[arg-type]
            box_slot=1,
            expected_species_id=0x54,
            timing=RedPCStorageTiming(wait_frames=1),
        )
    assert executor.actions == []

    reader.raw = _raw(WARTORTLE, ZUBAT)
    with pytest.raises(RedPCStorageError, match="does not contain"):
        deposit_party_member(
            executor,
            reader,  # type: ignore[arg-type]
            party_slot=2,
            expected_species_id=0x54,
            timing=RedPCStorageTiming(wait_frames=1),
        )
    assert executor.actions == []


def test_open_bills_pc_verifies_generic_and_bills_menu_boundaries() -> None:
    reader = _Reader()
    reader.menu = MenuCursorState(0, 0, 0, 0, 0)

    class Executor:
        actions: list[MacroAction] = []
        confirms = 0

        def execute(self, action: MacroAction) -> None:
            self.actions.append(action)
            if action.kind is not MacroActionKind.CONFIRM:
                return
            self.confirms += 1
            if self.confirms == 1:
                reader.menu = MenuCursorState(0, 0, 3, 1, 2)
            elif self.confirms == 4:
                reader.menu = MenuCursorState(0, 0, 4, 1, 2)

    executor = Executor()
    open_bills_pc(
        executor,
        reader,  # type: ignore[arg-type]
        timing=RedPCStorageTiming(wait_frames=1),
    )

    assert executor.confirms == 4
    assert reader.menu == MenuCursorState(0, 0, 4, 1, 2)
