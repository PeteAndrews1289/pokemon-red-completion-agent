from types import SimpleNamespace

import pytest

from pokemon_red_completion.observation import PokemonRedStateReader


@pytest.mark.parametrize("battle,cursor,text,expected", [
    (2, False, "BLUE wants to fight", True),
    (2, False, "LASS wants to fight", True),
    (2, True, "BLUE wants to fight", False),
    (1, False, "BLUE wants to fight", False),
    (2, False, "Use next POK MON", False),
    (2, False, "Choose a POK MON", False),
])
def test_introduction_is_not_a_replacement_prompt(battle, cursor, text, expected):
    reader = SimpleNamespace(
        _active_menu_cursor=lambda: cursor,
        read_screen_text_rows=lambda: ("",) * 12 + (text,),
    )
    assert PokemonRedStateReader.trainer_introduction_visible(
        reader, SimpleNamespace(battle_state=battle),
    ) is expected
