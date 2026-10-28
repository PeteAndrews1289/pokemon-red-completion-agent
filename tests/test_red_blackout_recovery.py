from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_blackout_recovery import settle_red_blackout


@pytest.mark.parametrize("field_loss", [False, True])
@pytest.mark.parametrize(
    "mutation",
    [
        None,
        {"player_money": 9677},
        {"party_species_ids": (28, 28)},
        {"bag_items": ()},
        {"badge_bits": 1},
    ],
)
def test_blackout_retains_party_bag_and_exact_native_penalty(mutation, field_loss):
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
    if field_loss:
        before = replace(before, battle_state=0)
    if mutation:
        after = replace(after, **mutation)
    states = iter((before, before, after))
    calls = []
    live = [before]

    def read():
        live[0] = next(states)
        return live[0]

    reader = SimpleNamespace(
        read=read,
        read_last_blackout_map=lambda: 6,
        read_input_readiness=lambda: SimpleNamespace(ready=not field_loss or live[0] is after),
        read_bottom_dialogue_box_visible=lambda: field_loss and live[0] is not after,
    )

    def run():
        return settle_red_blackout(
            SimpleNamespace(execute=calls.append),
            reader,
            SimpleNamespace(pressed_buttons=()),
            allow_field_loss=field_loss,
        )

    if mutation:
        with pytest.raises(ValueError, match="unexpected resources"):
            run()
        return
    result = run()
    assert result["cash_lost"] == 4839
    assert len(calls) == 2


@pytest.mark.parametrize("hp,battle", [((1, 0), 2), ((0, 0), 0), ((), 2)])
def test_blackout_cannot_be_requested_before_an_actual_loss(hp, battle):
    reader = SimpleNamespace(
        read=lambda: SimpleNamespace(battle_state=battle, party_hp=hp, player_money=100)
    )
    with pytest.raises(ValueError, match="observed all-party loss"):
        settle_red_blackout(None, reader, None)
