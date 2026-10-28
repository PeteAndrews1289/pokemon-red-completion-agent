from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.red_tm_storage import tm_storage_inventory


@pytest.mark.parametrize("items", [(196,), (198,), (64,), (206, 206), (250,), ()])
def test_protect_hms_keys_and_missing_tms(items):
    with pytest.raises(ValueError):
        tm_storage_inventory(((206, 1), (246, 1)), (), items)


def test_tm_storage_conserves_and_quotes_capacity():
    assert tm_storage_inventory(((206, 1), (246, 1), (198, 1)), ((206, 2),), (206, 246)) == (
        {198: 1},
        {206: 3, 246: 1},
    )
    with pytest.raises(ValueError):
        tm_storage_inventory(((206, 1),), ((206, 99),), (206,))


@pytest.mark.parametrize("fault", [None, "money", "inventory", "not_ready"])
def test_native_storage_verifies_effects(monkeypatch, fault):
    from pokemon_red_completion import red_tm_storage as module

    fields = dict(
        map_id=154,
        player_x=13,
        player_y=4,
        player_money=7149,
        party_species_ids=(28,),
        party_levels=(48,),
        party_moves=((44, 39, 58, 55),),
        party_hp=(150,),
        party_pp=((25, 30, 10, 25),),
        party_status=(0,),
        badge_bits=63,
        event_flags=b"abc",
        battle_state=0,
        bag_items=((206, 1), (246, 1)),
    )
    raw = NS(**fields)
    pc = {20: 7}
    ready = True
    reader = NS(
        read=lambda: raw,
        read_pc_items=lambda: tuple(pc.items()),
        read_input_readiness=lambda: NS(ready=ready),
    )

    def deposit(actions, r, controller, item, timing):
        nonlocal raw, ready
        bag = dict(raw.bag_items)
        bag.pop(item)
        pc[item] = 1
        raw = NS(**(vars(raw) | {"bag_items": tuple(bag.items())}))
        if fault == "money":
            raw.player_money -= 1
        if fault == "inventory":
            pc[item] = 2
        if fault == "not_ready":
            ready = False

    monkeypatch.setattr(module.sabrina, "_deposit_pc_item", deposit)
    if fault:
        with pytest.raises(RuntimeError):
            module.store_selected_tms(None, reader, None, (206, 246))
    else:
        assert module.store_selected_tms(None, reader, None, (206, 246))["sales"] == 0
