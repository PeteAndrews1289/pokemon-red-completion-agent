from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_observation import RecordingMemory

from pokemon_red_completion import battle_recovery as recovery
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)


def prompt_memory():
    cursor = int(RamAddress.TILE_MAP) + 12 * 20 + 14
    values = {
        RamAddress.TOP_MENU_ITEM_Y: 10,
        RamAddress.TOP_MENU_ITEM_X: 14,
        RamAddress.MAX_MENU_ITEM: 1,
        RamAddress.MENU_WATCHED_KEYS: 3,
        RamAddress.CURRENT_MENU_ITEM: 1,
        RamAddress.MENU_CURSOR_LOCATION: cursor & 255,
        int(RamAddress.MENU_CURSOR_LOCATION) + 1: cursor >> 8,
        cursor: 0xED,
    }
    for i, ch in enumerate("Use next POK MON"):
        values[int(RamAddress.TILE_MAP) + 14 * 20 + i] = (
            ord(ch) - ord("A") + 0x80
            if ch.isupper()
            else ord(ch) - ord("a") + 0xA0
            if ch.islower()
            else 0x7F
        )
    return values


@pytest.mark.parametrize(
    "fault",
    [None, "trainer", "healthy", "all_fainted", "stale_cursor", "wrong_text", "wrong_signature"],
)
def test_observed_wild_faint_prompt_does_not_alias_other_menus(fault):
    values = prompt_memory()
    raw = RawGameState(
        True, 19, 32, 9, 4, 1, party_hp=(0, 140, 27, 71), active_party_index=0, active_party_hp=0
    )
    if fault == "trainer":
        raw = replace(raw, battle_state=2)
    if fault == "healthy":
        raw = replace(raw, active_party_hp=20)
    if fault == "all_fainted":
        raw = replace(raw, party_hp=(0, 0, 0, 0))
    if fault == "stale_cursor":
        values[int(RamAddress.TILE_MAP) + 12 * 20 + 14] = 0xEC
    if fault == "wrong_text":
        values[int(RamAddress.TILE_MAP) + 14 * 20] = 0x7F
    if fault == "wrong_signature":
        values[RamAddress.TOP_MENU_ITEM_X] = 1
    assert PokemonRedStateReader(RecordingMemory(values)).read_wild_next_mon_prompt(raw) == (
        1 if fault is None else None
    )


@pytest.mark.parametrize("target", [1, 2, 3])
def test_forced_switch_accepts_yes_before_selecting_model_target(monkeypatch, target):
    state = {"phase": "yes_no", "cursor": 1, "active": 0}
    raw = RawGameState(
        True, 19, 32, 9, 4, 1, party_hp=(0, 140, 27, 71), active_party_index=0, active_party_hp=0
    )

    def read():
        return replace(
            raw, active_party_index=state["active"], active_party_hp=raw.party_hp[state["active"]]
        )

    reader = NS(
        read=read,
        read_battle_menu_state=lambda _: NS(
            phase=BattleMenuPhase.MAIN if state["phase"] == "main" else BattleMenuPhase.UNKNOWN
        ),
        read_wild_next_mon_prompt=lambda _: state["cursor"] if state["phase"] == "yes_no" else None,
    )
    emulator = NS(read_u8=lambda _: state["cursor"])
    monkeypatch.setattr(recovery, "_forced_party_menu_ready", lambda *a: True)

    def execute(action):
        if action.kind is MacroActionKind.WAIT:
            return
        if state["phase"] == "yes_no":
            if action.kind is MacroActionKind.MOVE:
                assert action.value == "up"
                state["cursor"] = 0
            else:
                assert action.kind is MacroActionKind.CONFIRM and state["cursor"] == 0
                state["phase"] = "party"
        elif state["phase"] == "party":
            if action.kind is MacroActionKind.MOVE:
                state["cursor"] += 1 if action.value == "down" else -1
            else:
                assert state["cursor"] == target
                state["active"], state["phase"] = target, "main"

    recovery.switch_active_battler(
        NS(execute=execute),
        reader,
        emulator,
        target,
        expected_battle_state=1,
        label="owned wild switch",
    )
    assert state["active"] == target
