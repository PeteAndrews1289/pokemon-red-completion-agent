from __future__ import annotations

from dataclasses import replace

import pokemon_red_completion.battle_recovery as battle_recovery
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    MapId,
    RamAddress,
    RawGameState,
)


class _SwitchSimulation:
    def __init__(self) -> None:
        self.stage = "main"
        self.command = 0
        self.cursor = 0
        self.active = 0
        self.actions: list[MacroAction] = []

    def read(self) -> RawGameState:
        return RawGameState(
            game_started=True,
            map_id=MapId.ROCK_TUNNEL_1F,
            player_x=22,
            player_y=27,
            party_count=3,
            battle_state=2,
            party_species_ids=(0xB3, 0x40, 0x3B),
            first_party_hp=50,
            first_party_max_hp=79,
            active_party_index=self.active,
            active_party_hp=30,
            active_party_max_hp=45,
        )

    def read_battle_menu_state(self, _raw: RawGameState) -> BattleMenuState:
        if self.stage == "main":
            return BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=self.command)
        return BattleMenuState(BattleMenuPhase.UNKNOWN)

    def read_u8(self, address: int) -> int:
        if address == RamAddress.CURRENT_MENU_ITEM:
            return self.cursor
        cursor_address = int(RamAddress.TILE_MAP)
        if address == RamAddress.MENU_CURSOR_LOCATION:
            return cursor_address & 0xFF if self.stage == "party" else 0
        if address == int(RamAddress.MENU_CURSOR_LOCATION) + 1:
            return cursor_address >> 8 if self.stage == "party" else 0
        if address == cursor_address:
            return 0xED if self.stage == "party" else 0
        raise AssertionError(f"unexpected memory read {address:#x}")

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.MOVE:
            if self.stage == "main" and action.value == "right":
                self.command = 2
            elif self.stage == "party" and action.value == "down":
                self.cursor += 1
            elif self.stage == "submenu" and action.value == "up":
                self.cursor = 0
        elif action.kind is MacroActionKind.CONFIRM:
            if self.stage == "main" and self.command == 2:
                self.stage = "party"
                self.cursor = 0
            elif self.stage == "party" and self.cursor == 1:
                self.stage = "submenu"
                self.cursor = 1
            elif self.stage == "submenu" and self.cursor == 0:
                self.stage = "switching"
        elif action.kind is MacroActionKind.WAIT and self.stage == "switching":
            self.active = 1
            self.stage = "main"
            self.command = 0


def test_sole_living_switch_target_refuses_to_make_a_strategic_choice() -> None:
    assert battle_recovery.sole_living_switch_target((0, 17), 0) == 1
    assert battle_recovery.sole_living_switch_target((0, 17, 9), 0) is None
    assert battle_recovery.sole_living_switch_target((12, 0), 0) is None
    assert battle_recovery.sole_living_switch_target((0, 17), None) is None
    assert battle_recovery.sole_living_switch_target((0, 17), 2) is None


def test_switch_active_battler_observes_party_menu_and_returns_to_main(monkeypatch) -> None:
    simulation = _SwitchSimulation()
    monkeypatch.setattr(battle_recovery, "_party_hp", lambda _emulator: (50, 30, 20))

    battle_recovery.switch_active_battler(
        simulation,
        simulation,
        simulation,
        1,
        label="DUX sleep pivot",
    )

    assert simulation.active == 1
    assert simulation.stage == "main"
    assert any(
        action.kind is MacroActionKind.MOVE and action.value == "right"
        for action in simulation.actions
    )


def test_forced_party_menu_accepts_a_late_balanced_team_slot(monkeypatch) -> None:
    simulation = _SwitchSimulation()
    simulation.cursor = 4
    monkeypatch.setattr(battle_recovery, "_menu_cursor_active", lambda _emulator: True)

    assert battle_recovery._forced_party_menu_ready(simulation, 6)
    assert not battle_recovery._forced_party_menu_ready(simulation, 3)


def test_switch_active_battler_advances_a_fainted_forced_party_menu(monkeypatch) -> None:
    simulation = _SwitchSimulation()
    simulation.stage = "faint_dialogue"

    original_read = simulation.read

    def read() -> RawGameState:
        raw = original_read()
        return replace(
            raw,
            active_party_hp=0 if simulation.active == 0 else 30,
        )

    simulation.read = read  # type: ignore[method-assign]

    original_execute = simulation.execute

    def execute(action: MacroAction) -> None:
        if action.kind is MacroActionKind.CONFIRM and simulation.stage == "faint_dialogue":
            simulation.stage = "party"
            simulation.cursor = 0
            simulation.actions.append(action)
            return
        if (
            action.kind is MacroActionKind.CONFIRM
            and simulation.stage == "party"
            and simulation.cursor == 1
        ):
            simulation.stage = "switching"
            simulation.actions.append(action)
            return
        original_execute(action)

    simulation.execute = execute  # type: ignore[method-assign]
    monkeypatch.setattr(battle_recovery, "_party_hp", lambda _emulator: (0, 30, 20))
    monkeypatch.setattr(
        battle_recovery,
        "_forced_party_menu_ready",
        lambda _emulator, _party_size: simulation.stage == "party",
    )

    battle_recovery.switch_active_battler(
        simulation,
        simulation,
        simulation,
        1,
        label="Route 9 fainted DUX",
    )

    assert simulation.active == 1
    assert simulation.stage == "main"


