from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import cast

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_field_moves import (
    ALWAYS_ON_BIKE_MASK,
    FLASH_MOVE_ID,
    GEN1_FIELD_MOVE_IDS,
    SEAFOAM_ISLANDS_B4F_MAP_ID,
    Gen1FieldMoveError,
    Gen1FieldMovePort,
    surf_menu_indices,
    surf_permission,
)
from pokemon_red_completion.gen1_traversal import SURF_MOVE_ID
from pokemon_red_completion.observation import (
    Badge,
    OverworldMovementMode,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    ReadOnlyMemory,
)
from pokemon_red_completion.route_executor import RouteActionPort

TACKLE_MOVE_ID = 0x21


def surf_state(
    *,
    map_id: int = 0,
    hp: tuple[int, ...] = (15, 25),
    moves: tuple[tuple[int, ...], ...] = (
        (TACKLE_MOVE_ID,),
        (FLASH_MOVE_ID, SURF_MOVE_ID),
    ),
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=4,
        player_y=17,
        party_count=len(hp),
        battle_state=0,
        badge_bits=int(Badge.SOUL),
        bag_items=((1, 1),),
        party_hp=hp,
        party_status=tuple(0 for _ in hp),
        party_moves=moves,
        party_pp=tuple(tuple(10 for _ in known) for known in moves),
    )


@dataclass
class MenuWorld:
    raw: RawGameState = field(default_factory=surf_state)
    mode: OverworldMovementMode = OverworldMovementMode.WALKING
    status_flags_6: int = 0
    stage: str = "field"
    cursor: int = 0
    actions: list[MacroAction] = field(default_factory=list)

    def read(self) -> RawGameState:
        return self.raw

    def read_overworld_movement_mode(self) -> OverworldMovementMode:
        return self.mode

    def read_u8(self, address: int) -> int:
        if address == RamAddress.STATUS_FLAGS_6:
            return self.status_flags_6
        if address == RamAddress.CURRENT_MENU_ITEM:
            return self.cursor
        if address == RamAddress.MAX_MENU_ITEM:
            return {
                "start": 5,
                "party": int(self.raw.party_count or 0) - 1,
                "submenu": 4,
            }.get(self.stage, 0)
        return 0

    def execute(self, action: MacroAction) -> object:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            return action
        if self.stage == "field":
            if action.kind is MacroActionKind.MOVE:
                return action  # collision only changes facing
            if action.kind is MacroActionKind.OPEN_MENU:
                self.stage, self.cursor = "start", 0
                return action
        if action.kind is MacroActionKind.MOVE:
            assert isinstance(action.value, str)
            self.cursor += 1 if action.value == "down" else -1
            return action
        if action.kind is MacroActionKind.CONFIRM:
            if self.stage == "start" and self.cursor == 1:
                self.stage, self.cursor = "party", 0
            elif self.stage == "party" and self.cursor == 1:
                self.stage, self.cursor = "submenu", 0
            elif self.stage == "submenu" and self.cursor == 1:
                self.stage = "surf_dialogue"
            elif self.stage == "surf_dialogue":
                self.raw = replace(self.raw, player_x=5)
                self.mode = OverworldMovementMode.SURFING
                self.stage = "field"
            return action
        raise AssertionError(f"unexpected action {action!r} in {self.stage}")


def real_reader(world: MenuWorld) -> PokemonRedStateReader:
    return cast(PokemonRedStateReader, world)


def action_port(world: MenuWorld) -> RouteActionPort:
    return cast(RouteActionPort, world)


def memory(world: MenuWorld) -> ReadOnlyMemory:
    return cast(ReadOnlyMemory, world)


def test_surf_row_counts_every_real_field_move_before_it() -> None:
    assert frozenset({0x0F, 0x13, 0x39, 0x46, 0x5B, 0x64, 0x87, 0x94}) == (GEN1_FIELD_MOVE_IDS)
    assert surf_menu_indices(surf_state()) == (1, 1)


def test_surf_menu_selection_skips_a_fainted_holder() -> None:
    raw = surf_state(
        hp=(0, 20),
        moves=((SURF_MOVE_ID,), (TACKLE_MOVE_ID, SURF_MOVE_ID)),
    )

    assert surf_menu_indices(raw) == (1, 0)


def test_surf_permission_fails_closed_on_forced_bike_and_seafoam_b4() -> None:
    world = MenuWorld(status_flags_6=ALWAYS_ON_BIKE_MASK)
    assert surf_permission(memory(world), world.raw).reason == "forced_bicycle_state"

    world.status_flags_6 = 0
    world.raw = replace(world.raw, map_id=SEAFOAM_ISLANDS_B4F_MAP_ID)
    permission = surf_permission(memory(world), world.raw)
    assert not permission.allowed
    assert permission.reason == "seafoam_b4_story_gate_unmodelled"


def test_field_port_compiles_surf_and_waits_for_exact_water_acknowledgement() -> None:
    world = MenuWorld()
    port = Gen1FieldMovePort(action_port(world), real_reader(world), memory(world))

    receipt = port.execute(MacroAction(MacroActionKind.FIELD_MOVE, "surf:right"))

    assert receipt.source_at == (17, 4)
    assert receipt.target_at == (17, 5)
    assert receipt.party_index == 1
    assert receipt.submenu_row == 1
    assert receipt.confirmation_count == 1
    assert port.receipts == [receipt]
    assert world.mode is OverworldMovementMode.SURFING
    assert (world.raw.player_y, world.raw.player_x) == (17, 5)
    assert [action.kind for action in world.actions if action.kind is not MacroActionKind.WAIT] == [
        MacroActionKind.MOVE,
        MacroActionKind.OPEN_MENU,
        MacroActionKind.MOVE,
        MacroActionKind.CONFIRM,
        MacroActionKind.MOVE,
        MacroActionKind.CONFIRM,
        MacroActionKind.MOVE,
        MacroActionKind.CONFIRM,
        MacroActionKind.CONFIRM,
    ]


def test_field_port_rejects_closed_or_unknown_macros_before_pressing_buttons() -> None:
    world = MenuWorld(status_flags_6=ALWAYS_ON_BIKE_MASK)
    port = Gen1FieldMovePort(action_port(world), real_reader(world), memory(world))

    with pytest.raises(Gen1FieldMoveError, match="forced_bicycle_state"):
        port.execute(MacroAction(MacroActionKind.FIELD_MOVE, "surf:right"))
    assert world.actions == []

    world.status_flags_6 = 0
    with pytest.raises(Gen1FieldMoveError, match="unsupported"):
        port.execute(MacroAction(MacroActionKind.FIELD_MOVE, "cut:up"))
    assert world.actions == []
