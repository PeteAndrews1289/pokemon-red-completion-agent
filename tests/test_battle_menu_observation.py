from __future__ import annotations

import pytest

from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)


class RecordingMemory:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = values
        self.reads: list[int] = []

    def read_u8(self, address: int) -> int:
        self.reads.append(int(address))
        return self.values.get(int(address), 0)


def _raw(*, battle_state: int | None) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_3,
        player_x=0,
        player_y=10,
        party_count=1,
        battle_state=battle_state,
    )


def _memory(
    *,
    top_y: int,
    top_x: int,
    watched_keys: int,
    current_item: int = 0,
    cursor_address: int = int(RamAddress.TILE_MAP),
    cursor_tile: int = 0xED,
) -> RecordingMemory:
    return RecordingMemory(
        {
            RamAddress.TOP_MENU_ITEM_Y: top_y,
            RamAddress.TOP_MENU_ITEM_X: top_x,
            RamAddress.MENU_WATCHED_KEYS: watched_keys,
            RamAddress.CURRENT_MENU_ITEM: current_item,
            RamAddress.MENU_CURSOR_LOCATION: cursor_address & 0xFF,
            int(RamAddress.MENU_CURSOR_LOCATION) + 1: cursor_address >> 8,
            cursor_address: cursor_tile,
        }
    )


def test_battle_menu_symbols_match_pinned_pokered_revision() -> None:
    assert RamAddress.TOP_MENU_ITEM_Y == 0xCC24
    assert RamAddress.TOP_MENU_ITEM_X == 0xCC25
    assert RamAddress.CURRENT_MENU_ITEM == 0xCC26
    assert RamAddress.MENU_WATCHED_KEYS == 0xCC29
    assert RamAddress.MENU_CURSOR_LOCATION == 0xCC30
    assert RamAddress.TILE_MAP == 0xC3A0


@pytest.mark.parametrize("battle_state", [None, 0, 3])
def test_battle_menu_reader_ignores_ram_outside_supported_battle_states(
    battle_state: int | None,
) -> None:
    memory = _memory(top_y=0x0E, top_x=0x09, watched_keys=0x11)

    state = PokemonRedStateReader(memory).read_battle_menu_state(
        _raw(battle_state=battle_state)
    )

    assert state == BattleMenuState(BattleMenuPhase.UNKNOWN)
    assert memory.reads == []


@pytest.mark.parametrize(
    ("top_x", "watched_keys", "current_item", "expected_command"),
    [
        (0x09, 0x11, 0, 0),
        (0x09, 0x11, 1, 1),
        (0x0F, 0x21, 0, 2),
        (0x0F, 0x21, 1, 3),
    ],
)
def test_battle_menu_reader_exposes_selected_main_command(
    top_x: int,
    watched_keys: int,
    current_item: int,
    expected_command: int,
) -> None:
    memory = _memory(
        top_y=0x0E,
        top_x=top_x,
        watched_keys=watched_keys,
        current_item=current_item,
    )

    state = PokemonRedStateReader(memory).read_battle_menu_state(
        _raw(battle_state=2)
    )

    assert state == BattleMenuState(
        BattleMenuPhase.MAIN,
        selected_main_command=expected_command,
    )
    assert state.selected_move_slot is None


@pytest.mark.parametrize("selected_move_slot", [1, 2, 3, 4])
def test_battle_menu_reader_exposes_one_based_move_slot(
    selected_move_slot: int,
) -> None:
    memory = _memory(
        top_y=0x0C,
        top_x=0x05,
        watched_keys=0xC7,
        current_item=selected_move_slot,
    )

    state = PokemonRedStateReader(memory).read_battle_menu_state(
        _raw(battle_state=2)
    )

    assert state == BattleMenuState(
        BattleMenuPhase.MOVE,
        selected_move_slot=selected_move_slot,
    )


@pytest.mark.parametrize("selected_move_slot", [0, 5])
def test_battle_menu_reader_rejects_move_slots_outside_party_move_range(
    selected_move_slot: int,
) -> None:
    memory = _memory(
        top_y=0x0C,
        top_x=0x05,
        watched_keys=0xC7,
        current_item=selected_move_slot,
    )

    state = PokemonRedStateReader(memory).read_battle_menu_state(
        _raw(battle_state=1)
    )

    assert state == BattleMenuState(BattleMenuPhase.UNKNOWN)


@pytest.mark.parametrize(
    ("top_y", "top_x", "watched_keys", "current_item"),
    [
        (0x0E, 0x09, 0x11, 0),
        (0x0E, 0x0F, 0x21, 1),
        (0x0C, 0x05, 0xC7, 2),
    ],
)
def test_battle_menu_reader_rejects_stale_unfilled_cursor(
    top_y: int,
    top_x: int,
    watched_keys: int,
    current_item: int,
) -> None:
    memory = _memory(
        top_y=top_y,
        top_x=top_x,
        watched_keys=watched_keys,
        current_item=current_item,
        cursor_tile=0xEC,
    )

    state = PokemonRedStateReader(memory).read_battle_menu_state(
        _raw(battle_state=2)
    )

    assert state == BattleMenuState(BattleMenuPhase.UNKNOWN)


def test_battle_menu_reader_rejects_cursor_outside_tile_map() -> None:
    memory = _memory(
        top_y=0x0C,
        top_x=0x05,
        watched_keys=0xC7,
        current_item=2,
        cursor_address=0xD000,
    )

    state = PokemonRedStateReader(memory).read_battle_menu_state(
        _raw(battle_state=2)
    )

    assert state == BattleMenuState(BattleMenuPhase.UNKNOWN)


@pytest.mark.parametrize(
    ("top_y", "top_x", "watched_keys"),
    [
        (0x0F, 0x09, 0x11),
        (0x0E, 0x08, 0x11),
        (0x0E, 0x09, 0x10),
        (0x0D, 0x05, 0xC7),
        (0x0C, 0x04, 0xC7),
        (0x0C, 0x05, 0xC6),
    ],
)
def test_battle_menu_reader_rejects_partial_signature_matches(
    top_y: int,
    top_x: int,
    watched_keys: int,
) -> None:
    memory = _memory(
        top_y=top_y,
        top_x=top_x,
        watched_keys=watched_keys,
        current_item=1,
    )

    state = PokemonRedStateReader(memory).read_battle_menu_state(
        _raw(battle_state=2)
    )

    assert state == BattleMenuState(BattleMenuPhase.UNKNOWN)
    assert RamAddress.CURRENT_MENU_ITEM not in memory.reads
