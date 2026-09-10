"""Exercise real menu selection with distinguishable duplicate positions.

This proves which slot the controller requests, not unique specimen identity.
The production withdrawal receipt still verifies species ordering, not genetics.
"""

from dataclasses import replace

import pytest
from test_red_pc_storage import WARTORTLE, ZUBAT, _raw, _Reader

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import MenuCursorState, RedCurrentBoxState
from pokemon_red_completion.red_pc_storage import RedPCStorageTiming, withdraw_box_member


@pytest.mark.parametrize("slot", [1, 3, 4])
@pytest.mark.parametrize("initial_cursor", [0, 2])
def test_three_copies_select_requested_position_not_first_species_match(slot, initial_cursor):
    reader = _Reader()
    reader.raw = _raw(WARTORTLE)
    original_species = (ZUBAT, 0x54, ZUBAT, ZUBAT)
    original_levels = (7, 5, 19, 28)
    reader.box = RedCurrentBoxState(0, original_species, original_levels)
    reader.menu = MenuCursorState(initial_cursor, 0, 4, 1, 2)

    class Controller:
        phase = "bills"
        selected_slot = None

        def execute(self, action):
            if action.kind is MacroActionKind.WAIT:
                return
            if action.kind is MacroActionKind.MOVE:
                delta = {"down": 1, "up": -1}[action.value]
                reader.menu = replace(
                    reader.menu, selected_visible_index=reader.menu.selected_visible_index + delta,
                )
                return
            assert action.kind is MacroActionKind.CONFIRM
            if self.phase == "bills":
                assert reader.menu.selected_absolute_index == 0
                self.phase = "box"
                reader.menu = MenuCursorState(initial_cursor, 0, 4, 1, 2)
            elif self.phase == "box":
                # Capture the actual observed selection, not the desired test argument.
                self.selected_slot = reader.menu.selected_absolute_index
                self.phase = "action"
                reader.menu = MenuCursorState(0, 0, 2, 10, 12)
            elif self.phase == "action":
                index = self.selected_slot
                assert index is not None
                reader.raw = _raw(WARTORTLE, original_species[index])
                reader.box = RedCurrentBoxState(
                    0, original_species[:index] + original_species[index + 1:],
                    original_levels[:index] + original_levels[index + 1:],
                )
                self.phase = "complete"
                reader.menu = MenuCursorState(0, 0, 4, 1, 2)
            else:
                raise AssertionError("unexpected confirmation after completed withdrawal")

    controller = Controller()
    report = withdraw_box_member(
        controller, reader, box_slot=slot, expected_species_id=ZUBAT,
        timing=RedPCStorageTiming(wait_frames=1),
    )
    assert controller.selected_slot == slot - 1
    assert report.passed and report.box_slot == slot
    expected_levels = {1: (5, 19, 28), 3: (7, 5, 28), 4: (7, 5, 19)}
    assert reader.box.levels == expected_levels[slot]
