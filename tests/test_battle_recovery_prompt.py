from __future__ import annotations

from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_recovery import (
    ProtectedRecoveryError,
    resolve_trainer_switch_prompt,
)
from pokemon_red_completion.observation import BattleMenuPhase


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
