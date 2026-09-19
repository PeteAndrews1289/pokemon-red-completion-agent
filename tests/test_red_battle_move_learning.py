from dataclasses import replace

import pytest
from test_battle_runtime import MeasuredTurnRuntime, _raw
from test_observation import RecordingMemory

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import (
    DEFAULT_BATTLE_RUNTIME_TIMING,
    BattleRuntimeError,
    _preserve_moves_at_learning_prompt,
    _verify_selected_turn_pp,
)
from pokemon_red_completion.observation import PokemonRedStateReader, RamAddress


def prompt_reader(text, *, x=15, maximum=1, cursor=True):
    location = int(RamAddress.TILE_MAP) + 20 * 8 + x
    values = {
        RamAddress.TOP_MENU_ITEM_Y: 8,
        RamAddress.TOP_MENU_ITEM_X: x,
        RamAddress.MAX_MENU_ITEM: maximum,
        RamAddress.MENU_WATCHED_KEYS: 3,
        RamAddress.CURRENT_MENU_ITEM: 0,
        RamAddress.MENU_CURSOR_LOCATION: location & 255,
        int(RamAddress.MENU_CURSOR_LOCATION) + 1: location >> 8,
        location: 0xED if cursor else 0x7F,
    }
    for i, ch in enumerate(text):
        values[int(RamAddress.TILE_MAP) + 20 * 14 + i] = (
            ord(ch) - ord("A") + 0x80
            if ch.isupper()
            else ord(ch) - ord("a") + 0xA0
            if ch.islower()
            else 0x7F
        )
    return PokemonRedStateReader(RecordingMemory(values))


@pytest.mark.parametrize(
    "text,expected",
    [("move to make room", "replace_move"), ("Abandon learning", "abandon_learning")],
)
def test_prompt_requires_text_live_cursor_and_defeated_enemy(text, expected):
    reader = prompt_reader(text)
    assert reader.read_move_learning_prompt(_raw(enemy_hp=0)) == (expected, 0)
    assert reader.read_move_learning_prompt(_raw(enemy_hp=1)) is None
    assert prompt_reader(text, cursor=False).read_move_learning_prompt(_raw(enemy_hp=0)) is None
    assert prompt_reader("Change Pokemon").read_move_learning_prompt(_raw(enemy_hp=0)) is None


def test_forget_prompt_is_distinct_from_fight_menu():
    reader = prompt_reader("Which move should   be forgotten", x=5, maximum=3)
    assert reader.read_move_learning_prompt(_raw(enemy_hp=0)) == ("forget_move", 0)


@pytest.mark.parametrize(
    "prompt,action",
    [
        (("replace_move", 0), MacroActionKind.CANCEL),
        (("forget_move", 0), MacroActionKind.CANCEL),
        (("abandon_learning", 0), MacroActionKind.CONFIRM),
        (("abandon_learning", 1), MacroActionKind.MOVE),
    ],
)
def test_preservation_never_confirms_a_move_replacement(prompt, action):
    class Runtime(MeasuredTurnRuntime):
        def read_move_learning_prompt(self, raw):
            return prompt

    runtime = Runtime(raw=_raw(enemy_hp=0))
    assert _preserve_moves_at_learning_prompt(
        runtime, runtime, runtime.raw, timing=DEFAULT_BATTLE_RUNTIME_TIMING
    )
    assert runtime.actions[0].kind is action
    if action is MacroActionKind.MOVE:
        assert runtime.actions[0].value == "up"


def test_unexpected_unselected_move_replacement_still_fails_pp_proof():
    before = _raw(moves=(51, 71, 15, 72), pp=(30, 18, 30, 0))
    after = replace(before, first_party_moves=(80, 71, 15, 72), first_party_pp=(20, 17, 30, 0))
    with pytest.raises(BattleRuntimeError, match="PP accounting"):
        _verify_selected_turn_pp(before, after, slot=2, label="regression")