def test_forced_switch_ignores_stale_cursor_until_delayed_party_menu(monkeypatch) -> None:
    simulation = _SwitchSimulation()
    simulation.stage = "faint_dialogue"
    simulation.cursor = 1
    confirmations = 0

    original_read = simulation.read

    def read() -> RawGameState:
        raw = original_read()
        return replace(raw, active_party_hp=0 if simulation.active == 0 else 30)

    simulation.read = read  # type: ignore[method-assign]
    original_execute = simulation.execute

    def execute(action: MacroAction) -> None:
        nonlocal confirmations
        if action.kind is MacroActionKind.CONFIRM and simulation.stage == "faint_dialogue":
            confirmations += 1
            simulation.actions.append(action)
            if confirmations == 3:
                simulation.stage = "party"
                simulation.cursor = 0
            return
        if (
            action.kind is MacroActionKind.CONFIRM
            and simulation.stage == "party"
            and simulation.cursor == 1
        ):
            simulation.stage = "switching"
            simulation.actions.append(action)
            return
        original_execute(action)

    simulation.execute = execute  # type: ignore[method-assign]
    monkeypatch.setattr(battle_recovery, "_party_hp", lambda _emulator: (0, 30, 20))
    monkeypatch.setattr(
        battle_recovery,
        "_forced_party_menu_ready",
        lambda _emulator, _party_size: simulation.stage == "party",
    )

    battle_recovery.switch_active_battler(
        simulation,
        simulation,
        simulation,
        1,
        label="delayed Route 22 forced switch",
    )

    assert confirmations == 3
    assert simulation.active == 1
    assert simulation.stage == "main"


def test_wild_forced_switch_never_steers_a_transient_run_command(monkeypatch) -> None:
    simulation = _SwitchSimulation()
    simulation.stage = "transient_main"
    simulation.command = 3
    simulation.cursor = 1
    battle_state = 1
    transient_waits = 0

    def read() -> RawGameState:
        return RawGameState(
            game_started=True,
            map_id=MapId.DIGLETTS_CAVE,
            player_x=37,
            player_y=30,
            party_count=2,
            battle_state=battle_state,
            party_species_ids=(0xB3, 0x05),
            party_hp=(0, 16),
            active_party_index=0 if simulation.active == 0 else 1,
            active_party_hp=0 if simulation.active == 0 else 16,
            enemy_species_id=0x3B,
            enemy_hp=25,
        )

    simulation.read = read  # type: ignore[method-assign]

    def menu(_raw: RawGameState) -> BattleMenuState:
        if simulation.stage in {"transient_main", "main"}:
            return BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=simulation.command)
        return BattleMenuState(BattleMenuPhase.UNKNOWN)

    simulation.read_battle_menu_state = menu  # type: ignore[method-assign]

    def execute(action: MacroAction) -> None:
        nonlocal battle_state, transient_waits
        simulation.actions.append(action)
        if simulation.stage == "transient_main":
            if action.kind in {MacroActionKind.MOVE, MacroActionKind.CONFIRM}:
                battle_state = 0
                return
            if action.kind is MacroActionKind.WAIT:
                transient_waits += 1
                simulation.stage = "party"
                simulation.cursor = 0
                return
        if simulation.stage == "party":
            if action.kind is MacroActionKind.MOVE and action.value == "down":
                simulation.cursor = 1
            elif action.kind is MacroActionKind.CONFIRM and simulation.cursor == 1:
                simulation.stage = "switching"
            return
        if simulation.stage == "switching" and action.kind is MacroActionKind.WAIT:
            simulation.active = 1
            simulation.stage = "main"
            simulation.command = 0

    simulation.execute = execute  # type: ignore[method-assign]
    monkeypatch.setattr(battle_recovery, "_party_hp", lambda _emulator: (0, 16))

    battle_recovery.switch_active_battler(
        simulation,
        simulation,
        simulation,
        1,
        expected_battle_state=1,
        label="Diglett capture",
        wait_frames=120,
    )

    assert battle_state == 1
    assert transient_waits == 1
    assert simulation.active == 1
