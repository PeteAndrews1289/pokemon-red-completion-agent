from types import SimpleNamespace

import pytest

from pokemon_red_completion.observation import MenuCursorState, PokemonRedStateReader, RamAddress
from pokemon_red_completion.red_postgame import continue_menu_visible, require_continue_selection


def test_text_observation_is_read_only_and_preserves_menu_rows():
    cells = {}
    for row, text in ((2, 'CONTINUE'), (4, 'NEW GAME'), (6, 'OPTION')):
        for col, char in enumerate(text, 2):
            cells[int(RamAddress.TILE_MAP) + row * 20 + col] = (
                ord(char) - ord('A') + 0x80 if char != ' ' else 0x7F)
    reader = PokemonRedStateReader(SimpleNamespace(read_u8=lambda at: cells.get(at, 0x7F)))
    rows = reader.read_screen_text_rows()
    assert continue_menu_visible(rows)
    cursor = MenuCursorState(0, 0, 2, 1, 2)
    require_continue_selection(rows, cursor)
    with pytest.raises(ValueError):
        require_continue_selection(rows, MenuCursorState(1, 0, 2, 1, 2))
    changed = list(rows)
    changed[2] = '  NEW GAME          '
    assert not continue_menu_visible(tuple(changed))
    with pytest.raises(ValueError):
        require_continue_selection(tuple(changed), cursor)
