from __future__ import annotations

from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_recovery import (
    ProtectedRecoveryError,
    resolve_trainer_switch_prompt,
)
from pokemon_red_completion.observation import BattleMenuPhase, RamAddress


class PromptReader:
    def __init__(self) -> None:
        self.prompt = True
        self.raw = SimpleNamespace(
            battle_state=2,
            party_hp=(70, 65, 0),
            active_party_index=0,
        )

    def read(self):
        return self.raw

    def trainer_switch_prompt_visible(self, _raw) -> bool:
        return self.prompt

    def read_battle_menu_state(self, _raw):
        return SimpleNamespace(phase=BattleMenuPhase.MAIN)


class PromptActions:
    def __init__(self, reader: PromptReader) -> None:
        self.reader = reader
        self.actions: list[MacroAction] = []

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.CANCEL:
            self.reader.prompt = False


def test_decline_trainer_switch_prompt_is_explicit_and_bounded() -> None:
    reader = PromptReader()
    actions = PromptActions(reader)
    resolve_trainer_switch_prompt(
        actions,
        reader,  # no emulator read is required when declining
        reader,
        target_index=None,
        label="model decline",
    )
    assert [action.kind for action in actions.actions] == [
        MacroActionKind.CANCEL,
        MacroActionKind.WAIT,
    ]


def test_trainer_switch_prompt_rejects_invalid_target_without_actions() -> None:
    reader = PromptReader()
    actions = PromptActions(reader)
    with pytest.raises(ProtectedRecoveryError, match="living switch target"):
        resolve_trainer_switch_prompt(
            actions,
            reader,
            reader,
            target_index=2,
            label="model switch",
        )
    assert actions.actions == []


@pytest.mark.parametrize("acknowledge_after", [2, 4, 5])
def test_delayed_decline_reasserts_only_same_answer_with_a_hard_bound(acknowledge_after):
    reader = PromptReader()
    seen = []

    def execute(action):
        seen.append(action.kind)
        if seen.count(MacroActionKind.CANCEL) >= acknowledge_after:
            reader.prompt = False

    actions = SimpleNamespace(execute=execute)
    if acknowledge_after > 4:
        with pytest.raises(ProtectedRecoveryError, match="bounded decline"):
            resolve_trainer_switch_prompt(actions, reader, reader, target_index=None, label="test")
    else:
        resolve_trainer_switch_prompt(actions, reader, reader, target_index=None, label="test")
    assert seen.count(MacroActionKind.CANCEL) == min(4, acknowledge_after)
    assert set(seen) == {MacroActionKind.CANCEL, MacroActionKind.WAIT}


def test_delayed_decline_cannot_cross_changed_battle_resources():
    reader = PromptReader()
    baseline = reader.raw

    def execute(action):
        reader.raw = SimpleNamespace(**{**vars(baseline), "party_hp": (60, 65, 0)})

    with pytest.raises(ProtectedRecoveryError, match="changed state"):
        resolve_trainer_switch_prompt(SimpleNamespace(execute=execute), reader, reader,
                                     target_index=None, label="test")


def test_prompt_settlement_never_confirms_into_an_unowned_attack():
    reader = PromptReader()
    phase = [BattleMenuPhase.UNKNOWN]
    cancels = []
    reader.read_battle_menu_state = lambda raw: SimpleNamespace(phase=phase[0])

    def execute(action):
        assert action.kind is not MacroActionKind.CONFIRM
        if action.kind is MacroActionKind.CANCEL:
            cancels.append(action)
            reader.prompt = False
            if len(cancels) == 3:
                phase[0] = BattleMenuPhase.MAIN

    resolve_trainer_switch_prompt(SimpleNamespace(execute=execute), reader, reader,
                                 target_index=None, label="test")
    assert len(cancels) == 3


def test_trainer_switch_prompt_requires_authenticated_prompt() -> None:
    reader = PromptReader()
    reader.prompt = False
    actions = PromptActions(reader)
    with pytest.raises(ProtectedRecoveryError, match="live trainer switch prompt"):
        resolve_trainer_switch_prompt(
            actions,
            reader,
            reader,
            target_index=None,
            label="model decline",
        )
    assert actions.actions == []


class LatePromptSimulation:
    def __init__(self, target_index: int, starting_cursor: int) -> None:
        self.target_index = target_index
        self.starting_cursor = starting_cursor
        self.cursor = 1
        self.stage = "prompt"
        self.active = 0
        self.actions: list[MacroAction] = []
        self.raw = SimpleNamespace(
            battle_state=2,
            party_hp=(70, 65, 60, 55, 50, 45),
            active_party_index=0,
        )

    def read(self):
        self.raw.active_party_index = self.active
        return self.raw

    def trainer_switch_prompt_visible(self, _raw) -> bool:
        return self.stage == "prompt"

    def read_battle_menu_state(self, _raw):
        return SimpleNamespace(
            phase=BattleMenuPhase.MAIN if self.stage == "main" else BattleMenuPhase.UNKNOWN
        )

    def read_u8(self, address: int) -> int:
        if address == RamAddress.CURRENT_MENU_ITEM:
            return self.cursor
        raise AssertionError(f"unexpected memory read {address:#x}")

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.MOVE:
            if self.stage == "prompt" and action.value == "up":
                self.cursor = 0
            elif self.stage == "party":
                self.cursor += 1 if action.value == "down" else -1
            elif self.stage == "submenu" and action.value == "up":
                self.cursor = 0
            return
        if action.kind is not MacroActionKind.CONFIRM:
            return
        if self.stage == "prompt" and self.cursor == 0:
            self.stage = "party"
            self.cursor = self.starting_cursor
        elif self.stage == "party" and self.cursor == self.target_index:
            self.stage = "submenu"
            self.cursor = 1
        elif self.stage == "submenu" and self.cursor == 0:
            self.active = self.target_index
            self.stage = "main"


@pytest.mark.parametrize(("target_index", "starting_cursor"), ((3, 5), (4, 2), (5, 0)))
def test_trainer_switch_prompt_executes_late_slot_without_changing_decline_semantics(
    monkeypatch, target_index, starting_cursor
) -> None:
    simulation = LatePromptSimulation(target_index, starting_cursor)
    monkeypatch.setattr(
        "pokemon_red_completion.battle_recovery._forced_party_menu_ready",
        lambda _emulator, party_size: simulation.stage == "party" and party_size == 6,
    )

    resolve_trainer_switch_prompt(
        simulation,
        simulation,
        simulation,
        target_index=target_index,
        label="model late-slot prompt switch",
    )

    assert simulation.active == target_index
    assert simulation.stage == "main"
    assert all(action.kind is not MacroActionKind.CANCEL for action in simulation.actions)
