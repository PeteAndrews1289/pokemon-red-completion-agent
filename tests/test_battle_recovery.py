from __future__ import annotations

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
