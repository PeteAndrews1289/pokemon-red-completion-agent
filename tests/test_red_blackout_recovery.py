from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_blackout_recovery import settle_red_blackout


def test_blackout_retains_party_bag_and_exact_native_penalty():
    before = RawGameState(
        True,
        134,
        4,
        4,
        2,
        2,
        party_hp=(0, 0),
        player_money=9677,
        party_species_ids=(28, 104),
        bag_items=((19, 11),),
    )
    after = replace(
        before,
        battle_state=0,
        map_id=6,
        party_hp=(116, 68),
        party_max_hp=(116, 68),
        party_status=(0, 0),
        player_money=4838,
        party_species_ids=before.party_species_ids,
        bag_items=before.bag_items,
    )
    states = iter((before, before, after))
    calls = []
    reader = SimpleNamespace(
        read=lambda: next(states),
        read_last_blackout_map=lambda: 6,
        read_input_readiness=lambda: SimpleNamespace(ready=True),
    )
    result = settle_red_blackout(
        SimpleNamespace(execute=calls.append), reader, SimpleNamespace(pressed_buttons=())
    )
    assert result["cash_lost"] == 4839
    assert len(calls) == 2


@pytest.mark.parametrize("hp,battle", [((1, 0), 2), ((0, 0), 0), ((), 2)])
def test_blackout_cannot_be_requested_before_an_actual_loss(hp, battle):
    reader = SimpleNamespace(
        read=lambda: SimpleNamespace(battle_state=battle, party_hp=hp, player_money=100)
    )
    with pytest.raises(ValueError, match="observed all-party loss"):
        settle_red_blackout(None, reader, None)
