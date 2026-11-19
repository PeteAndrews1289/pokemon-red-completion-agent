from types import SimpleNamespace as N
import pytest
from test_red_player_silph import setup
from pokemon_red_completion import red_player_silph as s


def test_card_key_previews_the_same_exact_trainer_using_only_combat_roles(monkeypatch):
    rt, actions, route, actor, raw, lesson, state, _, checked = setup(monkeypatch)
    contract = N(trainer_identity=(230, 30, 12))
    monkeypatch.setattr(s, 'silph_card_key_battle_contract', lambda *args: contract)
    quoted = []
    monkeypatch.setattr(s, 'trainer_party_quote', lambda rom, cls, number:
                        quoted.append((rom, cls, number)) or N(party=(N(level=33),)))
    row = s.silph_card_key_story_option(rt, actions, None, route=route, battler=actor,
                                      combat_levels=(37,))
    assert quoted == [(b'rom', 230, 12)]
    assert row[1].combat_required and row[1].opposition_known
    assert row[1].maximum_level_deficit == pytest.approx(-.04)
    assert row[1].opponent_fraction == pytest.approx(1/6)
    assert actions.actions_executed == 0 and state[0] == b'source'


@pytest.mark.parametrize('levels', [(), (True,), (0,), [37]])
def test_invalid_combat_roles_do_not_reach_execution(monkeypatch, levels):
    rt, actions, route, actor, raw, lesson, state, _, _ = setup(monkeypatch)
    monkeypatch.setattr(s, 'silph_card_key_battle_contract', lambda *args:
                        N(trainer_identity=(230, 30, 12)))
    monkeypatch.setattr(s, 'trainer_party_quote', lambda *args: N(party=(N(level=33),)))
    with pytest.raises(ValueError, match='challenge preview'):
        s.silph_card_key_story_option(rt, actions, None, route=route, battler=actor,
                                     combat_levels=levels)
    assert actions.actions_executed == 0 and state[0] == b'source'
